"""Tests for core.chat_stream_tools — tool execution loop extracted from chat.py."""

from unittest.mock import MagicMock, patch

import pytest

from core.chat_stream_tools import _run_tool_calls_impl, _summarize_tool_output
from core.chat_tool_helpers import merge_tool_calls


@pytest.fixture(autouse=True)
def _mock_methodology():
    """Prevent methodology gate from blocking tool dispatch in unit tests."""
    with patch("core.methodology.methodology_pre_check", return_value=(True, "")):
        yield


class TestSummarizeToolOutput:
    """Unit tests for _summarize_tool_output helper."""

    def test_short_output_passthrough(self):
        """Short outputs (<2000 chars) are returned unchanged."""
        short = "OK"
        assert _summarize_tool_output(short) == short

    def test_empty_output_passthrough(self):
        """Empty output is returned unchanged."""
        assert _summarize_tool_output("") == ""

    def test_none_output_passthrough(self):
        """None is not truncated (falsy check)."""
        assert _summarize_tool_output(None) is None

    def test_long_output_truncated(self):
        """Long outputs are summarized."""
        long_output = "line\n" * 1500  # ~7500 chars
        result = _summarize_tool_output(long_output)
        assert len(result) < len(long_output)
        assert "omitted" in result

    def test_error_output_highlighted(self):
        """Error keywords are prioritized in truncation."""
        err_output = "header\n" + ("data\n" * 500) + "error: something failed\n" + ("data\n" * 500)
        result = _summarize_tool_output(err_output, "run_test")
        assert "error" in result.lower()
        assert "flagged" in result


class TestRunToolCallsValidation:
    """Tests for Phase 1 of _run_tool_calls_impl — tool call validation."""

    def _make_session(self, tool_calls=None, **overrides):
        """Build a mock ChatSession with sensible defaults.

        Pre-computes _last_merged_tool_calls to avoid MagicMock auto-attribute
        shadowing the getattr fallback in _run_tool_calls_impl.
        """
        session = MagicMock()
        session.tools = MagicMock()
        session.tools.resolve_name = lambda n: n
        session.tvl = None
        session._WRITE_TOOLS = frozenset({"write_file", "edit_file", "patch_file"})
        session._consecutive_failures = 0
        session._consecutive_successes = 0
        session._effective_max = 60
        session._last_turn_had_errors = False
        session.messages = []
        session._dispatch_tool = MagicMock(return_value=("result", []))
        session._record_trace_failure = MagicMock()
        session.client = MagicMock()
        session.model = "test-model"
        # Pre-compute merged tool calls so getattr doesn't get a MagicMock default
        if tool_calls is not None:
            session._last_merged_tool_calls = merge_tool_calls(tool_calls)
        for k, v in overrides.items():
            setattr(session, k, v)
        return session

    def test_no_tvl_skips_validation(self):
        """When tvl is None, validation phase is skipped entirely."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": '{"cmd":"ls"}'}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls, tvl=None)
        sigs = set()
        cache = {}

        gen = _run_tool_calls_impl(session, tool_calls, sigs, cache, loop_idx=0)
        list(gen)
        # Should have dispatched the tool
        session._dispatch_tool.assert_called()

    def test_dedup_skips_non_write_tools(self):
        """Non-write tools with matching sigs are deduplicated."""
        tool_calls = [{"function": {"name": "read_file", "arguments": '{"path":"/tmp/x.txt"}'}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)
        sigs = {("read_file", '{"path":"/tmp/x.txt"}')}
        cache = {("read_file", '{"path":"/tmp/x.txt"}'): "cached result"}

        gen = _run_tool_calls_impl(session, tool_calls, sigs, cache, loop_idx=0)
        list(gen)
        # Should NOT dispatch since it was already cached
        session._dispatch_tool.assert_not_called()

    def test_write_tools_not_deduped(self):
        """Write tools always dispatch regardless of cache."""
        tool_calls = [{"function": {"name": "write_file", "arguments": '{"path":"/tmp/y.txt"}'}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)
        sigs = {("write_file", '{"path":"/tmp/y.txt"}')}
        cache = {("write_file", '{"path":"/tmp/y.txt"}'): "old"}

        gen = _run_tool_calls_impl(session, tool_calls, sigs, cache, loop_idx=0)
        list(gen)
        # Write tools MUST always dispatch
        session._dispatch_tool.assert_called()

    def test_adaptive_failure_shrinks_limit(self):
        """Consecutive failures shrink the effective max loop limit."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": "{}"}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)
        session._consecutive_failures = 2  # Already had 2 failures
        session._dispatch_tool.return_value = ("[错误] something", [])

        gen = _run_tool_calls_impl(session, tool_calls, set(), {}, loop_idx=3)
        list(gen)
        # 3rd failure should shrink limit
        assert session._consecutive_failures == 3
        assert session._effective_max <= 8  # loop_idx(3) + 5

    def test_confirm_flow_placeholder_and_replace(self):
        """Confirm flows insert placeholder then replace with real result."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": "{}"}, "id": "abc123"}]
        session = self._make_session(tool_calls=tool_calls)
        # Mock dispatch: first returns confirm side-effect, second returns real result
        call_count = [0]

        def mock_dispatch(name, args, confirmed=False):
            call_count[0] += 1
            if not confirmed:
                return ("ask user", [("confirm", {"message": "are you sure?"})])
            return ("done after confirm", [])

        session._dispatch_tool = mock_dispatch
        sigs = set()
        cache = {}

        gen = _run_tool_calls_impl(session, tool_calls, sigs, cache, loop_idx=0)
        list(gen)

        # Check placeholder was inserted then replaced
        messages = session.messages
        assert len(messages) == 1  # Only the final result
        assert messages[0]["tool_call_id"] == "abc123"
        assert "done after confirm" in messages[0]["content"]

    def test_tool_error_sets_last_turn_flag(self):
        """Tool dispatch exceptions set _last_turn_had_errors."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": "{}"}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)

        def failing_dispatch(name, args, confirmed=False):
            raise RuntimeError("simulated crash")

        session._dispatch_tool = failing_dispatch

        gen = _run_tool_calls_impl(session, tool_calls, set(), {}, loop_idx=0)
        list(gen)
        assert session._last_turn_had_errors is True
        session._record_trace_failure.assert_called()


