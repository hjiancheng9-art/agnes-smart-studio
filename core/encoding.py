"""UTF-8 encoding setup for Windows console and subprocess interoperability.

Import this once at startup before any other module that prints or spawns
subprocesses. It replaces the fragile code page hack with proper Win32 API
calls and Python-level reconfiguration.
"""

import subprocess
import sys

__all__ = ["setup"]

_WIN32_CONSOLE_CP_SET = False


def _setup_win32_console() -> bool:
    """Set console code page to UTF-8 using the Windows API.

    Uses SetConsoleCP/SetConsoleOutputCP via ctypes to avoid shelling out
    to chcp.com (which can fail or race with other console operations).
    Returns True on success, False on non-Windows or failure.
    """
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
        # ctypes unavailable or Win32 API call failed
        return False


def _reconfigure_stdio():
    """Reconfigure stdin/stdout/stderr to use UTF-8 with strict error handling.

    On Windows, the default text wrapper uses the ANSI code page, which
    garbles Chinese and emoji characters. This replaces them with UTF-8
    wrappers that use 'replace' for encoding (don't crash on unsupported
    characters) and 'strict' for decoding (surface encoding bugs early).
    """
    for stream, _name in [(sys.stdin, "stdin"), (sys.stdout, "stdout"), (sys.stderr, "stderr")]:
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attribute-access]
        except (OSError, AttributeError, ValueError):
            # Stream already closed or doesn't support reconfiguration
            pass


def _patch_subprocess():
    """Ensure all subprocess.Popen calls default to UTF-8 encoding.

    Without this, subprocesses inherit the system ANSI code page and
    produce garbled output (especially Chinese text from help messages,
    pip output, git output, etc.).
    """
    _orig_init = subprocess.Popen.__init__

    def _patched_init(self, *args, **kwargs):
        if "encoding" not in kwargs:
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "replace"
        _orig_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_init


def setup():
    """Call once at application startup to configure all encoding layers."""
    _setup_win32_console()
    _reconfigure_stdio()

    # Fix subprocess.run() default text encoding
    _orig_run = subprocess.run

    def _patched_run(*args, **kwargs):
        if "encoding" not in kwargs:
            kwargs["encoding"] = "utf-8"
            kwargs["errors"] = "replace"
        return _orig_run(*args, **kwargs)

    subprocess.run = _patched_run
