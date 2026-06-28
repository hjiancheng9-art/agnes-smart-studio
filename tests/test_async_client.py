"""Tests for core/async_client.py — AsyncCruxClient initialization and structure."""

import pytest
from core.async_client import AsyncCruxClient


class TestAsyncCruxClientInit:
    def test_init_with_defaults(self):
        client = AsyncCruxClient()
        assert client.base_url == "https://apihub.agnes-ai.com/v1"
        assert client.timeout == 120.0
        assert client.max_retries > 0

    def test_init_with_custom_params(self):
        client = AsyncCruxClient(
            api_key="sk-test",
            base_url="https://custom.api.com/v1",
            timeout=60.0,
        )
        assert client.api_key == "sk-test"
        assert client.base_url == "https://custom.api.com/v1"
        assert client.timeout == 60.0

    def test_base_url_stripped_of_trailing_slash(self):
        client = AsyncCruxClient(base_url="https://api.example.com/v1/")
        assert client.base_url == "https://api.example.com/v1"

    def test_http_client_created(self):
        client = AsyncCruxClient(api_key="sk-test")
        assert client._http is not None

    def test_http_client_has_auth_header(self):
        client = AsyncCruxClient(api_key="sk-test")
        headers = client._http.headers
        assert "Authorization" in headers

    @pytest.mark.asyncio
    async def test_close(self):
        client = AsyncCruxClient(api_key="sk-test")
        await client._http.aclose()
