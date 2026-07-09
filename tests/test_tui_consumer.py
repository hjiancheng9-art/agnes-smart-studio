"""
Tests for TUI Consumer — RunStateStore / EventReducer / Dispatcher / ConfirmBridge / Watchdog
"""
import time

import pytest

from core.stream_protocol import StreamEvent
from ui.tui_confirm_bridge import ConfirmBridge
from ui.tui_dispatcher import TuiDispatcher, TuiRenderer
from ui.tui_event_reducer import TuiEventReducer
from ui.tui_run_state import RunStateStore
from ui.tui_stream_watchdog import StreamWatchdog


class TestRunStateStore:
    def test_get_or_create(self):
        store = RunStateStore()
        state = store.get("r1")
        assert state.run_id == "r1"
        assert state.status == "STARTED"
        assert state.is_streaming is True

    def test_update(self):
        store = RunStateStore()
        store.update("r1", status="RUNNING", phase="routing")
        state = store.get("r1")
        assert state.status == "RUNNING"
        assert state.phase == "routing"

    def test_finish(self):
        store = RunStateStore()
        state = store.finish("r1")
        assert state.is_streaming is False
        assert state.status == "DONE"

    def test_error(self):
        store = RunStateStore()
        state = store.error("r1", "test error")
        assert state.is_streaming is False
        assert state.error == "test error"

    def test_get_active(self):
        store = RunStateStore()
        store.get("active1")
        store.get("active2")
        store.finish("done1")
        assert len(store.get_active()) == 2

    def test_cleanup(self):
        store = RunStateStore()
        store.finish("old1")
        store.finish("old2")
        store.get("still_active")
        cleaned = store.cleanup(max_age=-1)
        assert cleaned >= 2

    def test_stats(self):
        store = RunStateStore()
        store.get("r1")
        store.get("r2")
        store.finish("r1")
        stats = store.stats()
        assert stats["total"] >= 2

    def test_max_runs(self):
        store = RunStateStore(max_runs=3)
        store.get("r1")
        store.get("r2")
        store.get("r3")
        store.finish("r1")
        store.get("r4")  # should evict r1
        assert len(store.runs) <= 3


class FakeRenderer(TuiRenderer):
    """假渲染器 — 记录收到的 action"""
    def __init__(self):
        self.actions = []

    def _log(self, **kw):
        self.actions.append(kw)

    def render_message(self, run_id, text): self._log(type="message", run_id=run_id, text=text)
    def render_stream_start(self, run_id, message): self._log(type="stream_start", run_id=run_id)
    def render_stream_end(self, run_id, message): self._log(type="stream_end", run_id=run_id)
    def render_error(self, run_id, error): self._log(type="error", run_id=run_id, error=error)
    def render_status(self, run_id, status, phase, message): self._log(type="status", run_id=run_id, status=status)
    def render_confirm(self, confirm_id, tool, message, risk): self._log(type="confirm", confirm_id=confirm_id)
    def render_info(self, run_id, message): self._log(type="info", run_id=run_id)
    def render_media(self, run_id, media_type, payload): self._log(type="media", run_id=run_id)
    def render_intel_analysis(self, run_id, payload): self._log(type="intel", run_id=run_id)
    def render_tool_start(self, run_id, tool, args): self._log(type="tool_start", run_id=run_id)
    def render_tool_result(self, run_id, tool, result): self._log(type="tool_result", run_id=run_id)
    def render_final(self, run_id, content): self._log(type="final", run_id=run_id)
    def invalidate(self): self._log(type="invalidate")


