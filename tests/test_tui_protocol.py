"""
Tests for Stream Protocol, Confirm Manager, TUI Healthcheck — Phase 10
"""
import asyncio

from core.confirm_manager import ConfirmManager, ConfirmResult, get_confirm_manager
from core.stream_protocol import (
    KNOWN_KINDS,
    EventQueue,
    RunStatus,
    StreamEvent,
    make_error_event,
    make_status_event,
    normalize_event,
)
from core.tui_healthcheck import TuiBackendHealthcheck, quick_healthcheck


class TestStreamEvent:
    def test_from_text_tuple(self):
        e = StreamEvent.from_tuple(("text", "hello"), "r1")
        assert e.kind == "text"
        assert e.run_id == "r1"
        assert e.payload["message"] == "hello"

    def test_from_dict_payload(self):
        e = StreamEvent.from_tuple(("confirm", {"tool": "write", "message": "ok?"}), "r2")
        assert e.kind == "confirm"
        assert e.payload["tool"] == "write"

    def test_unknown_kind_fallback(self):
        e = StreamEvent.from_tuple(("weird_kind", "data"), "r3")
        assert e.kind == "info"  # fallback

    def test_auto_run_id(self):
        e = StreamEvent.from_tuple(("text", "hello"))
        assert len(e.run_id) == 12

    def test_to_status(self):
        e = StreamEvent.from_tuple(("text", "hello"), "r1")
        s = e.to_status(RunStatus.RUNNING, "working...")
        assert s.kind == "status"
        assert s.payload["status"] == "running"

    def test_normalize_event(self):
        e = normalize_event(("text", "hello"), "r1")
        assert e.kind == "text"
        assert isinstance(e, StreamEvent)

    def test_normalize_raw_event(self):
        e = normalize_event(StreamEvent(run_id="x", kind="text", payload={}))
        assert e.run_id == "x"


class TestEventQueue:
    def test_push_and_pop(self):
        q = EventQueue()
        e1 = StreamEvent(run_id="r1", kind="text", payload={})
        e2 = StreamEvent(run_id="r2", kind="info", payload={})
        q.push(e1)
        q.push(e2)
        assert q.size == 2
        events = q.pop_all()
        assert len(events) == 2
        assert q.empty

    def test_max_size(self):
        q = EventQueue(max_size=3)
        for i in range(5):
            q.push(StreamEvent(run_id=f"r{i}", kind="text", payload={}))
        assert q.size == 3  # oldest 2 dropped


class TestRunStatus:
    def test_all_statuses(self):
        statuses = [s.value for s in RunStatus]
        assert "started" in statuses
        assert "done" in statuses
        assert "error" in statuses
        assert "cancelled" in statuses
        assert "waiting_confirm" in statuses

    def test_status_helpers(self):
        e = make_status_event("run1", RunStatus.ROUTING, "routing")
        kind, payload = e
        assert kind == "status"
        assert payload["run_id"] == "run1"
        assert payload["status"] == "routing"

        e2 = make_error_event("run1", "tool timeout", "tool_timeout")
        kind2, payload2 = e2
        assert kind2 == "error"
        assert payload2["error"] == "tool timeout"


class TestConfirmManager:
    def setup_method(self):
        self.cm = ConfirmManager(default_timeout=0.5, default_action="deny")

    def test_create_request(self):
        req = self.cm.create("write_file", "确认写入？")
        assert req.tool == "write_file"
        assert req.message == "确认写入？"
        assert not req.is_resolved

    def test_respond(self):
        req = self.cm.create("test", "allow?")
        assert self.cm.respond(req.confirm_id, True)
        assert req.result == ConfirmResult.CONFIRMED
        assert req.is_resolved

    def test_respond_twice(self):
        req = self.cm.create("test", "allow?")
        self.cm.respond(req.confirm_id, True)
        assert not self.cm.respond(req.confirm_id, False)  # already resolved

    def test_timeout(self):
        async def run():
            cm = ConfirmManager(default_timeout=0.5, default_action="deny")
            req = cm.create("test", "timeout test", timeout_seconds=0.1)
            result, reason = await cm.wait(req.confirm_id)
            return result, reason
        result, reason = asyncio.run(run())
        assert result == ConfirmResult.TIMEOUT
        assert "超时" in reason

    def test_wait_with_response(self):
        async def run():
            cm = ConfirmManager(default_timeout=5.0)
            req = cm.create("test", "prompt", timeout_seconds=5.0)
            # Respond after a small delay
            asyncio.get_running_loop().call_later(0.1, lambda: cm.respond(req.confirm_id, True))
            result, _ = await cm.wait(req.confirm_id)
            return result
        result = asyncio.run(run())
        assert result == ConfirmResult.CONFIRMED

    def test_cancel(self):
        req = self.cm.create("test", "cancel me")
        assert self.cm.cancel(req.confirm_id)
        assert req.result == ConfirmResult.CANCELLED

    def test_cancel_all(self):
        for _ in range(3):
            self.cm.create("test", "cancel")
        assert self.cm.cancel_all() == 3

    def test_get_pending(self):
        self.cm.create("test", "pending")
        assert len(self.cm.get_pending()) == 1

    def test_cleanup(self):
        req = self.cm.create("test", "old")
        self.cm.respond(req.confirm_id, True)
        # Force cleanup with negative max_age
        assert self.cm.cleanup(max_age=-1) >= 1

    def test_to_dict(self):
        req = self.cm.create("write", "ok?", risk="high")
        d = req.to_dict()
        assert d["tool"] == "write"
        assert d["risk"] == "high"

    def test_global_singleton(self):
        cm = get_confirm_manager()
        assert cm is not None


class TestTuiHealthcheck:
    def test_quick_healthcheck(self):
        result = quick_healthcheck()
        assert result["overall"] in ("ok", "degraded")
        assert result["passed"] > 0

    def test_required_events(self):
        hc = TuiBackendHealthcheck()
        result = asyncio.run(hc.check_required_events())
        assert result.overall in ("ok", "degraded")

    def test_simulate_events(self):
        hc = TuiBackendHealthcheck()
        events = asyncio.run(hc._simulate_events())
        assert len(events) >= 5
        kinds = [e.kind for e in events]
        assert "stream_start" in kinds
        assert "text" in kinds
        assert "stream_end" in kinds

    def test_full_healthcheck(self):
        hc = TuiBackendHealthcheck()
        result = asyncio.run(hc.run())
        assert result.overall in ("ok", "degraded")
        assert result.duration >= 0


class TestKnownKinds:
    def test_required_kinds_present(self):
        required = {"text", "info", "status", "error", "confirm",
                     "stream_start", "stream_end", "intel_analysis",
                     "tool_start", "tool_result", "final", "image", "video"}
        for kind in required:
            assert kind in KNOWN_KINDS, f"Missing kind: {kind}"
