"""Tests for utils/gallery.py — gallery helpers, type icons, thumbnail."""

from utils.gallery import (
    GALLERY_FILE,
    THUMB_MAX,
    _type_icon,
    generate_gallery,
)


class TestConstants:
    def test_gallery_file(self):
        assert GALLERY_FILE.name == "gallery.html"

    def test_thumb_max(self):
        assert THUMB_MAX == 320


class TestTypeIcon:
    def test_text_to_image(self):
        result = _type_icon("text_to_image")
        assert "🖼" in result

    def test_image_to_video(self):
        result = _type_icon("image_to_video")
        assert "🎬" in result

    def test_pipeline(self):
        result = _type_icon("pipeline")
        assert "🔗" in result

    def test_unknown_type(self):
        result = _type_icon("unknown")
        assert isinstance(result, str)


class TestGenerateGallery:
    def test_generates_html_file(self):
        result = generate_gallery()
        assert GALLERY_FILE.exists()
        content = GALLERY_FILE.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content or "<html" in content.lower()
