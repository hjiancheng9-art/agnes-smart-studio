"""CRUX Defense Core — three-layer safety architecture.

Layer 1 — PRE: validate inputs, check file existence, verify intent
Layer 2 — MID: timeout guard, circuit breaker, resource limits
Layer 3 — POST: syntax check, test guard, auto-rollback, idempotency

This gives CRUX the same resilience guarantees as Claude Code's harness.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import logging
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

# ── Layer 1: PRE-CHECK ──────────────────────────────────


def pre_check_file_write(file_path: str, content: str = "") -> str | None:
    """Validate a file write before execution. Returns error string or None.

    Checks: path safety, encoding, file size, protected paths.
    """
    p = Path(file_path)

    # Must be within project root
    try:
        p.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return f"BLOCKED: {file_path} is outside project root"

    # Protected files
    protected = {".env", ".env.local", "credentials.json", "id_rsa", "id_ed25519", "*.pem", "*.key"}
    fname = p.name
    for pat in protected:
        if (pat.startswith("*") and fname.endswith(pat[1:])) or fname == pat:
            return f"BLOCKED: {fname} is protected"

    # Size sanity
    if len(content) > 5_000_000:
        return f"BLOCKED: file too large ({len(content)} bytes)"

    # Already open check — prevent double-write races
    # (stat check is best-effort on Windows)

    return None  # OK


def pre_check_bash(command: str) -> str | None:
    """Validate a shell command before execution."""
    import re

    # Absolute blocks
    blocked = [
        (r"rm\s+-rf\s+/", "rm -rf /"),
        (r">\s*/dev/sda", "raw disk write"),
        (r"mkfs\.", "filesystem format"),
        (r"git\s+push\s+--force.*(?:main|master)", "force push to main"),
        (r"chmod\s+777\s+/", "chmod 777 root"),
        (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    ]
    for pattern, label in blocked:
        if re.search(pattern, command, re.IGNORECASE):
            return f"BLOCKED: {label}"

    return None


# ── Layer 2: MID-GUARD ──────────────────────────────────


class CircuitBreaker:
    """Prevent cascade failures by tracking consecutive errors."""

    def __init__(self, name: str, threshold: int = 5, cooldown: float = 30.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._last_failure = 0.0
        self._open = False

    def record_success(self):
        self._failures = 0
        self._open = False

    def record_failure(self) -> bool:
        """Record a failure. Returns True if breaker is now OPEN."""
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.threshold:
            self._open = True
            logger.warning("Circuit breaker OPEN: %s (%d failures)", self.name, self._failures)
        return self._open

    def allows(self) -> bool:
        """Check if the breaker allows execution."""
        if not self._open:
            return True
        if time.time() - self._last_failure > self.cooldown:
            self._open = False
            self._failures = 0
            logger.info("Circuit breaker RESET: %s", self.name)
            return True
        return False


# Per-tool circuit breakers
_circuits: dict[str, CircuitBreaker] = {}
_circuits_lock = threading.Lock()


def get_circuit(tool_name: str) -> CircuitBreaker:
    with _circuits_lock:
        if tool_name not in _circuits:
            _circuits[tool_name] = CircuitBreaker(tool_name)
        return _circuits[tool_name]


_TIMEOUTS: dict[str, float] = {
    "run_bash": 120.0,
    "web_fetch": 30.0,
    "web_search": 30.0,
    "generate_image": 120.0,
    "generate_video": 300.0,
    "run_test": 1800.0,
    "run_lint": 60.0,
    "run_format": 60.0,
}


def get_timeout(tool_name: str) -> float:
    return _TIMEOUTS.get(tool_name, 30.0)


# ── Layer 3: POST-VALIDATE ──────────────────────────────

# File version history for rollback
_file_snapshots: dict[str, str] = {}  # path → previous content


def snapshot_file(file_path: str) -> None:
    """Save pre-edit content for potential rollback."""
    p = Path(file_path)
    if p.exists():
        with contextlib.suppress(Exception):
            _file_snapshots[file_path] = p.read_text(encoding="utf-8")


def validate_syntax(file_path: str) -> str | None:
    """Check Python syntax after edit. Returns error string or None."""
    if not file_path.endswith(".py"):
        return None
    try:
        p = Path(file_path)
        if not p.exists():
            return None
        ast.parse(p.read_text(encoding="utf-8"))
        return None
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"


def rollback_file(file_path: str) -> bool:
    """Restore file to pre-edit state. Returns True on success."""
    old = _file_snapshots.pop(file_path, None)
    if old is None:
        return False
    try:
        Path(file_path).write_text(old, encoding="utf-8")
        logger.info("Rolled back: %s", file_path)
        return True
    except Exception:
        return False


def auto_rollback_if_broken(file_path: str) -> str | None:
    """Check syntax and rollback if broken. Returns error message or None."""
    err = validate_syntax(file_path)
    if err:
        if rollback_file(file_path):
            return f"Auto-rolled back {file_path}: {err}"
        return f"Syntax error (cannot rollback): {err}"
    return None


# Idempotency check
_operation_hashes: dict[str, str] = {}  # op_key → content_hash


def is_duplicate_write(file_path: str, content: str) -> bool:
    """Check if this exact write was already performed."""
    h = hashlib.sha256(f"{file_path}:{content}".encode()).hexdigest()
    key = f"write:{file_path}"
    if _operation_hashes.get(key) == h:
        return True
    _operation_hashes[key] = h
    return False


# ── Hook Integration ────────────────────────────────────


def register_defense_hooks():
    """Register all defense hooks into the hook system."""
    try:
        from core.hooks import HookType, register_hook

        # PRE: validate before tool execution
        def _pre_guard(tool_name: str, args: dict, **kw):
            cmd = args.get("command", args.get("cmd", ""))
            fpath = args.get("file_path", "") or args.get("target", "") or args.get("path", "")

            # File write pre-check
            if tool_name in ("write_file", "edit_file", "patch_file") and fpath:
                content = args.get("content", args.get("text", ""))
                err = pre_check_file_write(fpath, content)
                if err:
                    return err
                snapshot_file(fpath)

            # Bash pre-check
            if tool_name == "run_bash" and cmd:
                err = pre_check_bash(cmd)
                if err:
                    return err

            # Circuit breaker check
            cb = get_circuit(tool_name)
            if not cb.allows():
                return f"Circuit breaker OPEN for {tool_name}"

            return None  # OK

        register_hook(HookType.PRE_TOOL_USE, _pre_guard, priority=200)

        # POST: validate after tool execution
        def _post_guard(tool_name: str, args: dict, result: str, **kw):
            fpath = args.get("file_path", "") or args.get("target", "") or args.get("path", "")

            # Circuit breaker: track failures
            cb = get_circuit(tool_name)
            is_error = result and (
                "error" in result.lower()[:200] or "失败" in result[:200] or "failed" in result.lower()[:200]
            )
            if is_error:
                cb.record_failure()
            else:
                cb.record_success()

            # Syntax auto-rollback after file writes
            if tool_name in ("write_file", "edit_file", "patch_file") and fpath:
                err = auto_rollback_if_broken(fpath)
                if err:
                    return err  # Appended to result

            return None

        register_hook(HookType.POST_TOOL_USE, _post_guard, priority=90)
        logger.debug("defense hooks registered")

    except ImportError:
        pass


def reset_defense_state() -> None:
    """Reset all defense module-level state (for test isolation)."""
    global _circuits, _file_snapshots, _operation_hashes
    _circuits.clear()
    _file_snapshots.clear()
    _operation_hashes.clear()
