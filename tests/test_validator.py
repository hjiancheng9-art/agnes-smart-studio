"""Tests for core/validator.py — 参数校验器"""

import pytest

from core.validator import (
    ValidationError,
    validate_frame_rate,
    validate_image_size,
    validate_image_urls,
    validate_model,
    validate_num_frames,
    validate_seed,
    validate_video_resolution,
)


class TestNumFrames:
    """帧数校验 8n+1"""

    def test_valid_values(self):
        for n in [81, 121, 161, 201, 241, 281, 321, 361, 401, 441]:
            assert validate_num_frames(n) == n

    def test_rounds_to_nearest(self):
        result = validate_num_frames(100)
        assert result in [81, 121]

    def test_clamps_high(self):
        assert validate_num_frames(1000) == 441

    def test_clamps_low(self):
        assert validate_num_frames(-1) == 81

    def test_zero(self):
        assert validate_num_frames(0) == 81


class TestVideoResolution:
    """视频分辨率校验"""

    def test_valid_resolutions(self):
        for w, h in [(1280, 720), (720, 1280), (1024, 1024), (1024, 768), (768, 1024)]:
            assert validate_video_resolution(w, h) == (w, h)

    def test_rounds_to_nearest(self):
        result = validate_video_resolution(1000, 600)
        assert result is not None


class TestImageSize:
    """图片尺寸校验"""

    def test_valid_sizes(self):
        for s in ["1024x768", "1024x1024", "768x1024", "576x1024"]:
            assert validate_image_size(s) == s

    def test_invalid_format_raises(self):
        with pytest.raises(ValidationError):
            validate_image_size("not_a_size")

    def test_arbitrary_size_accepted(self):
        result = validate_image_size("9999x1")
        assert result == "9999x1"


class TestModel:
    """模型名校验"""

    def test_valid_model(self):
        result = validate_model("agnes-2.0-flash")
        assert result is not None

    def test_empty_model_raises(self):
        with pytest.raises(ValidationError):
            validate_model("")


class TestFrameRate:
    """帧率校验"""

    def test_valid_framerates(self):
        for rate in [1, 12, 24, 30, 60]:
            assert validate_frame_rate(rate) == rate

    def test_clamps_high(self):
        assert validate_frame_rate(120) == 60

    def test_clamps_low(self):
        assert validate_frame_rate(-1) == 1


class TestSeed:
    """随机种子校验"""

    def test_valid_seed(self):
        assert validate_seed(42) == 42

    def test_none_seed(self):
        assert validate_seed(None) is None


class TestImageUrls:
    """图片 URL 校验"""

    def test_single_url(self):
        result = validate_image_urls("https://example.com/img.png")
        assert isinstance(result, list)
        assert len(result) == 1

    def test_url_list(self):
        urls = ["https://a.com/1.png", "https://b.com/2.jpg"]
        result = validate_image_urls(urls)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            validate_image_urls("")

    def test_empty_list_raises(self):
        with pytest.raises(ValidationError):
            validate_image_urls([])


class TestValidationError:
    """校验错误异常"""

    def test_is_exception(self):
        assert issubclass(ValidationError, Exception)

    def test_message(self):
        err = ValidationError("参数无效")
        assert "参数无效" in str(err)
