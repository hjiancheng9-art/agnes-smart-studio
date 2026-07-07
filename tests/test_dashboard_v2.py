"""
TDD tests for DashboardState + render (ui/dashboard.py)
"""
from __future__ import annotations

from ui.dashboard import DashboardState, render_dashboard
from ui.responsive import LayoutManager


class TestDashboardState:
    def test_default_idle(self):
        s = DashboardState()
        assert s.state == "idle"
        assert not s._show_secondary

    def test_state_transitions(self):
        s = DashboardState()
        s.set_state("active")
        assert s.state == "active"
        s.set_state("error")
        assert s.state == "error"
        s.set_state("streaming")
        assert s.state == "streaming"

    def test_error_messages(self):
        s = DashboardState()
        s.set_error("Something broke")
        assert s.error_msg == "Something broke"
        assert s.state == "error"
        s.clear_error()
        assert s.error_msg == ""
        assert s.state == "idle"

    def test_activity_pulse(self):
        s = DashboardState()
        assert not s.is_hot
        s.set_activity(tool_name="test_tool", status="running")
        assert s.is_hot

    def test_secondary_toggle(self):
        s = DashboardState()
        s.toggle_secondary()
        assert s._show_secondary
        s.toggle_secondary()
        assert not s._show_secondary

    def test_secondary_update(self):
        s = DashboardState()
        s.update_secondary(cpu=45.0, mem_pct=60.0, mem_used=4096,
                           mem_total=8192, disk=55.0, processes=128, uptime=72.5)
        assert s._cpu_pct == 45.0
        assert s._memory_pct == 60.0
        assert s._memory_used_mb == 4096
        assert s._disk_pct == 55.0
        assert s._process_count == 128
        assert s._uptime_hours == 72.5


class TestRenderDashboard:
    def setup_method(self):
        self.mgr = LayoutManager()

    def test_idle_render(self):
        state = DashboardState()
        config = self.mgr.update(width=120)
        result = render_dashboard(state, config)
        assert len(result) > 0
        assert any('Context' in t for _, t in result)

    def test_error_render(self):
        state = DashboardState()
        state.set_error("Something went wrong!")
        config = self.mgr.update(width=120)
        result = render_dashboard(state, config)
        has_error = any('ERROR' in t for _, t in result)
        assert has_error

    def test_hidden_when_not_visible(self):
        state = DashboardState()
        config = self.mgr.update(width=85)  # NARROW → hidden
        result = render_dashboard(state, config)
        assert result == []

    def test_compact_mode(self):
        state = DashboardState()
        config = self.mgr.update(width=120)  # NORMAL → compact
        result = render_dashboard(state, config)
        # Compact mode should have fewer sections
        has_tool_section = any('TOOL' in t for _, t in result)
        assert not has_tool_section

    def test_secondary_panel(self):
        state = DashboardState()
        state.toggle_secondary()
        state.update_secondary(cpu=95.0, mem_pct=92.0, disk=98.0)
        config = self.mgr.update(width=150)  # WIDE → expanded
        result = render_dashboard(state, config)
        has_system = any('SYSTEM' in t for _, t in result)
        assert has_system
        has_error_style = any('class:error' in s for s, _ in result)
        assert has_error_style  # 95% CPU → error color

    def test_context_thresholds(self):
        state = DashboardState()
        state._context_pct = 90.0
        config = self.mgr.update(width=120)
        result = render_dashboard(state, config)
        # High context should show warning/error
        found_ctx = [t for s, t in result if '90' in t and 'Context' in t]
        assert len(found_ctx) > 0
