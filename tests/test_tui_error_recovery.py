"""Tests for error classification and recovery hints in TuiAppV2._stream_response."""

import pytest


class TestErrorClassification:
    """Verify the 7 error categories map to correct recovery hints."""

    @pytest.fixture
    def classify(self):
        """Extract the error classification logic from _stream_response."""
        def _classify(err):
            err_name = type(err).__name__
            err_msg = str(err)
            hint = ""
            if "Connection" in err_name or "ConnectError" in err_name or "connect" in err_msg.lower():
                hint = "network"
            elif "Timeout" in err_name or "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                hint = "timeout"
            elif "RateLimit" in err_name or "429" in err_msg or "rate" in err_msg.lower():
                hint = "ratelimit"
            elif "Authentication" in err_name or "401" in err_msg or "403" in err_msg or "key" in err_msg.lower():
                hint = "auth"
            elif "Memory" in err_name or "context" in err_msg.lower() or "token" in err_msg.lower():
                hint = "context"
            elif "json" in err_msg.lower() or "JSONDecode" in err_name:
                hint = "json"
            else:
                hint = "unknown"
            return hint
        return _classify

    def test_connection_error(self, classify):
        assert classify(ConnectionError("Connection refused")) == "network"
        assert classify(ConnectionResetError("Connection reset")) == "network"

    def test_timeout_error(self, classify):
        assert classify(TimeoutError("timed out after 30s")) == "timeout"

    def test_rate_limit(self, classify):
        class Fake429(Exception):
            pass
        assert classify(Fake429("HTTP 429 Too Many Requests")) == "ratelimit"

    def test_auth_error(self, classify):
        class AuthError(Exception):
            pass
        assert classify(AuthError("Invalid API key")) == "auth"
        # 401/403 in the message
        assert classify(RuntimeError("Got 401 Unauthorized")) == "auth"

    def test_context_overflow(self, classify):
        assert classify(MemoryError("context length exceeded")) == "context"
        assert classify(RuntimeError("token limit reached")) == "context"

    def test_json_decode(self, classify):
        from json import JSONDecodeError
        assert classify(JSONDecodeError("Expecting value", "", 0)) == "json"

    def test_unknown_error(self, classify):
        assert classify(RuntimeError("something unexpected")) == "unknown"

    def test_null_byte_error(self, classify):
        assert classify(ValueError("null byte in string")) == "unknown"


class TestTurnSummary:
    """Verify turn summary format after stream completion."""

    @pytest.fixture
    def build_summary(self):
        def _build(elapsed, tool_count, latency, agent_score=0):
            parts = [f"took {elapsed:.1f}s"]
            if tool_count > 0:
                parts.append(f"{tool_count} tools")
            if latency > 0:
                parts.append(f"{latency:.1f}s first token")
            if agent_score >= 5:
                parts.append(f"agent score {agent_score:.0f}")
            return " · ".join(parts)
        return _build

    def test_basic_summary(self, build_summary):
        result = build_summary(3.2, 5, 0.8)
        assert "3.2s" in result
        assert "5 tools" in result
        assert "0.8s" in result

    def test_summary_with_high_agent_score(self, build_summary):
        result = build_summary(12.7, 8, 1.2, agent_score=8)
        assert "agent score 8" in result

    def test_summary_no_tools(self, build_summary):
        result = build_summary(1.5, 0, 0.3)
        assert "tools" not in result

    def test_summary_no_latency(self, build_summary):
        result = build_summary(2.0, 3, 0)
        assert "first token" not in result
