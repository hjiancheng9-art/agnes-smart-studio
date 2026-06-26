"""Tests for utils.templates, utils.progress, utils.image_input."""

import base64
from unittest.mock import MagicMock

import pytest

# ── utils.templates ──────────────────────────────────────────────────────


class TestTemplates:
    """Prompt template library."""

    def test_list_templates_returns_list(self):
        from utils.templates import list_templates

        templates = list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_get_template_exists(self):
        from utils.templates import get_template, list_templates

        names = list_templates()
        # Pick first template that exists
        tpl = get_template(names[0])
        assert isinstance(tpl, dict)

    def test_get_template_nonexistent(self):
        from utils.templates import get_template

        assert get_template("nonexistent_xyz") is None

    def test_apply_template_enhances_prompt(self):
        from utils.templates import apply_template, list_templates

        names = list_templates()
        enhanced, negative = apply_template(names[0], "a cat")
        assert isinstance(enhanced, str)
        assert isinstance(negative, str)
        assert "a cat" in enhanced

    def test_apply_template_nonexistent_returns_original(self):
        from utils.templates import apply_template

        enhanced, negative = apply_template("nonexistent_xyz", "my prompt")
        assert enhanced == "my prompt"
        assert negative == ""

    def test_get_template_info_string(self):
        from utils.templates import get_template_info, list_templates

        names = list_templates()
        info = get_template_info(names[0])
        assert isinstance(info, str)
        assert len(info) > 0

    def test_get_template_info_nonexistent(self):
        from utils.templates import get_template_info

        info = get_template_info("nonexistent_xyz")
        assert "未找到" in info


# ── utils.progress ───────────────────────────────────────────────────────


class TestVideoProgressTracker:
    """Progress tracking with anti-regression."""

    def test_create_tracker(self):
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        assert tracker.last_known_progress == 0
        assert tracker.current_status == "queued"
        assert tracker.history == []

    def test_update_progress(self):
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        tracker.update("processing", 50, {})
        assert tracker.last_known_progress == 50
        assert tracker.current_status == "processing"
        assert len(tracker.history) == 1
        assert tracker.history[0]["progress"] == 50

    def test_anti_regression(self):
        """Progress should never go backwards."""
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        tracker.update("processing", 80, {})
        tracker.update("queued", 10, {})  # API regressed
        assert tracker.last_known_progress == 80  # kept high
        assert tracker.progress_percent == 80

    def test_progress_percent_capped_at_100(self):
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        tracker.update("done", 150, {})
        assert tracker.progress_percent == 100

    def test_history_records_raw_progress(self):
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        tracker.update("processing", 80, {})
        tracker.update("queued", 10, {})
        assert tracker.history[1]["raw_progress"] == 10
        assert tracker.history[1]["progress"] == 80  # effective

    def test_non_numeric_progress_treated_as_zero(self):
        from utils.progress import VideoProgressTracker

        tracker = VideoProgressTracker()
        tracker.update("weird", "not-a-number", {})  # type: ignore[arg-type]  # tests non-numeric resilience
        assert tracker.last_known_progress == 0


class TestCreateProgressCallback:
    """Factory function for progress callbacks."""

    def test_callback_updates_progress(self):
        from utils.progress import create_progress_callback

        progress = MagicMock()
        task_id = 1
        cb = create_progress_callback(progress, task_id)
        cb("processing", 50, {})
        progress.update.assert_called_once()
        args = progress.update.call_args
        assert args[0] == (task_id,)
        assert args[1]["completed"] == 50

    def test_callback_anti_regression_on_zero(self):
        """When API returns progress=0 (simplified response), keep last known."""
        from utils.progress import create_progress_callback

        progress = MagicMock()
        cb = create_progress_callback(progress, 0)
        cb("processing", 80, {})
        cb("queued", 0, {})  # API returned 0 (simplified)
        # Second call should use last known (80), not 0
        second_call = progress.update.call_args_list[1]
        assert second_call[1]["completed"] == 80


# ── utils.image_input ────────────────────────────────────────────────────


class TestImageInput:
    """Image input normalization (URL/file/base64)."""

    def test_url_passthrough(self):
        from utils.image_input import load_image_as_url_or_data

        url = "https://example.com/image.png"
        assert load_image_as_url_or_data(url) == url

    def test_http_url_passthrough(self):
        from utils.image_input import load_image_as_url_or_data

        url = "http://example.com/image.jpg"
        assert load_image_as_url_or_data(url) == url

    def test_data_uri_passthrough(self):
        from utils.image_input import load_image_as_url_or_data

        uri = "data:image/png;base64,iVBORw0KGgo="
        assert load_image_as_url_or_data(uri) == uri

    def test_invalid_input_raises(self):
        from utils.image_input import load_image_as_url_or_data

        with pytest.raises(ValueError):
            load_image_as_url_or_data("not-a-url-or-file-or-base64!!!")

    def test_strips_quotes(self):
        from utils.image_input import load_image_as_url_or_data

        url = '"https://example.com/img.png"'
        result = load_image_as_url_or_data(url)
        assert result == "https://example.com/img.png"

    def test_file_to_data_uri(self, tmp_path):
        from utils.image_input import file_to_data_uri

        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        uri = file_to_data_uri(img_file)
        assert uri.startswith("data:image/png;base64,")
        # Verify it's valid base64
        b64_part = uri.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded.startswith(b"\x89PNG")

    def test_file_to_data_uri_jpeg(self, tmp_path):
        from utils.image_input import file_to_data_uri

        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        uri = file_to_data_uri(img_file)
        assert uri.startswith("data:image/jpeg;base64,")
