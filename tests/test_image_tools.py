"""Tests for core/image_tools.py — utility functions, image check, format helpers."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from core.image_tools import (
    IMAGE_OUT,
    _check_image,
    _check_pillow,
    _fmt_size,
    _safe_output_path,
)


class TestCheckPillow:
    def test_returns_none_when_available(self):
        assert _check_pillow() is None



class TestCheckImage:
    def test_returns_none_for_valid_file(self, tmp_path):
        f = tmp_path / "test.png"
        f.write_text("fake")
        err = _check_image(str(f))
        assert err is None

    def test_returns_error_for_missing_file(self):
        err = _check_image("/nonexistent/img.png")
        assert err is not None
        assert "不存在" in err

    def test_returns_error_for_empty_path(self):
        err = _check_image("")
        assert err is not None


class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(500) == "500B"

    def test_kb(self):
        assert "KB" in _fmt_size(2048)

    def test_mb(self):
        assert "MB" in _fmt_size(5 * 1024 * 1024)


class TestSafeOutputPath:
    def test_returns_string(self):
        p = _safe_output_path("test")
        assert isinstance(p, str)
        assert p.startswith(str(IMAGE_OUT))

    def test_custom_extension(self):
        p = _safe_output_path("resize", ".jpg")
        assert p.endswith(".jpg")


class TestConstants:
    def test_image_executor_map_exists(self):
        from core.image_tools import IMAGE_EXECUTOR_MAP
        assert isinstance(IMAGE_EXECUTOR_MAP, dict)

    def test_image_tool_defs_exists(self):
        from core.image_tools import IMAGE_TOOL_DEFS
        assert isinstance(IMAGE_TOOL_DEFS, list)

    def test_output_dir_exists(self):
        assert IMAGE_OUT.exists()
