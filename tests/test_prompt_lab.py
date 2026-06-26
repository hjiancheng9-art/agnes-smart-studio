"""Tests for #5 — Prompt Lab (A/B system prompt 实验框架).

守护四条契约：
1. **Variant CRUD**: 创建/停用/激活/删除变体
2. **分配逻辑**: 按 traffic_ratio 加权随机 / 手动指定
3. **Outcome 记录**: 工具调用计数 → 自动推断满意度 → 持久化
4. **统计聚合**: 按 variant 汇总 outcome 数据
"""
# pyright: reportOptionalMemberAccess=false

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.prompt_lab import PromptLab, reset_prompt_lab


@pytest.fixture(autouse=True)
def _isolate():
    """每个测试隔离全局单例 + 清理临时文件。"""
    reset_prompt_lab()
    yield
    reset_prompt_lab()
    # 清理测试产生的持久化文件
    for f in [
        Path("core/brain_data/prompt_lab_variants.json"),
        Path("core/brain_data/prompt_lab_outcomes.jsonl"),
    ]:
        if f.exists():
            f.unlink(missing_ok=True)


class TestVariantCRUD:
    def _make_lab(self):
        return PromptLab()

    def test_create_variant(self):
        """创建变体成功。"""
        lab = self._make_lab()
        v = lab.create_variant("concise", "简洁版", "- 回答限制1段")
        assert v.id == "v001"
        assert v.name == "concise"
        assert v.label == "简洁版"
        assert v.is_active is True

    def test_create_multiple_variants(self):
        """创建多个变体，ID 递增。"""
        lab = self._make_lab()
        v1 = lab.create_variant("concise", "简洁版", "- 1段")
        v2 = lab.create_variant("formal", "正式版", "- 正式语气")
        assert v1.id == "v001"
        assert v2.id == "v002"
        assert len(lab.list_variants()) == 2

    def test_deactivate_variant(self):
        """停用变体。"""
        lab = self._make_lab()
        v = lab.create_variant("test", "测试版", "- test")
        assert lab.deactivate_variant(v.id) is True
        assert v.is_active is False

    def test_activate_variant(self):
        """重新激活变体。"""
        lab = self._make_lab()
        v = lab.create_variant("test", "测试版", "- test")
        lab.deactivate_variant(v.id)
        assert lab.activate_variant(v.id) is True
        assert v.is_active is True

    def test_deactivate_unknown_returns_false(self):
        """停用不存在的变体返回 False。"""
        lab = self._make_lab()
        assert lab.deactivate_variant("v999") is False

    def test_delete_variant(self):
        """删除变体。"""
        lab = self._make_lab()
        v = lab.create_variant("test", "测试版", "- test")
        lab.record_outcome(satisfaction=4)  # 先记录一些 outcome
        assert lab.delete_variant(v.id) is True
        assert lab.get_variant(v.id) is None

    def test_list_active_only(self):
        """active_only 过滤。"""
        lab = self._make_lab()
        v1 = lab.create_variant("a", "A", "- a")
        v2 = lab.create_variant("b", "B", "- b")
        lab.deactivate_variant(v1.id)
        active = lab.list_variants(active_only=True)
        assert len(active) == 1
        assert active[0].id == v2.id


