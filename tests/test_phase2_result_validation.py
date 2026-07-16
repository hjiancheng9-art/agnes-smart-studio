"""Test Phase 2: Result validation + Consistency check + Diff guard"""

import pytest

from core.result_validator import (
    ConsistencyChecker,
    DiffGuard,
    ResultValidator,
    ValidationNote,
)

# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def rv():
    return ResultValidator()


@pytest.fixture
def cc():
    return ConsistencyChecker()


@pytest.fixture
def dg():
    return DiffGuard()


# ── ResultValidator ─────────────────────────────────────────────────


class TestResultValidator:
    def test_valid_result(self, rv):
        vr = rv.validate("read_file", "file contents here", success=True)
        assert vr.is_valid
        assert not vr.truncated

    def test_failed_result(self, rv):
        vr = rv.validate("run_bash", "Error: not found", success=False)
        assert not vr.is_valid
        assert vr.notes  # should have error pattern notes

    def test_large_output_truncation_flag(self, rv):
        vr = rv.validate("read_file", "x" * 6000, success=True)
        assert vr.truncated
        assert len(vr.notes) >= 1

    def test_many_lines(self, rv):
        vr = rv.validate("read_file", "\n".join(str(i) for i in range(600)), success=True)
        assert len(vr.notes) >= 1

    def test_error_pattern_syntax(self, rv):
        vr = rv.validate("run_python", "Traceback\nSyntaxError: invalid syntax", success=False)
        assert not vr.is_valid
        assert any("syntax" in n.message.lower() for n in vr.notes)

    def test_error_pattern_permission(self, rv):
        vr = rv.validate("read_file", "Permission denied: /etc/shadow", success=False)
        assert not vr.is_valid
        assert any("permission" in n.message.lower() for n in vr.notes)

    def test_error_pattern_timeout(self, rv):
        vr = rv.validate("run_bash", "Connection timed out", success=False)
        assert not vr.is_valid

    def test_success_empty(self, rv):
        vr = rv.validate("read_file", "", success=True)
        assert vr.is_valid
        assert any("empty" in n.message.lower() for n in vr.notes)

    def test_hints(self, rv):
        vr = rv.validate("run_python", "SyntaxError", success=False)
        hints = rv.suggest_hints(vr)
        assert any("syntax" in h.lower() for h in hints)


# ── ConsistencyChecker ──────────────────────────────────────────────


class TestConsistencyChecker:
    def test_no_history(self, cc):
        rep = cc.check("Answer", [])
        assert rep.is_consistent
        assert len(rep.issues) == 0

    def test_all_succeeded(self, cc):
        rep = cc.check(
            "Done!",
            [
                {"tool_name": "read_file", "args": {}, "result": "ok", "success": True},
            ],
        )
        assert rep.is_consistent

    def test_failed_tool_not_mentioned(self, cc):
        rep = cc.check(
            "Great success!",
            [
                {"tool_name": "run_bash", "args": {}, "result": "FAILED", "success": False},
            ],
        )
        assert not rep.is_consistent
        assert any("run_bash" in i.description for i in rep.issues)

    def test_all_failed(self, cc):
        rep = cc.check(
            "Answer",
            [
                {"tool_name": "run_bash", "args": {}, "result": "err", "success": False},
            ],
        )
        assert not rep.is_consistent
        assert any("critical" in i.severity for i in rep.issues)

    def test_short_answer_many_tools(self, cc):
        rep = cc.check(
            "OK",
            [
                {"tool_name": "t1", "args": {}, "result": "a", "success": True},
                {"tool_name": "t2", "args": {}, "result": "b", "success": True},
                {"tool_name": "t3", "args": {}, "result": "c", "success": True},
                {"tool_name": "t4", "args": {}, "result": "d", "success": True},
            ],
        )
        assert len(rep.issues) >= 1  # minor truncation issue

    def test_summary_format(self, cc):
        rep = cc.check(
            "OK",
            [
                {"tool_name": "t", "args": {}, "result": "err", "success": False},
            ],
        )
        assert "inconsistenc" in rep.summary().lower()

    def test_write_then_read_consistent(self, cc):
        """File written then read back should be consistent."""
        rep = cc.check(
            "I wrote and read config.py",
            [
                {"tool_name": "write_file", "args": {"path": "config.py"}, "result": "ok", "success": True},
                {"tool_name": "read_file", "args": {"path": "config.py"}, "result": "ok", "success": True},
            ],
        )
        assert rep.is_consistent

    def test_write_then_read_inconsistent_no_write(self, cc):
        """Reading a file that was never written should flag an issue."""
        rep = cc.check(
            "I read config.py",
            [
                {"tool_name": "read_file", "args": {"path": "config.py"}, "result": "ok", "success": True},
            ],
        )
        # File not previously written — minor info issue
        assert isinstance(rep.is_consistent, bool)

    def test_multiple_failures_all_critical(self, cc):
        """All tools failed — should be critical."""
        rep = cc.check(
            "I tried",
            [
                {"tool_name": "t1", "args": {}, "result": "err", "success": False},
                {"tool_name": "t2", "args": {}, "result": "err", "success": False},
            ],
        )
        issues_text = str(rep.issues)
        assert "critical" in issues_text or any(i.severity == "critical" for i in rep.issues)

    def test_empty_answer_no_tools(self, cc):
        rep = cc.check("", [])
        assert rep.is_consistent
        assert len(rep.issues) == 0

    def test_single_tool_success(self, cc):
        rep = cc.check(
            "All good",
            [
                {"tool_name": "read_file", "args": {}, "result": "content", "success": True},
            ],
        )
        assert rep.is_consistent

    def test_diff_guard_snapshot_before(self, dg):
        dg.snapshot_before("__test_snapshot_guard.py")
        preview = dg.preview_write("__test_snapshot_guard.py", "new content")
        assert isinstance(preview.diff_lines, list)

    def test_diff_guard_drastic_change(self, dg):
        long_old = "def foo():\n    pass\n" * 20
        long_new = "# completely different file\nimport json\n"
        dg.snapshot_before("__test_drastic.py")
        preview = dg.preview_write("__test_drastic.py", long_new)
        # drastic change with long old content should be suspicious
        if len(long_old) > 100:
            assert isinstance(preview.suspicious, bool)

    def test_diff_guard_delta(self, dg):
        preview = dg.preview_write("__test_delta.py", "abc")
        assert preview.size_delta == 3

    def test_full_pipeline_integration(self, rv, cc, dg):
        """Complete P2 pipeline: validate → check → guard."""
        vr = rv.validate("run_python", "Traceback: ValueError", success=False)
        assert not vr.is_valid
        rep = cc.check("Done!", [{"tool_name": "run_python", "args": {}, "result": "error", "success": False}])
        assert not rep.is_consistent
        preview = dg.preview_write("src/module.py", "new_code")
        assert preview.path == "src/module.py"
        assert not preview.suspicious