class TestRunToolCallsOutput:
    """Tests for result formatting and side-effects."""

    def _make_session(self, tool_calls=None, **overrides):
        session = MagicMock()
        session.tools = MagicMock()
        session.tools.resolve_name = lambda n: n
        session.tvl = None
        session._WRITE_TOOLS = frozenset({"write_file"})
        session._consecutive_failures = 0
        session._consecutive_successes = 0
        session._effective_max = 60
        session._last_turn_had_errors = False
        session.messages = []
        session._dispatch_tool = MagicMock(return_value=("ok result", []))
        session._record_trace_failure = MagicMock()
        session.client = MagicMock()
        session.model = "test-model"
        if tool_calls is not None:
            session._last_merged_tool_calls = merge_tool_calls(tool_calls)
        for k, v in overrides.items():
            setattr(session, k, v)
        return session

    def test_tool_result_yielded_to_ui(self):
        """Each tool call yields a ('tool_result', ...) for the UI."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": "{}"}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)

        gen = _run_tool_calls_impl(session, tool_calls, set(), {}, loop_idx=0)
        results = list(gen)

        tool_results = [r for r in results if r[0] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0][1]["name"] == "run_bash"

    def test_tool_result_appended_to_messages(self):
        """Tool results are appended to session.messages."""
        tool_calls = [{"function": {"name": "run_bash", "arguments": "{}"}, "id": "1"}]
        session = self._make_session(tool_calls=tool_calls)

        gen = _run_tool_calls_impl(session, tool_calls, set(), {}, loop_idx=0)
        list(gen)

        assert len(session.messages) > 0
        assert session.messages[-1]["role"] == "tool"
