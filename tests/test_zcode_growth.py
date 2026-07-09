"""RED phase tests for core/growth_engine.py.

Tests: ToolStats, IntentStats, GrowthEngine, singleton, TRM hook.
"""

from unittest import mock

# ---------------------------------------------------------------------------
# ToolStats dataclass
# ---------------------------------------------------------------------------


class TestToolStats:
    """ToolStats dataclass fields and computed properties."""

    def test_default_values(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="test_tool")
        assert ts.tool == "test_tool"
        assert ts.source == ""
        assert ts.calls == 0
        assert ts.successes == 0
        assert ts.failures == 0
        assert ts.total_latency_ms == 0.0
        assert ts.consecutive_failures == 0
        assert ts.demoted is False
        assert ts.probation_successes == 0

    def test_success_rate_no_calls(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t")
        assert ts.success_rate == 0.5  # neutral prior

    def test_success_rate_with_calls(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t", calls=10, successes=8)
        assert ts.success_rate == 0.8

    def test_success_rate_zero_successes(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t", calls=10, successes=0)
        assert ts.success_rate == 0.0

    def test_avg_latency_no_calls(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t")
        assert ts.avg_latency_ms == 9999.0

    def test_avg_latency_with_calls(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t", calls=10, total_latency_ms=5000.0)
        assert ts.avg_latency_ms == 500.0

    def test_score_composite(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t", calls=10, successes=10, total_latency_ms=5000.0)
        s = ts.score
        assert 0.0 <= s <= 1.0

    def test_score_failed_tool(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(tool="t", calls=10, successes=0, total_latency_ms=100.0)
        assert ts.score < 0.5

    def test_to_dict_and_from_dict_roundtrip(self):
        from core.growth_engine import ToolStats

        ts = ToolStats(
            tool="my_tool",
            source="crux",
            calls=5,
            successes=4,
            failures=1,
            total_latency_ms=2500.0,
            demoted=True,
            consecutive_failures=1,
            probation_successes=2,
        )
        d = ts.to_dict()
        ts2 = ToolStats.from_dict(d)
        assert ts2.tool == ts.tool
        assert ts2.source == ts.source
        assert ts2.calls == ts.calls
        assert ts2.successes == ts.successes
        assert ts2.demoted == ts.demoted
        assert ts2.probation_successes == ts.probation_successes


# ---------------------------------------------------------------------------
# IntentStats dataclass
# ---------------------------------------------------------------------------


class TestIntentStats:
    """IntentStats dataclass."""

    def test_default_values(self):
        from core.growth_engine import IntentStats

        is_ = IntentStats(intent="search")
        assert is_.intent == "search"
        assert is_.tools == {}
        assert is_.total_calls == 0
        assert is_.last_recalc_at == 0

    def test_ensure_tool_creates_new(self):
        from core.growth_engine import IntentStats

        is_ = IntentStats(intent="search")
        ts = is_.ensure_tool("new_tool", source="test")
        assert ts.tool == "new_tool"
        assert ts.source == "test"
        assert "new_tool" in is_.tools

    def test_ensure_tool_returns_existing(self):
        from core.growth_engine import IntentStats, ToolStats

        is_ = IntentStats(intent="search")
        is_.tools["existing"] = ToolStats(tool="existing", source="original")
        ts = is_.ensure_tool("existing", source="different")
        assert ts.source == "original"

    def test_ordered_tools_sorts_by_score(self):
        from core.growth_engine import IntentStats, ToolStats

        is_ = IntentStats(intent="search")
        # high score
        is_.tools["best"] = ToolStats(tool="best", calls=10, successes=10, total_latency_ms=100)
        # low score
        is_.tools["worst"] = ToolStats(tool="worst", calls=10, successes=1, total_latency_ms=30000)
        ordered = is_.ordered_tools
        assert ordered[0].tool == "best"
        assert ordered[1].tool == "worst"

    def test_ordered_tools_demoted_at_bottom(self):
        from core.growth_engine import IntentStats, ToolStats

        is_ = IntentStats(intent="search")
        is_.tools["a"] = ToolStats(tool="a", calls=10, successes=10, total_latency_ms=100, demoted=True)
        is_.tools["b"] = ToolStats(tool="b", calls=10, successes=5, total_latency_ms=100, demoted=False)
        ordered = is_.ordered_tools
        assert ordered[0].tool == "b"
        assert ordered[-1].tool == "a"

    def test_tool_names_returns_list(self):
        from core.growth_engine import IntentStats, ToolStats

        is_ = IntentStats(intent="search")
        is_.tools["a"] = ToolStats(tool="a", calls=2, successes=1)
        is_.tools["b"] = ToolStats(tool="b", calls=10, successes=9)
        names = is_.tool_names
        assert isinstance(names, list)
        assert "a" in names
        assert "b" in names

    def test_to_dict_and_from_dict_roundtrip(self):
        from core.growth_engine import IntentStats, ToolStats

        is_ = IntentStats(intent="execute")
        is_.tools["t1"] = ToolStats(tool="t1", calls=5, successes=4)
        is_.total_calls = 5
        is_.last_recalc_at = 3
        d = is_.to_dict()
        is2 = IntentStats.from_dict(d)
        assert is2.intent == "execute"
        assert is2.total_calls == 5
        assert is2.last_recalc_at == 3
        assert "t1" in is2.tools


# ---------------------------------------------------------------------------
# GrowthEngine
# ---------------------------------------------------------------------------


class TestGrowthEngine:
    """GrowthEngine lifecycle."""

    def test_construction(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        assert isinstance(ge.intents, dict)
        assert ge._total_calls_ever >= 0

    def test_record_creates_intent(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        ts = ge.record("search", "code_search", success=True, latency_ms=120)
        assert ts.tool == "code_search"
        assert ts.calls == 1
        assert ts.successes == 1
        assert "search" in ge.intents
        assert ge._total_calls_ever == 1

    def test_record_failure_increments_consecutive(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        ge.record("search", "bad_tool", success=False)
        ge.record("search", "bad_tool", success=False)
        ts = ge.record("search", "bad_tool", success=False)
        assert ts.consecutive_failures == 3

    def test_auto_demotion_after_consecutive_failures(self):
        from core.growth_engine import CONSECUTIVE_FAIL_THRESHOLD, GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        tool = "failing_tool"
        for _ in range(CONSECUTIVE_FAIL_THRESHOLD):
            ge.record("search", tool, success=False)
        ts = ge.get_tool_stats("search", tool)
        assert ts is not None
        assert ts.demoted is True

    def test_record_success_clears_consecutive_failures(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        ge.record("search", "t", success=False)
        ge.record("search", "t", success=False)
        ts = ge.record("search", "t", success=True)
        assert ts.consecutive_failures == 0

    def test_get_route_returns_ordered(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        ge.record("search", "fast_tool", success=True, latency_ms=10)
        ge.record("search", "slow_tool", success=True, latency_ms=5000)
        route = ge.get_route("search")
        assert isinstance(route, list)
        assert route[0] == "fast_tool"

    def test_get_route_unknown_intent(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        route = ge.get_route("nonexistent")
        assert route == []

    def test_get_tool_stats_returns_none_for_unknown(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        assert ge.get_tool_stats("unknown", "unknown") is None

    def test_get_summary_includes_total(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        ge.record("search", "t", success=True)
        summary = ge.get_summary()
        assert "Growth Engine" in summary
        assert str(ge._total_calls_ever) in summary

    def test_reset_clears_all(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.record("search", "t", success=True)
        ge.reset()
        assert ge._total_calls_ever == 0
        assert ge.intents == {}

    def test_auto_tune_insufficient_data(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        result = ge.auto_tune(apply=False)
        assert result.get("status") == "insufficient data"

    def test_detect_bottlenecks_low_data(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        bottlenecks = ge.detect_bottlenecks()
        assert bottlenecks == []

    def test_suggest_improvements_returns_list(self):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        suggestions = ge.suggest_improvements()
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0

    def test_save_and_load_roundtrip(self, tmp_path):
        from core.growth_engine import GrowthEngine

        ge = GrowthEngine()
        ge.reset()
        # Override STATS_FILE to use tmp
        with mock.patch("core.growth_engine.STATS_FILE", tmp_path / "growth.json"):
            ge.record("search", "t", success=True, latency_ms=50)
            ge.save()
            ge2 = GrowthEngine()
            # ge2 loads from the same file
            # Check that data survived
            assert ge2._total_calls_ever >= 1 or ge2.intents  # depends on tmp cleanup


# ---------------------------------------------------------------------------
# Singleton & TRM hook
# ---------------------------------------------------------------------------


class TestGrowthEngineSingleton:
    """get_growth_engine singleton."""

    def test_returns_same_instance(self):
        from core.growth_engine import get_growth_engine

        g1 = get_growth_engine()
        g2 = get_growth_engine()
        assert g1 is g2

    def test_returns_growth_engine_instance(self):
        from core.growth_engine import GrowthEngine, get_growth_engine

        ge = get_growth_engine()
        assert isinstance(ge, GrowthEngine)


class TestTRMHook:
    """hook_trm_route convenience function."""

    def test_exists_and_callable(self):
        from core.growth_engine import hook_trm_route

        assert callable(hook_trm_route)

    def test_delegates_to_record(self):
        from core.growth_engine import get_growth_engine, hook_trm_route

        get_growth_engine()
        ts = hook_trm_route("search", "tool_x", success=True, latency_ms=30)
        assert ts.tool == "tool_x"
        assert ts.calls >= 1
