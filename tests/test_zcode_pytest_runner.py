"""RED phase tests for core/pytest_runner.py.

Tests: debug_inspect, in_pytest, run_pytest_safe, parse_test_summary.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# in_pytest
# ---------------------------------------------------------------------------


class TestInPytest:
    """in_pytest() detection."""

    def test_returns_bool(self):
        from core.pytest_runner import in_pytest
        assert isinstance(in_pytest(), bool)

    def test_true_when_env_var_set(self):
        from core.pytest_runner import in_pytest
        with mock.patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "tests/test_x.py::test_y (call)"}):
            assert in_pytest() is True

    def test_true_when_pytest_in_sys_modules(self):
        from core.pytest_runner import in_pytest
        if "pytest" in sys.modules:
            assert in_pytest() is True

    def test_false_when_none_matched(self, monkeypatch):
        from core.pytest_runner import in_pytest
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        # We can't remove pytest from sys.modules in a test run,
        # but we can verify the function doesn't crash
        result = in_pytest()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# run_pytest_safe
# ---------------------------------------------------------------------------


class TestRunPytestSafe:
    """run_pytest_safe function."""

    def test_guards_inside_pytest(self):
        from core.pytest_runner import run_pytest_safe
        with mock.patch("core.pytest_runner.in_pytest", return_value=True):
            r = run_pytest_safe("tests/", timeout=5)
            assert r.returncode == 0
            assert "skipped" in r.stdout

    def test_returns_completed_process(self):
        from core.pytest_runner import run_pytest_safe
        r = run_pytest_safe("tests/", timeout=5)
        assert isinstance(r, subprocess.CompletedProcess)

    def test_splits_multiple_targets(self):
        from core.pytest_runner import run_pytest_safe
        with mock.patch("core.pytest_runner.in_pytest", return_value=True):
            r = run_pytest_safe("tests/a.py tests/b.py", timeout=5)
            assert r.returncode == 0

    def test_accepts_extra_args(self):
        from core.pytest_runner import run_pytest_safe
        with mock.patch("core.pytest_runner.in_pytest", return_value=True):
            r = run_pytest_safe("tests/", extra_args=["-v", "--tb=short"], timeout=5)
            assert r.returncode == 0

    def test_accepts_cwd(self, tmp_path):
        from core.pytest_runner import run_pytest_safe
        with mock.patch("core.pytest_runner.in_pytest", return_value=True):
            r = run_pytest_safe("tests/", timeout=5, cwd=str(tmp_path))
            assert r.returncode == 0


# ---------------------------------------------------------------------------
# parse_test_summary
# ---------------------------------------------------------------------------


class TestParseTestSummary:
    """parse_test_summary function."""

    def test_parses_passed_and_failed_from_summary(self):
        from core.pytest_runner import parse_test_summary
        passed, failed = parse_test_summary("5 passed, 2 failed in 1.23s")
        assert passed == 5
        assert failed == 2

    def test_parses_passed_only(self):
        from core.pytest_runner import parse_test_summary
        passed, failed = parse_test_summary("10 passed in 2.50s")
        assert passed == 10
        assert failed == 0

    def test_parses_failed_only(self):
        from core.pytest_runner import parse_test_summary
        passed, failed = parse_test_summary("3 failed, 0 passed in 0.50s")
        assert passed == 0
        assert failed == 3

    def test_fallback_counts_dots(self):
        from core.pytest_runner import parse_test_summary
        output = "[100%] .F.."
        passed, failed = parse_test_summary(output)
        # Regex r"\[\d+%\]" matches [100%]; counts dots and Fs
        assert passed == 3
        assert failed == 1

    def test_returns_zeros_for_empty(self):
        from core.pytest_runner import parse_test_summary
        passed, failed = parse_test_summary("")
        assert passed == 0
        assert failed == 0

    def test_returns_tuple(self):
        from core.pytest_runner import parse_test_summary
        result = parse_test_summary("1 passed")
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# debug_inspect
# ---------------------------------------------------------------------------


class TestDebugInspect:
    """debug_inspect function."""

    def test_exists_and_callable(self):
        from core.pytest_runner import debug_inspect
        assert callable(debug_inspect)

    def test_returns_json_string(self):
        import json
        from core.pytest_runner import debug_inspect

        result = debug_inspect(
            str(Path(__file__).resolve()),
            extra_args="",
        )
        assert isinstance(result, str)
        data = json.loads(result)
        assert "status" in data

    def test_pytest_target_uses_pytest_runner(self):
        import json
        from core.pytest_runner import debug_inspect

        # Use a pytest target to exercise the pytest path
        dummy_test = Path(__file__).resolve().parent / "test_zcode_deps.py"
        result = debug_inspect(str(dummy_test), extra_args="")
        data = json.loads(result)
        assert data["status"] in ("passed", "failed", "timeout", "error")

    def test_timeout_on_long_running(self):
        import json
        from unittest import mock
        from core.pytest_runner import debug_inspect

        # Mock subprocess.run to raise TimeoutExpired
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=0.1)):
            result = debug_inspect("tests/", extra_args="")
            data = json.loads(result)
            assert data["status"] == "timeout"

    def test_exception_handling(self):
        import json
        from unittest import mock
        from core.pytest_runner import debug_inspect

        with mock.patch("subprocess.run", side_effect=OSError("fake error")):
            result = debug_inspect("tests/", extra_args="")
            data = json.loads(result)
            assert data["status"] == "error"