class TestTuiEventReducer:
    def setup_method(self):
        self.store = RunStateStore()
        self.reducer = TuiEventReducer(self.store)

    def make_event(self, kind, run_id="r1", message=""):
        return StreamEvent(run_id=run_id, kind=kind, payload={"message": message, "run_id": run_id})

    def test_stream_start_creates_state(self):
        event = self.make_event("stream_start")
        action = self.reducer.reduce(event)
        assert action["type"] == "stream_start"
        state = self.store.get("r1")
        assert state.is_streaming is True

    def test_stream_end_marks_done(self):
        self.reducer.reduce(self.make_event("stream_start"))
        action = self.reducer.reduce(self.make_event("stream_end"))
        assert action["type"] == "stream_end"
        state = self.store.get("r1")
        assert state.is_streaming is False
        assert state.status == "DONE"

    def test_text_produces_append(self):
        event = StreamEvent(run_id="r1", kind="text", payload={"message": "hello"})
        action = self.reducer.reduce(event)
        assert action["type"] == "append_text"
        assert "hello" in action["text"]

    def test_error_marks_state(self):
        event = StreamEvent(run_id="r1", kind="error", payload={"message": "fail"})
        action = self.reducer.reduce(event)
        assert action["type"] == "error"
        state = self.store.get("r1")
        assert state.is_streaming is False

    def test_confirm_produces_confirm_action(self):
        event = StreamEvent(run_id="r1", kind="confirm",
                            payload={"confirm_id": "c1", "tool": "write", "message": "ok?", "risk": "low"})
        action = self.reducer.reduce(event)
        assert action["type"] == "confirm"
        assert action["confirm_id"] == "c1"

    def test_unknown_kind_fallsback_to_info(self):
        event = StreamEvent(run_id="r1", kind="weird_stuff", payload={"message": "data"})
        action = self.reducer.reduce(event)
        assert action["type"] == "info"

    def test_two_runs_dont_mix(self):
        store = RunStateStore()
        reducer = TuiEventReducer(store)

        reducer.reduce(StreamEvent(run_id="r1", kind="stream_start", payload={"run_id": "r1"}))
        reducer.reduce(StreamEvent(run_id="r2", kind="stream_start", payload={"run_id": "r2"}))

        reducer.reduce(StreamEvent(run_id="r1", kind="error", payload={"run_id": "r1", "message": "r1 fail"}))
        reducer.reduce(StreamEvent(run_id="r2", kind="stream_end", payload={"run_id": "r2"}))

        assert store.get("r1").is_streaming is False  # errored
        assert store.get("r2").is_streaming is False  # finished
        assert "r1 fail" in store.get("r1").error


class TestTuiDispatcher:
    def test_dispatch_text(self):
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        dispatcher.dispatch({"type": "append_text", "run_id": "r1", "text": "hello"})
        assert len(renderer.actions) >= 1
        assert renderer.actions[-1]["type"] == "message"

    def test_dispatch_confirm(self):
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        dispatcher.dispatch({"type": "confirm", "run_id": "r1", "confirm_id": "c1", "message": "ok?"})
        assert any(a["type"] == "confirm" for a in renderer.actions)

    def test_dispatch_error(self):
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        dispatcher.dispatch({"type": "error", "run_id": "r1", "error": "fail"})
        assert any(a["type"] == "error" for a in renderer.actions)

    def test_dispatch_batch_invalidates_once(self):
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        dispatcher.dispatch_batch([
            {"type": "append_text", "run_id": "r1", "text": "a"},
            {"type": "append_text", "run_id": "r1", "text": "b"},
            {"type": "stream_end", "run_id": "r1"},
        ])
        invalidates = [a for a in renderer.actions if a["type"] == "invalidate"]
        assert len(invalidates) == 1

    def test_unknown_action_becomes_info(self):
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        dispatcher.dispatch({"type": "unknown_xxx", "run_id": "r1"})
        assert any(a["type"] == "info" for a in renderer.actions)


class TestConfirmBridge:
    def test_resolve_approved(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)
        req = cm.create("write", "ok?")
        assert bridge.resolve(req.confirm_id, True) is True
        assert req.result.value == "confirmed"

    def test_resolve_denied(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)
        req = cm.create("write", "ok?")
        assert bridge.resolve(req.confirm_id, False) is True
        assert req.result.value == "denied"

    def test_cancel(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)
        req = cm.create("write", "ok?")
        assert bridge.cancel(req.confirm_id) is True
        assert req.result.value == "cancelled"

    def test_get_pending(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)
        cm.create("write", "ok?")
        pending = bridge.get_pending()
        assert len(pending) == 1
        assert pending[0]["tool"] == "write"


