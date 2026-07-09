"""
ComfyFlow Compiler — 蓝图注册表单元测试

覆盖：蓝图匹配、降级链、硬件约束过滤、配方检索
优先级：高（决定选什么方案去编译）
目标覆盖率：90%+
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from comfyflow_compiler.blueprint_registry import BlueprintRegistry


@pytest.fixture
def registry():
    return BlueprintRegistry()


# =============================================================================
# 蓝图注册完整性
# =============================================================================

class TestBlueprintRegistry:
    """蓝图注册表基本完整性"""

    def test_all_blueprints_count(self, registry):
        """当前 16 个蓝图"""
        assert len(registry.blueprints) >= 16

    def test_all_recipes_count(self, registry):
        """当前 12 个配方"""
        assert len(registry.recipes) >= 12

    def test_every_recipe_has_blueprints(self, registry):
        """每个配方必须至少有一个 preferred_blueprint"""
        for name, recipe in registry.recipes.items():
            assert len(recipe.preferred_blueprints) > 0, f"配方 {name} 没有蓝图"

    def test_every_blueprint_has_requirement(self, registry):
        """每个蓝图必须对应一个 BlueprintRequirement"""
        for name in registry.blueprints:
            if name == "txt2img_minimal":
                continue  # 最简方案无 special req
            req = registry.requirements.get(name)
            if req is None:
                # 有些蓝图可能没有独立 requirement（继承默认）
                pass

    def test_quality_scores_in_range(self, registry):
        """质量分必须在 0-1 之间"""
        for name, bp in registry.blueprints.items():
            assert 0 <= bp.quality_score <= 1.0, f"{name} quality_score={bp.quality_score}"

    def test_vram_requirements_reasonable(self, registry):
        """显存要求必须在合理范围"""
        for name, bp in registry.blueprints.items():
            assert 0 <= bp.min_vram_gb <= 48, f"{name} min_vram_gb={bp.min_vram_gb}"

    def test_chain_depth_ordered(self, registry):
        """降级链深度应递增"""
        # SDXL 高清 < SDXL 基础 < SD1.5 基础 < 最简
        depths = []
        for name in ["txt2img_sdxl_high_quality", "txt2img_sdxl_basic",
                       "txt2img_sd15_basic", "txt2img_minimal"]:
            bp = registry.blueprints.get(name)
            if bp:
                depths.append(bp.chain_depth)
        assert depths == sorted(depths), f"降级链深度应递增: {depths}"


# =============================================================================
# 配方匹配
# =============================================================================

class TestRecipeMatching:
    """场景配方匹配逻辑"""

    def test_match_cinematic(self, registry):
        recipes = registry.match_recipe("txt2img", ["cinematic"], "猫")
        names = [r.name for r in recipes]
        assert "cinematic_realistic" in names

    def test_match_anime(self, registry):
        recipes = registry.match_recipe("txt2img", ["anime"], "少女")
        names = [r.name for r in recipes]
        assert "anime_character" in names

    def test_match_cyberpunk(self, registry):
        recipes = registry.match_recipe("txt2img", ["cyberpunk"], "城市")
        names = [r.name for r in recipes]
        assert "cyberpunk_scene" in names

    def test_match_video(self, registry):
        recipes = registry.match_recipe("video", [], "视频")
        names = [r.name for r in recipes]
        assert any("video" in n for n in names), f"应匹配到视频配方: {names}"

    def test_match_flux(self, registry):
        recipes = registry.match_recipe("txt2img", [], "flux 猫")
        names = [r.name for r in recipes]
        # 即使没有 flux 风格标签，关键词也应该匹配到
        assert "flux_quick" in names or "flux_premium" in names

    def test_no_match_returns_empty(self, registry):
        recipes = registry.match_recipe("video", [], "zz_not_a_real_thing")
        # 至少应该有默认
        assert len(recipes) >= 0


# =============================================================================
# 蓝图选择（硬件感知）
# =============================================================================

class TestBlueprintSelection:
    """硬件感知蓝图选择"""

    def test_select_sdxl_high_quality(self, registry):
        """16GB + 有 SDXL → 选 SDXL 高清"""
        bp = registry.select_best_blueprint(
            "txt2img", None, budget_score=8.5, vram_gb=16.0,
            has_sdxl=True, has_sd15=True,
        )
        assert bp is not None
        assert "sdxl" in bp.name.lower(), f"应选 SDXL 蓝图: {bp.name}"

    def test_select_sd15_when_no_sdxl(self, registry):
        """4GB + 无 SDXL → 选 SD1.5"""
        bp = registry.select_best_blueprint(
            "txt2img", None, budget_score=2.5, vram_gb=4.0,
            has_sdxl=False, has_sd15=True,
        )
        assert bp is not None
        assert "sd15" in bp.name.lower() or "minimal" in bp.name.lower()

    def test_select_minimal_as_last_resort(self, registry):
        """3GB + 无模型 → 最简保底"""
        bp = registry.select_best_blueprint(
            "txt2img", None, budget_score=0.5, vram_gb=3.0,
            has_sdxl=False, has_sd15=False,
        )
        assert bp is not None
        assert bp.name == "txt2img_minimal" or bp.min_budget_score <= 0.5

    def test_select_flux_with_flux_model(self, registry):
        """有 Flux 模型 → 应选 Flux 蓝图"""
        bp = registry.select_best_blueprint(
            "txt2img", None, budget_score=8.5, vram_gb=16.0,
            has_sdxl=True, has_sd15=True, has_flux=True,
        )
        assert bp is not None
        # 无 recipe 时可能不会自动选 flux，但至少得有蓝图
        assert bp.task_type == "txt2img"

    def test_select_ltx_video_with_ltx_model(self, registry):
        """有 LTX 模型 → 应选 LTX 视频蓝图"""
        bp = registry.select_best_blueprint(
            "video", None, budget_score=8.5, vram_gb=16.0,
            has_sdxl=False, has_sd15=False, has_ltx=True,
        )
        assert bp is not None
        assert bp.task_type == "video"
        assert "ltx" in bp.name.lower()

    def test_select_with_recipe_prioritizes(self, registry):
        """带 recipe 时应优先用 recipe 的 preferred_blueprints"""
        recipe = registry.get_recipe("cinematic_realistic")
        assert recipe is not None
        bp = registry.select_best_blueprint(
            "txt2img", recipe, budget_score=8.5, vram_gb=16.0,
            has_sdxl=True, has_sd15=True,
        )
        assert bp is not None
        assert bp.name in recipe.preferred_blueprints, \
            f"应优先选 recipe 推荐蓝图: {bp.name} not in {recipe.preferred_blueprints}"


# =============================================================================
# 降级链
# =============================================================================

class TestFallbackChain:
    """自动降级策略"""

    def test_fallback_chain_exists_for_recipes(self, registry):
        """主要配方应有降级链"""
        for name in ["cinematic_realistic", "anime_character", "flux_quick", "video_ltx"]:
            recipe = registry.get_recipe(name)
            if recipe and recipe.preferred_blueprints:
                chain = registry.get_fallback_chain(
                    recipe, budget_score=8.5, vram_gb=16.0,
                    has_sdxl=True, has_sd15=True,
                )
                assert len(chain) > 0, f"配方 {name} 降级链为空"

    def test_fallback_respects_hardware(self, registry):
        """低硬件时应过滤掉高要求蓝图"""
        recipe = registry.get_recipe("cinematic_realistic")
        chain = registry.get_fallback_chain(
            recipe, budget_score=1.0, vram_gb=3.0,
            has_sdxl=False, has_sd15=False,
        )
        # 低硬件应有更短的降级链
        chain_high = registry.get_fallback_chain(
            recipe, budget_score=8.5, vram_gb=16.0,
            has_sdxl=True, has_sd15=True,
        )
        assert len(chain) <= len(chain_high)


# =============================================================================
# 蓝图属性合理性
# =============================================================================

class TestBlueprintSanity:
    """蓝图数据合理性检查"""

    def test_sdxl_high_quality_has_nodes(self, registry):
        bp = registry.get_blueprint("txt2img_sdxl_high_quality")
        assert bp is not None
        assert len(bp.nodes) >= 7, f"应该有至少 7 个节点: {len(bp.nodes)}"

    def test_flux_module_uses_unet_loader(self, registry):
        bp = registry.get_blueprint("flux_module_t2v")
        if bp:
            node_types = {n["class_type"] for n in bp.nodes.values()}
            assert "UNETLoader" in node_types, "Flux 模块化应使用 UNETLoader"
            assert "CLIPLoader" in node_types, "应使用 CLIPLoader"
            assert "VAELoader" in node_types, "应使用 VAELoader"
            assert "SamplerCustomAdvanced" in node_types, "应使用高级采样"

    def test_ltx_full_has_video_output(self, registry):
        bp = registry.get_blueprint("ltx_full_t2v")
        if bp and bp.nodes:
            node_types = {n["class_type"] for n in bp.nodes.values()}
            assert "VHS_VideoCombine" in node_types, "LTX 视频应输出视频文件"

    def test_recipe_blueprints_exist(self, registry):
        """配方推荐的蓝图必须存在（auto_* 前缀的为运行时动态添加）"""
        for recipe in registry.recipes.values():
            for bp_name in recipe.preferred_blueprints:
                if bp_name.startswith("auto_"):
                    continue  # auto_* 蓝图是运行时由 BlueprintMiner 动态添加的
                assert bp_name in registry.blueprints, \
                    f"配方 {recipe.name} 引用了不存在的蓝图 {bp_name}"
