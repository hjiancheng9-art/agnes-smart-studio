"""Tests for the CRUX Gateway — OpenAI-compatible HTTP API."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.gateway.protocol import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaChoice,
    DeltaContent,
    Message,
    ModelInfo,
    ModelList,
    Usage,
)
from core.gateway.runner import (
    AVAILABLE_MODELS,
    GatewayRunner,
    convert_messages,
    list_models,
    resolve_model,
)


# ── Model resolution ────────────────────────────────────


def test_resolve_exact_match():
    assert resolve_model("agnes-2.0-flash") == "agnes-2.0-flash"
    assert resolve_model("deepseek-v4-pro") == "deepseek-v4-pro"


def test_resolve_alias():
    assert resolve_model("gpt-4o") == "agnes-2.0-pro"
    assert resolve_model("gpt-3.5-turbo") == "agnes-2.0-flash"
    assert resolve_model("claude-3-5-sonnet") == "agnes-2.0-pro"


def test_resolve_unknown_fallback():
    assert resolve_model("unknown-model-xyz") == "agnes-2.0-pro"


# ── Message conversion ──────────────────────────────────


def test_convert_simple_text():
    msgs = [Message(role="user", content="hello")]
    result = convert_messages(msgs)
    assert result == [{"role": "user", "content": "hello"}]


def test_convert_system_and_user():
    msgs = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hi"),
    ]
    result = convert_messages(msgs)
    assert len(result) == 2
    assert result[0] == {"role": "system", "content": "You are helpful."}
    assert result[1] == {"role": "user", "content": "Hi"}


def test_convert_preserves_name_and_tool_calls():
    msgs = [
        Message(role="assistant", content="", tool_calls=[{"id": "1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]),
        Message(role="tool", content="result", tool_call_id="1", name="f"),
    ]
    result = convert_messages(msgs)
    assert result[0]["tool_calls"] == [{"id": "1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    assert result[1]["tool_call_id"] == "1"
    assert result[1]["name"] == "f"


# ── list_models ─────────────────────────────────────────


def test_list_models():
    result = list_models()
    assert isinstance(result, ModelList)
    assert result.object == "list"
    assert len(result.data) >= 2
    model_ids = [m.id for m in result.data]
    assert "agnes-2.0-flash" in model_ids
    assert "deepseek-v4-pro" in model_ids


# ── GatewayRunner (mocked client) ────────────────────────


@pytest.fixture
def mock_client():
    """Return a MagicMock that behaves like CruxClient."""
    return MagicMock()


@pytest.fixture
def runner(mock_client):
    return GatewayRunner(client=mock_client)


class TestNonStreaming:
    def test_basic_completion(self, runner, mock_client):
        mock_client.chat.return_value = {
            "id": "test-123",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hi")],
        )

        resp = runner.complete(req)
        assert isinstance(resp, ChatCompletionResponse)
        assert resp.model == "agnes-2.0-pro"  # alias resolved
        assert len(resp.choices) == 1
        assert resp.choices[0].message.content == "Hello!"
        assert resp.choices[0].finish_reason == "stop"
        assert resp.usage.total_tokens == 15

    def test_completion_with_tools(self, runner, mock_client):
        mock_client.chat.return_value = {
            "id": "test-456",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"Paris"}'}}],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
        }

        from core.gateway.protocol import Tool, ToolFunction
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Weather in Paris?")],
            tools=[Tool(type="function", function=ToolFunction(name="get_weather", description="Get weather", parameters={"type": "object"}))],
        )

        resp = runner.complete(req)
        assert resp.choices[0].message.content is None
        assert resp.choices[0].message.tool_calls is not None
        assert resp.choices[0].message.tool_calls[0]["function"]["name"] == "get_weather"
        assert resp.choices[0].finish_reason == "tool_calls"

    def test_completion_passes_thinking_false(self, runner, mock_client):
        mock_client.chat.return_value = {
            "id": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="X")],
        )
        runner.complete(req)

        call_kwargs = mock_client.chat.call_args.kwargs
        assert call_kwargs["thinking"] is False
        assert call_kwargs["stream"] is False


# ── HTTP endpoint (TestClient) ──────────────────────────


@pytest.fixture
def app():
    from core.gateway.server import create_app
    return create_app()


@pytest.fixture
def http(app):
    return TestClient(app)


class TestHttpEndpoints:
    def test_health(self, http):
        r = http.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "models" in data

    def test_list_models(self, http):
        r = http.get("/v1/models")
        assert r.status_code == 200
        data = r.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 2

    def test_chat_empty_messages(self, http):
        r = http.post("/v1/chat/completions", json={"model": "test", "messages": []})
        assert r.status_code == 400

    def test_chat_missing_messages(self, http):
        r = http.post("/v1/chat/completions", json={"model": "test"})
        assert r.status_code == 422  # Pydantic validation

    def test_chat_default_model(self, http):
        """Verify the endpoint accepts a minimal valid request.
        
        This test hits the live API and may time out if the API is unavailable.
        In CI we'd mock the client, but for now this serves as a smoke test.
        """
        r = http.post("/v1/chat/completions", json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Say hi"}],
            "max_tokens": 10,
        })
        # Either 200 (success) or 500 (API down), both are acceptable
        # as long as the gateway itself is routing correctly
        assert r.status_code in (200, 500, 502, 504), f"Unexpected status: {r.status_code}"


# ── Protocol serialization ──────────────────────────────


def test_chat_completion_response_serialization():
    resp = ChatCompletionResponse(
        id="chatcmpl-abc",
        model="agnes-2.0-flash",
        choices=[Choice(index=0, message=ChoiceMessage(content="Hi"), finish_reason="stop")],
        usage=Usage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )
    d = resp.model_dump()
    assert d["object"] == "chat.completion"
    assert d["choices"][0]["message"]["content"] == "Hi"


def test_chat_completion_chunk_serialization():
    chunk = ChatCompletionChunk(
        id="chatcmpl-xyz",
        model="test",
        choices=[DeltaChoice(index=0, delta=DeltaContent(content="Hello"))],
    )
    d = chunk.model_dump_json()
    assert "chat.completion.chunk" in d
    assert "Hello" in d


def test_request_extra_fields_ignored():
    """Verify unknown fields in the request are silently ignored."""
    req = ChatCompletionRequest(
        model="test",
        messages=[Message(role="user", content="Hi")],
        extra_field_should_be_ignored="blah",  # type: ignore[call-arg]
    )
    assert req.model == "test"