class TestStreamWatchdog:
    def test_timeout_detection(self):
        store = RunStateStore()
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        watchdog = StreamWatchdog(store, dispatcher, timeout_sec=0.1)

        store.get("r1")  # created, is_streaming=True
        # Manually set last_event_at to far in past
        state = store.get("r1")
        state.last_event_at = time.time() - 10

        actions = watchdog.tick()
        assert len(actions) >= 1
        assert actions[0]["type"] == "error"
        assert "timeout" in actions[0]["error"]

    def test_no_timeout_for_active(self):
        store = RunStateStore()
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        watchdog = StreamWatchdog(store, dispatcher, timeout_sec=9999)

        store.get("r1")
        actions = watchdog.tick()
        assert len(actions) == 0  # not timed out

    def test_no_timeout_for_finished(self):
        store = RunStateStore()
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        watchdog = StreamWatchdog(store, dispatcher, timeout_sec=0.1)

        store.finish("r1")  # not streaming
        state = store.get("r1")
        state.last_event_at = time.time() - 10

        actions = watchdog.tick()
        assert len(actions) == 0  # finished, should not timeout

    def test_run_loop_integrates(self):
        store = RunStateStore()
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)
        watchdog = StreamWatchdog(store, dispatcher, timeout_sec=0.1)

        state = store.get("r1")
        state.last_event_at = time.time() - 10
        watchdog.run_loop()
        assert any(a["type"] == "error" for a in renderer.actions)


class TestFullTuiPipeline:
    """完整 TUI 消费链路测试"""

    def test_reduce_dispatch_flow(self):
        store = RunStateStore()
        reducer = TuiEventReducer(store)
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)

        events = [
            StreamEvent(run_id="t1", kind="stream_start", payload={"run_id": "t1"}),
            StreamEvent(run_id="t1", kind="text", payload={"run_id": "t1", "message": "hello"}),
            StreamEvent(run_id="t1", kind="status", payload={"run_id": "t1", "status": "running", "phase": "plan"}),
            StreamEvent(run_id="t1", kind="confirm", payload={"run_id": "t1", "confirm_id": "c1", "tool": "write", "message": "ok?"}),
            StreamEvent(run_id="t1", kind="stream_end", payload={"run_id": "t1"}),
        ]

        for event in events:
            action = reducer.reduce(event)
            dispatcher.dispatch(action)

        # Verify all rendered
        types = [a["type"] for a in renderer.actions]
        assert "stream_start" in types
        assert "message" in types
        assert "confirm" in types
        assert "stream_end" in types

    def test_unknown_events_dont_crash(self):
        store = RunStateStore()
        reducer = TuiEventReducer(store)
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)

        raw_events = [
            ("text", "hi"),
            ("unknown_kind", "blah"),
            ("status", {"status": "ok"}),
            ("", ""),
        ]

        for kind, payload in raw_events:
            try:
                event = StreamEvent(run_id="t1", kind=kind, payload={"message": str(payload)})
                action = reducer.reduce(event)
                dispatcher.dispatch(action)
            except Exception:
                pytest.fail(f"Event ({kind}, {payload}) crashed the pipeline")

        assert True  # didn't crash

    def test_confirm_approve_resolves_backend(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)

        # TUI receives confirm
        req = cm.create("write_file", "确认写入?")

        # TUI shows dialog, user approves
        result = bridge.resolve(req.confirm_id, True)
        assert result is True
        assert req.result.value == "confirmed"

    def test_confirm_deny(self):
        from core.confirm_manager import ConfirmManager
        cm = ConfirmManager()
        bridge = ConfirmBridge(cm)

        req = cm.create("delete", "确认删除?")
        result = bridge.resolve(req.confirm_id, False)
        assert result is True
        assert req.result.value == "denied"

    def test_two_run_ids_no_crosstalk(self):
        store = RunStateStore()
        reducer = TuiEventReducer(store)
        renderer = FakeRenderer()
        dispatcher = TuiDispatcher(renderer)

        # Interleaved events from two runs
        events = [
            StreamEvent(run_id="rA", kind="stream_start", payload={"run_id": "rA"}),
            StreamEvent(run_id="rB", kind="stream_start", payload={"run_id": "rB"}),
            StreamEvent(run_id="rA", kind="text", payload={"run_id": "rA", "message": "A's message"}),
            StreamEvent(run_id="rB", kind="text", payload={"run_id": "rB", "message": "B's message"}),
            StreamEvent(run_id="rA", kind="error", payload={"run_id": "rA", "message": "A failed"}),
            StreamEvent(run_id="rB", kind="stream_end", payload={"run_id": "rB"}),
        ]

        for event in events:
            action = reducer.reduce(event)
            dispatcher.dispatch(action)

        assert store.get("rA").is_streaming is False  # errored
        assert store.get("rB").is_streaming is False  # finished
        assert store.get("rA").status == "ERROR"
        assert store.get("rB").status == "DONE"
