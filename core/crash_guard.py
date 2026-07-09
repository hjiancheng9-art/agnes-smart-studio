"""Global crash guard — ensures every unhandled exception leaves a trace.

Pattern: Claude Code's stability model — when something breaks, you always know why.
Installed at startup via `install()` and writes crash reports to the incident store.
"""

import logging
import sys
import threading
import traceback
from datetime import datetime, timezone

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
        from core.incident_store import record_incident

        record_incident(
            category="crash",
            severity="critical",
            summary=report.split("\n")[0][:200],
            details={"traceback": report[:4000]},
            timestamp=datetime.now(timezone.utc).isoformat(),
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

    # Call original hook if any
    if _original_excepthook:
        _original_excepthook(exc_type, exc_value, exc_tb)


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
