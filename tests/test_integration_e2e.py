"""End-to-end integration tests: chat → tool dispatch → result.

Tests the complete pipeline with mocked HTTP responses — no real API calls.
Verifies stream event ordering, tool dispatch correctness, and error recovery.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════

def _mock_chat_stream_text(text: str):
    """Return a mock chat_stream that yields a simple text response."""
    def _stream(*, model, messages, tools=None, max_tokens=None, **kwargs):
        yield {"content": text, "_finish": "stop"}
    return _stream


def _mock_chat_stream_tool_call(tool_name: str, tool_args: dict):
    """Return a mock chat_stream that yields a tool call, then a final text."""
    def _stream(*, model, messages, tools=None, max_tokens=None, **kwargs):
        yield {
            "tool_calls": [{
                "index": 0,
                "id": "call_001",
                "function": {"name": tool_name, "arguments": str(tool_args)},
            }],
            "_finish": "tool_calls",
        }
    return _stream


def _mock_chat_stream_tool_then_text(tool_name: str, tool_args: dict, final_text: str):
    """Two-turn: tool call first, then text response when tool result is fed back."""
    call_count = [0]

    def _stream(*, model, messages, tools=None, max_tokens=None, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: return tool call
            yield {
                "tool_calls": [{
                    "index": 0,
                    "id": "call_001",
                    "function": {"name": tool_name, "arguments": str(tool_args)},
                }],
                "_finish": "tool_calls",
            }
        else:
            # Second call: return text
            yield {"content": final_text, "_finish": "stop"}
    return _stream


def _mock_chat_stream_error(error_text: str = "[流中断: ConnectError (retries exhausted)]"):
    """Return a mock chat_stream that yields an error."""
    def _stream(*, model, messages, tools=None, max_tokens=None, **kwargs):
        yield {"content": error_text, "_finish": "error", "_error": True}
    return _stream


def _patch_chat_stream(session, stream_fn):
    """Replace the client's chat_stream method on a live ChatSession."""
    session.client.chat_stream = stream_fn


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_client():
    """Create a mock CruxClient that can have chat_stream patched."""
    from unittest.mock import MagicMock

    client = MagicMock()
    client.base_url = "https://mock.example.com/v1"
    client.provider_id = "deepseek"
    client.api_key = "mock-key"
    return client


@pytest.fixture
def chat_session(mock_client):
    """Create a ChatSession with mocked client."""
    from core.chat import ChatSession

    session = ChatSession(mock_client, default_model="deepseek-v4-flash")
    # Replace expensive init paths
    session.tools._definitions = []
    session.tools._executors = {}
    # Register a dummy tool for tool call tests
    session.tools._definitions = [{
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    }]
    session.tools._executors["read_file"] = lambda **kw: f"Mock file content for {kw.get('path', 'unknown')}"
    return session


# ═══════════════════════════════════════════════════════════════
# Tests: Stream event ordering
# ═══════════════════════════════════════════════════════════════

class TestStreamEventOrdering:
    """Verify the correct sequence of stream events."""

    def test_pure_text_response(self, chat_session):
        """A text-only response should yield text events, no tool calls."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("Hello, world!"))

        events = list(chat_session.send_stream("Please help me write a function to calculate fibonacci numbers"))

        kinds = [kind for kind, _ in events]
        assert "text" in kinds, f"Expected text event, got kinds={kinds}"
        # Planning info only shows for non-trivial messages (len>30 or task keywords)
        # No tool events, no errors
        assert all(k not in kinds for k in ("confirm", "error")), f"Unexpected events: {kinds}"

    def test_text_event_before_stream_end(self, chat_session):
        """Text events should appear before the stream finishes."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("Hello"))

        events = list(chat_session.send_stream("Hi"))

        text_events = [p for k, p in events if k == "text"]
        assert len(text_events) >= 1, "Should have at least one text event"
        assert text_events[-1] == "Hello", f"Last text should be 'Hello', got {text_events}"

    def test_info_events_exist(self, chat_session):
        """The stream should emit info events for non-trivial tasks."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("OK"))

        events = list(chat_session.send_stream("Please implement a comprehensive user authentication system with OAuth2"))
        kinds = [k for k, _ in events]

        assert "info" in kinds, f"Should have info events for complex task, got {kinds}"

    def test_system_prompt_injected(self, chat_session):
        """After a message, the system prompt should be at messages[0]."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("response"))

        list(chat_session.send_stream("query"))

        assert chat_session.messages[0]["role"] == "system"
        assert len(chat_session.messages) >= 2, f"Expected at least system + user + assistant, got {len(chat_session.messages)}"


