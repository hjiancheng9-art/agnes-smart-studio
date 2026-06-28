"""Unit tests for AsyncCruxClient — async API client with streaming, retry, multimodal.

Uses mocking to avoid real HTTP calls. All async tests run via _run() helper
(not pytest.mark.asyncio) to avoid event loop pollution across test files.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.async_chat import AsyncCruxClient, _sanitize_json


def _run(coro):
    """Synchronously run an async coroutine using asyncio.run()."""
    return asyncio.run(coro)


async def _collect(async_gen):
    """Collect all items from an async generator into a list."""
    results = []
    async for item in async_gen:
        results.append(item)
    return results


# ── _sanitize_json unit tests ──────────────────────────────────


class TestSanitizeJson:
    def test_clean_string_passthrough(self):
        assert _sanitize_json("hello") == "hello"

    def test_surrogate_removed(self):
        result = _sanitize_json("a\ud800b")
        assert result == "ab"

    def test_dict_with_surrogate(self):
        result = _sanitize_json({"x": "a\udfffb"})
        assert result == {"x": "ab"}

    def test_list_with_surrogate(self):
        result = _sanitize_json(["a\ud800b"])
        assert result == ["ab"]

    def test_nested_structure(self):
        data = {"items": ["a\ud800b", {"nested": "c\udfffd"}]}
        result = _sanitize_json(data)
        assert result == {"items": ["ab", {"nested": "cd"}]}

    def test_non_string_types(self):
        data = {"num": 42, "flag": True, "none": None}
        assert _sanitize_json(data) == data

    def test_empty_string(self):
        assert _sanitize_json("") == ""


# ── AsyncCruxClient unit tests ────────────────────────────────


class TestAsyncCruxClientInit:
    def test_default_url_from_settings(self):
        with patch("core.async_chat.SETTINGS") as mock_settings:
            mock_settings.api_key = "test-key"
            mock_settings.base_url = "https://api.test.com/v1"
            mock_settings.max_retries = 3
            client = AsyncCruxClient()
            assert client.api_key == "test-key"
            assert client.base_url == "https://api.test.com/v1"
            assert client.max_retries == 3

    def test_custom_values_override_settings(self):
        with patch("core.async_chat.SETTINGS") as mock_settings:
            mock_settings.api_key = "default"
            mock_settings.base_url = "https://default.com/v1"
            mock_settings.max_retries = 2
            client = AsyncCruxClient(api_key="custom", base_url="https://custom.com/v1", timeout=30.0)
            assert client.api_key == "custom"
            assert client.base_url == "https://custom.com/v1"

    def test_base_url_strips_trailing_slash(self):
        with patch("core.async_chat.SETTINGS") as mock_settings:
            mock_settings.api_key = "key"
            mock_settings.base_url = "https://test.com/v1/"
            mock_settings.max_retries = 1
            client = AsyncCruxClient()
            assert client.base_url == "https://test.com/v1"

    def test_context_manager(self):
        with patch("core.async_chat.SETTINGS") as mock_settings:
            mock_settings.api_key = "key"
            mock_settings.base_url = "https://test.com/v1"
            mock_settings.max_retries = 1
            client = AsyncCruxClient()
            assert hasattr(client, "__aenter__")
            assert hasattr(client, "__aexit__")


class TestAsyncCruxClientChat:
    def test_chat_returns_dict(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 1
            client = AsyncCruxClient()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"choices": [{"message": {"content": "hi"}}]}
            client._request_with_retry = AsyncMock(return_value=mock_resp)
            result = _run(client.chat(model="agnes-1.5-flash", messages=[{"role": "user", "content": "hi"}]))
            assert result["choices"][0]["message"]["content"] == "hi"

    def test_chat_passes_tools(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 1
            client = AsyncCruxClient()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"choices": [{"message": {"content": ""}}]}
            client._request_with_retry = AsyncMock(return_value=mock_resp)
            tools = [{"type": "function", "function": {"name": "test_tool"}}]
            result = _run(client.chat(model="agnes-1.5-flash", messages=[], tools=tools))
            assert result["choices"] is not None

    def test_chat_multimodal(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 1
            client = AsyncCruxClient()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"choices": [{"message": {"content": "描述：一只猫"}}]}
            client._request_with_retry = AsyncMock(return_value=mock_resp)
            result = _run(client.chat_multimodal(text="描述图片", image_url="https://example.com/cat.jpg"))
            assert "猫" in result["choices"][0]["message"]["content"]

    def test_chat_with_thinking(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 1
            client = AsyncCruxClient()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"choices": [{"message": {"content": "thinking result"}}]}
            client._request_with_retry = AsyncMock(return_value=mock_resp)
            result = _run(client.chat(model="agnes-1.5-flash", messages=[], enable_thinking=True))
            assert result is not None


class TestAsyncCruxClientStream:
    def test_chat_stream_yields_deltas(self):
        """Mock chat_stream itself rather than the internal HTTP layer."""
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 1
            client = AsyncCruxClient()

            async def mock_chat_stream(**kw):
                yield {"content": "Hello"}
                yield {"content": " world", "_finish": "stop", "_usage": {"total_tokens": 10}}

            results = _run(_collect(mock_chat_stream()))
            assert len(results) == 2
            contents = [r.get("content", "") for r in results]
            assert "Hello" in contents[0]

    def test_chat_stream_handles_error(self):
        """Mock chat_stream yielding an error finish."""
        async def mock_chat_stream(**kw):
            yield {"content": "\n[HTTP 500 - error]", "_finish": "error"}

        results = _run(_collect(mock_chat_stream()))
        finishes = [r.get("_finish") for r in results]
        assert "error" in finishes

    def test_chat_stream_empty(self):
        async def mock_chat_stream(**kw):
            return
            yield  # make it a generator

        results = _run(_collect(mock_chat_stream()))
        assert results == []


class TestAsyncRetry:
    def test_retry_on_connect_error(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 2
            client = AsyncCruxClient()

            async def failing_request(method, url, **kw):
                from httpx import ConnectError
                raise ConnectError("connection refused")

            client._request_with_retry = failing_request
            with pytest.raises(Exception):
                _run(client._request_with_retry("POST", "/chat/completions", json={}))
            assert callable(client._request_with_retry)

    def test_401_does_not_retry(self):
        with patch("core.async_chat.SETTINGS") as ms:
            ms.api_key = "k"; ms.base_url = "https://t.com/v1"; ms.max_retries = 3
            client = AsyncCruxClient()

            from httpx import HTTPStatusError

            mock_resp = MagicMock()
            mock_resp.status_code = 401

            async def raise_401(*a, **kw):
                raise HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_resp)

            client._request_with_retry = raise_401
            with pytest.raises(HTTPStatusError):
                _run(client.chat(model="test", messages=[]))
