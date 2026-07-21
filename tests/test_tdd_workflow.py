"""Tests for core/tdd_workflow.py — TDD Red-Green-Refactor workflow."""

from __future__ import annotations

import json

import pytest

from core.tdd_workflow import (
    TDD_DIR,
    tdd_abort,
    tdd_cycle,
    tdd_done,
    tdd_run_tests,
    tdd_start,
    tdd_status,
)


@pytest.fixture(autouse=True)
def _clean_tdd_dir():
    """Remove any leftover TDD sessions before/after each test."""
    for f in TDD_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
    yield
    for f in TDD_DIR.glob("*.json"):
        f.unlink(missing_ok=True)


class TestTddStart:
    def test_creates_session_file(self):
        s = tdd_start("test feature")
        assert (TDD_DIR / f"{s['id']}.json").exists()
        assert s["phase"] == "red"
        assert s["completed"] is False

    def test_test_files_optional(self):
        s = tdd_start("no tests", test_files=["tests/test_x.py"])
        assert s["test_files"] == ["tests/test_x.py"]

    def test_id_truncation(self):
        long_feature = "a" * 60
        s = tdd_start(long_feature)
        assert len(s["id"]) <= 40


class TestTddRunTests:
    def test_runs_and_returns_structure(self, tmp_path):
        # Use a tiny temp test file to avoid nested-pytest deadlock
        test_file = tmp_path / "test_trivial.py"
        test_file.write_text("def test_ok(): assert True\n")
        result = tdd_run_tests(str(test_file))
        assert "passed" in result
        assert "returncode" in result

    def test_verbose_flag(self, tmp_path):
        test_file = tmp_path / "test_trivial2.py"
        test_file.write_text("def test_ok(): assert True\n")
        result = tdd_run_tests(str(test_file), verbose=True)
        assert "passed" in result


class TestTddCycle:
    def test_records_red_cycle(self):
        s = tdd_start("cycle test")
        updated = tdd_cycle(s["id"], "red", {"passed": False, "summary": "1 failed"})
        assert len(updated["cycles"]) == 1
        assert updated["cycles"][0]["phase"] == "red"
        assert updated["phase"] == "red"

    def test_green_after_red(self):
        s = tdd_start("green test")
        tdd_cycle(s["id"], "red", {"passed": False, "summary": "1 failed"})
        updated = tdd_cycle(s["id"], "green", {"passed": True, "summary": "1 passed"})
        assert updated["phase"] == "green"
        assert len(updated["cycles"]) == 2

    def test_refactor_phase(self):
        s = tdd_start("refactor test")
        tdd_cycle(s["id"], "red", {"passed": False, "summary": "1 failed"})
        tdd_cycle(s["id"], "green", {"passed": True, "summary": "1 passed"})
        updated = tdd_cycle(s["id"], "refactor", {"passed": True, "summary": "1 passed"})
        assert updated["phase"] == "refactor"
        assert len(updated["cycles"]) == 3

    def test_cycle_on_completed_session_fails(self):
        s = tdd_start("done test")
        tdd_done(s["id"])
        result = tdd_cycle(s["id"], "red", {"passed": False, "summary": "x"})
        assert "error" in result

    def test_cycle_nonexistent_session(self):
        result = tdd_cycle("no_such_id", "red", {"passed": False, "summary": "x"})
        assert "error" in result


class TestTddDone:
    def test_marks_session_completed(self):
        s = tdd_start("completion test")
        result = tdd_done(s["id"])
        assert result["done"] is True
        # File should still exist but marked completed
        data = json.loads((TDD_DIR / f"{s['id']}.json").read_text(encoding="utf-8"))
        assert data["completed"] is True
        assert "completed_at" in data

    def test_done_nonexistent_session(self):
        result = tdd_done("no_such_id")
        assert "error" in result


class TestTddAbort:
    def test_deletes_session_file(self):
        s = tdd_start("abort me")
        path = TDD_DIR / f"{s['id']}.json"
        assert path.exists()
        result = tdd_abort(s["id"])
        assert result["aborted"] is True
        assert not path.exists()

    def test_abort_nonexistent_session(self):
        result = tdd_abort("no_such_id")
        assert "error" in result


class TestTddStatus:
    def test_single_session(self):
        s = tdd_start("status test")
        info = tdd_status(s["id"])
        assert info["feature"] == "status test"
        assert info["phase"] == "red"

    def test_lists_all_sessions(self):
        tdd_start("session A")
        tdd_start("session B")
        result = tdd_status()
        assert len(result["sessions"]) == 2

    def test_nonexistent_session(self):
        result = tdd_status("no_such_id")
        assert "error" in result


class TestTddPath:
    def test_tdd_dir_is_absolute(self):
        assert TDD_DIR.is_absolute(), f"TDD_DIR must be absolute, got: {TDD_DIR}"
        assert "output" in str(TDD_DIR)
        assert "tdd" in str(TDD_DIR)


class TestMethodologyTddGate:
    """Verify that methodology_pre_check respects completed/aborted sessions."""

    def test_active_red_session_blocks_write(self):
        from core.methodology import _get_active_tdd_phase

        tdd_start("gate test")
        phase = _get_active_tdd_phase()
        assert phase == "red", f"Expected 'red', got '{phase}'"

    def test_completed_session_no_block(self):
        from core.methodology import _get_active_tdd_phase

        s = tdd_start("gate completed")
        tdd_done(s["id"])
        phase = _get_active_tdd_phase()
        assert phase == "", f"Completed session should not gate, got '{phase}'"

    def test_aborted_session_no_block(self):
        from core.methodology import _get_active_tdd_phase

        s = tdd_start("gate aborted")
        tdd_abort(s["id"])
        phase = _get_active_tdd_phase()
        assert phase == "", f"Aborted session should not gate, got '{phase}'"

    def test_pre_check_blocks_implementation_in_red(self):
        from core.methodology import methodology_pre_check

        tdd_start("block test")
        allowed, reason = methodology_pre_check("write_file", {"file_path": "core/foo.py"})
        assert allowed is False, f"Should block write_file in red phase, got: {reason}"
        assert "TDD 红灯" in reason

    def test_pre_check_allows_test_file_in_red(self):
        from core.methodology import methodology_pre_check

        tdd_start("allow test")
        allowed, reason = methodology_pre_check("write_file", {"file_path": "tests/test_x.py"})
        assert allowed is True, f"Should allow test file in red phase, got: {reason}"

    def test_pre_check_allows_after_completed(self):
        from core.methodology import methodology_pre_check

        s = tdd_start("after done")
        tdd_done(s["id"])
        allowed, reason = methodology_pre_check("write_file", {"file_path": "core/foo.py"})
        assert allowed is True, f"Should allow after done, got: {reason}"