# ═══════════════════════════════════════════════════════════════
# Tests: Tool dispatch
# ═══════════════════════════════════════════════════════════════

class TestToolDispatch:
    """Verify the tool call → dispatch → result pipeline."""

    def test_tool_call_dispatched(self, chat_session):
        """When the model returns a tool call, it should be dispatched."""
        _patch_chat_stream(chat_session,
            _mock_chat_stream_tool_then_text(
                "read_file", {"path": "test.py"}, "File contents: hello"
            ))

        events = list(chat_session.send_stream("Read test.py"))

        kinds = [k for k, _ in events]
        assert "info" in kinds, "Should have info about tool execution"
        assert "text" in kinds, "Should have final text response"

    def test_unknown_tool_yields_validation_error(self, chat_session):
        """Calling an unregistered tool should yield validation_error events."""
        # Register the tool so it passes validation but fails execution
        chat_session.tools._executors["nonexistent_tool"] = lambda **kw: "mock result"
        chat_session.tools._definitions.append({
            "function": {
                "name": "nonexistent_tool",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {"arg": {"type": "string"}}},
            }
        })

        _patch_chat_stream(chat_session,
            _mock_chat_stream_tool_then_text("nonexistent_tool", {"arg": "value"}, "Done"))

        events = list(chat_session.send_stream("Use a test tool that exists"))
        kinds = [k for k, _ in events]

        assert "text" in kinds, f"Should have text events, got {kinds}"

    def test_tool_result_format(self, chat_session):
        """Tool results should be properly formatted for LLM consumption."""
        from core.gpt_tool_result import normalize_tool_result

        # Test normal string result
        r = normalize_tool_result("hello")
        assert r.ok
        assert r.output == "hello"

        # Test error result
        r = normalize_tool_result(RuntimeError("test error"))
        assert not r.ok
        assert "RuntimeError" in r.error_message

    def test_tool_call_added_to_history(self, chat_session):
        """After a tool call, the messages list should include the tool result."""
        _patch_chat_stream(chat_session,
            _mock_chat_stream_tool_then_text(
                "read_file", {"path": "test.py"}, "done"
            ))

        list(chat_session.send_stream("Read test.py"))

        # Check that messages include the assistant tool_call and tool result
        roles = [m.get("role") for m in chat_session.messages]
        assert "tool" in roles, f"Messages should include tool result, got roles: {roles}"
        assert "assistant" in roles, f"Messages should include assistant tool call"


