"""Global crash guard — ensures every unhandled exception leaves a trace.

Pattern: Claude Code's stability model — when something breaks, you always know why.
Installed at startup via `install()` and writes crash reports to the incident store.
"""

import logging
import sys
import threading
import traceback

logger = logging.getLogger("crux.crash_guard")

_installed = False
_original_excepthook = None
_original_thread_excepthook = None


def _format_tb(exc_type, exc_value, exc_tb) -> str:
    """Format exception as a compact one-line summary + full traceback."""
    summary = f"{exc_type.__name__}: {exc_value}"
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    return summary + "\n" + "".join(tb_lines)


def _record_crash(report: str) -> None:
    """Write crash report to incident store (if available) and log."""
    logger.error("CRUX crash:\n%s", report)

    # Best-effort write to incident store
    try:
        from core.incident import save_incident

        save_incident(
            {
                "primary_category": "crash",
                "severities": {"critical": 1},
                "total_incidents": 1,
                "summary": report.split("\n")[0][:200],
                "recommendation": "Check traceback for root cause",
            }
        )
    except Exception:
        logger.debug("Cannot write crash to incident store", exc_info=True)


def _crash_handler(exc_type, exc_value, exc_tb) -> None:
    """sys.excepthook replacement — logs all unhandled exceptions."""
    # Skip KeyboardInterrupt (user-initiated)
    if exc_type is KeyboardInterrupt:
        if _original_excepthook:
            _original_excepthook(exc_type, exc_value, exc_tb)
        return

    report = _format_tb(exc_type, exc_value, exc_tb)
    _record_crash(report)

    # Attempt self-healing for code-level crashes
    _attempt_self_heal(exc_type, exc_value)

    # Call original hook if any
    if _original_excepthook:
        _original_excepthook(exc_type, exc_value, exc_tb)


def _attempt_self_heal(exc_type, exc_value) -> None:
    """Best-effort self-healing on crash.  Only for code-level errors."""
    try:
        if exc_type in (SyntaxError, ImportError, NameError, AttributeError, TypeError):
            from core.self_heal import SelfHealer
            h = SelfHealer()
            h.scan_syntax()
            h.scan_silent_exceptions()
            n = h.fix_silent_exceptions()
            h.quick_fix()
            if n > 0:
                logger.info("crash_guard: auto-fixed %d silent exceptions", n)
    except Exception:
        pass  # never let self-healing compound a crash


def _thread_crash_handler(args) -> None:
    """threading.excepthook replacement — catches crashes in non-main threads."""
    exc_type, exc_value, exc_tb = args.exc_type, args.exc_value, args.exc_traceback
    if exc_type is KeyboardInterrupt:
        return
    report = _format_tb(exc_type, exc_value, exc_tb)
    _record_crash(f"[thread:{args.thread.name}] {report}")


def install() -> None:
    """Install the global crash guard. Idempotent — safe to call multiple times."""
    global _installed, _original_excepthook, _original_thread_excepthook

    if _installed:
        return

    _original_excepthook = sys.excepthook
    _original_thread_excepthook = threading.excepthook

    sys.excepthook = _crash_handler
    threading.excepthook = _thread_crash_handler

    _installed = True
    logger.debug("Crash guard installed")


def uninstall() -> None:
    """Restore original exception hooks. For test isolation."""
    global _installed
    if _installed:
        sys.excepthook = _original_excepthook
        threading.excepthook = _original_thread_excepthook
        _installed = False
