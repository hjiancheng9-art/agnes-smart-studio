"""Tests for core/runtime_health.py — circuit breaker and health monitoring."""

from __future__ import annotations

import time

import pytest

from core.runtime_health import (
    CIRCUIT_BREAKER_TIMEOUT,
    MAX_FAILURE_RATE,
    MAX_FAILURES_PER_TOOL,
    RuntimeHealth,
    ToolHealth,
    get_runtime_health,
    startup_health_check,
)


class TestToolHealth:
    """ToolHealth dataclass — per-tool health tracking."""

    def test_default_values(self):
        th = ToolHealth()
        assert th.total_calls == 0
        assert th.failures == 0
        assert th.circuit_open is False

    def test_failure_rate_zero_when_no_calls(self):
        th = ToolHealth()
        assert th.failure_rate == 0.0

    def test_failure_rate_calculation(self):
        th = ToolHealth(total_calls=10, failures=3)
        assert th.failure_rate == 0.3

    def test_healthy_below_max_rate(self):
        th = ToolHealth(total_calls=10, failures=4)  # 40%
        assert th.failure_rate < MAX_FAILURE_RATE
        assert th.healthy is True

    def test_unhealthy_above_max_rate(self):
        th = ToolHealth(total_calls=10, failures=6)  # 60%
        assert th.failure_rate >= MAX_FAILURE_RATE
        assert th.healthy is False

    def test_circuit_open_timeout(self):
        """When circuit is open, healthy only after timeout."""
        th = ToolHealth(
            total_calls=10,
            failures=0,
            circuit_open=True,
            circuit_opened_at=time.time() - CIRCUIT_BREAKER_TIMEOUT - 1,
        )
        assert th.healthy is True  # timeout elapsed

    def test_circuit_open_not_yet_timed_out(self):
        """When circuit opened recently, not healthy yet."""
        th = ToolHealth(
            total_calls=10,
            failures=0,
            circuit_open=True,
            circuit_opened_at=time.time(),
        )
        assert th.healthy is False


class TestRuntimeHealthCircuitBreaker:
    """RuntimeHealth — circuit breaker behavior."""

    @pytest.fixture
    def rh(self):
        """Fresh RuntimeHealth with no disk state."""
        return RuntimeHealth(auto_load=False)

    def test_track_success_increments_calls(self, rh):
        rh.track_success("test_tool")
        th = rh._get_tool("test_tool")
        assert th.total_calls == 1
        assert th.failures == 0

    def test_track_failure_increments_both(self, rh):
        rh.track_failure("test_tool")
        th = rh._get_tool("test_tool")
        assert th.total_calls == 1
        assert th.failures == 1

    def test_track_success_resets_circuit_breaker(self, rh):
        # Open circuit breaker first
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("test_tool")
        th = rh._get_tool("test_tool")
        assert th.circuit_open is True

        # Success should reset
        rh.track_success("test_tool")
        assert th.circuit_open is False
        assert th.failures == 0

    def test_circuit_breaker_opens_at_threshold(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL - 1):
            rh.track_failure("test_tool")
        th = rh._get_tool("test_tool")
        assert th.circuit_open is False  # not yet

        rh.track_failure("test_tool")  # hits threshold
        assert th.circuit_open is True

    def test_track_success_mixed_with_failures(self, rh):
        rh.track_success("tool")
        rh.track_failure("tool")
        rh.track_success("tool")
        th = rh._get_tool("tool")
        assert th.total_calls == 3
        assert th.failures == 1


class TestRuntimeHealthChecks:
    """RuntimeHealth — should_retry, tool_healthy, check, get_summary."""

    @pytest.fixture
    def rh(self):
        return RuntimeHealth(auto_load=False)

    def test_healthy_tool_can_retry(self, rh):
        rh.track_success("tool")
        assert rh.should_retry("tool") is True
        assert rh.tool_healthy("tool") is True

    def test_failed_but_below_threshold_can_retry(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL - 1):
            rh.track_failure("tool")
        assert rh.should_retry("tool") is True

    def test_circuit_open_cannot_retry_recently(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("tool")
        th = rh._get_tool("tool")
        th.circuit_opened_at = time.time()  # just now
        assert rh.should_retry("tool") is False

    def test_unknown_tool_can_retry(self, rh):
        """Tool not tracked yet — assume healthy."""
        assert rh.should_retry("unknown") is True

    def test_check_returns_status_dict(self, rh):
        result = rh.check()
        assert isinstance(result, dict)
        assert "health" in result
        assert "needs_fix" in result
        assert "circuits_open" in result
        assert "tools_unhealthy" in result

    def test_check_needs_fix_when_tools_unhealthy(self, rh):
        for _ in range(MAX_FAILURES_PER_TOOL):
            rh.track_failure("broken_tool")
        result = rh.check()
        assert "broken_tool" in result["tools_unhealthy"]
        assert result["needs_fix"] is True

    def test_get_summary_returns_string(self, rh):
        rh.track_success("tool")
        summary = rh.get_summary()
        assert isinstance(summary, str)
        assert "tool" in summary.lower() or "100" in summary or "tool" in summary


class TestGetRuntimeHealth:
    """get_runtime_health() — singleton access."""

    def test_returns_same_instance(self):
        rh1 = get_runtime_health()
        rh2 = get_runtime_health()
        assert rh1 is rh2

    def test_returns_runtime_health_instance(self):
        rh = get_runtime_health()
        assert isinstance(rh, RuntimeHealth)


class TestStartupHealthCheck:
    """startup_health_check() — startup validation."""

    def test_returns_status_dict(self):
        result = startup_health_check()
        assert isinstance(result, dict)
        assert "health" in result
        assert "needs_fix" in result
