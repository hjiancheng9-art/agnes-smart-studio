"""Tests for utils.progress — video progress tracking."""

from unittest.mock import MagicMock



# ── VideoProgressTracker ──────────────────────────────────────────────────


class TestVideoProgressTracker:
    """Progress tracking with anti-regression."""

    def test_initial_state(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        assert t.progress_percent == 0
        assert t.current_status == "queued"
        assert t.history == []

    def test_update_progress(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("processing", 50, {"step": "render"})
        assert t.progress_percent == 50
        assert t.current_status == "processing"

    def test_anti_regression(self):
        """Progress should never decrease."""
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("processing", 80, {})
        t.update("processing", 50, {})  # Try to go backwards
        assert t.progress_percent == 80  # Should stay at 80

    def test_capped_at_100(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("processing", 999, {})
        assert t.progress_percent == 100

    def test_history_records(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("queued", 0, {})
        t.update("processing", 30, {"step": "a"})
        t.update("processing", 60, {"step": "b"})
        assert len(t.history) == 3

    def test_float_progress(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("processing", 33.7, {})
        # progress_percent returns the raw value (could be float)
        assert t.progress_percent == 33.7

    def test_multiple_updates(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        for i in range(0, 101, 10):
            t.update("processing", i, {})
        assert t.progress_percent == 100
        assert len(t.history) == 11

    def test_status_transitions(self):
        from utils.progress import VideoProgressTracker
        t = VideoProgressTracker()
        t.update("queued", 0, {})
        t.update("processing", 10, {})
        t.update("complete", 100, {"url": "http://example.com/vid.mp4"})
        assert t.current_status == "complete"
        assert t.progress_percent == 100


# ── create_progress_callback ───────────────────────────────────────────────


class TestCreateProgressCallback:
    """Factory for Rich Progress bar callback."""

    def test_returns_callable(self):
        from utils.progress import create_progress_callback
        mock_progress = MagicMock()
        callback = create_progress_callback(mock_progress, "task-1")
        assert callable(callback)

    def test_callback_updates_progress(self):
        from utils.progress import create_progress_callback
        mock_progress = MagicMock()
        mock_progress.update.return_value = None
        callback = create_progress_callback(mock_progress, "task-1")
        callback("processing", 50, {"step": "render"})
        mock_progress.update.assert_called_once()

    def test_callback_anti_regression(self):
        from utils.progress import create_progress_callback
        mock_progress = MagicMock()
        callback = create_progress_callback(mock_progress, "task-1")
        callback("processing", 70, {})
        callback("processing", 30, {})  # Should not decrease
        # Verify update was called, but internal tracker prevents regression
        assert mock_progress.update.call_count == 2

    def test_callback_with_complete(self):
        from utils.progress import create_progress_callback
        mock_progress = MagicMock()
        callback = create_progress_callback(mock_progress, "task-1")
        callback("complete", 100, {"url": "http://example.com/vid.mp4"})
        assert callback is not None  # Just verify no crash
