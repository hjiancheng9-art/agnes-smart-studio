"""#5 Prompt Lab — A/B system prompt 实验框架。

核心能力：
1. **Variant 管理**: 创建/切换/删除 system prompt 变体（A/B 实验）
2. **Outcome 记录**: 每次 send_stream 结束后记录质量指标（满意度/完成度/修正次数）
3. **统计聚合**: 按 variant 汇总 outcome → 对比效果
4. **自动分配**: 按 traffic_ratio 自动选择 variant（或手动 /prompt-assign）

设计原则：
- **零侵入**: chat.py 仅在 _build_system_prompt 末尾追加 variant 差异片段，
  在 send_stream return 前调用 record_outcome()
- **持久化**: JSONL 格式存储在 crux_manifest.json 同级目录
- **降级安全**: 任何 IO/序列化异常静默，不阻塞主流程

存储格式 (prompt_lab_variants.json):
[
  {"id": "v001", "name": "concise", "label": "简洁版",
   "instructions": "- 回答限制在1段\n- 禁止寒暄",
   "traffic_ratio": 0.5, "is_active": true, "created": "..."},
  ...
]

存储格式 (prompt_lab_outcomes.jsonl):
{"variant_id":"v001","session_ts":"...","satisfaction":4,"completions":1,"corrections":0,"tool_calls":3} ...
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "PromptLab",
    "Variant",
    "Outcome",
    "get_prompt_lab",
    "reset_prompt_lab",
]

# ── 数据结构 ────────────────────────────────────────────────────────


@dataclass
class Variant:
    """System prompt 变体定义。"""

    id: str  # 唯一 ID（v001, v002...）
    name: str  # 英文短名（concise, formal, creative...）
    label: str  # 中文标签（简洁版, 正式版, 创意版...）
    instructions: str  # 差异化指令片段（追加到 base prompt 末尾）
    traffic_ratio: float = 0.5  # 流量分配比例（所有 active 变体自动归一化）
    is_active: bool = True  # 是否参与实验
    created: str = ""  # ISO 时间戳


@dataclass
class Outcome:
    """单次对话的质量记录。"""

    variant_id: str
    session_ts: str
    satisfaction: int  # 用户满意度 1-5（可由工具调用推断或手动反馈）
    completions: int = 1  # 本次会话完成的任务数
    corrections: int = 0  # 修正/重试次数（从 tool error 计数推断）
    tool_calls: int = 0  # 本次会话的工具调用总数


# ── Prompt Lab 核心 ─────────────────────────────────────────────────

_PROMPT_LAB_DIR = Path(__file__).resolve().parent.parent / "core" / "brain_data"
_VARIANTS_FILE = _PROMPT_LAB_DIR / "prompt_lab_variants.json"
_OUTCOMES_FILE = _PROMPT_LAB_DIR / "prompt_lab_outcomes.jsonl"
_PROMPT_LAB_INSTANCE: PromptLab | None = None


class PromptLab:
    """A/B Prompt 实验管理器。

    线程安全：单实例在 ChatSession 内同步调用，无并发问题。
    """

    def __init__(self) -> None:
        self._variants: dict[str, Variant] = {}
        self._outcomes: list[Outcome] = []
        self._current_variant_id: str | None = None
        self._session_tool_error_count: int = 0
        self._session_tool_call_count: int = 0
        self._load()

    # ── Variant CRUD ─────────────────────────────────────────────

    def create_variant(
        self,
        name: str,
        label: str,
        instructions: str,
        traffic_ratio: float = 0.5,
    ) -> Variant:
        """创建新变体并持久化。"""
        # 生成 ID
        idx = len(self._variants) + 1
        vid = f"v{idx:03d}"
        # 防止 ID 冲突
        while vid in self._variants:
            idx += 1
            vid = f"v{idx:03d}"

        v = Variant(
            id=vid,
            name=name,
            label=label,
            instructions=instructions,
            traffic_ratio=max(0.0, min(1.0, traffic_ratio)),
            created=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._variants[vid] = v
        self._save_variants()
        return v

    def list_variants(self, active_only: bool = False) -> list[Variant]:
        """列出变体列表。"""
        variants = list(self._variants.values())
        if active_only:
            variants = [v for v in variants if v.is_active]
        return variants

    def get_variant(self, variant_id: str) -> Variant | None:
        """按 ID 获取变体。"""
        return self._variants.get(variant_id)

    def deactivate_variant(self, variant_id: str) -> bool:
        """停用变体（从实验中移除，保留数据）。"""
        v = self._variants.get(variant_id)
        if v:
            v.is_active = False
            self._save_variants()
            return True
        return False

    def activate_variant(self, variant_id: str) -> bool:
        """重新激活变体。"""
        v = self._variants.get(variant_id)
        if v:
            v.is_active = True
            self._save_variants()
            return True
        return False

    def delete_variant(self, variant_id: str) -> bool:
        """删除变体及其所有 outcome 数据。"""
        if variant_id in self._variants:
            del self._variants[variant_id]
            # 同步清除相关 outcomes
            self._outcomes = [o for o in self._outcomes if o.variant_id != variant_id]
            self._save_variants()
            self._save_outcomes()
            return True
        return False

    # ── 分配逻辑 ────────────────────────────────────────────────

    def assign_variant(self, variant_id: str | None = None) -> Variant | None:
        """分配当前会话使用的变体。

        - variant_id 指定时：强制分配
        - 未指定时：按 traffic_ratio 加权随机分配
        - 无 active 变体时：返回 None（走 baseline）
        """
        if variant_id:
            v = self._variants.get(variant_id)
            if v and v.is_active:
                self._current_variant_id = variant_id
                return v
            return None

        active = [v for v in self._variants.values() if v.is_active]
        if not active:
            self._current_variant_id = None
            return None

        # 加权随机
        total_ratio = sum(v.traffic_ratio for v in active)
        if total_ratio <= 0:
            self._current_variant_id = None
            return None

        r = random.uniform(0, total_ratio)
        cumulative = 0.0
        chosen = active[0]
        for v in active:
            cumulative += v.traffic_ratio
            if r <= cumulative:
                chosen = v
                break
        self._current_variant_id = chosen.id
        return chosen

    @property
    def current_variant(self) -> Variant | None:
        """当前会话的变体。"""
        if self._current_variant_id:
            return self._variants.get(self._current_variant_id)
        return None

    def get_active_instructions(self) -> str:
        """获取当前变体的差异化指令片段（空串=无变体）。"""
        v = self.current_variant
        if v:
            return f"\n\n## Prompt 变体 [{v.label}]\n{v.instructions}"
        return ""

    # ── Outcome 记录 ─────────────────────────────────────────────

    def record_tool_error(self) -> None:
        """记录一次工具调用错误（供 send_stream 的 tool dispatch 路径调用）。"""
        self._session_tool_error_count += 1

    def record_tool_call(self) -> None:
        """记录一次工具调用。"""
        self._session_tool_call_count += 1

    def record_outcome(
        self,
        satisfaction: int = 3,
        completions: int = 1,
    ) -> None:
        """记录本次会话的 outcome（send_stream 末尾调用）。

        satisfaction 默认 3（中性），可由工具调用结果推断：
        - 无修正 → 4
        - 有修正 → 2
        """
        if not self._current_variant_id:
            return  # 无变体，不记录

        # 自动推断 satisfaction
        inferred = satisfaction
        if self._session_tool_error_count == 0 and self._session_tool_call_count > 0:
            inferred = max(inferred, 4)  # 无错误，至少 4
        elif self._session_tool_error_count > 2:
            inferred = min(inferred, 2)  # 多次错误，最多 2

        outcome = Outcome(
            variant_id=self._current_variant_id,
            session_ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
            satisfaction=inferred,
            completions=completions,
            corrections=self._session_tool_error_count,
            tool_calls=self._session_tool_call_count,
        )
        self._outcomes.append(outcome)
        self._save_outcomes()

        # 重置会话计数器
        self._session_tool_error_count = 0
        self._session_tool_call_count = 0

    # ── 统计 ────────────────────────────────────────────────────

    def stats(self, variant_id: str | None = None) -> dict[str, Any]:
        """按变体汇总统计。variant_id=None 时返回所有变体。"""
        vid_filter = {variant_id} if variant_id else {v.id for v in self._variants.values()}

        result: dict[str, Any] = {}
        for vid in vid_filter:
            variant = self._variants.get(vid)
            if not variant:
                continue
            outcomes = [o for o in self._outcomes if o.variant_id == vid]
            if not outcomes:
                result[vid] = {
                    "label": variant.label,
                    "name": variant.name,
                    "active": variant.is_active,
                    "count": 0,
                }
                continue
            avg_sat = sum(o.satisfaction for o in outcomes) / len(outcomes)
            avg_comp = sum(o.completions for o in outcomes) / len(outcomes)
            avg_err = sum(o.corrections for o in outcomes) / len(outcomes)
            avg_tools = sum(o.tool_calls for o in outcomes) / len(outcomes)
            result[vid] = {
                "label": variant.label,
                "name": variant.name,
                "active": variant.is_active,
                "count": len(outcomes),
                "avg_satisfaction": round(avg_sat, 2),
                "avg_completions": round(avg_comp, 2),
                "avg_corrections": round(avg_err, 2),
                "avg_tool_calls": round(avg_tools, 2),
            }
        return result

    def summary_text(self) -> str:
        """生成人类可读的统计摘要。"""
        all_stats = self.stats()
        if not all_stats:
            return "📝 Prompt Lab: 暂无实验变体。用 create 创建第一个变体。"

        lines = ["📊 Prompt Lab 实验统计"]
        for _vid, s in all_stats.items():
            if s["count"] == 0:
                lines.append(f"  [{s['label']}] 无数据 (name={s['name']})")
            else:
                lines.append(
                    f"  [{s['label']}] n={s['count']} "
                    f"满意度={s['avg_satisfaction']} "
                    f"完成度={s['avg_completions']} "
                    f"修正={s['avg_corrections']} "
                    f"工具调用={s['avg_tool_calls']}"
                )
        return "\n".join(lines)

    # ── 持久化 ─────────────────────────────────────────────────

    def _load(self) -> None:
        """从磁盘加载变体和 outcome。"""
        try:
            if _VARIANTS_FILE.exists():
                data = json.loads(_VARIANTS_FILE.read_text(encoding="utf-8"))
                for item in data:
                    v = Variant(**item)
                    self._variants[v.id] = v
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        try:
            if _OUTCOMES_FILE.exists():
                for line in _OUTCOMES_FILE.read_text(encoding="utf-8").strip().split("\n"):
                    line = line.strip()
                    if line:
                        o = Outcome(**json.loads(line))
                        self._outcomes.append(o)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def _save_variants(self) -> None:
        """持久化变体列表。"""
        try:
            _PROMPT_LAB_DIR.mkdir(parents=True, exist_ok=True)
            _VARIANTS_FILE.write_text(
                json.dumps([asdict(v) for v in self._variants.values()], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except (OSError, TypeError):
            pass

    def _save_outcomes(self) -> None:
        """持久化 outcome（追加式 JSONL）。"""
        try:
            _PROMPT_LAB_DIR.mkdir(parents=True, exist_ok=True)
            with open(_OUTCOMES_FILE, "a", encoding="utf-8") as f:
                o = self._outcomes[-1]
                f.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")
        except (OSError, TypeError, IndexError):
            pass

    def reset_session(self) -> None:
        """重置会话级计数器。"""
        self._session_tool_error_count = 0
        self._session_tool_call_count = 0
        self._current_variant_id = None


# ── 全局单例 ───────────────────────────────────────────────────────


def get_prompt_lab() -> PromptLab:
    """获取全局 PromptLab 单例。"""
    global _PROMPT_LAB_INSTANCE
    if _PROMPT_LAB_INSTANCE is None:
        _PROMPT_LAB_INSTANCE = PromptLab()
    return _PROMPT_LAB_INSTANCE


def reset_prompt_lab() -> None:
    """重置全局单例（供测试隔离）。"""
    global _PROMPT_LAB_INSTANCE
    if _PROMPT_LAB_INSTANCE is not None:
        _PROMPT_LAB_INSTANCE.reset_session()
    _PROMPT_LAB_INSTANCE = None