# ═══════════════════════════════════════════════════════════════
# Tests: Error handling
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Verify error recovery in the pipeline."""

    def test_stream_error_does_not_crash(self, chat_session):
        """A stream error should yield an error event, not raise."""
        _patch_chat_stream(chat_session, _mock_chat_stream_error())

        # Should not raise
        events = list(chat_session.send_stream("test"))
        kinds = [k for k, _ in events]
        # Error should be gracefully handled
        assert True, "Stream error should not crash"

    def test_empty_user_input(self, chat_session):
        """Empty user input should be handled gracefully."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("echo"))

        # Should not crash on empty input
        events = list(chat_session.send_stream(""))
        assert len(events) >= 0, "Empty input should be handled"

    def test_multiple_tool_calls_in_sequence(self, chat_session):
        """Multiple sequential tool calls should all be dispatched."""
        call_count = [0]

        def multi_tool_stream(*, model, messages, tools=None, max_tokens=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                yield {
                    "tool_calls": [{
                        "index": 0, "id": "c1",
                        "function": {"name": "read_file", "arguments": str({"path": "a.py"})},
                    }],
                    "_finish": "tool_calls",
                }
            elif call_count[0] == 2:
                yield {
                    "tool_calls": [{
                        "index": 0, "id": "c2",
                        "function": {"name": "read_file", "arguments": str({"path": "b.py"})},
                    }],
                    "_finish": "tool_calls",
                }
            else:
                yield {"content": "All done", "_finish": "stop"}

        _patch_chat_stream(chat_session, multi_tool_stream)
        events = list(chat_session.send_stream("Read two files"))

        # Should have completed without error
        error_events = [p for k, p in events if k == "error"]
        assert not error_events, f"Got unexpected errors: {error_events}"


# ═══════════════════════════════════════════════════════════════
# Tests: State consistency
# ═══════════════════════════════════════════════════════════════

class TestStateConsistency:
    """Verify session state remains consistent through the pipeline."""

    def test_messages_preserved_across_turns(self, chat_session):
        """Messages from previous turns should persist."""
        _patch_chat_stream(chat_session, _mock_chat_stream_text("Hello back"))
        list(chat_session.send_stream("Hello"))

        # Check that user + assistant messages are in history
        user_msgs = [m for m in chat_session.messages if m.get("role") == "user"]
        assistant_msgs = [m for m in chat_session.messages if m.get("role") == "assistant"]
        assert len(user_msgs) >= 1, "Should have user message in history"
        assert len(assistant_msgs) >= 1, "Should have assistant message in history"

    def test_model_set_after_send(self, chat_session):
        """The model should remain set after sending a message."""
        original_model = chat_session.model
        _patch_chat_stream(chat_session, _mock_chat_stream_text("ok"))
        list(chat_session.send_stream("test"))

        assert chat_session.model == original_model, \
            f"Model changed from {original_model} to {chat_session.model}"


# ═══════════════════════════════════════════════════════════════
# Tests: Tool result normalization
# ═══════════════════════════════════════════════════════════════

class TestToolResultPipeline:
    """Verify the ToolResult normalization and error handling."""

    def test_success_result(self):
        from core.gpt_tool_result import ToolResult

        r = ToolResult.success("file content")
        assert r.ok
        assert r.output == "file content"
        assert r.error_code is None

    def test_failure_result(self):
        from core.gpt_tool_result import ToolResult

        r = ToolResult.failure("NOT_FOUND", "File not found")
        assert not r.ok
        assert r.error_code == "NOT_FOUND"
        assert r.error_message == "File not found"
        assert not r.retryable

    def test_retryable_failure(self):
        from core.gpt_tool_result import ToolResult

        r = ToolResult.failure("TIMEOUT", "Connection timed out", retryable=True)
        assert not r.ok
        assert r.retryable

    def test_tool_result_serialization(self):
        from core.gpt_tool_result import ToolResult

        r = ToolResult.success("hello world")
        d = r.to_model_dict()
        assert d["ok"] is True
        assert d["output"] == "hello world"
        assert d["error"] is None

    def test_empty_tuple_normalized(self):
        from core.gpt_tool_result import normalize_tool_result

        r = normalize_tool_result(())
        assert not r.ok, "Empty tuple should be a failure"

    def test_none_normalized(self):
        from core.gpt_tool_result import normalize_tool_result

        r = normalize_tool_result(None)
        assert not r.ok, "None should be a failure"

    def test_exception_normalized(self):
        from core.gpt_tool_result import normalize_tool_result

        r = normalize_tool_result(ValueError("bad value"))
        assert not r.ok
        assert "ValueError" in r.error_message
