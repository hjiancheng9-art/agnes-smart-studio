"""Smoke tests for core/video_editor.py — ffmpeg video editor wrappers.

Tests cover:
- Module imports and __all__ exports
- Helper functions (_run, _safe_output_path, _check_ffmpeg)
- Error/validation paths of all 5 executors (no real ffmpeg needed)
- Tool definitions (VIDEO_EDITOR_TOOL_DEFS) structure
- Executor map (VIDEO_EDITOR_EXECUTOR_MAP) completeness
"""

import json
from unittest.mock import patch

import pytest

from core.video_editor import (
    OUTPUT_ROOT,
    VIDEO_EDITOR_EXECUTOR_MAP,
    VIDEO_EDITOR_TOOL_DEFS,
    VIDEO_OUT,
    _check_ffmpeg,
    _run,
    _safe_output_path,
    execute_composite_overlay,
    execute_render_final,
    execute_video_concat,
    execute_video_speed,
    execute_video_trim,
)


class TestModuleStructure:
    def test_video_out_dir_exists(self):
        assert VIDEO_OUT.exists()

    def test_output_root_is_parent_of_videos(self):
        assert VIDEO_OUT.parent == OUTPUT_ROOT

    def test_tool_defs_count(self):
        assert len(VIDEO_EDITOR_TOOL_DEFS) == 5

    def test_tool_def_names(self):
        names = {t["function"]["name"] for t in VIDEO_EDITOR_TOOL_DEFS}
        assert names == {"video_concat", "video_trim", "composite_overlay", "video_speed", "render_final"}

    def test_executor_map_keys_match_tool_defs(self):
        def_names = {t["function"]["name"] for t in VIDEO_EDITOR_TOOL_DEFS}
        assert set(VIDEO_EDITOR_EXECUTOR_MAP.keys()) == def_names

    def test_executor_map_values_callable(self):
        for name, fn in VIDEO_EDITOR_EXECUTOR_MAP.items():
            assert callable(fn), f"{name} executor is not callable"


class TestRunHelper:
    def test_run_returns_completed_process(self):
        result = _run(["python", "--version"], timeout=10)
        assert result.returncode == 0

    def test_run_captures_stdout(self):
        result = _run(["echo", "hello"], timeout=10)
        assert "hello" in result.stdout

    @patch("core.video_editor._run", side_effect=FileNotFoundError)
    def test_check_ffmpeg_not_found(self, mock_run):
        result = _check_ffmpeg()
        assert result is not None
        assert "ffmpeg" in result


class TestSafeOutputPath:
    def test_returns_string(self):
        path = _safe_output_path("test_smoke")
        assert isinstance(path, str)

    def test_ends_with_mp4(self):
        path = _safe_output_path("test_smoke")
        assert path.endswith(".mp4")

    def test_custom_extension(self):
        path = _safe_output_path("test_smoke", ext=".mkv")
        assert path.endswith(".mkv")

    def test_contains_prefix(self):
        path = _safe_output_path("my_prefix")
        assert "my_prefix" in path


class TestVideoConcat:
    @patch("core.video_editor._check_ffmpeg", return_value="ffmpeg not available")
    def test_concat_no_ffmpeg(self, mock_ff):
        result = json.loads(execute_video_concat('["a.mp4","b.mp4"]'))
        assert result["success"] is False
        assert "ffmpeg" in result["error"]

    def test_concat_invalid_json(self):
        result = json.loads(execute_video_concat("not json"))
        assert result["success"] is False
        assert "JSON" in result["error"]

    def test_concat_single_video(self):
        result = json.loads(execute_video_concat('["one.mp4"]'))
        assert result["success"] is False
        assert "2" in result["error"]

    def test_concat_missing_files(self):
        result = json.loads(execute_video_concat('["no_such_1.mp4","no_such_2.mp4"]'))
        assert result["success"] is False
        assert "\u4e0d\u5b58\u5728" in result["error"]

    def test_concat_empty_array(self):
        result = json.loads(execute_video_concat("[]"))
        assert result["success"] is False


class TestVideoTrim:
    @patch("core.video_editor._check_ffmpeg", return_value="no ffmpeg")
    def test_trim_no_ffmpeg(self, mock_ff):
        result = json.loads(execute_video_trim("video.mp4"))
        assert result["success"] is False

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_trim_file_not_exists(self, mock_ff):
        result = json.loads(execute_video_trim("nonexistent.mp4"))
        assert result["success"] is False
        assert "\u4e0d\u5b58\u5728" in result["error"]