class TestAssignment:
    def _make_lab(self):
        return PromptLab()

    def test_manual_assign(self):
        """手动分配指定变体。"""
        lab = self._make_lab()
        v = lab.create_variant("concise", "简洁版", "- 简短回答")
        assigned = lab.assign_variant(v.id)
        assert assigned is not None
        assert assigned.id == v.id
        assert lab.current_variant.id == v.id

    def test_manual_assign_inactive_returns_none(self):
        """手动分配已停用的变体返回 None。"""
        lab = self._make_lab()
        v = lab.create_variant("test", "测试", "- test")
        lab.deactivate_variant(v.id)
        result = lab.assign_variant(v.id)
        assert result is None

    def test_manual_assign_unknown_returns_none(self):
        """手动分配不存在的变体返回 None。"""
        lab = self._make_lab()
        result = lab.assign_variant("v999")
        assert result is None

    def test_auto_assign_no_variants(self):
        """无变体时自动分配返回 None。"""
        lab = self._make_lab()
        result = lab.assign_variant()  # 无指定
        assert result is None

    def test_auto_assign_weighted(self):
        """加权随机分配：验证分配结果在合法范围内。"""
        lab = self._make_lab()
        _v1 = lab.create_variant("a", "A", "- a", traffic_ratio=0.7)
        _v2 = lab.create_variant("b", "B", "- b", traffic_ratio=0.3)

        assigned_ids = set()
        for _ in range(50):
            v = lab.assign_variant()
            if v:
                assigned_ids.add(v.id)
        # 高概率两个都被分到
        assert assigned_ids.issubset({"v001", "v002"})

    def test_get_active_instructions(self):
        """获取当前变体差异化指令。"""
        lab = self._make_lab()
        # 无变体 → 空串
        assert lab.get_active_instructions() == ""

        v = lab.create_variant("formal", "正式版", "- 使用敬语")
        lab.assign_variant(v.id)
        instructions = lab.get_active_instructions()
        assert "正式版" in instructions
        assert "使用敬语" in instructions


class TestOutcome:
    def _make_lab_with_variant(self):
        lab = PromptLab()
        v = lab.create_variant("test", "测试版", "- test")
        lab.assign_variant(v.id)
        return lab, v

    def test_record_outcome_without_variant(self):
        """无变体时不记录 outcome。"""
        lab = PromptLab()
        lab.record_outcome(satisfaction=4)
        assert len(lab._outcomes) == 0

    def test_record_outcome_default_satisfaction(self):
        """默认满意度=3（中性）。"""
        lab, v = self._make_lab_with_variant()
        lab.record_outcome()
        assert len(lab._outcomes) == 1
        assert lab._outcomes[0].satisfaction == 3

    def test_record_outcome_no_error_boost(self):
        """无工具错误 → 满意度至少 4。"""
        lab, v = self._make_lab_with_variant()
        lab.record_tool_call()
        lab.record_tool_call()
        lab.record_outcome(satisfaction=3)
        assert lab._outcomes[-1].satisfaction >= 4

    def test_record_outcome_many_errors_lower(self):
        """多次工具错误 → 满意度最多 2。"""
        lab, v = self._make_lab_with_variant()
        for _ in range(3):
            lab.record_tool_error()
        lab.record_outcome(satisfaction=5)
        assert lab._outcomes[-1].satisfaction <= 2

    def test_record_tool_counts(self):
        """验证工具调用/错误计数记录到 outcome。"""
        lab, v = self._make_lab_with_variant()
        lab.record_tool_call()
        lab.record_tool_call()
        lab.record_tool_call()
        lab.record_tool_error()
        lab.record_outcome(satisfaction=3)
        o = lab._outcomes[-1]
        assert o.tool_calls == 3
        assert o.corrections == 1

    def test_reset_session_clears_counters(self):
        """reset_session 清除计数器和当前变体。"""
        lab, v = self._make_lab_with_variant()
        lab.record_tool_call()
        lab.record_tool_error()
        lab.reset_session()
        assert lab._session_tool_call_count == 0
        assert lab._session_tool_error_count == 0
        assert lab.current_variant is None


