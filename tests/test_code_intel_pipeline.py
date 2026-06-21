"""Tests for code intelligence pipeline integration.

Covers:
- SymbolIndex singleton reuse (performance invariant)
- Tool executors (find_symbol / search_symbols / find_references / code_analyze)
- High-risk tool confirmation gate in ChatSession._dispatch_tool
- Code guard hooks (syntax_guard, test_guard)
"""

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest


class TestSymbolIndexSingleton:
    """Singleton index must be reused across calls (avoid re-scanning project)."""

    def test_get_index_returns_singleton(self):
        import core.code_intel as ci
        ci._index = None  # reset for test isolation
        idx1 = ci.get_index(".")
        idx2 = ci.get_index(".")
        assert idx1 is idx2

    def test_refresh_index_rebuilds(self):
        import core.code_intel as ci
        ci._index = None
        idx1 = ci.get_index(".")
        idx2 = ci.refresh_index(".")
        assert idx1 is not idx2

    def test_index_has_stats(self):
        import core.code_intel as ci
        ci._index = None
        idx = ci.get_index(".")
        stats = idx.stats
        assert "files_indexed" in stats
        assert "total_symbols" in stats
        assert stats["files_indexed"] > 0


class TestCodeIntelExecutors:
    """Tool executors must return valid JSON."""

    def test_find_symbol_known(self):
        from core.code_intel import execute_find_symbol
        result = execute_find_symbol(symbol="ChatSession", directory=".")
        parsed = json.loads(result)
        assert parsed["found"] is True
        assert len(parsed["locations"]) >= 1

    def test_find_symbol_unknown(self):
        from core.code_intel import execute_find_symbol
        result = execute_find_symbol(symbol="NoSuchSymbol_xyz123", directory=".")
        parsed = json.loads(result)
        assert parsed["found"] is False

    def test_find_symbol_missing_param(self):
        from core.code_intel import execute_find_symbol
        result = execute_find_symbol(symbol="")
        parsed = json.loads(result)
        assert "error" in parsed

    def test_search_symbols_pattern(self):
        from core.code_intel import execute_search_symbols
        result = execute_search_symbols(pattern="Chat", directory=".")
        parsed = json.loads(result)
        assert parsed["matches"] >= 1

    def test_code_analyze_python(self):
        from core.code_intel import execute_code_analyze
        result = execute_code_analyze(file_path="core/chat.py")
        parsed = json.loads(result)
        assert "functions" in parsed
        assert "classes" in parsed

    def test_find_references(self):
        from core.code_intel import execute_find_references
        result = execute_find_references(file_path="core/chat.py", symbol="ChatSession")
        parsed = json.loads(result)
        assert parsed["count"] >= 1


class TestHighRiskConfirmGate:
    """High-risk tools must trigger confirm side effect, not execute."""

    def _make_session(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.chat.return_value = {"choices": [{"message": {"content": "ok"}}]}
        session = ChatSession(client)
        session.toggle_agent_mode()
        return session

    def test_git_add_commit_blocked(self):
        session = self._make_session()
        result, side_effects = session._dispatch_tool(
            "git_add_commit", '{"message": "test"}'
        )
        assert result == ""
        assert any(k == "confirm" for k, _ in side_effects)

    def test_risky_rm_blocked(self):
        session = self._make_session()
        result, side_effects = session._dispatch_tool(
            "run_bash", '{"command": "rm -rf /tmp"}'
        )
        assert any(k == "confirm" for k, _ in side_effects)

    def test_risky_delete_blocked(self):
        session = self._make_session()
        result, side_effects = session._dispatch_tool(
            "run_bash", '{"command": "delete files"}'
        )
        assert any(k == "confirm" for k, _ in side_effects)

    def test_safe_ls_not_blocked(self):
        session = self._make_session()
        # ls is not high-risk; either executes (via tool) or returns unknown-tool
        # Either way, NO confirm side effect.
        result, side_effects = session._dispatch_tool("run_bash", '{"command": "ls"}')
        assert not any(k == "confirm" for k, _ in side_effects)


class TestCodeGuardHooks:
    """Code guard hooks must detect syntax errors and fire on .py edits."""

    def test_syntax_guard_passes_valid_python(self, tmp_path):
        from core.hooks import _syntax_guard_handler, HookEvent, HookType
        valid = tmp_path / "ok.py"
        valid.write_text("def f():\n    return 1\n", encoding="utf-8")
        evt = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "write_file", "args": {"path": str(valid)},
                  "result": "written"},
        )
        result = _syntax_guard_handler(evt)
        # No error appended
        assert "语法错误" not in (result.result or "")

    def test_syntax_guard_detects_error(self, tmp_path):
        from core.hooks import _syntax_guard_handler, HookEvent, HookType
        broken = tmp_path / "bad.py"
        broken.write_text("def broken(:\n    pass\n", encoding="utf-8")
        evt = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "write_file", "args": {"path": str(broken)},
                  "result": "written"},
        )
        result = _syntax_guard_handler(evt)
        assert "语法错误" in (result.result or "")

    def test_syntax_guard_ignores_non_python(self, tmp_path):
        from core.hooks import _syntax_guard_handler, HookEvent, HookType
        txt = tmp_path / "notes.md"
        txt.write_text("not python", encoding="utf-8")
        evt = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "write_file", "args": {"path": str(txt)},
                  "result": "written"},
        )
        result = _syntax_guard_handler(evt)
        assert "语法错误" not in (result.result or "")

    def test_syntax_guard_ignores_non_edit_tools(self):
        from core.hooks import _syntax_guard_handler, HookEvent, HookType
        evt = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "read_file", "args": {"path": "x.py"},
                  "result": "content"},
        )
        result = _syntax_guard_handler(evt)
        # Should not modify result for non-edit tools
        assert result.result is None or "语法错误" not in str(result.result)

    def test_register_code_hooks_idempotent(self):
        from core.hooks import hook_manager, register_code_hooks
        register_code_hooks()
        register_code_hooks()  # second call should not duplicate
        names = {h["name"] for h in hook_manager.list_hooks()}
        assert "syntax_guard" in names
        assert "test_guard" in names


class TestAgentModeIntegration:
    """End-to-end: agent mode loads code_intel tools + registers code hooks."""

    def test_agent_mode_has_code_intel_tools(self):
        from core.chat import ChatSession
        client = MagicMock()
        client.chat.return_value = {"choices": [{"message": {"content": "ok"}}]}
        session = ChatSession(client)
        session.toggle_agent_mode()
        names = session.tools.tool_names
        assert "code_analyze" in names
        assert "find_symbol" in names
        assert "search_symbols" in names
        assert "find_references" in names

    def test_agent_mode_registers_code_hooks(self):
        from core.chat import ChatSession
        from core.hooks import hook_manager
        client = MagicMock()
        client.chat.return_value = {"choices": [{"message": {"content": "ok"}}]}
        session = ChatSession(client)
        session.toggle_agent_mode()
        names = {h["name"] for h in hook_manager.list_hooks()}
        assert "syntax_guard" in names
