"""Tests for core/chat.py — session snapshot, routing integration, edge cases."""

import json

from core.chat import ChatSession, _PipelineToolbus


class TestSessionSnapshot:
    def test_snapshot_saves_file(self, tmp_path):
        snap_dir = tmp_path / "sessions"
        snap_dir.mkdir()
        ChatSession._SNAPSHOT_DIR = snap_dir

        # Use a real ChatSession-like object with _SNAPSHOT_INTERVAL
        class FakeSession:
            model = "deepseek-v4-flash"
            messages = [{"role": "user", "content": "hello"}]
            _turn_count = 5
            _SNAPSHOT_INTERVAL = 5
            _SNAPSHOT_DIR = snap_dir

        fs = FakeSession()
        ChatSession._maybe_snapshot(fs)

        snap_file = snap_dir / "latest.json"
        assert snap_file.exists()
        data = json.loads(snap_file.read_text())
        assert data["model"] == "deepseek-v4-flash"
        assert data["turn"] == 5
        assert len(data["messages"]) > 0

    def test_restore_returns_none_when_no_snapshot(self, tmp_path):
        ChatSession._SNAPSHOT_DIR = tmp_path / "nonexistent_sessions"
        result = ChatSession.restore_latest_snapshot()
        assert result is None

    def test_restore_returns_data(self, tmp_path):
        snap_dir = tmp_path / "sessions"
        snap_dir.mkdir()
        ChatSession._SNAPSHOT_DIR = snap_dir
        (snap_dir / "latest.json").write_text(
            json.dumps(
                {
                    "model": "pro",
                    "turn": 3,
                    "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
                }
            )
        )
        result = ChatSession.restore_latest_snapshot()
        assert result is not None
        assert result["model"] == "pro"

    def test_snapshot_skips_when_not_interval(self, tmp_path):
        snap_dir = tmp_path / "sessions"
        snap_dir.mkdir()
        ChatSession._SNAPSHOT_DIR = snap_dir

        class FakeSession:
            model = "flash"
            messages = [{"role": "user", "content": "x"}]
            _turn_count = 3  # not a multiple of 5
            _SNAPSHOT_INTERVAL = 5
            _SNAPSHOT_DIR = snap_dir

        ChatSession._maybe_snapshot(FakeSession())
        assert not (snap_dir / "latest.json").exists()


class TestPipelineToolbus:
    def test_call_dispatches(self):
        import asyncio

        calls = []

        def dispatch(name, args_json):
            calls.append((name, args_json))
            return (f"ok: {name}", [])

        tb = _PipelineToolbus(dispatch, None)
        result = asyncio.run(tb.call("read_file", {"path": "test.py"}))
        assert "ok: read_file" in result
        assert len(calls) == 1
        assert calls[0][0] == "read_file"

    def test_list_tools_returns_list(self):
        class FakeRegistry:
            _executors = {"a": None, "b": None, "c": None}

        tb = _PipelineToolbus(lambda n, a: ("", []), FakeRegistry())
        tools = tb.list_tools()
        assert set(tools) == {"a", "b", "c"}

    def test_list_tools_handles_missing_registry(self):
        tb = _PipelineToolbus(lambda n, a: ("", []), None)
        tools = tb.list_tools()
        assert tools == []


class TestDefaultModel:
    def test_resolves_to_light(self):
        model = ChatSession._resolve_default_model()
        assert "flash" in model.lower() or "light" in model.lower()


class TestRecordTraceFailure:
    def test_does_not_crash(self):
        """_record_trace_failure should never raise, even without a real session."""

        class FakeSession:
            _last_user_text = "test"
            _intel_mode = "BALANCED"

        fs = FakeSession()
        # Should not raise
        ChatSession._record_trace_failure(fs, "test error", step_name="test")
