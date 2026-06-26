"""Tests for core.resilience — error classification, retry, checkpoint."""

import contextlib
import json
from unittest.mock import patch

import pytest

# ── ErrorClassifier ──────────────────────────────────────────────────────


class TestErrorClassifier:
    """Classify exceptions by type for recovery decisions."""

    def test_rate_limit_detection(self):
        from core.resilience import ErrorClassifier, ErrorType

        err = Exception("Error 429: rate limit exceeded")
        assert ErrorClassifier.classify(err) == ErrorType.RATE_LIMIT

    def test_auth_error_detection(self):
        from core.resilience import ErrorClassifier, ErrorType

        err = Exception("401 unauthorized")
        assert ErrorClassifier.classify(err) == ErrorType.AUTH_ERROR

    def test_network_error_detection(self):
        from core.resilience import ErrorClassifier, ErrorType

        err = ConnectionError("connection refused")
        assert ErrorClassifier.classify(err) == ErrorType.NETWORK_ERROR

    def test_file_error_detection(self):
        from core.resilience import ErrorClassifier, ErrorType

        err = FileNotFoundError("no such file")
        assert ErrorClassifier.classify(err) == ErrorType.FILE_ERROR

    def test_code_error_detection(self):
        from core.resilience import ErrorClassifier, ErrorType

        # TypeError matches CODE_ERROR pattern without triggering VALIDATION
        err = TypeError("unsupported operand type")
        assert ErrorClassifier.classify(err) == ErrorType.CODE_ERROR

    def test_unknown_error(self):
        from core.resilience import ErrorClassifier, ErrorType

        # Avoid keywords that match other patterns ("invalid", "expected", etc.)
        err = Exception("zzz completely novel problem")
        assert ErrorClassifier.classify(err) == ErrorType.UNKNOWN

    def test_is_retryable_rate_limit(self):
        from core.resilience import ErrorClassifier

        err = Exception("429 rate limit")
        assert ErrorClassifier.is_retryable(err) is True

    def test_is_retryable_auth_not_retryable(self):
        from core.resilience import ErrorClassifier

        err = Exception("401 unauthorized")
        assert ErrorClassifier.is_retryable(err) is False

    def test_get_recovery_hint(self):
        from core.resilience import ErrorClassifier

        err = Exception("429 too many requests")
        hint = ErrorClassifier.get_recovery_hint(err)
        assert isinstance(hint, str)
        assert len(hint) > 0
        assert "Rate" in hint or "limit" in hint.lower()


# ── RetryPolicy ──────────────────────────────────────────────────────────


class TestRetryPolicy:
    """Retry with exponential backoff."""

    def test_succeeds_first_try(self):
        from core.resilience import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        call_count = [0]

        def func():
            call_count[0] += 1
            return "ok"

        result = policy.execute(func)
        assert result == "ok"
        assert call_count[0] == 1

    def test_retries_on_retryable_error(self):
        from core.resilience import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay=0.001)
        call_count = [0]

        def func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("connection timeout")
            return "success"

        result = policy.execute(func)
        assert result == "success"
        assert call_count[0] == 3

    def test_raises_after_max_retries(self):
        from core.resilience import RetryPolicy

        policy = RetryPolicy(max_retries=2, base_delay=0.001)

        def func():
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            policy.execute(func)

    def test_non_retryable_error_raises_immediately(self):
        from core.resilience import RetryPolicy

        policy = RetryPolicy(max_retries=5, base_delay=0.001)
        call_count = [0]

        def func():
            call_count[0] += 1
            raise ValueError("401 unauthorized")  # not retryable

        with pytest.raises(ValueError):
            policy.execute(func)
        assert call_count[0] == 1  # no retries

    def test_backoff_increases_delay(self):
        from core.resilience import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay=0.05, backoff_factor=2.0)
        timings = []

        def mock_sleep(seconds):
            timings.append(seconds)

        with patch("core.resilience.time.sleep", mock_sleep):

            def func():
                raise ConnectionError("timeout")

            with contextlib.suppress(ConnectionError):
                policy.execute(func)

        # Delays should increase: 0.05, 0.1, (then fail)
        assert len(timings) == 3
        assert timings[0] < timings[1] < timings[2]


