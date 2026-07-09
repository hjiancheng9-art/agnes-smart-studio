"""Tests for core/config.py — 配置管理"""

from core.config import IMAGE_SIZES, VALID_NUM_FRAMES, VIDEO_ASPECT_RATIOS, Settings


class TestSettings:
    """配置管理测试"""

    def test_default_creation(self):
        s = Settings()
        assert s is not None

    def test_save_does_not_crash(self):
        s = Settings()
        if hasattr(s, "save"):
            s.save()  # 不应崩溃

    def test_default_image_size(self):
        s = Settings()
        assert s.default_image_size is not None
        assert "x" in s.default_image_size

    def test_default_num_frames(self):
        s = Settings()
        assert s.default_num_frames > 0

    def test_default_frame_rate(self):
        s = Settings()
        assert s.default_frame_rate in [24, 30, 12, 60]

    def test_default_text_model(self):
        s = Settings()
        assert s.default_text_model is not None

    def test_default_image_model(self):
        s = Settings()
        assert s.default_image_model is not None

    def test_default_video_model(self):
        s = Settings()
        assert s.default_video_model is not None

    def test_video_resolution(self):
        s = Settings()
        assert s.default_video_width > 0
        assert s.default_video_height > 0

    def test_max_retries(self):
        s = Settings()
        assert s.max_retries >= 0

    def test_reflection_settings(self):
        s = Settings()
        assert isinstance(s.reflection_enabled, bool)

    def test_video_poll_interval(self):
        s = Settings()
        assert s.video_poll_interval > 0

    def test_video_max_wait(self):
        s = Settings()
        assert s.video_max_wait > 0

    def test_reflection_interval(self):
        s = Settings()
        assert s.reflection_interval > 0

    def test_base_url(self):
        s = Settings()
        assert s.base_url is not None


class TestConfigConstants:
    """配置常量测试"""

    def test_image_sizes_is_dict(self):
        assert isinstance(IMAGE_SIZES, dict)

    def test_image_sizes_contains_1024x768(self):
        assert "1024x768" in IMAGE_SIZES.values()

    def test_image_sizes_has_all_ratios(self):
        assert len(IMAGE_SIZES) == 9

    def test_valid_num_frames(self):
        assert len(VALID_NUM_FRAMES) > 0
        assert all(n % 8 == 1 for n in VALID_NUM_FRAMES)

    def test_video_aspect_ratios_is_dict(self):
        assert isinstance(VIDEO_ASPECT_RATIOS, dict)

    def test_video_aspect_ratios_non_empty(self):
        assert len(VIDEO_ASPECT_RATIOS) > 0
