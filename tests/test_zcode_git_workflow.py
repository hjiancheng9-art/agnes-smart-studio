"""RED phase tests for core/git_workflow.py.

Tests: GitWorkflow class, key methods, convenience functions.
"""

from unittest import mock

# ---------------------------------------------------------------------------
# GitWorkflow construction
# ---------------------------------------------------------------------------


class TestGitWorkflowConstruction:
    """GitWorkflow initialization."""

    def test_default_root(self):
        from core.git_workflow import ROOT, GitWorkflow
        gw = GitWorkflow()
        assert gw.root == ROOT

    def test_custom_root(self, tmp_path):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow(root=tmp_path)
        assert gw.root == tmp_path

    def test_methods_exist(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        assert callable(gw.status)
        assert callable(gw.diff)
        assert callable(gw.stage_all)
        assert callable(gw.commit)
        assert callable(gw.create_branch)
        assert callable(gw.current_branch)
        assert callable(gw.log)
        assert callable(gw.safe_autocommit)
        assert callable(gw.snapshot)
        assert callable(gw.restore_snapshot)


# ---------------------------------------------------------------------------
# GitWorkflow methods (unit-tested with mock)
# ---------------------------------------------------------------------------


class TestGitWorkflowStatus:
    """status / diff / current_branch methods."""

    def test_status_returns_string(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        result = gw.status()
        assert isinstance(result, str)

    def test_status_returns_clean_when_empty(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            assert gw.status() == "(clean)"

    def test_diff_when_empty(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            assert gw.diff() == "(no changes)"

    def test_current_branch_returns_string(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        result = gw.current_branch()
        assert isinstance(result, str)


class TestGitWorkflowStageAndCommit:
    """stage_all / commit / safe_autocommit methods."""

    def test_stage_all_returns_message(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            msg = gw.stage_all()
            assert "staged" in msg or "error" in msg or "changes" in msg

    def test_commit_returns_output(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "commit ok", "")):
            result = gw.commit("test message")
            assert result == "commit ok"

    def test_safe_autocommit_nothing_to_commit(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "status", return_value="(clean)"):
            result = gw.safe_autocommit("test message")
            assert result["committed"] is False
            assert "nothing to commit" in result["message"]


class TestGitWorkflowBranch:
    """create_branch method."""

    def test_create_branch_sanitizes_name(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            result = gw.create_branch("My Feature Branch With Spaces")
            assert "my-feature-branch-with" in result


class TestGitWorkflowLog:
    """log method."""

    def test_log_returns_string(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        result = gw.log(n=3)
        assert isinstance(result, str)

    def test_log_empty_repo_returns_message(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            assert gw.log() == "(no commits)"


class TestGitWorkflowSnapshot:
    """snapshot / restore_snapshot methods."""

    def test_snapshot_returns_string(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            result = gw.snapshot(label="test-snap")
            assert "test-snap" in result

    def test_snapshot_auto_label(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(0, "", "")):
            result = gw.snapshot()
            assert "snapshot" in result.lower()

    def test_restore_snapshot_no_label(self):
        from core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        with mock.patch.object(gw, "_run", return_value=(1, "", "nothing to pop")):
            result = gw.restore_snapshot()
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    """Module-level convenience functions."""

    def test_git_status_exists(self):
        from core.git_workflow import git_status
        assert callable(git_status)
        result = git_status()
        assert isinstance(result, str)

    def test_git_autocommit_exists(self):
        from core.git_workflow import git_autocommit
        assert callable(git_autocommit)
        with mock.patch("core.git_workflow.GitWorkflow.safe_autocommit", return_value={"committed": False, "message": "nothing"}):
            result = git_autocommit("test")
            assert isinstance(result, dict)

    def test_git_snapshot_exists(self):
        from core.git_workflow import git_snapshot
        assert callable(git_snapshot)
        with mock.patch("core.git_workflow.GitWorkflow.snapshot", return_value="snapshot 'test' saved"):
            result = git_snapshot(label="test")
            assert "test" in result
