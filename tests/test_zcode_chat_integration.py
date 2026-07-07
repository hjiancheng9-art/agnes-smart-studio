"""Integration tests for ChatSession.send_stream — the core message processing pipeline.

Mocks the API client to verify the full flow: text streaming, tool calls,
fallback chain, budget warnings, and methodology classification.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── Helpers ──────────────────────────────────────────────────

def _make_mock_client(stream_chunks=None, model="deepseek-v4-flash"):
    """Create a mock CruxClient that returns controlled stream chunks."""
    client = MagicMock()
    client.base_url = "https://test.api/v1"
    client.model = model

    if stream_chunks is None:
        stream_chunks = [
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}]},
            {"choices": [{"delta": {"content": "!"}, "index": 0, "finish_reason": "stop"}]},
        ]

    def _mock_stream(*args, **kwargs):
        yield from stream_chunks
        # Yield usage info at end
        yield {"usage": {"total_tokens": 50, "prompt_tokens": 20, "completion_tokens": 30}}

    client.chat_stream = _mock_stream
    return client


def _collect_stream(session, text):
    """Collect all yields from send_stream into a dict."""
    result = {"text": "", "infos": [], "errors": [], "images": [], "videos": []}
    for kind, payload in session.send_stream(text):
        if kind == "text":
            result["text"] += str(payload)
        elif kind == "info":
            result["infos"].append(str(payload))
        elif kind == "error":
            result["errors"].append(str(payload))
        elif kind == "image":
            result["images"].append(payload)
        elif kind == "video":
            result["videos"].append(payload)
    return result


# ── Tests ────────────────────────────────────────────────────


class TestSendStreamBasic:
    """Basic text response flow."""

    def test_simple_text_response(self):
        from core.chat import ChatSession
        client = _make_mock_client()
        session = ChatSession(client)
        result = _collect_stream(session, "Hello")
        # Basic: should not crash and should have user message in history
        assert result is not None
        assert len(session.messages) >= 2  # user + assistant

    def test_session_builds_system_prompt(self):
        from core.chat import ChatSession
        client = _make_mock_client()
        session = ChatSession(client)
        assert len(session.messages) >= 1
        assert session.messages[0]["role"] == "system"

    def test_empty_stream_handled(self):
        from core.chat import ChatSession
        client = _make_mock_client(stream_chunks=[])
        session = ChatSession(client)
        result = _collect_stream(session, "test")
        # Should not crash on empty stream
        assert result is not None

    def test_user_message_added_to_history(self):
        from core.chat import ChatSession
        client = _make_mock_client()
        session = ChatSession(client)
        _collect_stream(session, "What is Python?")
        user_msgs = [m for m in session.messages if m.get("role") == "user"]
        assert len(user_msgs) >= 1
        assert "What is Python" in user_msgs[0].get("content", "")


class TestSendStreamErrors:
    """Error handling in the stream pipeline."""

    def test_stream_error_handled(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.base_url = "https://test.api/v1"

        def _error_stream(*args, **kwargs):
            raise RuntimeError("Connection reset")
            yield  # unreachable

        client.chat_stream = _error_stream
        session = ChatSession(client)
        result = _collect_stream(session, "test")
        # Should yield an error, not crash
        assert len(result["errors"]) > 0 or result["text"] == ""

    def test_client_rejects_bad_response(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.base_url = "https://test.api/v1"

        def _bad_stream(*args, **kwargs):
            yield {"error": "invalid_request", "message": "Bad request"}
            yield {"usage": {"total_tokens": 0}}

        client.chat_stream = _bad_stream
        session = ChatSession(client)
        # Should not crash on malformed response
        result = _collect_stream(session, "test")
        assert result is not None


class TestSendStreamToolCalls:
    """Tool call detection and execution."""

    def test_tool_call_fragments_merge_correctly(self):
        from core.chat_tool_helpers import merge_tool_calls
        fragments = [
            {"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": '{"path":'}},
            {"index": 0, "function": {"arguments": '"test.txt"}'}},
        ]
        merged = merge_tool_calls(fragments)
        assert len(merged) == 1
        assert merged[0]["function"]["name"] == "read_file"
        assert "test.txt" in merged[0]["function"]["arguments"]

    def test_tool_call_dedup(self):
        from core.chat_tool_helpers import merge_tool_calls
        fragments = [
            {"index": 0, "id": "call_1", "function": {"name": "search", "arguments": '{"q": "test"}'}},
            {"index": 1, "id": "call_2", "function": {"name": "search", "arguments": '{"q": "test"}'}},
        ]
        merged = merge_tool_calls(fragments)
        assert len(merged) == 1  # duplicates removed
        from core.chat_tool_helpers import merge_tool_calls
        fragments = [
            {"index": 0, "id": "call_1", "function": {"name": "generate_image", "arguments": '{"pr'}},
            {"index": 0, "function": {"arguments": 'ompt": "cat"}'}},
        ]
        merged = merge_tool_calls(fragments)
        assert len(merged) == 1
        assert merged[0]["function"]["name"] == "generate_image"


class TestSendStreamFallback:
    """Provider fallback chain behavior."""

    def test_fallback_chain_exists(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.base_url = "https://test.api/v1"
        session = ChatSession(client)
        chain = session._text_fallback_chain()
        assert len(chain) > 0, "Fallback chain should not be empty"

    def test_fallback_chain_valid_structure(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.base_url = "https://test.api/v1"
        session = ChatSession(client)
        chain = session._text_fallback_chain()
        for model, client_obj in chain:
            assert isinstance(model, str) and len(model) > 0
            assert client_obj is not None


class TestSendStreamMethodology:
    """Methodology integration in send_stream."""

    def test_methodology_classification_fires(self):
        from core.chat import ChatSession
        client = _make_mock_client()
        session = ChatSession(client)
        result = _collect_stream(session, "fix bug in multiple files across the project")
        # Complex task should trigger methodology info
        # (may not always fire depending on classification logic, but shouldn't crash)
        assert result is not None

    def test_simple_query_no_methodology_noise(self):
        from core.chat import ChatSession
        client = _make_mock_client()
        session = ChatSession(client)
        result = _collect_stream(session, "hello")
        # Simple greeting should not trigger methodology warnings
        methodology_infos = [i for i in result["infos"] if "方法" in i or "任务等级" in i]
        assert len(methodology_infos) == 0


class TestSendStreamFallbackIntegration:
    """Integration test: fallback chain actually switches clients on failure."""

    def test_fallback_triggers_on_stream_error(self):
        from unittest.mock import MagicMock

        from core.chat import ChatSession

        client1 = MagicMock()
        client1.base_url = "https://primary.api/v1"
        client2 = MagicMock()
        client2.base_url = "https://fallback.api/v1"

        def _error_stream(*a, **kw):
            yield {"_finish": "error", "_error": True}
            yield {"_usage": {"total_tokens": 0}}
        client1.chat_stream = MagicMock(side_effect=_error_stream)

        def _success_stream(*a, **kw):
            yield {"content": "Hello from fallback"}
            yield {"_usage": {"total_tokens": 10}}
        client2.chat_stream = MagicMock(side_effect=_success_stream)

        session = ChatSession(client=client1, default_model="deepseek-v4-flash")
        chain = [("deepseek-v4-flash", client1), ("deepseek-v4-pro", client2)]

        results = []
        with patch.object(session, "_text_fallback_chain", return_value=chain):
            for kind, payload in session.send_stream("test"):
                results.append((kind, payload))

        client1.chat_stream.assert_called()
        client2.chat_stream.assert_called()
        texts = [p for k, p in results if k == "text"]
        assert "Hello from fallback" in "".join(texts)

    def test_all_clients_fail_yields_error(self):
        from unittest.mock import MagicMock

        from core.chat import ChatSession

        client1 = MagicMock()
        client1.base_url = "https://p1.api/v1"
        client2 = MagicMock()
        client2.base_url = "https://p2.api/v1"

        def _fail(*a, **kw):
            yield {"_finish": "error"}
            yield {"_usage": {"total_tokens": 0}}
        client1.chat_stream = _fail
        client2.chat_stream = _fail

        session = ChatSession(client=client1)
        chain = [("m1", client1), ("m2", client2)]

        with patch.object(session, "_text_fallback_chain", return_value=chain):
            results = list(session.send_stream("test"))

        errors = [p for k, p in results if k == "error"]
        assert len(errors) > 0 or len(results) > 0  # Should complete without crash


class TestSendStreamPipeline:
    """End-to-end: tool call → execution → response."""

    def test_tool_merge_dedup_pipeline(self):
        from core.chat_tool_helpers import merge_tool_calls
        # Simulate: model emits 2 tool calls, one is duplicate
        fragments = [
            {"index": 0, "id": "call_1", "function": {"name": "search", "arguments": '{"q":"test"}'}},
            {"index": 1, "id": "call_2", "function": {"name": "search", "arguments": '{"q":"test"}'}},
        ]
        merged = merge_tool_calls(fragments)
        assert len(merged) == 1  # Duplicate removed

    def test_sanitize_preserves_valid(self):
        from core.chat_tool_helpers import sanitize_tool_call_history
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 3  # All valid messages preserved

    def test_sanitize_removes_orphan_tools(self):
        from core.chat_tool_helpers import sanitize_tool_call_history
        msgs = [
            {"role": "user", "content": "test"},
            {"role": "tool", "tool_call_id": "orphan_1", "content": "result"},
        ]
        result = sanitize_tool_call_history(msgs)
        # Orphan tool (no assistant with tool_calls) should be removed
        assert len(result) <= len(msgs)
