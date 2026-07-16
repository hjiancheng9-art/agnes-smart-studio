"""MCP Bridge shared utilities — binary discovery, version detection, MCP message format."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger("crux.mcp_utils")
import sys
from typing import Any

_log = logging.getLogger("crux.mcp_utils")


def _kill_process_tree(proc) -> None:
    """Kill a process and ALL of its descendants.

    A plain proc.kill() only terminates the direct child. On Windows a
    grandchild that inherited the stdout/stderr pipes keeps them open, so
    communicate() blocks long past the timeout -- the root cause of the
    "timeout freezes everything" hang. Killing the whole tree closes the
    pipes immediately and frees the caller on time.
    """
    import contextlib as _ctx

    try:
        if hasattr(proc, "poll"):
            if proc.poll() is not None:
                return
        elif getattr(proc, "returncode", None) is not None:
            return
    except Exception:
        logger.debug("Exception in _mcp_utils", exc_info=True)
    pid = getattr(proc, "pid", None)
    if pid is None:
        with _ctx.suppress(Exception):
            proc.kill()
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            import signal as _signal

            with _ctx.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(os.getpgid(pid), _signal.SIGKILL)
    except (subprocess.SubprocessError, OSError, ValueError):
        with _ctx.suppress(Exception):
            proc.kill()
    finally:
        with _ctx.suppress(Exception):
            proc.kill()


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
            _log.warning("Encoding recovered for %s: detected=%s", source, encoding)
        elif encoding != "utf-8":
            _log.info("Non-UTF-8 encoding detected for %s: %s", source, encoding)
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
        """Run the command via Popen and kill the WHOLE process tree on timeout.

        subprocess.run(timeout=...) only kills the direct child, so a grandchild
        that inherited the pipes can block communicate() far past the timeout.
        We manage the process directly and call _kill_process_tree so the caller
        is always freed within ~timeout seconds.
        """
        popen_kwargs = {
            "stdout": subprocess.PIPE if capture_output else None,
            "stderr": subprocess.PIPE if capture_output else None,
            "stdin": subprocess.PIPE if input_data is not None else stdin,
            "env": env,
            "cwd": cwd,
            "shell": shell,
            "startupinfo": startupinfo,
        }
        # New process group / session so the whole tree can be killed at once.
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = popen_kwargs.get("creationflags", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            popen_kwargs["start_new_session"] = True
        popen_kwargs.update(extra_kwargs)

        proc = subprocess.Popen(cmd, **popen_kwargs)
        stdin_bytes = input_data.encode("utf-8", errors="replace") if isinstance(input_data, str) else input_data
        try:
            out_b, err_b = proc.communicate(input=stdin_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            # Reap without blocking on the (now dead) pipes indefinitely.
            try:
                out_b, err_b = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                out_b, err_b = b"", b""
            raise subprocess.TimeoutExpired(cmd, timeout, output=out_b, stderr=err_b) from None

        stdout = _safe_decode(out_b, "run_subprocess.stdout") if out_b else ""
        stderr = _safe_decode(err_b, "run_subprocess.stderr") if err_b else ""
        completed = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        if check and proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd, stdout, stderr)
        return completed

    try:
        loop = asyncio.get_running_loop()
        running = loop.is_running()
    except RuntimeError:
        running = False

    if running:
        import concurrent.futures

        # NOTE: do NOT use `with ThreadPoolExecutor()` here. Its __exit__ calls
        # shutdown(wait=True), which would block the event loop until a stuck
        # worker finishes -- exactly the freeze we are fixing. Instead we submit,
        # wait with a hard cap, and on timeout kill the tree and let the daemon
        # pool die on its own without blocking the caller.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="run_subprocess")
        future = pool.submit(_sync_worker)
        try:
            # Small grace over the child timeout for kill/reap bookkeeping.
            result = future.result(timeout=timeout + 15)
            pool.shutdown(wait=False)
            return result
        except concurrent.futures.TimeoutError:
            # Worker is wedged; abandon it (daemon threads won't block exit).
            pool.shutdown(wait=False)
            raise subprocess.TimeoutExpired(cmd, timeout) from None
        except subprocess.TimeoutExpired:
            pool.shutdown(wait=False)
            raise

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

    _extra: dict = {}
    if sys.platform == "win32":
        _extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        _extra["start_new_session"] = True

    proc = await asyncio.subprocess.create_subprocess_exec(
        *cmd,
        stdin=stdin_arg,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        **_extra,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(input=stdin_data), timeout=timeout)
    except asyncio.TimeoutError:
        import contextlib as _ctx

        with _ctx.suppress(Exception):
            await asyncio.get_running_loop().run_in_executor(None, _kill_process_tree, proc)
        with _ctx.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)
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
