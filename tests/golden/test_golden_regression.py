"""
ComfyFlow Compiler — Golden 回归测试

保存已知输入输出，每次运行对比，确保不改坏已有功能。
"""

from __future__ import annotations
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from comfyflow_compiler.intent_parser import parse_intent


GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden_data")
os.makedirs(GOLDEN_DIR, exist_ok=True)


def save_golden(name: str, data):
    path = os.path.join(GOLDEN_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_golden(name: str):
    path = os.path.join(GOLDEN_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestGoldenIntentParser:
    """意图解析器回归 — 修了意图分类代码后跑这个"""

    GOLDEN_NAME = "intent_cinematic_cat"

    def test_intent_parser_golden(self):
        """赛博朋克猫的解析结果应保持稳定"""
        result = parse_intent("生成一张电影感赛博朋克猫，霓虹雨夜，9:16")

        output = {
            "task_type": result.task_type,
            "subject": result.subject,
            "style": sorted(result.style),
            "mood": result.mood,
            "aspect_ratio": result.aspect_ratio,
            "quality_mode": result.quality_mode,
        }

        golden = load_golden(self.GOLDEN_NAME)
        if golden is None:
            save_golden(self.GOLDEN_NAME, output)
            pytest.skip("首次运行，已保存 golden 数据")

        assert output == golden, (
            f"意图解析结果与 golden 不一致!\n"
            f"  Golden: {golden}\n"
            f"  当前:   {output}\n"
            f"  (如果是有意修改，删除 golden_data/{self.GOLDEN_NAME}.json 重新生成)"
        )

    def test_intent_classify_flux(self):
        """Flux 分类结果应稳定"""
        from comfyflow_compiler.intent_parser import classify_production_intent
        result = classify_production_intent("用 Flux 画一只金龙，竖屏")
        golden = load_golden("intent_flux")
        if golden is None:
            save_golden("intent_flux", result)
            pytest.skip("首次运行，已保存 golden 数据")
        assert result == golden


class TestGoldenBlueprintSelection:
    """蓝图选择回归"""

    def test_sdxl_selection(self):
        from comfyflow_compiler.blueprint_registry import BlueprintRegistry
        reg = BlueprintRegistry()
        bp = reg.select_best_blueprint(
            "txt2img", None, budget_score=8.5, vram_gb=16.0,
            has_sdxl=True, has_sd15=True,
        )
        golden = load_golden("blueprint_sdxl_high")
        if golden is None:
            save_golden("blueprint_sdxl_high", bp.name if bp else None)
            pytest.skip("首次运行，已保存 golden 数据")
        assert bp is not None
        assert bp.name == golden, f"蓝图选择变化: {bp.name} vs golden {golden}"


class TestGoldenBudgetTier:
    """预算等级回归"""

    def test_budget_tiers(self):
        from comfyflow_compiler.hardware_profiler import compute_runtime_budget
        from comfyflow_compiler.models import HardwareProfile

        tiers = {}
        for vram in [3, 4, 6, 8, 12, 16, 24]:
            hw = HardwareProfile(vram_gb=float(vram))
            budget = compute_runtime_budget(hw)
            tiers[str(vram)] = {"tier": budget.tier, "score": budget.score}

        golden = load_golden("budget_tiers")
        if golden is None:
            save_golden("budget_tiers", tiers)
            pytest.skip("首次运行，已保存 golden 数据")

        for vram, expected in golden.items():
            actual = tiers.get(vram)
            assert actual == expected, (
                f"VRAM {vram}G 预算变化: {actual} vs golden {expected}"
            )
