"""Tests for utils/templates.py — prompt template application."""

from unittest.mock import patch

import pytest

from utils.templates import apply_template, get_template, get_template_info, list_templates

SAMPLE_TEMPLATES = {
    "cyberpunk": {
        "image": "cyberpunk cityscape style",
        "video": "a drone shot cyberpunk video",
        "negative": "blurry, low quality",
    },
    "anime": {
        "image": "anime art style, cel shaded",
        "negative": "realistic, photorealistic",
    },
    "minimal": {
        "image": "minimal style",
    },
}


@pytest.fixture
def mock_templates():
    """Mock PROMPT_TEMPLATES in core.config with sample data."""
    with patch("utils.templates.PROMPT_TEMPLATES", SAMPLE_TEMPLATES):
        yield


class TestListTemplates:
    """Tests for list_templates()."""

    def test_returns_template_names(self, mock_templates):
        names = list_templates()
        assert isinstance(names, list)
        assert "cyberpunk" in names
        assert "anime" in names
        assert len(names) == len(SAMPLE_TEMPLATES)


class TestGetTemplate:
    """Tests for get_template()."""

    def test_existing_template(self, mock_templates):
        tpl = get_template("cyberpunk")
        assert tpl is not None
        assert tpl["image"] == "cyberpunk cityscape style"

    def test_nonexistent_template_returns_none(self, mock_templates):
        assert get_template("nonexistent") is None


class TestApplyTemplate:
    """Tests for apply_template() — the core template application function."""

    def test_apply_image_template(self, mock_templates):
        enhanced, negative = apply_template("cyberpunk", "a city", target="image")
        assert "a city" in enhanced
        assert "cyberpunk cityscape style" in enhanced
        assert negative == "blurry, low quality"

    def test_apply_video_template(self, mock_templates):
        enhanced, negative = apply_template("cyberpunk", "a city", target="video")
        assert "a city" in enhanced
        assert "drone shot cyberpunk video" in enhanced
        assert negative == "blurry, low quality"

    def test_nonexistent_template_returns_original(self, mock_templates):
        enhanced, negative = apply_template("nonexistent", "my prompt", target="image")
        assert enhanced == "my prompt"
        assert negative == ""

    def test_template_without_negative(self, mock_templates):
        enhanced, negative = apply_template("minimal", "test prompt", target="image")
        assert "minimal style" in enhanced
        assert negative == ""

    def test_template_video_falls_back_to_image(self, mock_templates):
        enhanced, _negative = apply_template("minimal", "test", target="video")
        assert "minimal style" in enhanced

    def test_default_target_is_image(self, mock_templates):
        enhanced, _negative = apply_template("cyberpunk", "test")
        assert "cyberpunk cityscape style" in enhanced


class TestGetTemplateInfo:
    """Tests for get_template_info()."""

    def test_existing_template_info(self, mock_templates):
        info = get_template_info("cyberpunk")
        assert "cyberpunk" in info

    def test_nonexistent_template_info(self, mock_templates):
        info = get_template_info("nonexistent")
        assert "nonexistent" in info or "\u672a\u627e\u5230" in info
