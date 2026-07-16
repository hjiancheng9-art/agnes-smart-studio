"""Tests for sandbox — execution safety boundary."""

import pytest

pytestmark = pytest.mark.unit

import pytest

from core.interfaces.execution import CodeExecutor, ExecutionConfig, ExecutionResult

# ═══════════════════════════════════════════════════
#  Sandbox contract tests
# ═══════════════════════════════════════════════════


class FakeExecutor(CodeExecutor):
    """Fake executor for testing — no real code execution."""

    def __init__(self, safe: bool = True, result: str = "ok"):
        self._safe = safe
        self._result = result
        self.executed_codes: list[str] = []
        self.executed_files: list[str] = []

    def execute(self, code: str, config=None) -> ExecutionResult:
        self.executed_codes.append(code)
        if not self._safe:
            return ExecutionResult(success=False, stderr="unsafe", exit_code=1)
        return ExecutionResult(success=True, stdout=self._result, exit_code=0)

    def execute_file(self, path: str, config=None) -> ExecutionResult:
        self.executed_files.append(path)
        return ExecutionResult(success=True, stdout="file ran", exit_code=0)

    def is_safe(self, code: str) -> bool:
        return self._safe and "rm -rf" not in code and "os.system" not in code


class TestFakeExecutor:
    """Verify FakeExecutor works as a test double."""

    def test_safe_code_passes(self):
        exe = FakeExecutor(safe=True)
        assert exe.is_safe("print('hello')")

    def test_dangerous_code_blocked(self):
        exe = FakeExecutor(safe=True)
        assert not exe.is_safe("os.system('rm -rf /')")

    def test_execute_records_code(self):
        exe = FakeExecutor()
        exe.execute("x = 1 + 1")
        assert "x = 1 + 1" in exe.executed_codes

    def test_execute_returns_result(self):
        exe = FakeExecutor(result="hello world")
        r = exe.execute("print('hi')")
        assert r.success
        assert r.stdout == "hello world"

    def test_execute_file_records_path(self):
        exe = FakeExecutor()
        exe.execute_file("/tmp/test.py")
        assert "/tmp/test.py" in exe.executed_files


class TestExecutionConfig:
    """ExecutionConfig controls sandbox parameters."""

    def test_defaults(self):
        cfg = ExecutionConfig()
        assert cfg.timeout_seconds == 30.0
        assert cfg.allow_network is False
        assert cfg.allow_filesystem is True

    def test_custom_config(self):
        cfg = ExecutionConfig(
            timeout_seconds=5.0,
            max_memory_mb=128,
            allow_network=True,
            denied_modules=["os", "subprocess"],
        )
        assert cfg.timeout_seconds == 5.0
        assert cfg.allow_network is True
        assert "os" in cfg.denied_modules


class TestExecutionResult:
    """ExecutionResult captures all execution output."""

    def test_success_result(self):
        r = ExecutionResult(success=True, stdout="output", exit_code=0)
        assert r.success
        assert r.stdout == "output"
        assert r.exit_code == 0

    def test_failure_result(self):
        r = ExecutionResult(success=False, stderr="error", exit_code=1)
        assert not r.success
        assert r.stderr == "error"
        assert r.exit_code == 1
