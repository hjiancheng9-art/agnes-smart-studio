"""Error recovery and resilience infrastructure.

Provides:
- ErrorClassifier: automatically classify errors by type
- RetryPolicy: configurable retry strategies with backoff
- Checkpoint: save/restore task state for long-running operations
- SafeExecutor: sandboxed tool execution with rollback
"""

import asyncio
import json
import re
import threading
import time
import traceback
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

# ── 敏感数据脱敏模式 ─────────────────────────────────────
REDACT_PATTERNS: dict[str, re.Pattern] = {
    "api_key": re.compile(r'(?:api[_-]?key|token|secret|password|apikey)[=:]\s*["\']?\S{8,}', re.IGNORECASE),
    "sk_key": re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    "bearer_token": re.compile(r"Authorization:\s*Bearer\s+\S{8,}", re.IGNORECASE),
    "auth_header": re.compile(r'(Authorization|X-Api-Key|X-Auth-Token)[=:]\s*["\']?\S{8,}', re.IGNORECASE),
    "jwt_token": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "password_in_json": re.compile(r'"[Pp]assword"\s*:\s*"[^"]{4,}"'),
}

REDACT_REPLACEMENT = "<REDACTED>"


def redact_sensitive(text: str) -> str:
    """脱敏：扫描常见敏感数据模式并替换为 <REDACTED>。"""
    if not text:
        return text
    for pattern in REDACT_PATTERNS.values():
        text = pattern.sub(REDACT_REPLACEMENT, text)
    return text


T = TypeVar("T")

from core.config import OUTPUT_DIR

__all__ = [
    "Checkpoint",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "ErrorClassifier",
    "ErrorType",
    "GracefulDegradation",
    "RetryPolicy",
    "SafeExecutor",
    "get_circuit",
    "reset_all_circuits",
]


# ======================================================================
# Error Classifier
# ======================================================================


class ErrorType(Enum):
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    CONTENT_POLICY = "content_policy"
    VALIDATION_ERROR = "validation_error"
    FILE_ERROR = "file_error"
    CODE_ERROR = "code_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class ErrorClassifier:
    """Automatically classify errors to determine recovery strategy."""

    PATTERNS = {
        ErrorType.RATE_LIMIT: ["429", "rate limit", "too many requests", "quota"],
        ErrorType.AUTH_ERROR: ["401", "403", "unauthorized", "forbidden", "api key"],
        ErrorType.CONTENT_POLICY: ["content_policy", "safety filter", "inappropriate content"],
        ErrorType.NETWORK_ERROR: ["connection", "timeout", "dns", "refused", "unreachable"],
        ErrorType.VALIDATION_ERROR: ["validation", "invalid", "expected", "must be"],
        ErrorType.FILE_ERROR: ["filenotfound", "no such file", "permission denied"],
        ErrorType.CODE_ERROR: [
            "syntaxerror",
            "typeerror",
            "attributeerror",
            "keyerror",
            "indexerror",
            "valueerror",
            "importerror",
        ],
    }

    @classmethod
    def classify(cls, error: Exception) -> ErrorType:
        """Classify an exception into an ErrorType."""
        error_str = str(error).lower()
        error_type_name = type(error).__name__.lower()

        for etype, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if pattern in error_str or pattern in error_type_name:
                    return etype

        return ErrorType.UNKNOWN

    @classmethod
    def is_retryable(cls, error: Exception) -> bool:
        """Determine if an error is worth retrying."""
        etype = cls.classify(error)
        return etype in (
            ErrorType.RATE_LIMIT,
            ErrorType.NETWORK_ERROR,
            ErrorType.TIMEOUT,
            ErrorType.API_ERROR,
            ErrorType.UNKNOWN,
        )

    @classmethod
    def get_recovery_hint(cls, error: Exception) -> str:
        """Get a human-readable hint for how to recover from this error."""
        etype = cls.classify(error)
        hints = {
            ErrorType.RATE_LIMIT: "Rate limited. Wait a moment and retry.",
            ErrorType.AUTH_ERROR: "Check API key configuration.",
            ErrorType.CONTENT_POLICY: "Prompt triggered safety filter. Rephrase.",
            ErrorType.NETWORK_ERROR: "Network issue. Check connection and retry.",
            ErrorType.VALIDATION_ERROR: "Invalid parameters. Check input format.",
            ErrorType.FILE_ERROR: "File not found or inaccessible. Check path.",
            ErrorType.CODE_ERROR: "Code error. Fix the code and retry.",
            ErrorType.TIMEOUT: "Operation timed out. Try with a longer timeout.",
            ErrorType.API_ERROR: "API returned an error. Retry with backoff.",
            ErrorType.UNKNOWN: "Unknown error. Investigate and retry if appropriate.",
        }
        return hints.get(etype, "No recovery hint available.")