class TestStats:
    def _make_lab_with_data(self):
        lab = PromptLab()
        v1 = lab.create_variant("concise", "简洁版", "- 简短", traffic_ratio=0.5)
        v2 = lab.create_variant("verbose", "详细版", "- 详细说明", traffic_ratio=0.5)

        # 给 v1 记录 3 个 outcome
        for sat in [4, 5, 4]:
            lab.assign_variant(v1.id)
            lab.record_tool_call()
            lab.record_outcome(satisfaction=sat)

        # 给 v2 记录 2 个 outcome
        for sat in [3, 2]:
            lab.assign_variant(v2.id)
            lab.record_tool_error()
            lab.record_outcome(satisfaction=sat)

        return lab, v1, v2

    def test_stats_all_variants(self):
        """汇总所有变体统计。"""
        lab, v1, v2 = self._make_lab_with_data()
        stats = lab.stats()
        assert v1.id in stats
        assert v2.id in stats
        assert stats[v1.id]["count"] == 3
        assert stats[v2.id]["count"] == 2
        # v1 满意度应高于 v2
        assert stats[v1.id]["avg_satisfaction"] > stats[v2.id]["avg_satisfaction"]

    def test_stats_single_variant(self):
        """查询单个变体统计。"""
        lab, v1, v2 = self._make_lab_with_data()
        stats = lab.stats(variant_id=v1.id)
        assert v1.id in stats
        assert v2.id not in stats
        assert stats[v1.id]["avg_satisfaction"] == pytest.approx((4 + 5 + 4) / 3, 0.01)

    def test_summary_text(self):
        """summary_text 生成非空摘要。"""
        lab, v1, v2 = self._make_lab_with_data()
        text = lab.summary_text()
        assert "简洁版" in text
        assert "详细版" in text
        assert "Prompt Lab" in text

    def test_stats_empty(self):
        """无数据时统计正常。"""
        lab = PromptLab()
        stats = lab.stats()
        assert stats == {}

    def test_stats_variant_no_outcomes(self):
        """有变体但无 outcome 时 count=0。"""
        lab = PromptLab()
        v = lab.create_variant("test", "测试", "- test")
        stats = lab.stats()
        assert stats[v.id]["count"] == 0


class TestPersistence:
    def test_save_and_reload_variants(self):
        """变体持久化 + 重新加载。"""
        lab1 = PromptLab()
        v1 = lab1.create_variant("a", "A", "- a指令")
        v2 = lab1.create_variant("b", "B", "- b指令")
        lab1._save_variants()

        # 新实例加载
        lab2 = PromptLab()
        assert lab2.get_variant(v1.id) is not None
        assert lab2.get_variant(v2.id) is not None
        assert lab2.get_variant(v1.id).name == "a"
        assert lab2.get_variant(v2.id).instructions == "- b指令"

    def test_outcomes_append(self):
        """outcome 追加写入 JSONL。"""
        lab = PromptLab()
        v = lab.create_variant("test", "测试", "- test")
        lab.assign_variant(v.id)
        lab.record_outcome(satisfaction=4)
        lab.record_outcome(satisfaction=5)

        outcomes_file = Path("core/brain_data/prompt_lab_outcomes.jsonl")
        assert outcomes_file.exists()
        lines = outcomes_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        o1 = json.loads(lines[0])
        assert o1["variant_id"] == v.id
        assert o1["satisfaction"] == 4

    def test_load_from_corrupt_file(self):
        """损坏的持久化文件不崩溃。"""
        # 写入损坏数据
        from core.prompt_lab import _VARIANTS_FILE

        _VARIANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VARIANTS_FILE.write_text("NOT JSON{{{{", encoding="utf-8")
        lab = PromptLab()
        assert lab.list_variants() == []


class TestCommands:
    def test_commands_registered(self):
        """验证 /prompt-stats 和 /prompt-assign 已注册。"""
        from core.commands import COMMANDS

        keys = [c.key for c in COMMANDS]
        assert "prompt_stats" in keys
        assert "prompt_assign" in keys

    def test_prompt_stats_in_category(self):
        """命令在诊断配置分类。"""
        from core.commands import get_by_category

        cats = get_by_category()
        assert "诊断配置" in cats
        diag_names = [item[0] for item in cats["诊断配置"]]
        assert "/prompt-stats" in diag_names
        assert "/prompt-assign" in diag_names