# ── Checkpoint ───────────────────────────────────────────────────────────


class TestCheckpoint:
    """Save/restore task state."""

    def test_save_and_load(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        cp = Checkpoint("task-1")
        cp.save({"step": "generate", "phase": "images", "data": [1, 2, 3]})

        loaded = cp.load()
        assert loaded is not None
        assert loaded["step"] == "generate"
        assert loaded["phase"] == "images"
        assert loaded["data"] == [1, 2, 3]
        assert loaded["task_id"] == "task-1"
        assert "saved_at" in loaded

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        cp = Checkpoint("never-saved")
        assert cp.load() is None

    def test_exists(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        cp = Checkpoint("exists-test")
        assert cp.exists() is False
        cp.save({"step": "init"})
        assert cp.exists() is True

    def test_clear(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        cp = Checkpoint("clear-test")
        cp.save({"step": "done"})
        assert cp.exists() is True
        cp.clear()
        assert cp.exists() is False

    def test_list_checkpoints(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        cp1 = Checkpoint("task-a")
        cp1.save({"step": "step1", "phase": "alpha"})
        cp2 = Checkpoint("task-b")
        cp2.save({"step": "step2", "phase": "beta"})

        checkpoints = Checkpoint.list_checkpoints()
        assert len(checkpoints) == 2
        task_ids = {c["task_id"] for c in checkpoints}
        assert "task-a" in task_ids
        assert "task-b" in task_ids

    def test_list_empty(self, tmp_path, monkeypatch):
        from core.resilience import Checkpoint

        monkeypatch.setattr(Checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
        assert Checkpoint.list_checkpoints() == []


# ── SafeExecutor ─────────────────────────────────────────────────────────


class TestSafeExecutor:
    """Tool execution with error capture."""

    def test_successful_execution(self, tmp_path, monkeypatch):
        from core.resilience import SafeExecutor

        monkeypatch.setattr(SafeExecutor, "LOG_FILE", tmp_path / "audit.jsonl")
        executor = SafeExecutor()
        result = executor.execute("test_tool", lambda: "hello world")
        assert result["success"] is True
        assert result["result"] == "hello world"
        assert result["error"] == ""
        assert result["execution_time"] >= 0

    def test_failed_execution(self, tmp_path, monkeypatch):
        from core.resilience import SafeExecutor

        monkeypatch.setattr(SafeExecutor, "LOG_FILE", tmp_path / "audit.jsonl")

        def failing_tool():
            raise FileNotFoundError("no such file")

        executor = SafeExecutor()
        result = executor.execute("fail_tool", failing_tool)
        assert result["success"] is False
        assert "no such file" in result["error"]
        assert result["error_type"] != ""

    def test_result_truncation(self, tmp_path, monkeypatch):
        from core.resilience import SafeExecutor

        monkeypatch.setattr(SafeExecutor, "LOG_FILE", tmp_path / "audit.jsonl")
        executor = SafeExecutor(max_result_size=10)

        def big_tool():
            return "x" * 1000

        result = executor.execute("big_tool", big_tool)
        assert result["success"] is True
        assert "[truncated]" in result["result"]
        assert len(result["result"]) < 1000

    def test_audit_log_written(self, tmp_path, monkeypatch):
        from core.resilience import SafeExecutor

        log_file = tmp_path / "audit.jsonl"
        monkeypatch.setattr(SafeExecutor, "LOG_FILE", log_file)
        executor = SafeExecutor()
        executor.execute("logged_tool", lambda: "ok")
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["tool"] == "logged_tool"
        assert data["success"] is True

    def test_execute_with_args(self, tmp_path, monkeypatch):
        from core.resilience import SafeExecutor

        monkeypatch.setattr(SafeExecutor, "LOG_FILE", tmp_path / "audit.jsonl")
        executor = SafeExecutor()

        def adder(a, b):
            return str(a + b)

        result = executor.execute("adder", adder, {"a": 3, "b": 4})
        assert result["success"] is True
        assert result["result"] == "7"
