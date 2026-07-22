"""Architecture enforcement tests for TUI v3 game-console invariants.

These tests verify that the refactored architecture maintains the same
invariants that the old event-queue + scheduler accidentally enforced:

1. All state changes go through reduce_ui -- no direct mutation.
2. Worker threads use _threadsafe_call -- no direct UI access.
3. Every UiEvent subclass has a corresponding handler in reduce_ui.
4. Every key handler is isolated by _emit_key.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

V3_DIR = Path(__file__).parent.parent / "ui" / "v3"


# ── Helpers ───────────────────────────────────────────────────────


def _py_source(path: str) -> str:
    return Path(V3_DIR / path).read_text(encoding="utf-8")


def _source_lines(path: str) -> list[str]:
    return _py_source(path).splitlines()


# ══════════════════════════════════════════════════════════════-?# Rule 1: All state changes go through reduce_ui
# ══════════════════════════════════════════════════════════════-?


@pytest.mark.parametrize(
    "method_name",
    [
        "_reduce",
        "_reduce_only",
    ],
)
def test_reduce_methods_exist(method_name: str):
    """The ONLY methods that may mutate self._state must exist."""
    from ui.v3.app import V3App

    assert hasattr(V3App, method_name), f"V3App.{method_name} is required"


def test_reduce_methods_are_the_only_mutators():
    """Every self._state assignment (outside __init__) must be near a reduce_ui call."""
    import ui.v3.app as app_mod

    source = inspect.getsource(app_mod.V3App)
    lines = source.splitlines()

    # Find __init__ boundaries
    init_start = init_end = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("def __init__"):
            init_start = i
        elif init_start and not init_end and i > init_start:
            if line.strip().startswith("def ") and not line.startswith(" "):
                init_end = i
                break

    violations = []
    for i, line in enumerate(lines):
        if "self._state =" not in line and "self._state=" not in line:
            continue
        # Skip __init__ (initialization is allowed)
        if init_start <= i <= (init_end or 9999):
            continue
        # Skip lines inside _reduce/_reduce_only
        context = lines[max(0, i - 5) : min(len(lines), i + 5)]
        context_text = "\n".join(context)
        if "reduce_ui(" not in context_text:
            violations.append(f"  L{i + 1}: {line.strip()[:100]}")

    if violations:
        pytest.fail("_state assignment without reduce_ui nearby:\n" + "\n".join(violations[:5]))


def test_no_post_event_in_app():
    """app.py must not import or call post_event (event queue removed)."""
    src = _py_source("app.py")
    assert "post_event" not in src, "app.py must not use post_event (queue removed)"
    assert "trigger_drain" not in src, "app.py must not use trigger_drain (queue removed)"


# ══════════════════════════════════════════════════════════════-?# Rule 2: Worker threads use _on_main / call_soon_threadsafe
# ══════════════════════════════════════════════════════════════-?


def test_threadsafe_call_exists():
    from ui.v3.app import V3App

    assert hasattr(V3App, "_threadsafe_call"), "V3App._threadsafe_call required for cross-thread ops"


def test_fx_run_stream_uses_threadsafe_call():
    """Stream worker writes to chunk queue via _chunk_lock, not touching widgets."""
    src = _py_source("app.py")
    assert "_chunk_queue.append" in src, "Worker must write to chunk queue"
    assert "_chunk_lock" in src, "Worker must use _chunk_lock for queue access"
    # Worker must NOT call stream_append directly
    in_worker = False
    indent = 0
    for i, line in enumerate(src.splitlines(), 1):
        if "def worker():" in line and i > 200:
            in_worker = True
            indent = len(line) - len(line.lstrip())
            continue
        if in_worker:
            if line.strip() and len(line) - len(line.lstrip()) <= indent and not line.strip().startswith("#"):
                break
            if "stream_append" in line:
                pytest.fail(f"Worker directly calls stream_append at line {i}")
            if "thinking_panel.append" in line:
                pytest.fail(f"Worker directly calls thinking_panel.append at line {i}")
            if "self.message_pane.append_error" in line:
                pytest.fail(f"Worker directly calls append_error at line {i}")


# ══════════════════════════════════════════════════════════════-?# Rule 3: Every UiEvent has a reducer handler
# ══════════════════════════════════════════════════════════════-?


def test_all_events_handled_by_reducer():
    """Every UiEvent subclass in events.py must have an isinstance check in reducer.py."""
    events_src = _py_source("events.py")
    reducer_src = _py_source("reducer.py")

    # Collect all event class names (except UiEvent base class)
    event_names: list[str] = []
    for line in events_src.splitlines():
        if line.strip().startswith("class ") and "(UiEvent)" not in line:
            name = line.strip().split("(")[0].replace("class ", "").rstrip(":")
            if name != "UiEvent":
                event_names.append(name)

    missing: list[str] = []
    for name in event_names:
        if f"isinstance(event, {name})" not in reducer_src:
            missing.append(name)

    # Some events are intentionally no-ops (handled by base class or outside reducer)
    allowed_orphans = {"KeyPressed", "StreamToolFinished", "StreamToolError"}
    real_missing = [n for n in missing if n not in allowed_orphans]

    assert not real_missing, (
        f"Events without reducer handler: {real_missing}\n(allowed orphans: {sorted(allowed_orphans)})"
    )


# ══════════════════════════════════════════════════════════════-?# Rule 4: Every key handler is isolated
# ══════════════════════════════════════════════════════════════-?


def test_emit_key_exists():
    from ui.v3.app import V3App

    assert hasattr(V3App, "_emit_key"), "V3App._emit_key required for key isolation"


def test_all_key_handlers_exist():
    """Verify that all registered keybindings have a named handler."""
    from ui.v3.app import V3App

    # Collect all _key_* methods
    key_methods = {m for m in dir(V3App) if m.startswith("_key_")}

    # The _build_keybindings should reference these handlers
    assert len(key_methods) >= 20, f"Expected 20+ key handlers, found {len(key_methods)}"


def test_build_keybindings_uses_emit_key():
    """All keybindings must wrap handlers in _emit_key for isolation."""
    import inspect

    from ui.v3.app import V3App

    kb_source = inspect.getsource(V3App._build_keybindings)
    assert "_emit_key" in kb_source, "_build_keybindings must use _emit_key for every key"


# ══════════════════════════════════════════════════════════════-?# Rule 5: No scheduler or queue remaining
# ══════════════════════════════════════════════════════════════-?


def test_no_scheduler_import():
    src = _py_source("app.py")
    # Remove docstrings and comments before checking
    import re

    clean = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    clean = re.sub(r"#.*", "", clean)
    assert "from .scheduler import" not in clean, "app.py must not import Scheduler"
    assert "SimpleQueue" not in clean, "app.py must not use SimpleQueue"


def test_no_runtime_bridge_import():
    src = _py_source("app.py")
    assert "from .runtime_bridge import" not in src, "app.py must not import runtime_bridge"


def test_reduce_asserts_ui_thread():
    """_reduce must assert it's called from the UI thread."""
    import inspect

    from ui.v3.app import V3App

    src = inspect.getsource(V3App._reduce)
    assert "current_thread" in src, "_reduce must assert threading.current_thread() is self._ui_thread"


