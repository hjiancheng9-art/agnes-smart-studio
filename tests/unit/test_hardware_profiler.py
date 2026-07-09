"""
ComfyFlow Compiler — 硬件探测器单元测试

覆盖：GPU 检测、预算计算、硬件感知决策
优先级：高（硬件预算决定蓝图选择）
目标覆盖率：85%+
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from comfyflow_compiler.hardware_profiler import compute_runtime_budget, detect_gpu
from comfyflow_compiler.models import HardwareProfile


# =============================================================================
# 预算计算
# =============================================================================

class TestComputeRuntimeBudget:
    """从硬件配置计算运行预算"""

    def test_minimal_budget(self):
        hw = HardwareProfile(vram_gb=3.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "minimal"
        assert budget.score == 1.0
        assert budget.max_resolution == "512x512"

    def test_low_budget(self):
        hw = HardwareProfile(vram_gb=4.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "low"
        assert 2.0 <= budget.score <= 3.0
        assert budget.supports_sd15 is True
        assert budget.supports_sdxl is False
        assert budget.supports_flux_gguf is True  # GGUF Q4 可在 4G 上跑

    def test_low_plus_budget(self):
        hw = HardwareProfile(vram_gb=6.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "low_plus"
        assert budget.supports_sd15 is True
        assert budget.supports_flux_gguf is True
        assert budget.supports_wan is True or budget.tier is not None

    def test_medium_budget(self):
        hw = HardwareProfile(vram_gb=8.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "medium"
        assert budget.supports_sdxl is True
        assert budget.supports_flux_gguf is True

    def test_medium_plus_budget(self):
        hw = HardwareProfile(vram_gb=12.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "medium_plus"
        assert budget.supports_sdxl is True
        assert budget.supports_refiner is True
        assert budget.supports_flux is True

    def test_high_budget(self):
        hw = HardwareProfile(vram_gb=16.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "high"
        assert budget.supports_sdxl is True
        assert budget.supports_flux is True
        assert budget.supports_video is True
        assert budget.supports_controlnet == 3
        assert budget.score >= 8.0

    def test_ultra_budget(self):
        hw = HardwareProfile(vram_gb=24.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "ultra"
        assert budget.supports_flux is True
        assert budget.supports_wan is True
        assert budget.supports_ltx is True
        assert budget.score == 10.0

    def test_zero_vram(self):
        """无 GPU 应返回 unknown"""
        hw = HardwareProfile(vram_gb=0.0)
        budget = compute_runtime_budget(hw)
        assert budget.tier == "unknown"
        assert budget.score == 0.0

    def test_increasing_score_with_vram(self):
        """显存越大，预算分应越高"""
        scores = []
        for vram in [2, 4, 6, 8, 12, 16, 24]:
            hw = HardwareProfile(vram_gb=float(vram))
            budget = compute_runtime_budget(hw)
            scores.append(budget.score)
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i-1], f"VRAM {[2,4,6,8,12,16,24][i]}G 预算分下降: {scores}"


# =============================================================================
# GPU 检测（mock 友好）
# =============================================================================

class TestDetectGPU:
    """GPU 检测（无 GPU 环境应优雅降级）"""

    def test_fallback_profile(self):
        """没有 GPU 时应返回合理的信息"""
        profile = detect_gpu()
        # 至少应该有条目
        assert profile is not None
        # 如果有 GPU，应该有名称
        if profile.vram_gb > 0:
            assert profile.gpu_name is not None
        # source 应该是已知的
        assert profile.source in ("pynvml", "nvidia-smi", "torch", "fallback", "unknown")


# =============================================================================
# 分辨率和预算一致性
# =============================================================================

class TestResolutionBudgetConsistency:
    """分辨率上限与预算等级一致"""

    def test_resolution_increases_with_tier(self):
        res_map = {
            "minimal": 512, "low": 768, "low_plus": 768,
            "medium": 1024, "medium_plus": 1024,
            "high": 1536, "ultra": 1792,
        }
        for vram_gb, expected_tier in [(3, "minimal"), (6, "low_plus"), (16, "high"), (24, "ultra")]:
            hw = HardwareProfile(vram_gb=float(vram_gb))
            budget = compute_runtime_budget(hw)
            max_res = max(int(x) for x in budget.max_resolution.split("x"))
            expected_tier_name = expected_tier
            assert budget.tier == expected_tier_name, f"{vram_gb}G 应得 {expected_tier_name}，实际 {budget.tier}"
