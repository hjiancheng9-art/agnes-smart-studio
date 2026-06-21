"""Tests for utils.downloader — image/video download with auth fallback."""

import os
from unittest.mock import patch, MagicMock

import pytest


class TestSanitizeFilename:
    """Filename sanitization helpers."""

    def test_removes_invalid_chars(self):
        from utils.downloader import _sanitize_filename
        assert _sanitize_filename("file<>:name") == "file___name"

    def test_truncates_long_name(self):
        from utils.downloader import _sanitize_filename
        long_name = "a" * 200
        result = _sanitize_filename(long_name)
        assert len(result) <= 80


class TestGuessExt:
    """Extension guessing from URL."""

    def test_png_extension(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/image.png") == ".png"

    def test_jpg_extension(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/photo.jpg") == ".jpg"

    def test_mp4_extension(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/video.mp4") == ".mp4"

    def test_strips_query_string(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/image.png?token=abc123") == ".png"

    def test_unknown_returns_default(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/no-extension") == ".png"

    def test_custom_default(self):
        from utils.downloader import _guess_ext
        assert _guess_ext("https://example.com/unknown", default=".mp4") == ".mp4"


class TestDownloadImage:
    """Image download with retry strategy."""

    def test_successful_download(self, tmp_path, monkeypatch):
        from utils import downloader

        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG fake image data"

        with patch("utils.downloader.httpx.get", return_value=mock_resp):
            result = downloader.download_image("https://example.com/img.png")

        assert result.endswith(".png")
        assert os.path.exists(result)
        with open(result, "rb") as f:
            assert f.read() == b"\x89PNG fake image data"

    def test_download_with_custom_filename(self, tmp_path, monkeypatch):
        from utils import downloader
        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"image-bytes"

        with patch("utils.downloader.httpx.get", return_value=mock_resp):
            result = downloader.download_image(
                "https://example.com/img.png", filename="custom.png"
            )

        assert result.endswith("custom.png")

    def test_download_failure_raises(self, tmp_path, monkeypatch):
        from utils import downloader
        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("utils.downloader.httpx.get", return_value=mock_resp), pytest.raises(RuntimeError, match="图片下载失败"):
            downloader.download_image("https://example.com/missing.png")

    def test_download_network_error_raises(self, tmp_path, monkeypatch):
        from utils import downloader
        import httpx
        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        def raise_error(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        with patch("utils.downloader.httpx.get", side_effect=raise_error), pytest.raises(RuntimeError, match="图片下载失败"):
            downloader.download_image("https://example.com/img.png")


class TestDownloadVideo:
    """Video download with content-size validation."""

    def test_successful_download(self, tmp_path, monkeypatch):
        from utils import downloader
        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x00\x00\x00\x20ftyp" + b"\x00" * 2000  # > 1000 bytes

        with patch("utils.downloader.httpx.get", return_value=mock_resp):
            result = downloader.download_video("https://example.com/clip.mp4")

        assert result.endswith(".mp4")
        assert os.path.exists(result)

    def test_small_content_rejected(self, tmp_path, monkeypatch):
        """Videos under 1000 bytes are considered invalid."""
        from utils import downloader
        monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"too small"  # < 1000 bytes

        with patch("utils.downloader.httpx.get", return_value=mock_resp), pytest.raises(RuntimeError, match="视频下载失败"):
            downloader.download_video("https://example.com/clip.mp4")