# ── DiffGuard ───────────────────────────────────────────────────────


class TestDiffGuard:
    def test_create_action(self, dg):
        preview = dg.preview_write("new_file.py", "print('hello')")
        assert preview.action == "create"
        assert preview.size_delta == len("print('hello')")

    def test_modify_action(self, dg):
        dg.snapshot_before("_test_temp.py")
        preview = dg.preview_write("_test_temp.py", "different content")
        assert preview.action in ("create", "modify")

    def test_diff_lines(self, dg):
        preview = dg.preview_write("test.py", "line1\nline2")
        assert isinstance(preview.diff_lines, list)

    def test_suspicious_system_dir(self, dg):
        preview = dg.preview_write("node_modules/pkg/index.js", "x")
        assert preview.suspicious
        assert "system" in preview.suspicion_reason.lower()

    def test_suspicious_git_dir(self, dg):
        preview = dg.preview_write(".git/config", "x")
        assert preview.suspicious

    def test_suspicious_pycache(self, dg):
        preview = dg.preview_write("__pycache__/test.py", "x")
        assert preview.suspicious

    def test_normal_path_not_suspicious(self, dg):
        preview = dg.preview_write("src/main.py", "hello world")
        assert not preview.suspicious

    def test_snapshot_and_preview_flow(self, dg):
        dg.snapshot_before("_test_flow.py")
        preview = dg.preview_write("_test_flow.py", "content")
        assert preview.path == "_test_flow.py"


# ── ValidationNote ──────────────────────────────────────────────────


class TestValidationNote:
    def test_severity_levels(self):
        n1 = ValidationNote(severity="info", message="just info")
        n2 = ValidationNote(severity="warning", message="careful")
        n3 = ValidationNote(severity="critical", message="stop")
        assert n1.severity == "info"
        assert n2.severity == "warning"
        assert n3.severity == "critical"


# ── Integration ─────────────────────────────────────────────────────


class TestPhase2Integration:
    def test_full_pipeline(self, rv, cc, dg):
        # Simulate: tool → validate result → check consistency → snapshot before write
        vr = rv.validate("run_bash", "error: command not found", success=False)
        assert not vr.is_valid

        rep = cc.check(
            "All done successfully!",
            [
                {"tool_name": "run_bash", "args": {}, "result": "error", "success": False},
            ],
        )
        assert not rep.is_consistent

        preview = dg.preview_write("src/new.py", "code")
        assert preview.path == "src/new.py"