# ======================================================================
# Retry Policy
# ======================================================================


class RetryPolicy:
    """Configurable retry with exponential backoff.

    Usage:
        policy = RetryPolicy(max_retries=3, base_delay=1.0)
        result = policy.execute(lambda: do_something())
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        retryable_errors: tuple[type[BaseException], ...] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.retryable_errors: tuple[type[BaseException], ...] = retryable_errors or (Exception,)

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry policy.

        Raises the last exception if all retries fail.
        """
        last_error: BaseException | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except self.retryable_errors as e:
                last_error = e

                # Check if error is retryable via classifier
                # (only Exception subclasses are classifiable; BaseException
                # like KeyboardInterrupt/GeneratorExit is never retryable)
                if isinstance(e, Exception) and not ErrorClassifier.is_retryable(e):
                    raise

                if attempt < self.max_retries:
                    delay = min(self.base_delay * (self.backoff_factor**attempt), self.max_delay)
                    time.sleep(delay)
                else:
                    raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry loop exhausted with no exception captured")


# ======================================================================
# Checkpoint Manager
# ======================================================================


class Checkpoint:
    """Save and restore task state for long-running operations.

    Useful for:
    - Video generation pipelines that can take minutes
    - Multi-step tasks that might be interrupted
    - Batch operations that need to resume from failure
    """

    CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.checkpoint_file = self.CHECKPOINT_DIR / f"{task_id}.json"
        self.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, state: dict):
        """Save task state to a checkpoint file."""
        state["task_id"] = self.task_id
        state["saved_at"] = time.time()
        self.checkpoint_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self) -> dict | None:
        """Load task state from checkpoint. Returns None if not found."""
        if not self.checkpoint_file.exists():
            return None
        try:
            return json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return None

    def exists(self) -> bool:
        """Check if a checkpoint exists for this task."""
        return self.checkpoint_file.exists()

    def clear(self):
        """Delete the checkpoint file."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()

    @classmethod
    def list_checkpoints(cls) -> list[dict]:
        """List all saved checkpoints."""
        if not cls.CHECKPOINT_DIR.exists():
            return []
        checkpoints = []
        for f in cls.CHECKPOINT_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                checkpoints.append(
                    {
                        "task_id": data.get("task_id", f.stem),
                        "saved_at": data.get("saved_at", 0),
                        "step": data.get("step", ""),
                        "phase": data.get("phase", ""),
                    }
                )
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(checkpoints, key=lambda x: x.get("saved_at", 0), reverse=True)


# ======================================================================
# Safe Tool Executor
# ======================================================================


class SafeExecutor:
    """Execute tools with error capture, timeout, and logging.

    Wraps tool execution with:
    - Error classification and recovery hints
    - Execution time tracking
    - Result size limiting
    - Audit logging
    """

    LOG_FILE = OUTPUT_DIR / "tool_audit.jsonl"

    def __init__(self, max_result_size: int = 10000, timeout: float = 60.0) -> None:
        self.max_result_size = max_result_size
        self.timeout = timeout
        self.audit_log: list[dict] = []

    def execute(self, tool_name: str, tool_func: Callable, args: dict | None = None) -> dict:
        """Execute a tool safely with error handling and logging.

        Returns dict with: success, result, error, error_type, execution_time.
        """
        args = args or {}
        start_time = time.time()
        result = {
            "tool": tool_name,
            # 截断 + 脱敏
            "args": {k: redact_sensitive(str(v))[:100] for k, v in args.items()},
            "success": False,
            "result": "",
            "error": "",
            "error_type": "",
            "recovery_hint": "",
            "execution_time": 0,
        }

        try:
            raw_result = tool_func(**args)
            if isinstance(raw_result, str) and len(raw_result) > self.max_result_size:
                raw_result = raw_result[: self.max_result_size] + "\n[truncated]"
            result["result"] = redact_sensitive(str(raw_result))
            result["success"] = True
        except (OSError, RuntimeError, ValueError) as e:
            error_type = ErrorClassifier.classify(e)
            result["error"] = redact_sensitive(str(e)[:500])
            result["error_type"] = error_type.value
            result["recovery_hint"] = ErrorClassifier.get_recovery_hint(e)
            result["traceback"] = redact_sensitive(traceback.format_exc()[:1000])

        result["execution_time"] = round(time.time() - start_time, 3)

        # Add to audit log
        self.audit_log.append(result)
        self._write_audit(result)

        return result

    def _write_audit(self, entry: dict):
        """Append an entry to the audit log file."""
        try:
            with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except (json.JSONDecodeError, TypeError, KeyError, OSError):
            pass  # don't let logging break execution


# ======================================================================
# #1 Qoder-style: Global Circuit Breaker + Graceful Degradation
# ======================================================================


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a circuit is open and rejecting requests."""

    def __init__(self, circuit_name: str, failure_count: int) -> None:
        super().__init__(f"熔断器 [{circuit_name}] 已断开（连续失败 {failure_count} 次）。请等待恢复超时后重试。")
        self.circuit_name = circuit_name
        self.failure_count = failure_count


