"""MCP Bridge shared utilities — binary discovery, version detection, MCP message format."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any

_log = logging.getLogger("crux.mcp_utils")


def _safe_decode(raw: bytes, source: str = "subprocess") -> str:
    """Decode subprocess output with encoding auto-detection.

    Falls back to UTF-8 with replace if recovery fails.
    Reports encoding issues via logging.
    """
    if not raw:
        return ""
    try:
        from core.encoding_fix import fix_garbled_bytes, report_encoding_issue

        text, encoding, recovered = fix_garbled_bytes(raw)
        if recovered:
            _log.warning(
                "Encoding recovered for %s: detected=%s", source, encoding
            )
        elif encoding != "utf-8":
            _log.info(
                "Non-UTF-8 encoding detected for %s: %s", source, encoding
            )
        issue = report_encoding_issue(text, source=source)
        if issue:
            _log.warning("%s", issue)
        return text
    except ImportError:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")

# ── MCP JSON-RPC message helpers ──────────────────────────────


def make_result(req_id: str, result: object, ensure_ascii: bool = False) -> str:
    """Build a MCP result JSON response."""
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False)


def make_error(req_id: str | None, code: int, message: str) -> str:
    """Build a MCP error JSON response."""
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}, ensure_ascii=False)


def make_tool_result(req_id: str | None, text: str, is_error: bool = False, meta: dict | None = None) -> str:
    """Build a tool_call result JSON response."""
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if meta:
        result["_meta"] = meta
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False)


def find_binary(*names: str) -> str | None:
    """Find the first available binary in PATH (or common install paths)."""
    for name in names:
        binary = shutil.which(name)
        if binary:
            return binary
    return None


def find_binary_at(path: str, *names: str) -> str | None:
    """Find a binary under a specified directory prefix."""
    for name in names:
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# ── Subprocess runner (UTF-8 safe) ────────────────────────────


def run_subprocess(
    cmd: list[str],
    *,
    timeout: float = 30,
    input_data: str | None = None,
    env_add: dict[str, str] | None = None,
    cwd: str | None = None,
    shell: bool = False,
    check: bool = False,
    stdin: Any | None = None,
    startupinfo: Any | None = None,
    capture_output: bool = True,
    **extra_kwargs: Any,
) -> subprocess.CompletedProcess:
    """UTF-8 safe subprocess runner with automatic async context detection.

    If called from within a running event loop (asyncio.get_running_loop),
    offloads subprocess.run to a ThreadPoolExecutor so rich.Live rendering
    stays responsive and the input box does not disappear.

    In sync contexts (no running loop), executes directly for backward
    compatibility.  Timeout is extended by 30s in async mode for thread safety.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["LANG"] = "en_US.UTF-8"
    if env_add:
        env.update(env_add)

    extra_kwargs.pop("text", None)
    extra_kwargs.pop("encoding", None)
    extra_kwargs.pop("errors", None)

    def _sync_worker():
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input_data,
            env=env,
            cwd=cwd,
            shell=shell,
            check=check,
            stdin=stdin,
            startupinfo=startupinfo,
            **extra_kwargs,
        )

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_sync_worker)
                try:
                    return future.result(timeout=timeout + 30)
                except concurrent.futures.TimeoutError:
                    raise subprocess.TimeoutExpired(cmd, timeout) from None
    except RuntimeError:
        pass

    return _sync_worker()


async def run_subprocess_async(
    cmd: list[str],
    *,
    timeout: float = 30,
    input_data: str | None = None,
    env_add: dict[str, str] | None = None,
    cwd: str | None = None,
    shell: bool = False,
    check: bool = False,
    **extra_kwargs: Any,
) -> subprocess.CompletedProcess:
    """Async subprocess — does NOT block the event loop.

    Uses asyncio.create_subprocess_exec under the hood, keeping the
    event loop alive (rich.Live stays responsive, input box stays visible).

    Same signature as run_subprocess. Use this from async contexts
    (chat loop, tool dispatch via run_side_effect) instead of the
    blocking run_subprocess.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["LANG"] = "en_US.UTF-8"
    if env_add:
        env.update(env_add)

    stdin_arg = asyncio.subprocess.PIPE if input_data else None
    stdin_data = input_data.encode("utf-8", errors="replace") if input_data else None

    proc = await asyncio.subprocess.create_subprocess_exec(
        *cmd,
        stdin=stdin_arg,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(input=stdin_data), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise subprocess.TimeoutExpired(cmd, timeout) from None

    stdout = _safe_decode(stdout_bytes, "run_subprocess_async.stdout") if stdout_bytes else ""
    stderr = _safe_decode(stderr_bytes, "run_subprocess_async.stderr") if stderr_bytes else ""

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode or -1, cmd, output=stdout, stderr=stderr)

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode or 0,
        stdout=stdout,
        stderr=stderr,
    )


def get_version(binary: str, version_flag: str = "--version") -> str:
    """Get binary version string, with tolerant defaults."""
    try:
        r = run_subprocess([binary, version_flag], timeout=10)
        return (r.stdout.strip() or r.stderr.strip())[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "unknown"


def check_binary_health(name: str, binary: str | None) -> tuple[bool, str]:
    """Check if binary is usable, returns (ok, version_or_error)."""
    if not binary:
        return False, f"{name} binary not found in PATH"
    version = get_version(binary)
    if version == "unknown":
        return False, f"{name} binary not executable"
    return True, version


# ── Tool registry helpers ─────────────────────────────────────


def build_tools_json(tools: list[dict[str, Any]]) -> str:
    """Build a tools/list JSON response."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "result": {"tools": tools},
            "id": None,
        },
        ensure_ascii=False,
    )
