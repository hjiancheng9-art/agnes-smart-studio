"""Tests for core/browser_tools.py — task management, provider configs, constants."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.browser_tools import (
    PROVIDER_CONFIGS,
    SESSION_DIR,
    TASK_FILE,
    _find_task,
    _load_tasks,
    _save_tasks,
    _update_task,
    reset_browser_tools,
)


class TestProviderConfigs:
    def test_is_dict(self):
        assert isinstance(PROVIDER_CONFIGS, dict)

    def test_has_key_providers(self):
        # Should have at minimum kling, jimeng, runway, luma, dalle, gemini
        assert len(PROVIDER_CONFIGS) >= 4


class TestTaskManagement:
    def test_load_empty_returns_empty(self):
        with patch("core.browser_tools.TASK_FILE", Path("/nonexistent/tasks.json")):
            tasks = _load_tasks()
            assert tasks == []

    def test_save_and_load(self, tmp_path):
        fake_task_file = tmp_path / "tasks.json"
        with patch("core.browser_tools.TASK_FILE", fake_task_file):
            tasks = [{"task_id": "task1", "status": "pending"}]
            _save_tasks(tasks)
            loaded = _load_tasks()
            assert len(loaded) == 1
            assert loaded[0]["task_id"] == "task1"

    def test_find_existing_task(self):
        tasks = [{"task_id": "abc", "status": "done"}, {"task_id": "xyz", "status": "running"}]
        with patch("core.browser_tools._load_tasks", return_value=tasks):
            found = _find_task("abc")
            assert found is not None
            assert found["status"] == "done"

    def test_find_nonexistent_task(self):
        with patch("core.browser_tools._load_tasks", return_value=[{"task_id": "a"}]):
            found = _find_task("nonexistent")
            assert found is None

    def test_update_existing_task(self):
        tasks = [{"task_id": "task1", "status": "pending"}]
        with patch("core.browser_tools._load_tasks", return_value=tasks), \
             patch("core.browser_tools._save_tasks") as mock_save:
            _update_task("task1", {"status": "completed"})
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][0]
            assert saved[0]["status"] == "completed"

    def test_update_nonexistent_task_noop(self):
        with patch("core.browser_tools._load_tasks", return_value=[]), \
             patch("core.browser_tools._save_tasks") as mock_save:
            _update_task("nonexistent", {"status": "x"})
            mock_save.assert_not_called()

    def test_reset_browser_tools(self):
        # Should not raise
        reset_browser_tools()


class TestConstants:
    def test_session_dir_exists(self):
        assert SESSION_DIR.exists()
