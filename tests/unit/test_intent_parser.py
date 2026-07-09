"""
ComfyFlow Compiler — 意图解析器单元测试

覆盖：parse_intent, classify_production_intent
优先级：最高（入口第一关，错了全链崩）
目标覆盖率：95%+
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from comfyflow_compiler.intent_parser import parse_intent, classify_production_intent


# =============================================================================
# 生产意图分类测试
# =============================================================================

class TestClassifyProductionIntent:
    """9 种生产意图的分类准确性"""

    def test_flux_generation(self):
        assert classify_production_intent("用 Flux 画一只金龙") == "flux_generation"
        assert classify_production_intent("FLUX 出图，赛博朋克风格") == "flux_generation"
        assert classify_production_intent("flux 高质量生成") == "flux_generation"

    def test_ltx_video(self):
        assert classify_production_intent("做一个 LTX 视频") == "ltx_video"
        assert classify_production_intent("LTX 图生视频") == "ltx_video"
        assert classify_production_intent("用 ltx 生成视频") == "ltx_video"

    def test_wan_video(self):
        assert classify_production_intent("用 Wan 做一个视频") == "wan_video"
        assert classify_production_intent("WAN 生成视频") == "wan_video"

    def test_character_replace(self):
        assert classify_production_intent("给我换个衣服") == "character_replace"
        assert classify_production_intent("换装，变成古装") == "character_replace"
        assert classify_production_intent("角色替换") == "character_replace"

    def test_face_swap(self):
        assert classify_production_intent("给我换脸") == "face_swap"
        assert classify_production_intent("用 reactor 换脸") == "face_swap"
        assert classify_production_intent("faceid 生成") == "face_swap"

    def test_video_lipsync(self):
        assert classify_production_intent("数字人对口型") == "video_lipsync"
        assert classify_production_intent("做对口型视频") == "video_lipsync"

    def test_action_transfer(self):
        assert classify_production_intent("动作迁移") == "action_transfer"
        assert classify_production_intent("让角色跳舞") == "action_transfer"
        assert classify_production_intent("motion transfer") == "action_transfer"

    def test_image_edit(self):
        assert classify_production_intent("编辑这张图") == "image_edit"
        assert classify_production_intent("把背景替换掉") == "image_edit"
        assert classify_production_intent("inpaint 修复") == "image_edit"

    def test_flux_to_ltx(self):
        assert classify_production_intent("图片转视频") == "flux_to_ltx"
        assert classify_production_intent("图像动画化") == "flux_to_ltx"

    def test_unknown_intent(self):
        """通用描述不应被错误分类"""
        assert classify_production_intent("画一只猫") == ""
        assert classify_production_intent("你好") == ""


# =============================================================================
# 任务类型解析测试
# =============================================================================

class TestParseTaskType:
    """parse_intent 的任务类型识别"""

    def test_txt2img_default(self):
        task = parse_intent("一只猫")
        assert task.task_type == "txt2img"

    def test_txt2img_explicit(self):
        task = parse_intent("生成一张猫的照片")
        assert task.task_type == "txt2img"

    def test_img2img(self):
        task = parse_intent("重绘这张图")
        assert task.task_type == "img2img"

    def test_video(self):
        task = parse_intent("做一个视频")
        assert task.task_type == "video"

    def test_controlnet(self):
        task = parse_intent("按照这个姿势生成")
        assert task.task_type == "controlnet"

    def test_production_intent_overrides(self):
        """生产意图应覆盖任务类型"""
        task = parse_intent("用 Flux 画一只金龙")
        assert task.production_intent == "flux_generation"
        assert task.task_type == "txt2img"  # flux_generation 指定为 txt2img

        task = parse_intent("做一个 LTX 视频")
        assert task.production_intent == "ltx_video"
        assert task.task_type == "video"

        task = parse_intent("给我换个衣服")
        assert task.production_intent == "character_replace"
        assert task.task_type == "img2img"


# =============================================================================
# 主体提取测试
# =============================================================================

class TestParseSubject:
    """subject 字段提取质量"""

    def test_keep_core_subject(self):
        task = parse_intent("生成一张电影感赛博朋克猫，霓虹雨夜")
        assert "赛博朋克猫" in task.subject or "猫" in task.subject
        assert task.subject != "" 

    def test_remove_action_prefix(self):
        task = parse_intent("画一只金色的龙，火焰背景")
        assert "金色的龙" in task.subject

    def test_flux_subject(self):
        task = parse_intent("用 Flux 画一只金龙，竖屏")
        assert "金龙" in task.subject or "一只" in task.subject

    def test_character_replace_subject(self):
        task = parse_intent("给我换个衣服，变成古装风格")
        assert task.subject != ""


# =============================================================================
# 风格解析测试
# =============================================================================

class TestParseStyle:
    """风格标签识别"""

    def test_cinematic(self):
        task = parse_intent("电影感赛博朋克猫")
        assert "cinematic" in task.style
        assert "cyberpunk" in task.style

    def test_anime(self):
        task = parse_intent("二次元少女，清新风格")
        assert "anime" in task.style

    def test_default_style(self):
        task = parse_intent("一只猫")
        assert "realistic" in task.style

    def test_multiple_styles(self):
        task = parse_intent("电影感奇幻龙，油画风格")
        assert "cinematic" in task.style
        assert "fantasy" in task.style


# =============================================================================
# 宽高比测试
# =============================================================================

class TestParseAspectRatio:
    """宽高比识别"""

    def test_square_default(self):
        task = parse_intent("一只猫")
        assert task.aspect_ratio == "1:1"

    def test_portrait(self):
        task = parse_intent("竖屏二次元少女")
        assert task.aspect_ratio == "9:16"
        task = parse_intent("画一只猫，9:16")
        assert task.aspect_ratio == "9:16"

    def test_landscape(self):
        task = parse_intent("横屏电影感")
        assert task.aspect_ratio == "16:9"


# =============================================================================
# 质量模式测试
# =============================================================================

class TestParseQualityMode:
    """质量模式识别"""

    def test_balanced_default(self):
        task = parse_intent("一只猫")
        assert task.quality_mode == "balanced"

    def test_high_quality(self):
        task = parse_intent("高清电影感猫")
        assert task.quality_mode == "high"

    def test_fast(self):
        task = parse_intent("快速出图")
        assert task.quality_mode == "fast"

    def test_cinematic(self):
        task = parse_intent("电影级画质")
        assert task.quality_mode == "cinematic"


# =============================================================================
# 边界情况测试
# =============================================================================

class TestParseEdgeCases:
    """边界和异常输入"""

    def test_empty_string(self):
        task = parse_intent("")
        assert task.task_type == "txt2img"
        assert task.subject == ""  # short enough

    def test_very_short(self):
        task = parse_intent("猫")
        assert task.task_type == "txt2img"
        assert task.subject == "猫"

    def test_special_chars(self):
        task = parse_intent("画一只🐱猫，✨星空✨")
        assert task.subject != ""

    def test_numeric_input(self):
        task = parse_intent("生成一张 1920x1080 的壁纸")
        assert task.task_type == "txt2img"

    def test_mixed_language(self):
        task = parse_intent("a cyberpunk cat in rain, 电影感")
        assert "cyberpunk" in task.style
        assert "cinematic" in task.style
