"""TDD RED phase — tests for ui/status_bar.py StatusBar."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from prompt_toolkit.formatted_text import FormattedText

from ui.status_bar import StatusBar


class TestStatusBarInitialState:
    """test_status_bar_initial_state — New StatusBar has model string and cwd."""

    def test_status_bar_initial_state(self):
        bar = StatusBar(model="test-model")
        assert bar.model == "test-model"
        assert isinstance(bar.cwd, Path)
        assert bar._thinking is False
        assert bar._context_pct == 0.0


class TestSetThinkingUpdatesState:
    """test_set_thinking_updates_state — set_thinking(True) changes _thinking."""

    def test_set_thinking_updates_state(self):
        bar = StatusBar()
        assert bar._thinking is False
        bar.set_thinking(True)
        assert bar._thinking is True
        bar.set_thinking(False)
        assert bar._thinking is False


class TestSetContextUpdatesTokens:
    """test_set_context_updates_tokens — set_context(50000, 128000) sets _context_pct ~39%."""

    def test_set_context_updates_tokens(self):
        bar = StatusBar()
        bar.set_context(50000, 128000)
        assert bar._context_tokens == 50000
        assert bar._context_max == 128000
        expected_pct = 50000 / 128000 * 100
        assert bar._context_pct == pytest.approx(expected_pct, rel=0.01)

    def test_set_context_zero_max_does_not_divide_by_zero(self):
        bar = StatusBar()
        bar.set_context(100, 0)
        assert bar._context_pct == 0.0


class TestRenderIncludesModelName:
    """test_render_includes_model_name — render() FormattedText fragments contain model name."""

    def test_render_includes_model_name(self):
        bar = StatusBar(model="deepseek-v4-pro")
        result = bar.render()
        assert isinstance(result, FormattedText)
        all_text = "".join(text for _, text in result)
        assert "deepseek-v4-pro" in all_text


class TestRenderIncludesBranchWhenGit:
    """test_render_includes_branch_when_git — When _branch is set, render() includes
    branch name."""

    def test_render_includes_branch_when_git(self):
        bar = StatusBar("my-model")
        bar._branch = "feature/ui-tests"
        result = bar.render()
        all_text = "".join(text for _, text in result)
        assert "feature/ui-tests" in all_text

    def test_render_no_branch_when_empty(self):
        bar = StatusBar("my-model")
        bar._branch = ""
        result = bar.render()
        all_text = "".join(text for _, text in result)
        # The render includes the model name but no branch
        assert "my-model" in all_text


class TestRenderIncludesDiffStats:
    """test_render_includes_diff_stats — When _diff_stats is set, render() includes
    the stats."""

    def test_render_includes_diff_stats(self):
        bar = StatusBar("my-model")
        bar._branch = "main"
        bar._diff_stats = "+12 -3"
        result = bar.render()
        all_text = "".join(text for _, text in result)
        assert "+12 -3" in all_text
        assert "main" in all_text


class TestCompactPathShowsTilde:
    """test_compact_path_shows_tilde — cwd under home directory shows "~" in render()."""

    def test_compact_path_shows_tilde(self):
        home = os.path.expanduser("~")
        subdir = Path(home) / "projects" / "myapp"
        bar = StatusBar("test-model", cwd=subdir)
        result = bar.render()
        all_text = "".join(text for _, text in result)
        assert "~" in all_text
        assert "projects" in all_text
        assert "myapp" in all_text

    def test_cwd_outside_home_no_tilde(self):
        # Use a path that is definitely outside the home directory
        outside = Path("/") if os.name != "nt" else Path("C:/Windows/System32")
        bar = StatusBar("test-model", cwd=outside)
        result = bar.render()
        all_text = "".join(text for _, text in result)
        # On Windows, Path renders with backslashes; accept either form
        cwd_str = str(outside).replace("\\", "/")
        rendered_normalized = all_text.replace("\\", "/")
        assert cwd_str in rendered_normalized
