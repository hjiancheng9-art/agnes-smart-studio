"""UTF-8 encoding setup for Windows console and subprocess interoperability.

Import this once at startup before any other module that prints or spawns
subprocesses. It replaces the fragile code page hack with proper Win32 API
calls and Python-level reconfiguration.

Key design choice:
    The subprocess patch defaults to ``encoding="utf-8", errors="replace"``
    for backward compatibility, but now ALSO captures raw bytes and runs
    encoding-detection recovery when replacement characters are detected.

    For new code, use ``safe_run()`` which captures raw bytes and applies
    full encoding auto-detection before falling back to replacement mode.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any

__all__ = ["setup", "safe_run"]

_logger = logging.getLogger("crux.encoding")

_WIN32_CONSOLE_CP_SET = False

# Saved reference to the original (unpatched) subprocess.run.
# safe_run() uses this directly to bypass the patch and capture raw bytes.
_ORIG_RUN = subprocess.run


def _setup_win32_console() -> bool:
    """Set console code page to UTF-8 using the Windows API."""
    global _WIN32_CONSOLE_CP_SET
    if _WIN32_CONSOLE_CP_SET:
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        CP_UTF8 = 65001
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(CP_UTF8)
        kernel32.SetConsoleOutputCP(CP_UTF8)
        _WIN32_CONSOLE_CP_SET = True
        return True
    except (OSError, AttributeError):
        return False


def _reconfigure_stdio():
    """Reconfigure stdin/stdout/stderr to use UTF-8."""
    for stream in [sys.stdin, sys.stdout, sys.stderr]:
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, AttributeError, ValueError):
            pass


def _recover_text_from_bytes(raw: bytes, source: str = "subprocess") -> str:
    """Try to decode *raw* bytes with encoding auto-detection.

    Falls back to UTF-8 with replace if recovery fails.
    """
    if not raw:
        return ""

    try:
        from core.encoding_fix import fix_garbled_bytes, report_encoding_issue

        text, encoding, recovered = fix_garbled_bytes(raw)
        if recovered:
            _logger.warning(
                "Encoding recovered for %s: detected=%s, recovered=True",
                source, encoding,
            )
        elif encoding != "utf-8":
            _logger.info(
                "Non-UTF-8 encoding detected for %s: %s", source, encoding,
            )

        # Report any remaining issues (mojibake, replacement chars)
        issue = report_encoding_issue(text, source=source)
        if issue:
            _logger.warning("%s", issue)

        return text
    except ImportError:
        # encoding_fix not available yet (early startup)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _patch_subprocess_run():
    """Patch subprocess.run to add encoding recovery.

    The patched version intercepts calls with ``text=True`` and captures
    raw bytes alongside decoded text. When replacement characters (U+FFFD)
    are detected, it attempts encoding auto-detection and recovery.

    .stdout / .stderr are always strings when text mode is requested.
    .stdout_raw / .stderr_raw carry the original bytes (if captured).
    """
    global _ORIG_RUN

    def _patched_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        wants_text = kwargs.get("text", False) or kwargs.get("universal_newlines", False)
        capture = kwargs.get("capture_output", False)

        # If caller explicitly provides stdout/stderr pipes, don't intercept
        stdout_arg = kwargs.get("stdout")
        stderr_arg = kwargs.get("stderr")
        has_explicit_pipes = (
            stdout_arg is not None and stdout_arg != subprocess.PIPE
        ) or (stderr_arg is not None and stderr_arg != subprocess.PIPE)

        if not wants_text and not capture:
            return _ORIG_RUN(*args, **kwargs)

        # Set safe encoding defaults
        if "encoding" not in kwargs:
            kwargs["encoding"] = "utf-8"
        if "errors" not in kwargs:
            kwargs["errors"] = "replace"

        # When capturing text: capture raw bytes first, then decode with recovery
        if capture and wants_text and not has_explicit_pipes:
            # Run with binary capture
            bin_kwargs = dict(kwargs)
            bin_kwargs.pop("text", None)
            bin_kwargs.pop("universal_newlines", None)
            bin_kwargs.pop("encoding", None)
            bin_kwargs.pop("errors", None)
            bin_kwargs["capture_output"] = True

            result = _ORIG_RUN(*args, **bin_kwargs)

            stdout_raw = result.stdout
            stderr_raw = result.stderr

            result.stdout = _recover_text_from_bytes(
                stdout_raw or b"", "subprocess.stdout"
            )
            result.stderr = _recover_text_from_bytes(
                stderr_raw or b"", "subprocess.stderr"
            )

            # Attach raw bytes for callers that need them
            setattr(result, "stdout_raw", stdout_raw)
            setattr(result, "stderr_raw", stderr_raw)

            return result

        return _ORIG_RUN(*args, **kwargs)

    subprocess.run = _patched_run


def _patch_subprocess_popen():
    """Ensure subprocess.Popen defaults to UTF-8 encoding in text mode only.

    Only applies when the caller explicitly requests text mode via
    ``text=True`` or ``universal_newlines=True``. Binary-mode callers
    (like safe_run) are not affected.
    """
    _orig_init = subprocess.Popen.__init__

    def _patched_init(self, *args, **kwargs):
        wants_text = kwargs.get("text") or kwargs.get("universal_newlines")
        if wants_text and "encoding" not in kwargs:
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "replace"
        _orig_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_init


def safe_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a subprocess with encoding-safe text capture.

    Unlike ``subprocess.run(text=True)`` which silently replaces undecodable
    bytes with U+FFFD, this function:

    1. Captures raw bytes (bypassing the UTF-8 patch)
    2. Runs encoding auto-detection (GBK, Big5, UTF-8, etc.)
    3. Attempts recovery for garbled text
    4. Falls back to UTF-8 with replace only as last resort

    Use this for any subprocess that may produce non-UTF-8 output
    (git, pip, external CLI tools, Chinese-language tools, etc.).

    Parameters are the same as subprocess.run, with these defaults:
    - ``capture_output=True``
    - ``text=True`` (caller gets strings)
    """
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)

    # Strip user encoding args — we handle encoding internally
    kwargs.pop("encoding", None)
    kwargs.pop("errors", None)

    # Run in binary mode via the ORIGINAL (unpatched) subprocess.run
    # to get raw bytes without any encoding interference
    bin_kwargs = dict(kwargs)
    bin_kwargs.pop("text", None)
    bin_kwargs.pop("universal_newlines", None)

    result = _ORIG_RUN(*args, **bin_kwargs)

    # Decode raw bytes with full encoding recovery
    if result.stdout is not None:
        result.stdout = _recover_text_from_bytes(result.stdout, "safe_run.stdout")
    if result.stderr is not None:
        result.stderr = _recover_text_from_bytes(result.stderr, "safe_run.stderr")

    return result


def setup():
    """Call once at application startup to configure all encoding layers."""
    _setup_win32_console()
    _reconfigure_stdio()
    _patch_subprocess_popen()
    _patch_subprocess_run()
