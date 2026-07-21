"""Tests for runtime_health module — circuit breaker, state persistence, startup check."""

from __future__ import annotations

import time

import pytest

from core.runtime_health import (
    CIRCUIT_BREAKER_TIMEOUT,
    MAX_FAILURES_PER_TOOL,
    STATE_PATH,
    RuntimeHealth,
    ToolHealth,
    get_runtime_health,
    startup_health_check,
)


@pytest.fixture
def clean_health_state():
    """Remove persisted state before and after test."""
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    yield
    if STATE_PATH.exists():
        STATE_PATH.unlink()


@pytest.fixture
def rh(clean_health_state):
    """Fresh RuntimeHealth instance with no persisted state."""
    return RuntimeHealth(auto_load=False)


class TestToolHealth:
    """Unit tests for ToolHealth dataclass."""

    def test_initial_state(self):
        th = ToolHealth()
        assert th.total_calls == 0
        assert th.failures == 0
        assert th.failure_rate == 0.0
        assert th.healthy is True

    def test_with_successes(self):
        th = ToolHealth()
        th.total_calls = 10
        th.failures = 2
        assert th.failure_rate == 0.2
        assert th.healthy is True

    def test_unhealthy(self):
        th = ToolHealth()
        th.total_calls = 3
        th.failures = 2  # 66% failure rate
        assert th.failure_rate > 0.5
        assert th.healthy is False

    def test_circuit_breaker_reset_on_timeout(self):
        th = ToolHealth()
        th.circuit_open = True
        th.circuit_opened_at = time.time() - CIRCUIT_BREAKER_TIMEOUT - 1
        assert th.healthy is True  # Circuit breaker timed out


class TestRuntimeHealth:
    """Tests for RuntimeHealth class."""

    def test_initial_health(self, rh):
        assert rh.state.health == 100
        assert len(rh.state.tools) == 0

    def test_track_success(self, rh):
        rh.track_success("test_tool")
        assert rh.state.tools["test_tool"].total_calls == 1
        assert rh.state.tools["test_tool"].failures == 0
        assert rh.tool_healthy("test_tool")

    def test_track_failure_no_breaker(self, rh):
        # 1 failure out of 1 call = 100% > 50% threshold → unhealthy
        # But circuit breaker not open (needs 5 failures)
        rh.track_failure("test_tool")
        assert rh.state.tools["test_tool"].failures == 1
        assert rh.tool_healthy("test_tool") is False  # 100% failure rate
        assert rh.should_retry("test_tool") is True  # circuit breaker not open

    def test_circuit_breaker_opens_after_max_failures(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("test_tool")
        assert rh.state.tools["test_tool"].circuit_open is True
        assert rh.should_retry("test_tool") is False
        assert rh.tool_healthy("test_tool") is False

    def test_circuit_breaker_resets_after_timeout(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("test_tool")
        # Manually set the circuit opened time in the past
        rh.state.tools["test_tool"].circuit_opened_at = time.time() - CIRCUIT_BREAKER_TIMEOUT - 1
        assert rh.should_retry("test_tool") is True
        assert rh.state.tools["test_tool"].circuit_open is False  # auto-reset

    def test_success_resets_circuit_breaker(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("test_tool")
        assert rh.state.tools["test_tool"].circuit_open is True
        rh.track_success("test_tool")
        assert rh.state.tools["test_tool"].circuit_open is False

    def test_health_recalculation(self, rh):
        # 2 tools, 1 unhealthy → health ~50%
        rh.track_success("tool_a")
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("tool_b")
        assert rh.state.health < 80

    def test_check_returns_needs_fix(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("bad_tool")
        result = rh.check()
        assert result["needs_fix"] is True
        assert len(result["tools_unhealthy"]) > 0

    def test_get_summary(self, rh):
        summary = rh.get_summary()
        assert "Health:" in summary

    def test_persistence(self, rh, clean_health_state):
        rh.track_success("persistent_tool")
        rh._save()
        # Reload
        rh2 = RuntimeHealth()
        assert rh2.state.tools["persistent_tool"].total_calls == 1

    def test_corrupted_state_recovery(self, clean_health_state):
        STATE_PATH.write_text("not valid json", encoding="utf-8")
        rh = RuntimeHealth()
        assert rh.state.health == 100  # Fresh state on corruption

    def test_startup_health_check(self, rh):
        result = startup_health_check()
        assert "health" in result
        assert "needs_fix" in result
        assert isinstance(result["health"], int)


class TestGlobalRuntimeHealth:
    """Tests for global singleton and startup function."""

    def test_singleton(self):
        rh1 = get_runtime_health()
        rh2 = get_runtime_health()
        assert rh1 is rh2

    def test_startup_health_check_no_errors(self, clean_health_state):
        result = startup_health_check()
        assert result["health"] == 100
        assert result["needs_fix"] is False
