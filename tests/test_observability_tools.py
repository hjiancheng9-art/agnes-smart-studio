"""Tests for observability instrumentation on tool execution.

Covers:
  - async_chat.py tool_call loop TraceContext + metrics (structural check)
  - core/tools.py execute() TraceContext + metrics (error/success paths)
  - TraceContext nesting (tool_call -> registry_execute)
  - metrics counters integration
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))


class TestToolExecuteObservability:
    """ToolRegistry.execute() emits TraceContext span + metrics."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """Patch tools config and observability log to isolated temp."""
        self.tmp_path = tmp_path
        # Point TOOLS_CONFIG to temp (no external tools loaded)
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp_path / "tools.json")
        # Point observability log to temp
        self.log_file = tmp_path / "traces.jsonl"
        yield

    def _write_tools(self, tmp_path, tools_list):
        (tmp_path / "tools.json").write_text(
            json.dumps({"tools": tools_list}), encoding="utf-8"
        )

    def test_execute_success_creates_span(self, tmp_path):
        """Successful execute() should create a registry_execute span."""
        from core.tools import ToolRegistry
        from core.observability import tracer, metrics as _m

        self._write_tools(tmp_path, [{
            "name": "echo_ok", "type": "shell",
            "description": "echo", "command": "echo ok", "parameters": {}
        }])
        reg = ToolRegistry()
        reg.load()

        prev_tool_exec = _m.get("tool_executions")
        with patch.object(tracer, "_log_file", self.log_file):
            result = reg.execute("echo_ok", {})

        assert "ok" in result
        assert _m.get("tool_executions") == prev_tool_exec + 1
        # Verify span was written
        assert self.log_file.exists()
        lines = self.log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["name"] == "registry_execute"
        assert record["status"] == "ok"
        assert record["attributes"]["tool_name"] == "echo_ok"

    def test_execute_success_records_timing(self, tmp_path):
        """Successful execute() should record timing metric."""
        from core.tools import ToolRegistry
        from core.observability import metrics as _m

        self._write_tools(tmp_path, [{
            "name": "echo_timing", "type": "shell",
            "description": "echo", "command": "echo timing", "parameters": {}
        }])
        reg = ToolRegistry()
        reg.load()

        with patch.object(_m, "_timings", {}):
            reg.execute("echo_timing", {})
            summary = _m.summary()
            assert "tool_execute_ms" in summary["timings"]
            assert summary["timings"]["tool_execute_ms"]["count"] >= 1

    def test_execute_success_records_result_chars(self, tmp_path):
        """Successful execute() span should have result_chars attribute."""
        from core.tools import ToolRegistry
        from core.observability import tracer

        self._write_tools(tmp_path, [{
            "name": "echo_len", "type": "shell",
            "description": "echo", "command": "echo hello_world", "parameters": {}
        }])
        reg = ToolRegistry()
        reg.load()

        with patch.object(tracer, "_log_file", self.log_file):
            reg.execute("echo_len", {})

        record = json.loads(self.log_file.read_text(encoding="utf-8").strip().split("\n")[0])
        assert "result_chars" in record["attributes"]
        assert record["attributes"]["result_chars"] > 0

    def test_execute_unknown_tool_counts_error(self):
        """Unknown tool should increment tool_errors metric."""
        from core.tools import ToolRegistry
        from core.observability import metrics as _m

        reg = ToolRegistry()
        prev_errors = _m.get("tool_errors")
        reg.execute("no_such_tool", {})
        assert _m.get("tool_errors") >= prev_errors + 1

    def test_execute_runtime_error_counts_error(self, tmp_path):
        """RuntimeError in executor should increment tool_errors and re-raise."""
        from core.tools import ToolRegistry
        from core.observability import metrics as _m

        reg = ToolRegistry()
        reg.register("fail_tool", "fail desc", {"type": "object", "properties": {}, "required": []},
                      lambda: (_ for _ in ()).throw(RuntimeError("boom")), override=True)

        prev_errors = _m.get("tool_errors")
        with pytest.raises(RuntimeError, match="boom"):
            reg.execute("fail_tool", {})
        assert _m.get("tool_errors") >= prev_errors + 1

    def test_execute_generic_error_counts_error(self, tmp_path):
        """Non-RT/OSE/Value/Type errors should return error string + increment metric."""
        from core.tools import ToolRegistry
        from core.observability import metrics as _m

        reg = ToolRegistry()
        reg.register("generic_fail", "desc", {"type": "object", "properties": {}, "required": []},
                      lambda: (_ for _ in ()).throw(KeyError("missing_key")), override=True)

        prev_errors = _m.get("tool_errors")
        result = reg.execute("generic_fail", {})
        assert "错误" in result
        assert _m.get("tool_errors") >= prev_errors + 1


class TestToolCallSpanNesting:
    """Verify that tool_call span in chat.py nests properly with registry_execute."""

    def test_nested_spans_share_trace(self, tmp_path):
        """TraceContext auto-links parent-child: tool_call -> registry_execute."""
        from core.observability import TraceContext, tracer, metrics as _m

        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file):
            with TraceContext("tool_call", tool_name="generate_image", call_id="tc_123") as outer:
                outer.set_attribute("result_chars", 42)
                _m.increment("tool_calls")
                _m.timing("tool_call_ms", outer.duration_ms())
                # Simulate nested registry_execute
                with TraceContext("registry_execute", tool_name="generate_image") as inner:
                    inner.set_attribute("result_chars", 42)
                    _m.increment("tool_executions")
                    _m.timing("tool_execute_ms", inner.duration_ms())

        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        # Inner finishes first (LIFO), so inner is lines[0], outer is lines[1]
        inner_rec = json.loads(lines[0])
        outer_rec = json.loads(lines[1])
        # Same trace
        assert outer_rec["trace_id"] == inner_rec["trace_id"]
        # Inner has parent pointing to outer
        assert inner_rec["parent_id"] == outer_rec["span_id"]
        assert outer_rec["name"] == "tool_call"
        assert inner_rec["name"] == "registry_execute"


class TestAsyncChatObservabilityStructural:
    """Structural check: async_chat.py uses TraceContext + metrics in tool loop."""

    def test_async_chat_imports_observability(self):
        """AsyncChatSession module should import TraceContext and metrics."""
        import core.async_chat as ac
        # Module-level import
        assert hasattr(ac, "TraceContext") or "TraceContext" in dir(ac)

    def test_async_chat_tool_loop_has_trace_context(self):
        """Verify the tool dispatch loop in send_stream uses TraceContext."""
        import inspect
        import core.async_chat as ac

        source = inspect.getsource(ac.AsyncChatSession.send_stream)
        # The tool loop should contain TraceContext
        assert "TraceContext" in source, (
            "send_stream should use TraceContext for tool calls"
        )
        # And metrics increment/timing
        assert "metrics.increment" in source, (
            "send_stream should increment metrics for tool calls"
        )
        assert "metrics.timing" in source, (
            "send_stream should record timing metrics for tool calls"
        )


class TestTraceContextErrorPropagation:
    """Verify TraceContext correctly propagates errors to span status."""

    def test_oserror_recorded_as_error(self, tmp_path):
        """OSError inside TraceContext should produce error status span."""
        from core.observability import TraceContext, tracer

        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file), pytest.raises(OSError):
            with TraceContext("failing_tool", tool_name="crash_tool"):
                raise OSError("disk full")

        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert record["status"] == "error"
        assert record["name"] == "failing_tool"
        assert record["events"][0]["name"] == "exception"

    def test_runtime_error_recorded_as_error(self, tmp_path):
        """RuntimeError inside TraceContext should produce error status span."""
        from core.observability import TraceContext, tracer

        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file), pytest.raises(RuntimeError):
            with TraceContext("rt_fail"):
                raise RuntimeError("boom")

        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert record["status"] == "error"

    def test_value_error_recorded_as_error(self, tmp_path):
        """ValueError inside TraceContext should produce error status span."""
        from core.observability import TraceContext, tracer

        log_file = tmp_path / "traces.jsonl"
        with patch.object(tracer, "_log_file", log_file), pytest.raises(ValueError):
            with TraceContext("val_fail"):
                raise ValueError("bad value")

        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert record["status"] == "error"
