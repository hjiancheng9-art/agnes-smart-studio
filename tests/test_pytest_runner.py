"""Tests for core.pytest_runner — 递归守卫与安全 pytest 封装。

pytest_runner 是防止自检型 spawn 无限递归 fork 的安全关键模块，
被 capability / executor / self_audit / self_fix 调用。本测试固化其守卫
契约：在 pytest 进程内绝不 spawn 子 pytest，且参数拼装正确。
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.pytest_runner import in_pytest, parse_test_summary, run_pytest_safe


class TestParseTestSummary:
    """pytest 输出 → (passed, failed) 计数解析。"""

    def test_passed_and_failed(self):
        assert parse_test_summary("2 failed, 5 passed in 0.3s") == (5, 2)

    def test_passed_only(self):
        assert parse_test_summary("3 passed in 0.1s") == (3, 0)

    def test_failed_only(self):
        assert parse_test_summary("1 failed in 0.2s") == (0, 1)

    def test_empty_string(self):
        assert parse_test_summary("") == (0, 0)

    def test_no_tests_ran(self):
        # pytest 在 "no tests ran" 时不输出 passed/failed
        assert parse_test_summary("no tests ran in 0.01s") == (0, 0)

    def test_skipped_is_ignored(self):
        # 当前实现只解析 passed/failed，skipped/error/xfailed 不计入。
        # 固化这一行为（上游 capability/self_audit 拿到的是 passed/failed）。
        assert parse_test_summary("1 skipped, 2 passed in 0.1s") == (2, 0)

    def test_multiline_output(self):
        out = "=== FAILURES ===\nblah\n3 passed, 1 failed in 0.5s"
        assert parse_test_summary(out) == (3, 1)


class TestInPytest:
    """in_pytest() 三信号判定（任一命中即 True，保守策略）。"""

    def test_true_when_pytest_current_test_env_set(self, monkeypatch):
        # 信号 1：PYTEST_CURRENT_TEST 已设置（pytest 测试执行期间必有）
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x.py::test_y (call)")
        assert in_pytest() is True

    def test_true_in_running_pytest(self):
        # 信号 2/3：在 pytest 进程内跑此测试时，sys.modules 含 pytest 且
        # sys.argv[0] 指向 pytest 入口，天然为真。这几乎是免费断言，
        # 但固化了"测试运行期守卫必须生效"这一核心安全契约。
        assert in_pytest() is True


class TestRunPytestSafeRecursionGuard:
    """run_pytest_safe 在 pytest 内必须短路，绝不 spawn 子进程。"""

    def test_short_circuits_inside_pytest_no_subprocess(self):
        # 这是验证"递归 fork 被切断"的核心断言。
        with patch("core.pytest_runner.subprocess.run") as mock_run:
            result = run_pytest_safe()
        # subprocess.run 绝不能被调用
        mock_run.assert_not_called()
        # 返回伪 CompletedProcess，调用方据此判定"非失败"
        assert result.returncode == 0
        assert "skipped" in result.stdout
        assert result.stderr == ""

    def test_short_circuit_args_marker(self):
        # 短路返回的 args 标记，便于日志排查
        with patch("core.pytest_runner.subprocess.run"):
            result = run_pytest_safe()
        assert "guarded" in result.args[0] or "inside pytest" in result.args[0]


class TestRunPytestSafeRealBranch:
    """强制 in_pytest()→False 走真实分支，验证参数拼装与透传（不真 spawn）。"""

    def test_default_args_construction(self, monkeypatch):
        monkeypatch.setattr("core.pytest_runner.in_pytest", lambda: False)
        fake = subprocess.CompletedProcess(args=["pytest"], returncode=0, stdout="3 passed", stderr="")
        with patch("core.pytest_runner.subprocess.run", return_value=fake) as mock_run:
            result = run_pytest_safe()
        mock_run.assert_called_once()
        call = mock_run.call_args
        args = call.args[0]
        # 命令前缀：[python, -m, pytest, target, -q, --tb=no]
        assert args[0] == sys.executable
        assert args[1:4] == ["-m", "pytest", "tests/"]
        assert "-q" in args
        assert "--tb=no" in args
        # 透传默认参数
        assert call.kwargs["timeout"] == 30
        assert call.kwargs["cwd"] is None
        assert call.kwargs["capture_output"] is True
        assert call.kwargs["text"] is True
        # 透传子进程结果
        assert result.returncode == 0
        assert result.stdout == "3 passed"

    def test_custom_target_and_extra_args(self, monkeypatch):
        monkeypatch.setattr("core.pytest_runner.in_pytest", lambda: False)
        fake = subprocess.CompletedProcess(args=["pytest"], returncode=1, stdout="1 failed", stderr="")
        with patch("core.pytest_runner.subprocess.run", return_value=fake) as mock_run:
            run_pytest_safe(
                test_target="tests/test_x.py",
                extra_args=["-v", "--tb=long"],
                timeout=15,
                cwd="/some/dir",
            )
        call = mock_run.call_args
        args = call.args[0]
        assert "tests/test_x.py" in args
        assert "-v" in args
        assert "--tb=long" in args
        assert call.kwargs["timeout"] == 15
        assert call.kwargs["cwd"] == "/some/dir"
