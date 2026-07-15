"""Tests for core/tool_interceptor.py — safety interceptors + methodology gates."""

import pytest
from core.tool_interceptor import intercept_tool


class TestDangerousCommands:
    def test_rm_rf_root_blocked(self):
        ok, reason = intercept_tool("run_bash", {"command": "rm -rf /"})
        assert not ok
        assert "rm -rf" in reason.lower()

    def test_force_push_main_blocked(self):
        ok, reason = intercept_tool("run_bash", {"command": "git push --force origin main"})
        assert not ok

    def test_chmod_777_root_blocked(self):
        ok, reason = intercept_tool("run_bash", {"command": "chmod 777 /etc"})
        assert not ok

    def test_dd_to_dev_blocked(self):
        ok, reason = intercept_tool("run_bash", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert not ok

    def test_safe_command_allowed(self):
        ok, reason = intercept_tool("run_bash", {"command": "ls -la"})
        assert ok
        ok, reason = intercept_tool("run_bash", {"command": "git status"})
        assert ok

    def test_pip_uninstall_warned(self):
        ok, reason = intercept_tool("run_bash", {"command": "pip uninstall requests"})
        assert ok
        assert "WARNING" in reason

    def test_git_reset_hard_warned(self):
        ok, reason = intercept_tool("run_bash", {"command": "git reset --hard HEAD"})
        assert ok
        assert "WARNING" in reason

    def test_empty_command_allowed(self):
        ok, reason = intercept_tool("run_bash", {})
        assert ok

    def test_non_bash_tool_passes(self):
        ok, reason = intercept_tool("read_file", {"path": "test.py"})
        assert ok


class TestProtectedFiles:
    def test_env_file_blocked(self):
        ok, reason = intercept_tool("write_file", {"file_path": ".env"})
        assert not ok

    def test_env_production_blocked(self):
        ok, reason = intercept_tool("write_file", {"file_path": ".env.production"})
        assert not ok

    def test_credentials_blocked(self):
        ok, reason = intercept_tool("write_file", {"file_path": "credentials.json"})
        assert not ok

    def test_pem_blocked(self):
        ok, reason = intercept_tool("write_file", {"file_path": "key.pem"})
        assert not ok

    def test_id_rsa_blocked(self):
        ok, reason = intercept_tool("write_file", {"file_path": "id_rsa"})
        assert not ok

    def test_normal_py_allowed(self):
        ok, reason = intercept_tool("write_file", {"file_path": "test.py"})
        assert ok

    def test_edit_file_also_protected(self):
        ok, reason = intercept_tool("edit_file", {"file_path": ".env"})
        assert not ok

    def test_patch_file_also_protected(self):
        ok, reason = intercept_tool("patch_file", {"file_path": ".env"})
        assert not ok


class TestMethodologyGating:
    def test_protected_core_file_blocked(self):
        """core/methodology.py is the only hard-protected file."""
        from core.methodology import methodology_pre_check
        ok, reason = methodology_pre_check("write_file", {"path": "core/methodology.py"}, None)
        assert not ok

    def test_pip_install_blocked(self):
        from core.methodology import methodology_pre_check
        ok, reason = methodology_pre_check("pip_install", {"package": "requests"}, None)
        assert not ok

    def test_normal_write_allowed(self, monkeypatch):
        import core.methodology as m
        monkeypatch.setattr(m, "_get_active_tdd_phase", lambda: "")
        ok, reason = m.methodology_pre_check("write_file", {"path": "my_module.py"}, None)
        assert ok

    def test_c_level_blocks_write_without_plan(self, monkeypatch):
        import core.methodology as m
        monkeypatch.setattr(m, "_get_active_tdd_phase", lambda: "")
        state = m.MethodologyState()
        state.task_level = m.TaskLevel.C
        state.plan_exists = False
        ok, reason = m.methodology_pre_check("write_file", {"path": "impl.py"}, state)
        assert not ok
        assert "Plan" in reason

    def test_c_level_allows_write_with_plan(self, monkeypatch):
        import core.methodology as m
        monkeypatch.setattr(m, "_get_active_tdd_phase", lambda: "")
        state = m.MethodologyState()
        state.task_level = m.TaskLevel.C
        state.plan_exists = True
        ok, reason = m.methodology_pre_check("write_file", {"path": "impl.py"}, state)
        assert ok

    def test_d_level_requires_worktree(self):
        from core.methodology import MethodologyState, TaskLevel, methodology_pre_check
        state = MethodologyState()
        state.task_level = TaskLevel.D
        state.plan_exists = True
        state.test_baseline_recorded = True
        state.worktree_created = False
        ok, reason = methodology_pre_check("git_add_commit", {}, state)
        assert not ok
        assert "Worktree" in reason

    def test_d_level_allows_when_all_gates_pass(self):
        from core.methodology import MethodologyState, TaskLevel, methodology_pre_check
        state = MethodologyState()
        state.task_level = TaskLevel.D
        state.plan_exists = True
        state.test_baseline_recorded = True
        state.worktree_created = True
        ok, reason = methodology_pre_check("git_add_commit", {}, state)
        assert ok

    def test_tdd_red_blocks_impl_write(self):
        import json, os, tempfile
        from core.methodology import methodology_pre_check
        # Create a temp TDD session in red phase
        tdd_dir = "output/tdd"
        os.makedirs(tdd_dir, exist_ok=True)
        session_file = os.path.join(tdd_dir, "test_tdd.json")
        with open(session_file, "w") as f:
            json.dump({"phase": "red", "feature": "test"}, f)
        try:
            ok, reason = methodology_pre_check("write_file", {"file_path": "src/models.py"}, None)
            assert not ok
            assert "TDD" in reason or "红灯" in reason
        finally:
            os.remove(session_file)
            try:
                os.rmdir(tdd_dir)
            except OSError:
                pass

    def test_tdd_red_allows_test_write(self):
        import json, os
        from core.methodology import methodology_pre_check
        tdd_dir = "output/tdd"
        os.makedirs(tdd_dir, exist_ok=True)
        session_file = os.path.join(tdd_dir, "test_tdd.json")
        with open(session_file, "w") as f:
            json.dump({"phase": "red", "feature": "test"}, f)
        try:
            ok, reason = methodology_pre_check("write_file", {"file_path": "tests/test_models.py"}, None)
            assert ok  # test files are allowed in red phase
        finally:
            os.remove(session_file)
            try:
                os.rmdir(tdd_dir)
            except OSError:
                pass
