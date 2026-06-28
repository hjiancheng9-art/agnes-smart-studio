"""Tests for core.lore.intimate_slots.arbiter — Merit-Demerit Arbiter.

测试覆盖：赏分、罚分、衰减、降级/恢复、工具排序、供应商排序、
重复错误惩罚、高风险惩罚、干净会话奖励、熔断罚分、持久化、线程安全。
"""

from __future__ import annotations

import threading

import pytest

import core.lore.intimate_slots.arbiter as _arb_mod
from core.lore.intimate_slots.arbiter import (
    DECAY_HALF_LIFE,
    DEGRADE_THRESHOLD,
    DEMERIT_HIGH_RISK,
    DEMERIT_REPEATED,
    DEMERIT_TIMEOUT,
    DEMERIT_TOOL_FAIL,
    MERIT_FAST_TOOL,
    MERIT_NORMAL_TOOL,
    MERIT_SESSION_CLEAN,
    STATE_FILE,
    MeritDemeritArbiter,
    reset_arbiter,
)

# Always access arbiter via _a() so that reset_arbiter()
# (which replaces the module-level variable) is reflected in tests.


def _a():
    """Shorthand for the current arbiter singleton."""
    return _arb_mod.arbiter


@pytest.fixture(autouse=True)
def _reset():
    """Ensure fresh state before every test."""
    reset_arbiter()
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    yield
    reset_arbiter()
    if STATE_FILE.exists():
        STATE_FILE.unlink()


class TestMeritDemeritArbiter:
    """Core mutation and query tests."""

    def test_award_merit_basic(self):
        _a().award_merit("read_file", 1.0, "fast read")
        assert _a().get_score("read_file") == 1.0

    def test_assign_demerit_basic(self):
        _a().assign_demerit("write_file", -2.0, "timeout")
        assert _a().get_score("write_file") == -2.0

    def test_record_tool_success_fast(self):
        _a().record_tool_success("read_file", 0.1, "openai")
        assert _a().get_score("read_file") == MERIT_FAST_TOOL

    def test_record_tool_success_normal(self):
        _a().record_tool_success("read_file", 0.8, "openai")
        assert _a().get_score("read_file") == MERIT_NORMAL_TOOL

    def test_record_tool_failure(self):
        _a().record_tool_failure("generate_image", "api_error", "openai")
        assert _a().get_score("generate_image") == DEMERIT_TOOL_FAIL

    def test_record_tool_timeout(self):
        _a().record_tool_timeout("search", "openai")
        assert _a().get_score("search") == DEMERIT_TIMEOUT

    def test_repeated_error_penalty(self):
        # 3 consecutive same-tool + same-error triggers DEMERIT_REPEATED
        for _ in range(3):
            _a().record_tool_failure("search", "api_error", "openai")
        # 3 × DEMERIT_TOOL_FAIL + DEMERIT_REPEATED
        expected = DEMERIT_TOOL_FAIL * 3 + DEMERIT_REPEATED
        assert _a().get_score("search") == pytest.approx(expected)

    def test_repeated_error_reset_on_success(self):
        _a().record_tool_failure("search", "api_error")
        _a().record_tool_failure("search", "api_error")
        # Success resets streak
        _a().record_tool_success("search", 0.3)
        _a().record_tool_failure("search", "api_error")
        # streak is 1 again, no repeat penalty
        assert _a().get_score("search") == pytest.approx(
            DEMERIT_TOOL_FAIL * 2 + MERIT_FAST_TOOL + DEMERIT_TOOL_FAIL
        )

    def test_high_risk_no_confirm(self):
        _a().record_high_risk_call("run_bash", confirmed=False)
        assert _a().get_score("run_bash") == DEMERIT_HIGH_RISK

    def test_high_risk_confirmed(self):
        # Confirmed high-risk calls get no demerit
        _a().record_high_risk_call("run_bash", confirmed=True)
        assert _a().get_score("run_bash") == 0.0

    def test_circuit_trip(self):
        _a().record_circuit_trip("openai")
        assert _a().status["circuit_trips"] == 1
        with pytest.raises(KeyError):
            _ = _a().status["tools"]["openai"]
        # Provider entry should have the penalty
        assert _a().status["providers_scored"] == 1


