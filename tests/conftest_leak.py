"""Global state leak detector for pytest.

Detects which modules' global state was modified during a test module's
execution, producing actionable reports for flaky-test triage.

Usage:
    pytest --leak-report
    pytest --leak-report --leak-verbose  # show all modules, not just dirty ones
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

# ── Known global state holders and their snapshot keys ──

_LEAK_TARGETS: list[tuple[str, str, Callable[[], Any]]] = []


def _register(module_name: str, attr: str) -> None:
    """Register a module attribute to monitor for leaks."""

    def _snap() -> Any:
        try:
            mod = importlib.import_module(module_name)
            val = getattr(mod, attr, None)
            if val is None:
                return None
            if hasattr(val, "copy"):
                return val.copy() if isinstance(val, dict) else val
            if isinstance(val, (list, set)):
                return type(val)(val)
            if hasattr(val, "__dict__"):
                return dict(val.__dict__)
            return str(val)[:200]
        except Exception:
            return None

    _LEAK_TARGETS.append((module_name, attr, _snap))


# Register all known global-state holders
# (subset that is safe to snapshot without triggering side effects)
_register("core.tool_router", "_internal_tools")
_register("core.tool_router", "_mcp_tools")
_register("core.background", "_bg_manager")
_register("core.provider", "_mgr")
_register("core.pipeline_tools", "OUTPUT_ROOT")
_register("core.pipeline_tools", "MANIFEST_DIR")
_register("core.chat_prompt", "_cache")
_register("core.tool_cache", "_cache_singleton")
_register("core.agent_cache", "_cache")
_register("core.workspace_guard", "_cached_workspace")
_register("core.secret_redactor", "_cached_keys")
_register("core.skills", "_manager")
_register("core.permission", "_permission_manager")
_register("core.hooks", "hook_manager")
_register("core.plan_mode", "_plan_mode_manager")
_register("core.marketplace", "_marketplace")
_register("core.mcp_client", "_mcp_client")


class LeakDetector:
    """Snapshot → compare → report pattern for global state leak detection."""

    def __init__(self):
        self._before: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        """Take a snapshot of all registered global state."""
        snap = {}
        for module_name, attr, getter in _LEAK_TARGETS:
            key = f"{module_name}.{attr}"
            try:
                snap[key] = getter()
            except Exception:
                snap[key] = None
        return snap

    def compare(self, before: dict, after: dict) -> list[str]:
        """Find keys that changed between snapshots. Returns list of dirty keys."""
        dirty = []
        for key in before:
            b = before[key]
            a = after.get(key)
            if b != a:
                dirty.append(key)
        return dirty

    def report(self, dirty: list[str], verbose: bool = False) -> str:
        """Generate human-readable leak report."""
        if not dirty:
            return "[LEAK] No global state leaks detected"
        lines = [f"[LEAK] {len(dirty)} module(s) modified during test:"]
        for key in dirty:
            lines.append(f"  {key}")
        if verbose:
            lines.append(f"  (monitoring {len(_LEAK_TARGETS)} targets total)")
        return "\n".join(lines)


# Singleton for conftest use
_detector = LeakDetector()


def get_detector() -> LeakDetector:
    return _detector


# ── CLI entry point ──

if __name__ == "__main__":
    d = LeakDetector()
    snap1 = d.snapshot()
    print(f"Snapshot 1: {len(snap1)} targets")
    # Simulate some state change
    import core.tool_router as tr

    tr._internal_tools["__test_dummy__"] = lambda: None
    snap2 = d.snapshot()
    dirty = d.compare(snap1, snap2)
    print(d.report(dirty, verbose=True))
    # Clean up
    del tr._internal_tools["__test_dummy__"]
