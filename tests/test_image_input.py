"""Tests for utils.image_input — image input loading and conversion."""

import base64
from unittest.mock import patch, MagicMock

import pytest


# ── file_to_data_uri ────────────────────────────────────────────────────


class TestFileToDataUri:
    """Convert local image file to base64 data URI."""

    def test_png_file(self, tmp_path):
        from utils.image_input import file_to_data_uri
        # Create a minimal PNG file (1x1 transparent pixel)
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAI"
            "ABQABNjN9GQAAAABJRU5ErkJggg=="
        )
        f = tmp_path / "test.png"
        f.write_bytes(png_data)
        result = file_to_data_uri(f)
        assert result.startswith("data:image/png;base64,")
        # Verify it decodes back
        b64_part = result.split("base64,", 1)[1]
        assert base64.b64decode(b64_part) == png_data

    def test_jpg_file(self, tmp_path):
        from utils.image_input import file_to_data_uri
        # Create a minimal JPEG (JFIF header)
        jpeg_data = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10] + [0x00] * 20)
        f = tmp_path / "test.jpg"
        f.write_bytes(jpeg_data)
        result = file_to_data_uri(f)
        assert result.startswith("data:image/jpeg;base64,")

    def test_webp_file(self, tmp_path):
        from utils.image_input import file_to_data_uri
        f = tmp_path / "test.webp"
        f.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8")
        result = file_to_data_uri(f)
        assert result.startswith("data:image/webp;base64,")

    def test_unknown_extension_defaults_to_png(self, tmp_path):
        from utils.image_input import file_to_data_uri
        f = tmp_path / "test.xyz"
        f.write_bytes(b"some data")
        result = file_to_data_uri(f)
        assert "data:image/png;base64," in result


# ── load_image_as_url_or_data ────────────────────────────────────────────


class TestLoadImageAsUrlOrData:
    """Detect image input type and convert to URL or data URI."""

    def test_url_passthrough(self):
        from utils.image_input import load_image_as_url_or_data
        url = "https://example.com/image.png"
        assert load_image_as_url_or_data(url) == url

    def test_data_uri_passthrough(self):
        from utils.image_input import load_image_as_url_or_data
        uri = "data:image/png;base64,abc123"
        assert load_image_as_url_or_data(uri) == uri

    def test_local_file(self, tmp_path):
        from utils.image_input import load_image_as_url_or_data
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        result = load_image_as_url_or_data(str(f))
        assert result.startswith("data:image/png;base64,")

    def test_base64_detection_png(self):
        from utils.image_input import load_image_as_url_or_data
        # Encode a PNG-like header
        data = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        result = load_image_as_url_or_data(data)
        assert result.startswith("data:image/png;base64,")

    def test_invalid_input_raises(self):
        from utils.image_input import load_image_as_url_or_data
        with pytest.raises(ValueError):
            load_image_as_url_or_data("not_a_valid_input")

    def test_strips_quotes(self, tmp_path):
        from utils.image_input import load_image_as_url_or_data
        url = '"https://example.com/image.png"'
        assert load_image_as_url_or_data(url) == "https://example.com/image.png"


# ── clipboard_to_data_uri ──────────────────────────────────────────────


class TestClipboardToDataUri:
    """Grab image from clipboard."""

    def test_no_image_available(self):
        from utils.image_input import clipboard_to_data_uri
        # ImageGrab.grabclipboard returns None when no image
        with patch("PIL.ImageGrab.grabclipboard", return_value=None):
            assert clipboard_to_data_uri() is None

    def test_image_available(self):
        from utils.image_input import clipboard_to_data_uri
        # Create a mock PIL Image
        mock_img = MagicMock()
        with patch("PIL.ImageGrab.grabclipboard", return_value=mock_img):
            result = clipboard_to_data_uri()
            assert result is not None
            assert result.startswith("data:image/png;base64,")

    def test_import_error_returns_none(self):
        from utils.image_input import clipboard_to_data_uri
        with patch("PIL.ImageGrab.grabclipboard", side_effect=ImportError("no clipboard")):
            result = clipboard_to_data_uri()
            assert result is None
