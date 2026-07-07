"""
TDD tests for LayoutManager + EnvironmentInfo (ui/responsive.py)
"""
from __future__ import annotations

import os

from ui.responsive import Breakpoint, EnvironmentInfo, LayoutManager


class TestBreakpoints:
    def test_full(self):
        c = LayoutManager().update(width=165)
        assert c.dashboard_visible == True
        assert c.dashboard_compact == False

    def test_wide(self):
        c = LayoutManager().update(width=150)
        assert c.dashboard_visible == True

    def test_normal(self):
        c = LayoutManager().update(width=120)
        assert c.dashboard_visible == True
        assert c.dashboard_compact == True

    def test_narrow(self):
        c = LayoutManager().update(width=95)
        assert c.dashboard_visible == False

    def test_tight(self):
        c = LayoutManager().update(width=80)
        assert c.dashboard_visible == False
        assert c.animation_allowed == False

    def test_minimal(self):
        c = LayoutManager().update(width=60)
        assert c.dashboard_visible == False
        assert c.input_max_lines == 2


class TestEnvironmentInfo:
    def test_ssh_detection(self):
        os.environ['SSH_TTY'] = '/dev/pts/0'
        env = EnvironmentInfo.detect()
        assert env.is_ssh == True
        # SSH should not have clipboard
        assert env.has_clipboard == False
        os.environ.pop('SSH_TTY', None)

    def test_normal_desktop(self):
        # Clean environment
        for k in ['SSH_TTY', 'SSH_CONNECTION', 'TMUX']:
            os.environ.pop(k, None)
        env = EnvironmentInfo.detect()
        assert env.is_ssh == False
        assert env.is_tmux == False

    def test_tmux_detection(self):
        os.environ['TMUX'] = '/tmp/tmux-1000/default,1234,0'
        env = EnvironmentInfo.detect()
        assert env.is_tmux == True
        os.environ.pop('TMUX', None)


class TestLayoutManager:
    def test_theme_mode(self):
        mgr = LayoutManager()
        assert mgr.theme_mode in ('normal', 'high_contrast', 'mono')

    def test_ssh_override(self):
        os.environ['SSH_TTY'] = '/dev/pts/0'
        env = EnvironmentInfo.detect()
        mgr = LayoutManager(env=env)
        c = mgr.update(width=150)
        assert c.dashboard_visible == False  # SSH 强制隐藏
        assert c.animation_allowed == False
        os.environ.pop('SSH_TTY', None)

    def test_theme_override(self):
        mgr = LayoutManager()
        mgr._override_theme = "high_contrast"
        assert mgr.theme_mode == "high_contrast"
        mgr._override_theme = None

    def test_breakpoint_conversion(self):
        assert LayoutManager.width_to_breakpoint(170) == Breakpoint.FULL
        assert LayoutManager.width_to_breakpoint(145) == Breakpoint.WIDE
        assert LayoutManager.width_to_breakpoint(111) == Breakpoint.NORMAL
        assert LayoutManager.width_to_breakpoint(99) == Breakpoint.NARROW
        assert LayoutManager.width_to_breakpoint(80) == Breakpoint.TIGHT
        assert LayoutManager.width_to_breakpoint(40) == Breakpoint.MINIMAL

    def test_on_change_listener(self):
        mgr = LayoutManager()
        changes = []
        mgr.on_change(lambda c: changes.append(c))
        mgr.update(width=150)
        mgr.update(width=95)
        assert len(changes) == 2
        assert changes[0].dashboard_visible == True
        assert changes[1].dashboard_visible == False
