"""End-to-end tests against real CRUX/DeepSeek API.

Requires CRUX_API_KEY or DEEPSEEK_API_KEY in environment.
Auto-skipped when no API key is available.

Usage:
    pytest tests/test_e2e_real_api.py -v              # all tests
    pytest tests/test_e2e_real_api.py -v -m network   # only network tests
    CRUX_API_KEY=sk-xxx pytest ...                     # with key inline

Rate limiting note:
    DeepSeek API rate-limits concurrent requests. When running the full suite,
    some tests may fail with empty responses due to 429s. Run tests individually
    or with --dist loadscope for reliable results. The retry_empty mechanism
    handles occasional empty responses but cannot overcome sustained rate limits.

Markers:
    @pytest.mark.network — all tests in this file
    @pytest.mark.slow   — tests that take >10s
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = [pytest.mark.network]

# ═══════════════════════════════════════════════════════════════
# Skip conditions
# ═══════════════════════════════════════════════════════════════

_HAS_CRUX_KEY = bool(os.environ.get("CRUX_API_KEY") or os.environ.get("AGNES_API_KEY"))
_HAS_DS_KEY = bool(os.environ.get("DEEPSEEK_API_KEY"))
_HAS_ANY_KEY = _HAS_CRUX_KEY or _HAS_DS_KEY

needs_api_key = pytest.mark.skipif(
    not _HAS_ANY_KEY, reason="No API key available (set CRUX_API_KEY or DEEPSEEK_API_KEY)"
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _create_session(model: str = "deepseek-v4-flash"):
    """Create a ChatSession with a real client."""
    from core.chat import ChatSession
    from core.client import CruxClient

    client = CruxClient(provider_id="deepseek")
    session = ChatSession(client, default_model=model)
    return session


def _collect_stream(session, message: str, timeout: float = 120.0, *, retry_empty: bool = True):
    """Collect all stream events from send_stream with a timeout.

    When retry_empty is True and the first call returns no text, waits 2s
    and retries once (handles rate limiting / empty model responses).
    """
    for attempt in range(2):
        events: list[tuple[str, str | dict]] = []
        deadline = time.monotonic() + timeout

        for kind, payload in session.send_stream(message):
            events.append((kind, payload))
            if time.monotonic() > deadline:
                events.append(("timeout", f"Stream exceeded {timeout}s"))
                break

        text_chunks = [p for k, p in events if k == "text"]
        if text_chunks and "".join(str(c) for c in text_chunks).strip():
            return events

        if not retry_empty or attempt == 1:
            return events

        time.sleep(2.0)  # back off before retry

    return events


# ═══════════════════════════════════════════════════════════════
# Tests: Basic chat
# ═══════════════════════════════════════════════════════════════


class TestRealChatBasic:
    """Minimal chat tests against real API — validates end-to-end flow."""

    @needs_api_key
    @pytest.mark.slow
    def test_simple_greeting_returns_text(self):
        """A simple greeting should return a text response."""
        session = _create_session()
        events = _collect_stream(session, "Say exactly 'hello' and nothing else.", timeout=60.0)

        text_chunks = [p for k, p in events if k == "text"]
        assert len(text_chunks) > 0, f"Expected text in response, got kinds: {[k for k, _ in events]}"

        full_response = "".join(str(c) for c in text_chunks)
        assert len(full_response.strip()) > 0, "Response should not be empty"

    @needs_api_key
    @pytest.mark.slow
    def test_stream_events_have_expected_kinds(self):
        """Stream should produce text events (and optionally info/thinking)."""
        session = _create_session()
        events = _collect_stream(session, "What is 2+2? Answer in one word.", timeout=60.0)

        kinds = {k for k, _ in events}
        assert "text" in kinds, f"Expected text event, got kinds: {kinds}"
        # Should NOT have error events
        assert "error" not in kinds, f"Got unexpected error: {[p for k, p in events if k == 'error']}"

    @needs_api_key
    def test_messages_preserved_in_history(self):
        """After a turn, user + assistant messages should be in history."""
        session = _create_session()
        _collect_stream(session, "Reply with just 'OK'.", timeout=60.0)

        roles = [m.get("role") for m in session.messages]
        assert "user" in roles, "User message should be in history"
        assert "assistant" in roles, "Assistant message should be in history"


# ═══════════════════════════════════════════════════════════════
# Tests: Tool calling
# ═══════════════════════════════════════════════════════════════


class TestRealToolCalling:
    """Validate tool dispatch with real model."""

    @needs_api_key
    @pytest.mark.slow
    def test_chat_with_tools_available(self):
        """Model should respond normally even with tools registered in the session.

        DeepSeek V4 Flash may or may not choose to call tools — both outcomes
        are valid. The test verifies the stream completes without errors and
        produces at least some output (text or tool-related info).
        """
        session = _create_session("deepseek-v4-flash")

        # Register read_file tool
        session.tools._definitions = [
            {
                "function": {
                    "name": "read_file",
                    "description": "Read a file from disk",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "File path"}},
                        "required": ["path"],
                    },
                }
            }
        ]
        session.tools._executors["read_file"] = lambda **kw: f"Content of {kw.get('path', '?')}"

        events = _collect_stream(session, "What is the capital of France? Answer in one word.", timeout=60.0)

        # Should complete without error
        errors = [p for k, p in events if k == "error"]
        assert not errors, f"Got errors: {errors}"
        # Should have at least some output
        assert len(events) > 0, "Stream should produce events"


# ═══════════════════════════════════════════════════════════════
# Tests: Provider switching
# ═══════════════════════════════════════════════════════════════


class TestRealProviderFlow:
    """Validate provider lifecycle and failover."""

    @needs_api_key
    def test_provider_manager_loads(self):
        """Provider manager should load without error."""
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        mgr.load()
        assert mgr.state.active in mgr.providers, (
            f"Active provider '{mgr.state.active}' not in {list(mgr.providers.keys())}"
        )

    @needs_api_key
    def test_get_client_for_active_provider(self):
        """Should be able to create a client for the active provider."""
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        client = mgr.create_client()
        assert client is not None
        assert hasattr(client, "chat_stream"), "Client should have chat_stream method"
        with __import__("contextlib").suppress(Exception):
            client.close()


# ═══════════════════════════════════════════════════════════════
# Tests: Model info / capability
# ═══════════════════════════════════════════════════════════════


class TestRealModelInfo:
    """Validate model metadata and capability queries."""

    def test_model_registry_has_expected_models(self):
        """Model registry should contain core models."""
        from core.provider import MODEL_REGISTRY

        expected = ["deepseek-v4-pro", "deepseek-v4-flash", "agnes-2.0-flash"]
        for mid in expected:
            assert mid in MODEL_REGISTRY, f"Missing model: {mid}"

    def test_get_capability_for_known_model(self):
        """get_capability should return info for known models."""
        from core.provider import get_capability_info

        info = get_capability_info("deepseek-v4-flash")
        assert info is not None
        assert info.provider_id == "deepseek"
        assert info.supports_tools is True

    def test_resolve_model_alias(self):
        """Model aliases should resolve correctly."""
        from core.provider import resolve_model_alias

        assert resolve_model_alias("flash") == "deepseek-v4-flash"
        assert resolve_model_alias("pro") == "deepseek-v4-pro"


# ═══════════════════════════════════════════════════════════════
# Tests: Stream protocol correctness
# ═══════════════════════════════════════════════════════════════


class TestRealStreamProtocol:
    """Validate that stream events follow the correct protocol."""

    @needs_api_key
    @pytest.mark.slow
    def test_no_stream_start_in_events(self):
        """Stream events should NOT contain 'stream_start' (TUI sends it directly)."""
        session = _create_session()
        events = _collect_stream(session, "Say hi.", timeout=60.0)

        kinds = {k for k, _ in events}
        assert "stream_start" not in kinds, "stream_start should not be in yield events"
        assert "stream_end" not in kinds, "stream_end should not be in yield events"

    @needs_api_key
    @pytest.mark.slow
    def test_text_events_are_strings(self):
        """All text payloads should be strings."""
        session = _create_session()
        events = _collect_stream(session, "Say hello world.", timeout=60.0)

        for kind, payload in events:
            if kind == "text":
                assert isinstance(payload, str), f"Text payload should be str, got {type(payload)}"
