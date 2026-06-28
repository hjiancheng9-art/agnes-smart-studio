"""Tests for ui/badges.py — Badge class, session badges, rendering."""

from unittest.mock import MagicMock

from ui.badges import (
    Badge,
    render_badge_line,
    render_badge_plain,
    render_box_badges,
    session_badges,
)


class TestBadge:
    def test_creation(self):
        b = Badge("⚡", "Code", "cyan")
        assert b.icon == "⚡"
        assert b.text == "Code"
        assert b.color == "cyan"

    def test_render(self):
        b = Badge("⚡", "Code", "cyan")
        result = b.render()
        assert "⚡" in result
        assert "Code" in result
        assert "cyan" in result

    def test_render_dim(self):
        b = Badge("⚡", "Code", "cyan")
        result = b.render(dim=True)
        assert "dim" in result

    def test_render_box(self):
        b = Badge("⚡", "Code", "cyan")
        result = b.render_box()
        assert "⚡" in result
        assert "Code" in result


class TestSessionBadges:
    def test_none_session_returns_empty(self):
        result = session_badges(None)
        assert result == []

    def test_code_mode_badge(self):
        session = MagicMock()
        session.code_mode = True
        session.agent_mode = False
        session.enable_thinking = False
        session.active_skill = ""
        session.model = "deepseek-v4-pro"
        badges = session_badges(session)
        assert len(badges) >= 1
        assert badges[0].text == "Code"

    def test_agent_mode_badge(self):
        session = MagicMock()
        session.code_mode = False
        session.agent_mode = True
        session.enable_thinking = False
        session.active_skill = ""
        session.model = "deepseek-v4-pro"
        badges = session_badges(session)
        assert any(b.text == "Agent" for b in badges)

    def test_skill_badge(self):
        session = MagicMock()
        session.code_mode = False
        session.agent_mode = False
        session.enable_thinking = False
        session.active_skill = "showrunner"
        session.model = "deepseek-v4-pro"
        badges = session_badges(session)
        assert any("showrunner" in b.text for b in badges)


class TestRenderHelpers:
    def test_render_badge_line(self):
        b = Badge("⚡", "Code", "cyan")
        result = render_badge_line([b])
        assert isinstance(result, str)

    def test_render_badge_plain(self):
        b = Badge("⚡", "Code", "cyan")
        result = render_badge_plain([b])
        assert isinstance(result, str)

    def test_render_box_badges(self):
        b = Badge("⚡", "Code", "cyan")
        result = render_box_badges([b])
        assert isinstance(result, str)

    def test_empty_badges(self):
        assert isinstance(render_badge_line([]), str)
        assert isinstance(render_badge_plain([]), str)
        assert isinstance(render_box_badges([]), str)