class TestDegradation:
    """Degradation threshold and recovery tests."""

    def test_degrade_on_threshold(self):
        # Push total score below DEGRADE_THRESHOLD
        _a().assign_demerit("bad_tool", DEGRADE_THRESHOLD - 1.0)
        assert _a().is_degraded()

    def test_recover_above_threshold(self):
        _a().assign_demerit("bad_tool", DEGRADE_THRESHOLD - 1.0)
        assert _a().is_degraded()
        # Award enough to recover (threshold + 5.0 buffer)
        _a().award_merit("good_tool", abs(DEGRADE_THRESHOLD - 1.0) + 10.0)
        assert not _a().is_degraded()

    def test_session_clean_merit(self):
        _a().record_session_start()
        _a().record_session_end(error_count=0, call_count=5)
        assert _a().get_score("_session") == MERIT_SESSION_CLEAN


class TestDecay:
    """Exponential decay tests."""

    def test_decay_applied(self):
        _a().award_merit("test_tool", 10.0)
        # Manually trigger decay by manipulating timestamp
        old = _a()._state.last_decay_ts
        # Simulate elapsed time equal to half-life
        _a()._state.last_decay_ts = old - DECAY_HALF_LIFE
        # Trigger decay via a mutation
        _a().assign_demerit("other_tool", 0.0)
        # After one half-life, score should halve
        assert _a().get_score("test_tool") == pytest.approx(5.0, abs=0.5)

    def test_decay_min_interval(self):
        _a().award_merit("test_tool", 10.0)
        # A second mutation within the min interval does not trigger another decay
        _a().award_merit("test_tool", 1.0)
        assert _a().get_score("test_tool") == pytest.approx(11.0)


class TestPriorityQueries:
    """Tool suggestion and provider deprioritization."""

    def test_suggest_tool_priority(self):
        _a().award_merit("read_file", 3.0)
        _a().assign_demerit("write_file", -1.0)
        _a().award_merit("grep", 5.0)
        result = _a().suggest_tool_priority(["read_file", "write_file", "grep"])
        assert result == ["grep", "read_file", "write_file"]

    def test_deprioritize_providers(self):
        _a().record_provider_error("bad_provider")
        _a().record_provider_error("bad_provider")
        _a().record_provider_healthy("good_provider")
        result = _a().deprioritize_providers(["bad_provider", "good_provider", "unknown"])
        assert result[0] == "good_provider"


class TestPersistence:
    """Save/load roundtrip tests."""

    def test_persistence_roundtrip(self):
        _a().award_merit("read_file", 5.0)
        _a().record_circuit_trip("openai")
        _a().save()

        # Create a new arbiter to simulate restart
        fresh = MeritDemeritArbiter()
        assert fresh.get_score("read_file") == pytest.approx(5.0)
        assert fresh.status["circuit_trips"] == 1
        assert "openai" in fresh.report()["providers"]

    def test_load_corrupt_file(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text("not json", encoding="utf-8")
        fresh = MeritDemeritArbiter()
        # Should start fresh, no crash
        assert fresh.status["tools_scored"] == 0


class TestThreadSafety:
    """Concurrent mutations from multiple threads."""

    def test_concurrent_awards(self):
        errors = []

        def _worker(n):
            try:
                for _i in range(100):
                    _a().award_merit(f"tool_{n}", 1.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # 5 threads × 100 awards = 500 total
        total = sum(_a().get_score(f"tool_{t}") for t in range(5))
        assert total == pytest.approx(500.0)


class TestStatusAndReport:
    """Status dict and report output."""

    def test_status_fields(self):
        _a().award_merit("read_file", 2.0)
        _a().assign_demerit("rm_rf", -5.0)
        s = _a().status
        assert s["tools_scored"] == 2
        assert s["worst_tool"] == "rm_rf"
        assert isinstance(s["total_score"], float)

    def test_summary_string(self):
        s = _a().summary()
        assert "[功过格]" in s
        assert "tools:" in s
        assert "score:" in s

    def test_report_has_tools_and_providers(self):
        _a().record_tool_success("read_file", 0.2, "openai")
        r = _a().report()
        assert "tools" in r
        assert "read_file" in r["tools"]
        assert "providers" in r
        assert "openai" in r["providers"]
