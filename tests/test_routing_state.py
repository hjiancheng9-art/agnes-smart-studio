"""Tests for core.routing_state.RoutingState."""

from __future__ import annotations

from core.routing_state import RoutingState


class TestRoutingState:
    def test_default_init(self):
        state = RoutingState()
        assert state.active_provider == "deepseek"
        assert state.active_model == ""

    def test_custom_init(self):
        state = RoutingState(active_provider="crux", active_model="agnes-2.0-pro")
        assert state.active_provider == "crux"
        assert state.active_model == "agnes-2.0-pro"

    def test_select_updates_model(self):
        state = RoutingState()
        state.select("crux", "agnes-2.0-flash")
        assert state.active_provider == "crux"
        assert state.active_model == "agnes-2.0-flash"
        assert not state.pinned

    def test_select_with_pin(self):
        state = RoutingState()
        state.select("deepseek", "deepseek-v4-pro", pin=True)
        assert state.pinned is True

    def test_record_fallback(self):
        state = RoutingState()
        assert state.fallback_count == 0
        state.record_fallback()
        assert state.fallback_count == 1
        state.record_fallback()
        assert state.fallback_count == 2

    def test_can_fallback_same_provider(self):
        state = RoutingState(active_provider="deepseek")
        assert state.can_fallback("deepseek") is True

    def test_can_fallback_cross_provider_blocked(self):
        state = RoutingState(active_provider="deepseek")
        assert state.can_fallback("crux") is False

    def test_can_fallback_cross_provider_allowed(self):
        state = RoutingState(active_provider="deepseek", allow_cross_provider_fallback=True)
        assert state.can_fallback("crux") is True
