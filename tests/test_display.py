"""Tests for ui/display.py — output tracking, file opening, info display."""

from unittest.mock import patch

from ui.display import (
    _recent_outputs,
    get_recent_outputs,
    open_file,
    show_error,
    show_info,
    show_success,
    show_warning,
    track_output,
)


class TestOutputTracking:
    def setup_method(self):
        _recent_outputs.clear()

    def teardown_method(self):
        _recent_outputs.clear()

    def test_track_and_retrieve(self):
        track_output("image", {"local_path": "/tmp/img.png", "prompt": "a cat"})
        recent = get_recent_outputs()
        assert len(recent) >= 1
        assert recent[0]["type"] == "image"

    def test_track_with_url_fallback(self):
        track_output("video", {"url": "http://example.com/video.mp4"})
        recent = get_recent_outputs()
        assert recent[0]["path"] == "http://example.com/video.mp4"

    def test_no_path_not_tracked(self):
        before = len(_recent_outputs)
        track_output("image", {"prompt": "no path"})
        assert len(_recent_outputs) == before

    def test_max_limit(self):
        for i in range(60):
            track_output("image", {"local_path": f"/tmp/{i}.png"})
        recent = get_recent_outputs(100)
        assert len(recent) <= 50

    def test_limit_parameter(self):
        for i in range(10):
            track_output("image", {"local_path": f"/tmp/{i}.png"})
        assert len(get_recent_outputs(3)) == 3


class TestOpenFile:
    def test_file_not_found(self):
        with patch("os.path.exists", return_value=False):
            result = open_file("/nonexistent/file.png")
            assert result is False


class TestDisplayFunctions:
    def test_show_info_runs(self):
        show_info("test info")

    def test_show_success_runs(self):
        show_success("test")

    def test_show_warning_runs(self):
        show_warning("test")

    def test_show_error_runs(self):
        show_error("test")
