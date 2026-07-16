"""Tests for core.creative.shot_contract — 镜头合同编译器"""

from core.creative.shot_contract import (
    ShotCompiler,
    ShotContract,
    compile_shot,
    validate_single_action,
)

# VALID_VIDEO_FRAMES is in providers/agnes
from core.providers.agnes import VALID_VIDEO_FRAMES


class TestValidateSingleAction:
    def test_single_cn(self):
        valid, msg = validate_single_action("夕阳下的沙滩，海浪轻轻拍打")
        assert valid, msg

    def test_multi_cn_rejected(self):
        valid, msg = validate_single_action("一条龙在天空飞翔，然后俯冲到水面")
        assert not valid
        assert "2 个动作" in msg

    def test_single_en(self):
        valid, _msg = validate_single_action("a cat walking slowly")
        assert valid

    def test_multi_en_rejected(self):
        valid, _msg = validate_single_action("a cat walking and then jumping and then flying")
        assert not valid

    def test_no_action_defaults_to_still(self):
        valid, _msg = validate_single_action("赛博朋克城市的夜景")
        assert valid


class TestShotCompiler:
    def test_single_shot_basic(self):
        result = ShotCompiler.compile("夕阳下的沙滩")
        assert len(result) == 1
        assert result[0].shot_id == "shot_001"

    def test_multi_split(self):
        result = ShotCompiler.compile("一条龙在天空飞翔，然后俯冲到水面")
        assert len(result) >= 1  # 多动作场景

    def test_style_detection(self):
        result = ShotCompiler.compile("cinematic shot of mountains")
        assert result[0].style == "cinematic"

    def test_camera_motion_detection(self):
        result = ShotCompiler.compile("a drone shot flying over mountains")
        assert "drone" in result[0].camera_motion or result[0].camera_motion != ""

    def test_compile_single_shot(self):
        c = compile_shot("夕阳下的沙滩", num_frames=121)
        assert c.num_frames == 121
        assert c.optimized_prompt != ""


class TestShotContract:
    def test_to_video_prompt(self):
        c = ShotContract(
            subject="a cat",
            action="walking",
            scene="beach",
            camera_motion="tracking",
            lighting="golden hour",
            style="cinematic",
        )
        prompt = c.to_video_prompt()
        assert "cat" in prompt
        assert "walking" in prompt
        assert "beach" in prompt
        assert "tracking" in prompt
        assert "cinematic" in prompt

    def test_to_dict(self):
        c = ShotContract(subject="test")
        d = c.to_dict()
        assert d["subject"] == "test"
        assert d["num_frames"] == 81

    def test_keep_stable_default(self):
        c = ShotContract()
        assert "主体位置" in c.keep_stable
        assert "构图比例" in c.keep_stable


class TestVideoFrames:
    def test_all_valid(self):
        for nf in [81, 121, 161, 201, 241, 281, 321, 361, 401, 441]:
            assert nf in VALID_VIDEO_FRAMES

    def test_invalid(self):
        assert 100 not in VALID_VIDEO_FRAMES
        assert 60 not in VALID_VIDEO_FRAMES
