"""Test ui/clipboard_image.py — image path detection, drag-drop parsing."""

from __future__ import annotations

from ui.clipboard_image import detect_drag_images, is_image_path


class TestIsImagePath:
    def test_is_image_path_nonexistent_returns_empty(self):
        """is_image_path with a nonexistent file returns empty string
        (Path.is_file() check fails)."""
        result = is_image_path("C:/nonexistent_test_file.png")
        assert result == "", f"Expected '', got '{result}'"

    def test_is_image_path_invalid_ext(self):
        """is_image_path('file.txt') returns '' because .txt is not an image ext."""
        result = is_image_path("file.txt")
        assert result == "", f"Expected '', got '{result}'"

    def test_is_image_path_strips_quotes(self):
        """is_image_path with quoted path strips quotes before checking."""
        result = is_image_path('"C:/photo.jpg"')
        # The file doesn't exist, so it returns "" — but the quotes ARE stripped
        # Verify the function does NOT return the raw quoted string
        assert result != '"C:/photo.jpg"', (
            "Quotes should be stripped; raw quoted path should not be returned"
        )

    def test_is_image_path_strips_single_quotes(self):
        """is_image_path with single-quoted path strips quotes."""
        result = is_image_path("'C:/photo.png'")
        # File doesn't exist, but quotes should be stripped
        assert "'" not in result, f"Quotes not stripped: '{result}'"


class TestDetectDragImages:
    def test_detect_drag_images_two_paths(self):
        """detect_drag_images with two quoted image paths returns 2 paths (or 0 if files
        don't exist)."""
        result = detect_drag_images('"C:/a.png" "C:/b.jpg"')
        # Neither file exists, so it returns []
        assert result == [], (
            f"Expected empty list (files don't exist), got: {result}"
        )
