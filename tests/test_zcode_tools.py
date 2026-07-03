"""
ZCode TDD: CRUX tools.json registry validation tests.

RED phase — write tests first, confirm they fail, then fix.
"""

import json
import importlib
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tools():
    """Load tools.json once per test module."""
    path = PROJECT_ROOT / "tools.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["tools"]


@pytest.fixture(scope="module")
def tool_names(tools):
    return [t["name"] for t in tools]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestToolCount:
    def test_tool_count(self, tools):
        """tools.json has exactly 97 tools."""
        assert len(tools) == 97, f"Expected 97 tools, got {len(tools)}"


class TestToolIntegrity:
    def test_no_duplicate_names(self, tool_names, tools):
        """No duplicate tool names."""
        seen = set()
        dupes = []
        for name in tool_names:
            if name in seen:
                dupes.append(name)
            seen.add(name)
        assert not dupes, f"Duplicate tool names: {dupes}"

    def test_all_tools_have_required_fields(self, tools):
        """Every tool has 'name' and either 'function' or 'command'."""
        bad = []
        for t in tools:
            has_name = "name" in t
            has_func = "function" in t
            has_cmd = "command" in t
            if not has_name or not (has_func or has_cmd):
                bad.append(t.get("name", "<no-name>"))
        assert not bad, f"Tools missing required fields: {bad}"

    def test_all_functions_resolve(self, tools):
        """For each tool with 'function', the module.function path is importable."""
        failures = []
        for t in tools:
            func_path = t.get("function")
            if not func_path:
                continue
            parts = func_path.rsplit(".", 1)
            if len(parts) != 2:
                failures.append(f"{func_path}: cannot split into module.function")
                continue
            mod_name, attr_name = parts
            try:
                mod = importlib.import_module(mod_name)
                if not hasattr(mod, attr_name):
                    failures.append(f"{func_path}: module loaded but no attribute '{attr_name}'")
            except Exception as exc:
                failures.append(f"{func_path}: {exc}")
        assert not failures, "\n".join(failures)


class TestLspTools:
    LSP_TOOLS = [
        "lsp_goto_definition",
        "lsp_hover",
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_completion",
        "lsp_rename",
    ]

    def test_lsp_tools_present(self, tool_names):
        """All 6 LSP tools exist."""
        missing = [n for n in self.LSP_TOOLS if n not in tool_names]
        assert not missing, f"Missing LSP tools: {missing}"


class TestReviewTools:
    REVIEW_TOOLS = ["code_review", "security_review"]

    def test_review_tools_present(self, tool_names):
        """code_review and security_review exist."""
        missing = [n for n in self.REVIEW_TOOLS if n not in tool_names]
        assert not missing, f"Missing review tools: {missing}"


class TestFormatTools:
    def test_format_tools_present(self, tools):
        """run_format uses core.format_tools.execute_run_format."""
        run_format = next((t for t in tools if t["name"] == "run_format"), None)
        assert run_format is not None, "run_format tool not found"
        assert run_format.get("function") == "core.format_tools.execute_run_format", \
            f"Expected core.format_tools.execute_run_format, got {run_format.get('function')}"


class TestNotebookTools:
    def test_notebook_tools_present(self, tool_names):
        """5 notebook tools exist."""
        nb = [n for n in tool_names if "notebook" in n.lower()]
        assert len(nb) == 5, f"Expected 5 notebook tools, got {len(nb)}: {nb}"


class TestNewTools:
    NEW_TOOLS = ["http_request", "db_query", "estimate_tokens", "inspect_last_error"]

    def test_new_tools_present(self, tool_names):
        """http_request, db_query, estimate_tokens, inspect_last_error exist."""
        missing = [n for n in self.NEW_TOOLS if n not in tool_names]
        assert not missing, f"Missing new tools: {missing}"


class TestDebugInspect:
    def test_debug_inspect_resolves(self):
        """core.pytest_runner.debug_inspect is importable."""
        try:
            mod = importlib.import_module("core.pytest_runner")
            assert hasattr(mod, "debug_inspect"), \
                "core.pytest_runner has no attribute 'debug_inspect'"
        except Exception as exc:
            pytest.fail(f"core.pytest_runner.debug_inspect not importable: {exc}")


class TestDisplayTools:
    DISPLAY_FUNCS = [
        ("ui.display", "_view_image"),
        ("ui.display", "_update_plan"),
        ("ui.display", "_tool_search"),
        ("ui.display", "_request_user_input"),
    ]

    def test_display_tools_resolve(self):
        """ui.display._view_image, _update_plan, _tool_search, _request_user_input are importable."""
        failures = []
        for mod_name, attr_name in self.DISPLAY_FUNCS:
            try:
                mod = importlib.import_module(mod_name)
                if not hasattr(mod, attr_name):
                    failures.append(f"{mod_name}.{attr_name}: module loaded but no such attribute")
            except Exception as exc:
                failures.append(f"{mod_name}.{attr_name}: {exc}")
        assert not failures, "\n".join(failures)
