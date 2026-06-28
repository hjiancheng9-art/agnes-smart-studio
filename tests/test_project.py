"""Tests for core/project.py — Project management, sessions, history, teams, deploy."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.project import (
    PROJECTS_DIR,
    TEAM_CONFIGS,
    Project,
    deploy_to_github_pages,
    deploy_to_netlify,
    deploy_to_vercel,
    run_team,
)


@pytest.fixture
def temp_project():
    """Create a temporary project for isolated testing."""
    with tempfile.TemporaryDirectory() as td:
        p = Project(name="test-project", root_path=td)
        yield p


class TestProjectInit:
    def test_creates_dirs(self, temp_project):
        p = temp_project
        assert p.root.exists()
        assert p.sessions_path.exists()
        assert p.history_path.exists()

    def test_config_path(self, temp_project):
        p = temp_project
        assert p.config_path.name == "project.json"


class TestProjectConfig:
    def test_load_default_config(self, temp_project):
        cfg = temp_project.load_config()
        assert cfg["name"] == "test-project"
        assert "created" in cfg

    def test_save_and_reload(self, temp_project):
        cfg = temp_project.load_config()
        cfg["summary"] = "A test project"
        temp_project.save_config(cfg)
        reloaded = temp_project.load_config()
        assert reloaded["summary"] == "A test project"

    def test_last_access_updated_on_save(self, temp_project):
        cfg = temp_project.load_config()
        temp_project.save_config(cfg)
        reloaded = temp_project.load_config()
        assert reloaded["last_access"] != ""

    def test_set_summary(self, temp_project):
        temp_project.set_summary("New summary text")
        cfg = temp_project.load_config()
        assert cfg["summary"] == "New summary text"


class TestProjectSessions:
    def test_save_and_load_session(self, temp_project):
        messages = [{"role": "user", "content": "hello"}]
        temp_project.save_session("s1", messages)
        loaded = temp_project.load_session("s1")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["content"] == "hello"

    def test_load_nonexistent_session(self, temp_project):
        result = temp_project.load_session("nonexistent")
        assert result is None

    def test_list_sessions(self, temp_project):
        temp_project.save_session("s1", [{"role": "user", "content": "a"}])
        temp_project.save_session("s2", [{"role": "user", "content": "b"}])
        sessions = temp_project.list_sessions()
        assert len(sessions) >= 2

    def test_save_session_preserves_encoding(self, temp_project):
        messages = [{"role": "user", "content": "中文测试"}]
        temp_project.save_session("zh", messages)
        loaded = temp_project.load_session("zh")
        assert loaded[0]["content"] == "中文测试"


class TestFileHistory:
    def test_record_and_get_history(self, temp_project):
        temp_project.record_file_change("main.py", "modified", "changed line 3")
        history = temp_project.get_file_history()
        assert len(history) >= 1
        assert history[0]["file"] == "main.py"
        assert history[0]["kind"] == "modified"

    def test_history_limit(self, temp_project):
        for i in range(5):
            temp_project.record_file_change(f"file_{i}.py", "created")
        history = temp_project.get_file_history(limit=3)
        assert len(history) <= 3

    def test_content_preview_truncated(self, temp_project):
        long_text = "x" * 500
        temp_project.record_file_change("big.py", "modified", long_text)
        history = temp_project.get_file_history()
        assert len(history[0]["preview"]) <= 200


class TestAnalyzeCodebase:
    def test_empty_project(self, temp_project):
        stats = temp_project.analyze_codebase()
        assert isinstance(stats["files"], int)
        assert isinstance(stats["languages"], dict)
        assert isinstance(stats["total_lines"], int)

    def test_with_python_file(self, temp_project):
        (temp_project.root / "test.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")
        stats = temp_project.analyze_codebase()
        assert stats["files"] >= 1
        assert ".py" in stats["languages"]
        assert stats["total_lines"] >= 2


class TestTeamConfigs:
    def test_review_team_exists(self):
        assert "review" in TEAM_CONFIGS
        assert len(TEAM_CONFIGS["review"]["agents"]) == 3

    def test_debug_team_exists(self):
        assert "debug" in TEAM_CONFIGS
        assert len(TEAM_CONFIGS["debug"]["agents"]) == 3

    def test_feature_team_exists(self):
        assert "feature" in TEAM_CONFIGS
        assert len(TEAM_CONFIGS["feature"]["agents"]) == 3


class TestRunTeam:
    def test_unknown_team_type(self):
        result = run_team(None, "bogus", "context")
        assert "error" in result

    def test_review_team_calls_client(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "review feedback"}}]
        }
        result = run_team(mock_client, "review", "code context")
        assert result["team"] == "代码审查团队"
        assert len(result["agents"]) == 3

    def test_agent_failure_does_not_block_team(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API down")
        result = run_team(mock_client, "debug", "context")
        assert len(result["agents"]) == 3
        for agent in result["agents"]:
            assert "[失败]" in agent["output"]


class TestDeploy:
    def test_deploy_to_vercel(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Deployed to vercel", stderr="")
            result = deploy_to_vercel("/tmp/project")
            assert "Deployed" in result

    def test_deploy_to_netlify(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Deployed to netlify", stderr="")
            result = deploy_to_netlify("/tmp/project")
            assert "Deployed" in result

    def test_deploy_to_github_pages(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Published", stderr="", returncode=0)
            result = deploy_to_github_pages("/tmp/project")
            assert result  # not empty


class TestProjectsDir:
    def test_dir_exists(self):
        assert PROJECTS_DIR.exists()
