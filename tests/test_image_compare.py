"""Tests for core/image_compare.py — utility functions, path parsing, format helpers."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.image_compare import (
    IMAGE_OUT,
    _check_images,
    _check_pillow,
    _fmt_size,
    _parse_paths,
    _safe_output_path,
    compare_images_dispatch,
)


class TestCheckPillow:
    def test_returns_none_when_available(self):
        assert _check_pillow() is None



class TestCheckImages:
    def test_requires_at_least_2(self, tmp_path):
        f1 = tmp_path / "a.png"
        f1.write_text("fake")
        err = _check_images([str(f1)])
        assert err is not None
        assert "至少需要" in err

    def test_max_4_images(self):
        err = _check_images(["a.png", "b.png", "c.png", "d.png", "e.png"])
        assert err is not None
        assert "最多" in err

    def test_missing_file(self):
        err = _check_images(["/nonexistent/a.png", "/nonexistent/b.png"])
        assert err is not None
        assert "不存在" in err

    def test_valid_paths(self, tmp_path):
        f1 = tmp_path / "a.png"; f1.write_text("fake")
        f2 = tmp_path / "b.png"; f2.write_text("fake")
        err = _check_images([str(f1), str(f2)])
        assert err is None

    def test_empty_paths(self):
        err = _check_images([])
        assert err is not None


class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(500) == "500B"

    def test_kb(self):
        assert "KB" in _fmt_size(2048)

    def test_mb(self):
        assert "MB" in _fmt_size(5 * 1024 * 1024)


class TestParsePaths:
    def test_parses_json_array(self):
        result = _parse_paths(json.dumps(["a.png", "b.png"]))
        assert result == ["a.png", "b.png"]

    def test_parses_space_separated(self):
        result = _parse_paths("a.png b.png c.png")
        assert len(result) == 3

    def test_parses_comma_separated(self):
        result = _parse_paths("a.png, b.png")
        assert result == ["a.png", "b.png"]

    def test_accepts_list(self):
        result = _parse_paths(["a.png", "b.png"])
        assert result == ["a.png", "b.png"]


class TestSafeOutputPath:
    def test_returns_string(self):
        p = _safe_output_path("compare")
        assert isinstance(p, str)
        assert p.startswith(str(IMAGE_OUT))

    def test_uses_prefix(self):
        p = _safe_output_path("test_prefix", ".jpg")
        assert "test_prefix" in p
        assert p.endswith(".jpg")


class TestConstants:
    def test_compare_executor_map_exists(self):
        from core.image_compare import COMPARE_EXECUTOR_MAP
        assert isinstance(COMPARE_EXECUTOR_MAP, dict)

    def test_compare_tool_defs_exists(self):
        from core.image_compare import COMPARE_TOOL_DEFS
        assert isinstance(COMPARE_TOOL_DEFS, list)