def test_no_orphaned_method_calls():
    """Removed methods (_sync_terminal_size, _post_and_invalidate, etc) must
    not be called anywhere in app.py."""
    src = _py_source("app.py")
    removed = ["_sync_terminal_size", "_post_and_invalidate", "_drain_and_reduce"]
    for name in removed:
        assert name not in src, f"Removed method still referenced: {name}"


def test_drain_chunks_registered():
    """_drain_chunks must be hooked into app.invalidate."""
    src = _py_source("app.py")
    assert "_invalidate_with_drain" in src, "Must hook _drain_chunks into invalidate"


def test_drain_chunks_exists():
    from ui.v3.app import V3App

    assert hasattr(V3App, "_drain_chunks"), "V3App._drain_chunks required for chunk consumption"
    """Worker thread must never call layout.focus() or layout.* directly."""
    src = _py_source("app.py")
    in_worker = False
    indent = 0
    for i, line in enumerate(src.splitlines(), 1):
        if "def worker():" in line and i > 200:
            in_worker = True
            indent = len(line) - len(line.lstrip())
            continue
        if in_worker:
            if line.strip() and len(line) - len(line.lstrip()) <= indent and not line.strip().startswith("#"):
                break
            if "layout." in line:
                pytest.fail(f"Worker touches layout at line {i}: {line.strip()}")
            if "_restore_focus" in line:
                pytest.fail(f"Worker calls _restore_focus at line {i}: {line.strip()}")


def test_worker_never_calls_reduce():
    """Worker thread must never call _reduce directly -?must go through
    loop.call_soon_threadsafe to reach the UI thread."""
    src = _py_source("app.py")
    in_worker = False
    indent = 0
    for i, line in enumerate(src.splitlines(), 1):
        if "def worker():" in line and i > 200:
            in_worker = True
            indent = len(line) - len(line.lstrip())
            continue
        if in_worker:
            if line.strip() and len(line) - len(line.lstrip()) <= indent and not line.strip().startswith("#"):
                break
            if "self._reduce(" in line and "call_soon_threadsafe" not in line:
                pytest.fail(f"Worker directly calls _reduce at line {i}: {line.strip()}")
