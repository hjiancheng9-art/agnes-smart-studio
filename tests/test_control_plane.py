"""ControlPlane 单元测试 — ControlQueue / PendingOutbox / RunState / ToolRegistry"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestControlQueue:
    def test_push_and_poll(self):
        from core.control_plane import ControlEvent, ControlEventType, ControlQueue
        q = ControlQueue()
        q.push(ControlEvent(type=ControlEventType.INTERRUPT))
        assert q.has_events()
        ev = q.poll()
        assert ev is not None
        assert ev.type == ControlEventType.INTERRUPT
        assert not q.has_events()

    def test_priority_ordering(self):
        from core.control_plane import ControlEvent, ControlEventType, ControlQueue
        q = ControlQueue()
        q.push(ControlEvent(type=ControlEventType.PAUSE, priority=1))
        q.push(ControlEvent(type=ControlEventType.CANCEL, priority=2))
        q.push(ControlEvent(type=ControlEventType.PRIORITY_MESSAGE, priority=3))
        e1 = q.poll()
        e2 = q.poll()
        e3 = q.poll()
        assert e1.type == ControlEventType.PRIORITY_MESSAGE  # highest
        assert e2.type == ControlEventType.CANCEL
        assert e3.type == ControlEventType.PAUSE

    def test_peek_does_not_remove(self):
        from core.control_plane import ControlEventType, ControlQueue
        q = ControlQueue()
        q.push(type=ControlEventType.INTERRUPT)
        peek = q.peek()
        assert peek is not None
        assert q.has_events()
        poll = q.poll()
        assert poll is not None
        assert not q.has_events()

    def test_clear(self):
        from core.control_plane import ControlEventType, ControlQueue
        q = ControlQueue()
        q.push(type=ControlEventType.INTERRUPT)
        q.push(type=ControlEventType.PAUSE)
        q.clear()
        assert not q.has_events()

    def test_remove_by_id(self):
        from core.control_plane import ControlEvent, ControlEventType, ControlQueue
        q = ControlQueue()
        ev = ControlEvent(type=ControlEventType.INTERRUPT)
        q.push(ev)
        assert q.has_events()
        q.remove(ev.id)
        assert not q.has_events()


class TestPendingOutbox:
    def test_stage_and_commit(self):
        from core.control_plane import PendingOutbox
        outbox = PendingOutbox()
        msg = outbox.stage("hello")
        assert msg.state.value == "pending"
        committed = False
        def on_commit(m):
            nonlocal committed
            committed = True
        outbox.on_commit(on_commit)
        ok = outbox.commit(msg.id)
        assert ok
        assert msg.state.value == "committed"
        assert committed

    def test_retract_during_pending(self):
        from core.control_plane import PendingOutbox
        outbox = PendingOutbox()
        msg = outbox.stage("undo me")
        ok = outbox.retract(msg.id)
        assert ok
        assert msg.state.value == "retracted"

    def test_commit_invalid_id(self):
        from core.control_plane import PendingOutbox
        outbox = PendingOutbox()
        ok = outbox.commit("nonexistent")
        assert not ok

    def test_has_pending(self):
        from core.control_plane import PendingOutbox
        outbox = PendingOutbox()
        assert not outbox.has_pending()
        outbox.stage("hi")
        assert outbox.has_pending()
        for m in outbox.get_pending():
            outbox.commit(m.id)
        assert not outbox.has_pending()

    def test_undo_window_configurable(self):
        from core.control_plane import PendingOutbox
        assert PendingOutbox.UNDO_WINDOW_MS == 2000


class TestRunStateManager:
    def test_initial_idle(self):
        from core.control_plane import RunStateManager
        r = RunStateManager()
        assert r.is_idle
        assert not r.is_running

    def test_start_and_complete_run(self):
        from core.control_plane import RunStateManager
        r = RunStateManager()
        assert r.start_run("test-1")
        assert r.is_running
        assert r.complete_run()
        assert r.is_idle

    def test_pause_and_resume(self):
        from core.control_plane import RunState, RunStateManager
        r = RunStateManager()
        r.start_run()
        assert r.request_pause()
        assert r.state == RunState.PAUSING
        r.resume()
        assert r.is_running

    def test_cancel_run(self):
        from core.control_plane import RunState, RunStateManager
        r = RunStateManager()
        r.start_run()
        assert r.request_cancel()
        assert r.state == RunState.CANCELLING

    def test_invalid_transition_start_twice(self):
        from core.control_plane import RunStateManager
        r = RunStateManager()
        assert r.start_run()
        assert not r.start_run()

    def test_check_control_with_event(self):
        from core.control_plane import ControlEventType, ControlQueue, RunState, RunStateManager
        r = RunStateManager()
        q = ControlQueue()
        r.start_run("test")
        q.push(type=ControlEventType.CANCEL)
        ev = r.check_control(q)
        assert ev is not None
        assert r.state == RunState.CANCELLING

    def test_state_change_callback(self):
        from core.control_plane import RunState, RunStateManager
        r = RunStateManager()
        changes = []
        r.on_state_change(lambda old, new: changes.append((old, new)))
        r.start_run("cb-test")
        assert len(changes) == 1
        assert changes[0][1] == RunState.RUNNING


class TestToolInterruptRegistry:
    def test_defaults_loaded(self):
        from core.control_plane import get_control
        cp = get_control()
        t = cp.tools.get("pip_install")
        assert t.mode == "kill_process"
        t2 = cp.tools.get("patch_file")
        assert t2.mode == "cooperative"
        t3 = cp.tools.get("generate_image")
        assert t3.mode == "not_interruptible"

    def test_unknown_tool_defaults_cooperative(self):
        from core.control_plane import get_control
        cp = get_control()
        t = cp.tools.get("nonexistent_tool")
        assert t.mode == "cooperative"


class TestControlPlaneFlow:
    def test_send_and_retract(self):
        from core.control_plane import get_control
        cp = get_control()
        msg = cp.send_message("delete all")
        assert cp.get_pending_timer() > 0
        ok = cp.retract(msg.id)
        assert ok
        assert msg.state.value == "retracted"
        assert cp.get_pending_timer() == 0

    def test_priority_message_flow(self):
        from core.control_plane import get_control
        cp = get_control()
        cp.priority_message("urgent question")
        assert cp.queue.has_events()
        ev = cp.queue.poll()
        assert ev.type.value == "priority_message"
        assert "urgent" in ev.payload.get("text", "")

    def test_get_status_line(self):
        from core.control_plane import get_control
        cp = get_control()
        # Reset to clean state
        cp.runs.complete_run()
        cp.queue.clear()
        status = cp.get_status_line()
        assert isinstance(status, str)
        assert len(status) >= 0
