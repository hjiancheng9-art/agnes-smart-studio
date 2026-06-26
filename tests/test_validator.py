"""Unit tests for input validation module."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.validator import (
    validate_frame_rate,
    validate_image_size,
    validate_image_urls,
    validate_model,
    validate_num_frames,
    validate_seed,
    validate_video_resolution,
)


class TestImageSizeValidation:
    def test_valid_sizes(self):
        for size in ["1024x1024", "1024x768", "576x1024", "1024x576"]:
            result = validate_image_size(size)
            assert result == size or "x" in result

    def test_invalid_size_raises(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_image_size("abc")

    def test_empty_size(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_image_size("")

    def test_single_number_size(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_image_size("1024")


class TestModelValidation:
    def test_valid_image_model(self):
        assert validate_model("agnes-image-2.1-flash", "image") == "agnes-image-2.1-flash"

    def test_invalid_model_type_raises(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_model("not-a-model", "image")

    def test_empty_model_raises(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_model("", "image")


class TestSeedValidation:
    def test_none_seed_returns_none(self):
        assert validate_seed(None) is None

    def test_valid_seed(self):
        assert validate_seed(42) == 42
        assert validate_seed(0) == 0
        assert validate_seed(99999999) == 99999999

    def test_negative_seed_clamps_to_zero(self):
        assert validate_seed(-1) == 0


class TestVideoValidation:
    def test_valid_resolution(self):
        w, h = validate_video_resolution(1024, 768)
        assert w == 1024
        assert h == 768

    def test_valid_num_frames(self):
        assert validate_num_frames(121) == 121
        assert validate_num_frames(81) == 81

    def test_num_frames_clamped_to_min(self):
        result = validate_num_frames(10)
        assert result >= 81

    def test_valid_frame_rate(self):
        assert validate_frame_rate(24) == 24
        assert validate_frame_rate(30) == 30

    def test_frame_rate_clamped_to_max(self):
        result = validate_frame_rate(100)
        assert result <= 60


class TestImageUrlValidation:
    def test_single_valid_url(self):
        result = validate_image_urls("https://example.com/img.png")
        assert result == ["https://example.com/img.png"]

    def test_multiple_urls(self):
        result = validate_image_urls(["https://a.com/1.jpg", "https://b.com/2.jpg"])
        assert len(result) == 2

    def test_empty_urls(self):
        with pytest.raises((ValueError, RuntimeError)):
            validate_image_urls([])