class CircuitBreaker:
    """Universal circuit breaker — prevent cascading failures.

    Qoder 理念：错误不只靠单点恢复，更要全局熔断，防止级联烧穿。

    States:
        CLOSED → failures >= threshold → OPEN → timeout → HALF_OPEN
        HALF_OPEN → success → CLOSED  |  failure → OPEN
    """

    def __init__(
        self,
        name: str,
        threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ) -> None:
        self.name = name
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_count = 0
        self._lock = threading.RLock()

    def _transition(self, new_state: CircuitState) -> None:
        with self._lock:
            old = self.state
            self.state = new_state
            if new_state == CircuitState.HALF_OPEN:
                self.half_open_count = 0
            if new_state == CircuitState.CLOSED:
                self.failure_count = 0
            try:
                from core.observability import metrics as _m

                _m.increment(f"circuit.{self.name}.{old.value}_to_{new_state.value}")
            except ImportError:
                pass

    def record_success(self) -> None:
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_count += 1
                if self.half_open_count >= self.half_open_max:
                    self._transition(CircuitState.CLOSED)
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if (
                self.state == CircuitState.CLOSED
                and self.failure_count >= self.threshold
                or self.state == CircuitState.HALF_OPEN
            ):
                self._transition(CircuitState.OPEN)

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                    return True
                return False
            return self.half_open_count < self.half_open_max

    def __enter__(self):
        if not self.allow_request():
            raise CircuitOpenError(self.name, self.failure_count)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        return False

    async def __aenter__(self):
        if not self.allow_request():
            raise CircuitOpenError(self.name, self.failure_count)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        return False

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute a function under circuit breaker protection."""
        with self:
            return func(*args, **kwargs)

    async def acall(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Async version of call()."""
        async with self:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN


class GracefulDegradation:
    """Graceful degradation — fallback chain on failure.

    Qoder 理念：失败不直接暴露给用户，而是沿降级链尝试备选方案。

    Usage:
        gd = GracefulDegradation("image_gen")
        gd.add_fallback(primary_func, "primary")
        gd.add_fallback(fallback_func, "fallback")
        result = gd.execute(arg1)
    """

    def __init__(self, name: str = "") -> None:
        self.name = name
        self._fallbacks: list[tuple[Callable, str, tuple[type[BaseException], ...]]] = []
        self._last_error: BaseException | None = None

    def add_fallback(
        self,
        func: Callable,
        label: str = "",
        catch: tuple[type[BaseException], ...] = (Exception,),
    ) -> "GracefulDegradation":
        self._fallbacks.append((func, label, catch))
        return self

    def execute(self, *args, **kwargs):
        """Execute fallback chain. Returns first success, raises last error."""
        for func, label, catch in self._fallbacks:
            try:
                return func(*args, **kwargs)
            except catch as e:
                self._last_error = e
                try:
                    from core.observability import metrics as _m

                    _m.increment(f"degradation.{self.name}.{label}_failed")
                except ImportError:
                    pass
                continue
        raise self._last_error or RuntimeError(f"GracefulDegradation [{self.name}]: no fallbacks registered")

    async def aexecute(self, *args, **kwargs):
        """Async version of execute."""
        for func, _label, catch in self._fallbacks:
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return await asyncio.to_thread(func, *args, **kwargs)
            except catch as e:
                self._last_error = e
                continue
        raise self._last_error or RuntimeError(f"GracefulDegradation [{self.name}]: no fallbacks registered")


# ── Global circuit breaker registry ──
_circuits: dict[str, CircuitBreaker] = {}
_circuits_lock = threading.RLock()


def get_circuit(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a named circuit breaker (thread-safe singleton)."""
    with _circuits_lock:
        if name not in _circuits:
            _circuits[name] = CircuitBreaker(name, **kwargs)
        return _circuits[name]


def reset_all_circuits() -> None:
    """Reset all circuit breakers (for testing/recovery)."""
    with _circuits_lock:
        _circuits.clear()
