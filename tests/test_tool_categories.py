"""Unit tests for 工具分类系统 — ToolRegistry.tool_categories + ChatSession 渲染。

验证：
- tool_categories 正确按模块前缀归类
- 所有非 builtin 工具都被分到某个分类（无遗漏）
- 分类渲染输出包含 emoji + 分类名
- definitions 全量不变（分组不影响发给 LLM 的工具集）
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tools import ToolRegistry, TOOL_CATEGORIES, get_registry
from core.chat import ChatSession


@pytest.fixture
def registry():
    """加载真实 tools.json 的 ToolRegistry（不触达 API）。"""
    reg = get_registry()
    reg.load()
    return reg


@pytest.fixture
def session():
    """mock client 的 ChatSession。"""
    mock_client = MagicMock()
    return ChatSession(mock_client)


# ── ToolRegistry.tool_categories ───────────────────────────────────


class TestToolCategories:
    def test_categories_non_empty(self, registry):
        """加载后应有多个分类。"""
        cats = registry.tool_categories
        assert len(cats) >= 5, f"expected >= 5 categories, got {len(cats)}"

    def test_all_tools_classified(self, registry):
        """每个 definition 中的工具都必须出现在某个分类里（无遗漏）。"""
        cats = registry.tool_categories
        all_names = set(registry.tool_names)
        classified = set()
        for tools in cats.values():
            classified.update(tools)
        missing = all_names - classified
        assert not missing, f"{len(missing)} tools not classified: {missing}"

    def test_no_duplicate_across_categories(self, registry):
        """同一工具不应出现在多个分类里。"""
        cats = registry.tool_categories
        seen = []
        for tools in cats.values():
            seen.extend(tools)
        assert len(seen) == len(set(seen)), "duplicate tool across categories"

    def test_github_tools_in_github_category(self, registry):
        """github_* 工具应归入 GitHub 分类。"""
        cats = registry.tool_categories
        github_cat = next((v for k, v in cats.items() if "GitHub" in k), [])
        github_names = [n for n in github_cat if n.startswith("github_")]
        assert len(github_names) >= 9, f"expected >= 9 github tools, got {github_names}"

    def test_builtin_tools_in_generate_category(self, registry):
        """generate_image / generate_video 应归入生成分类。"""
        cats = registry.tool_categories
        gen_cat = next((v for k, v in cats.items() if "生成" in k), [])
        assert "generate_image" in gen_cat
        assert "generate_video" in gen_cat

    def test_total_count_matches_definitions(self, registry):
        """分类后的工具总数应等于 definitions 数量。"""
        cats = registry.tool_categories
        total = sum(len(v) for v in cats.values())
        assert total == len(registry.definitions)


# ── ChatSession._render_tool_categories ────────────────────────────


class TestRenderToolCategories:
    def test_render_contains_emoji_headers(self, session):
        """渲染输出应包含 emoji + 分类标题。"""
        session.tools = get_registry()
        session.tools.load()
        rendered = session._render_tool_categories()
        assert "当前可用工具" in rendered
        # 至少有一个 emoji 开头的分类行
        assert any(line.strip().startswith("- **") for line in rendered.split("\n"))

    def test_render_contains_github_category(self, session):
        """渲染应包含 GitHub 分类。"""
        session.tools = get_registry()
        session.tools.load()
        rendered = session._render_tool_categories()
        assert "GitHub" in rendered

    def test_render_empty_falls_back_to_flat_list(self, session):
        """无分类时回退到扁平列表（向后兼容）。"""
        session.tools = MagicMock()
        session.tools.tool_categories = {}
        session.tools.tool_names = ["tool_a", "tool_b"]
        rendered = session._render_tool_categories()
        assert "tool_a" in rendered
        assert "tool_b" in rendered


# ── definitions 不受分组影响 ────────────────────────────────────────


class TestDefinitionsUnchanged:
    def test_definitions_count_stable(self, registry):
        """分组前后 definitions 数量不变（分组是只读视图）。"""
        before = len(registry.definitions)
        _ = registry.tool_categories  # 触发分类
        after = len(registry.definitions)
        assert before == after

    def test_definitions_format_intact(self, registry):
        """每个 definition 仍是 OpenAI function 格式。"""
        for d in registry.definitions:
            assert d["type"] == "function"
            assert "name" in d["function"]
            assert "parameters" in d["function"]