class TestCompositeOverlay:
    @patch("core.video_editor._check_ffmpeg", return_value="no ffmpeg")
    def test_overlay_no_ffmpeg(self, mock_ff):
        result = json.loads(execute_composite_overlay("video.mp4", "subtitle"))
        assert result["success"] is False

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_overlay_file_not_exists(self, mock_ff):
        result = json.loads(execute_composite_overlay("no.mp4", "subtitle"))
        assert result["success"] is False
        assert "\u4e0d\u5b58\u5728" in result["error"]

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_overlay_unsupported_type(self, mock_ff, tmp_path):
        v = tmp_path / "v.mp4"
        v.write_bytes(b"\x00" * 100)
        result = json.loads(execute_composite_overlay(str(v), "invalid_type"))
        assert result["success"] is False
        assert "\u4e0d\u652f\u6301\u7684\u53e0\u52a0\u7c7b\u578b" in result["error"]

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_overlay_watermark_missing_image(self, mock_ff, tmp_path):
        v = tmp_path / "v.mp4"
        v.write_bytes(b"\x00" * 100)
        result = json.loads(execute_composite_overlay(str(v), "watermark", image_path="no_img.png"))
        assert result["success"] is False
        assert "\u53e0\u52a0\u56fe\u7247\u4e0d\u5b58\u5728" in result["error"]


class TestVideoSpeed:
    @patch("core.video_editor._check_ffmpeg", return_value="no ffmpeg")
    def test_speed_no_ffmpeg(self, mock_ff):
        result = json.loads(execute_video_speed("video.mp4", 2.0))
        assert result["success"] is False

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_speed_file_not_exists(self, mock_ff):
        result = json.loads(execute_video_speed("no.mp4", 2.0))
        assert result["success"] is False
        assert "\u4e0d\u5b58\u5728" in result["error"]

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_speed_zero_invalid(self, mock_ff, tmp_path):
        v = tmp_path / "v.mp4"
        v.write_bytes(b"\x00" * 100)
        result = json.loads(execute_video_speed(str(v), 0))
        assert result["success"] is False
        assert "\u5927\u4e8e 0" in result["error"]

    @patch("core.video_editor._check_ffmpeg", return_value=None)
    def test_speed_negative_invalid(self, mock_ff, tmp_path):
        v = tmp_path / "v.mp4"
        v.write_bytes(b"\x00" * 100)
        result = json.loads(execute_video_speed(str(v), -1.5))
        assert result["success"] is False


class TestRenderFinal:
    @patch("core.video_editor._check_ffmpeg", return_value="no ffmpeg")
    def test_render_no_ffmpeg(self, mock_ff):
        result = json.loads(execute_render_final('[]'))
        assert result["success"] is False

    def test_render_invalid_json(self):
        result = json.loads(execute_render_final("not json"))
        assert result["success"] is False
        assert "JSON" in result["error"]

    def test_render_empty_segments(self):
        result = json.loads(execute_render_final("[]"))
        assert result["success"] is False
        assert "\u4e0d\u80fd\u4e3a\u7a7a" in result["error"]

    def test_render_missing_segment_files(self):
        segs = json.dumps([{"path": "no_such.mp4", "duration": 5.0}])
        result = json.loads(execute_render_final(segs))
        assert result["success"] is False
        assert "\u7247\u6bb5\u6587\u4ef6\u4e0d\u5b58\u5728" in result["error"]

    def test_render_segment_missing_path_key(self):
        segs = json.dumps([{"duration": 5.0}])
        result = json.loads(execute_render_final(segs))
        assert result["success"] is False


class TestExecutorMapIntegration:
    def test_concat_executor_calls(self):
        result = json.loads(VIDEO_EDITOR_EXECUTOR_MAP["video_concat"](video_paths="not json"))
        assert result["success"] is False

    def test_trim_executor_calls(self):
        result = json.loads(
            VIDEO_EDITOR_EXECUTOR_MAP["video_trim"](video_path="no.mp4", start_seconds=0, end_seconds=-1)
        )
        assert result["success"] is False

    def test_speed_executor_calls(self):
        result = json.loads(VIDEO_EDITOR_EXECUTOR_MAP["video_speed"](video_path="no.mp4", speed=2.0))
        assert result["success"] is False

    def test_overlay_executor_calls(self):
        result = json.loads(
            VIDEO_EDITOR_EXECUTOR_MAP["composite_overlay"](
                video_path="no.mp4", overlay_type="subtitle", overlay_text="hello"
            )
        )
        assert result["success"] is False

    def test_render_executor_calls(self):
        result = json.loads(VIDEO_EDITOR_EXECUTOR_MAP["render_final"](video_segments="[]"))
        assert result["success"] is False
