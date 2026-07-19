"""Global error handler — catches unhandled exceptions at CLI boundaries
and converts them to user-readable messages with actionable suggestions.

Usage:
    from core.error_handler import friendly_exit
    friendly_exit(lambda: main())  # wraps main, catches everything
"""

from __future__ import annotations

import sys
import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Error classification + suggestion mapping ──────────

_ERROR_PATTERNS: list[tuple[str, str, str | None]] = [
    # (keyword, short description, suggested fix)
    ("DEEPSEEK_API_KEY", "DeepSeek API key is not set", "Run: crux init  OR  set DEEPSEEK_API_KEY in your environment"),
    ("module 'core.", "Missing Python dependency", "Run: pip install -r requirements.txt"),
    ("ModuleNotFoundError: No module named '", "Missing Python package", "Run: pip install <package>"),
    ("Connection refused", "Network connection failed", "Check your internet connection and firewall settings"),
    ("ConnectionError", "Network is unreachable", "Check if you are behind a proxy or VPN"),
    ("Permission denied", "File permission error", "Check file permissions or run from a different directory"),
    (
        "FileNotFoundError",
        "Required file not found",
        "Run from the project root directory, or reinstall with: pip install -e .",
    ),
    (
        "SyntaxError",
        "Code syntax error",
        "A recent code change introduced a syntax error. Run: python core/self_heal.py --fix",
    ),
    ("ImportError", "Import failed", "Run: pip install -r requirements.txt  OR  check PYTHONPATH"),
    ("KeyboardInterrupt", "Interrupted by user", None),  # special case: no suggestion needed
    ("OutOfMemoryError", "Out of memory", "Close other applications or reduce data size"),
    ("DiskFull", "Disk is full", "Free up disk space and try again"),
]


def classify_error(exc: BaseException) -> tuple[str, str | None]:
    """Given an exception, return (description, suggestion)."""
    exc_name = type(exc).__name__
    tb_str = "".join(traceback.format_exception_only(type(exc), exc))
    combined = f"{exc_name}: {exc} {tb_str}"

    for keyword, desc, suggestion in _ERROR_PATTERNS:
        if keyword.lower() in combined.lower():
            return desc, suggestion

    return f"{exc_name}: {exc}", "Check the error above and try again, or run: python core/self_heal.py"


def friendly_exit(fn: Callable[[], Any], *, debug: bool = False) -> int:
    """Wrap a main() function with human-readable error handling.

    Returns exit code: 0 on success, 1 on error.
    """
    try:
        fn()
        return 0
    except KeyboardInterrupt:
        print("\n  Interrupted")
        return 130
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else int(bool(e.code))
    except BaseException as e:
        desc, suggestion = classify_error(e)
        print(f"\n  Error: {desc}", file=sys.stderr)
        if suggestion:
            print(f"  Fix:   {suggestion}", file=sys.stderr)
        if debug:
            traceback.print_exc()
        return 1


def friendly_main(fn: Callable[[list[str]], Any]) -> Callable[[], int]:
    """Decorator: wraps a main() that takes sys.argv and returns exit code."""

    def wrapper() -> int:
        try:
            result = fn(sys.argv[1:])
            return result if isinstance(result, int) else 0
        except KeyboardInterrupt:
            print("\n  Interrupted")
            return 130
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else int(bool(e.code))
        except BaseException as e:
            desc, suggestion = classify_error(e)
            print(f"\n  Error: {desc}", file=sys.stderr)
            if suggestion:
                print(f"  Fix:   {suggestion}", file=sys.stderr)
            return 1

    return wrapper
