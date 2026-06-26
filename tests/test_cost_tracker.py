"""Tests for core.cost_tracker — cost/token/budget tracking."""

import json

import pytest


@pytest.fixture(autouse=True)
def isolate_cost_files(tmp_path, monkeypatch):
    """Redirect COST_LOG and COST_STATE to tmp_path so tests don't touch real files."""
    import core.cost_tracker as ct

    cost_log = tmp_path / "cost_log.jsonl"
    cost_state = tmp_path / "cost_state.json"
    monkeypatch.setattr(ct, "COST_LOG", cost_log)
    monkeypatch.setattr(ct, "COST_STATE", cost_state)
    # Clean state at start
    ct._save_state({"total_cost": 0.0, "total_calls": 0, "budget": None, "by_model": {}, "by_day": {}, "by_kind": {}})
    yield
    # Cleanup is automatic with tmp_path


class TestPricing:
    """calc_cost computes cost from pricing table."""

    def test_text_model_cost(self):
        from core.cost_tracker import calc_cost

        # agnes-2.0-flash: input 0.003/1k, output 0.012/1k
        cost = calc_cost("agnes-2.0-flash", "text", {"prompt_tokens": 1000, "completion_tokens": 500})
        # 1.0 * 0.003 + 0.5 * 0.012 = 0.003 + 0.006 = 0.009
        assert abs(cost - 0.009) < 1e-6

    def test_image_model_cost(self):
        from core.cost_tracker import calc_cost

        cost = calc_cost("agnes-image-2.0-flash", "image", call_count=1)
        assert abs(cost - 0.02) < 1e-6

    def test_video_model_cost(self):
        from core.cost_tracker import calc_cost

        cost = calc_cost("agnes-video-v2.0", "video", call_count=2)
        assert abs(cost - 0.70) < 1e-6

    def test_unknown_model_uses_default(self):
        from core.cost_tracker import calc_cost

        # Unknown model: should use defaults, not crash
        cost = calc_cost("some-unknown-model", "text", {"prompt_tokens": 1000, "completion_tokens": 0})
        # default text input 0.003/1k
        assert cost > 0

    def test_unknown_image_model_inferred(self):
        from core.cost_tracker import calc_cost

        cost = calc_cost("my-custom-image-model", "image")
        # Should infer image pricing
        assert cost > 0

    def test_no_usage_text_returns_zero(self):
        from core.cost_tracker import calc_cost

        # text model without usage → 0.0（不再误走 per_call 固定费）
        cost = calc_cost("agnes-2.0-flash", "text", usage=None)
        assert cost == 0.0

    def test_empty_usage_text_returns_zero(self):
        from core.cost_tracker import calc_cost

        # text model with empty usage dict → 0.0
        cost = calc_cost("agnes-2.0-flash", "text", usage={})
        assert cost == 0.0


class TestRecordUsage:
    """record_usage writes to log and accumulates state."""

    def test_record_returns_entry(self):
        from core.cost_tracker import record_usage

        entry = record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 100, "completion_tokens": 50}, label="test")
        assert entry["model"] == "agnes-2.0-flash"
        assert entry["label"] == "test"
        assert "cost" in entry
        assert entry["cost"] > 0

    def test_record_accumulates_state(self):
        from core.cost_tracker import get_summary, record_usage

        record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 1000, "completion_tokens": 500})
        record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 1000, "completion_tokens": 500})
        summary = get_summary()
        assert summary["total_calls"] == 2
        # Two calls of 0.009 each
        assert abs(summary["total_cost"] - 0.018) < 1e-5

    def test_record_writes_to_log(self):
        from core.cost_tracker import COST_LOG, record_usage

        record_usage("agnes-image-2.0-flash", "image", label="gen")
        assert COST_LOG.exists()
        lines = COST_LOG.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["model"] == "agnes-image-2.0-flash"
        assert data["kind"] == "image"

    def test_by_model_breakdown(self):
        from core.cost_tracker import get_summary, record_usage

        record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 1000, "completion_tokens": 0})
        record_usage("agnes-image-2.0-flash", "image")
        summary = get_summary()
        assert "agnes-2.0-flash" in summary["by_model"]
        assert "agnes-image-2.0-flash" in summary["by_model"]

    def test_by_kind_breakdown(self):
        from core.cost_tracker import get_summary, record_usage

        record_usage("agnes-image-2.0-flash", "image")
        summary = get_summary()
        assert "image" in summary["by_kind"]
        assert summary["by_kind"]["image"]["calls"] == 1


class TestSummary:
    """get_summary, get_recent_records, get_daily_breakdown."""

    def test_empty_summary(self):
        from core.cost_tracker import get_summary

        s = get_summary()
        assert s["total_cost"] == 0.0
        assert s["total_calls"] == 0

    def test_recent_records(self):
        from core.cost_tracker import get_recent_records, record_usage

        for _i in range(5):
            record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 100, "completion_tokens": 50})
        recs = get_recent_records(limit=3)
        assert len(recs) == 3

    def test_recent_records_empty(self):
        from core.cost_tracker import get_recent_records

        assert get_recent_records() == []

    def test_daily_breakdown(self):
        from core.cost_tracker import get_daily_breakdown, record_usage

        record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 1000, "completion_tokens": 500})
        bd = get_daily_breakdown(days=7)
        assert len(bd) >= 1
        assert "day" in bd[0]
        assert bd[0]["cost"] > 0


class TestBudget:
    """Budget management."""

    def test_set_budget(self):
        from core.cost_tracker import get_summary, set_budget

        result = set_budget(daily_usd=5.0)
        assert result == {"daily": 5.0}
        assert get_summary()["budget"] == {"daily": 5.0}

    def test_clear_budget(self):
        from core.cost_tracker import get_summary, set_budget

        set_budget(daily_usd=5.0)
        set_budget(daily_usd=None)
        assert get_summary()["budget"] is None

    def test_check_budget_under_limit(self):
        from core.cost_tracker import check_budget, record_usage, set_budget

        set_budget(daily_usd=100.0)  # high limit
        record_usage("agnes-2.0-flash", "text", {"prompt_tokens": 100, "completion_tokens": 50})
        assert check_budget() is None  # not over

    def test_check_budget_over_limit(self):
        from core.cost_tracker import check_budget, record_usage, set_budget

        set_budget(daily_usd=0.001)  # very low limit
        record_usage("agnes-image-2.0-flash", "image")  # costs 0.02
        warning = check_budget()
        assert warning is not None
        assert "预算" in warning or "%" in warning

    def test_check_budget_no_limit(self):
        from core.cost_tracker import check_budget

        assert check_budget() is None


class TestReset:
    """reset_cost clears state."""

    def test_reset_returns_old_total(self):
        from core.cost_tracker import get_summary, record_usage, reset_cost

        record_usage("agnes-image-2.0-flash", "image")
        result = reset_cost()
        assert result["cleared_total"] > 0
        # After reset, state should be clean
        s = get_summary()
        assert s["total_cost"] == 0.0
        assert s["total_calls"] == 0
