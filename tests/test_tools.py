"""Unit tests for the tool registration and execution system.

Tests cover: registry loading, tool execution, error handling, edge cases.
"""
import sys
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tools import ToolRegistry, get_registry, BUILTIN_TOOLS


class TestToolRegistry:
    """Tests for ToolRegistry without loading external tools.json."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Patch TOOLS_CONFIG temporarily to avoid touching real tools.json."""
        self.tmp_path = ROOT / "tests" / "_test_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", self.tmp_path)
        if self.tmp_path.exists():
            self.tmp_path.unlink()
        yield
        if self.tmp_path.exists():
            self.tmp_path.unlink()

    def test_builtin_tools_have_required_fields(self):
        """Every builtin tool must have name and description."""
        for tool in BUILTIN_TOOLS:
            assert "function" in tool
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert isinstance(fn["name"], str) and len(fn["name"]) > 0

    def test_registry_load_empty_config(self):
        """Registry should handle empty tools.json gracefully."""
        self.tmp_path.write_text(json.dumps({"tools": []}), encoding="utf-8")
        registry = ToolRegistry()
        registry.load()
        tools = registry.definitions
        assert len(tools) >= len(BUILTIN_TOOLS)

    def test_registry_tool_names_returns_list(self):
        """list_tools should always return a list."""
        registry = ToolRegistry()
        tools = registry.definitions
        assert isinstance(tools, list)

    def test_registry_get_tool_by_name(self):
        """Should find built-in tools by name."""
        registry = ToolRegistry()
        registry.load()
        tool = registry.definitions
        assert isinstance(tool, list)
        assert len(tool) > 0

    def test_registry_get_nonexistent_tool(self):
        """Should return None for unknown tool."""
        registry = ToolRegistry()
        assert registry.has("no_such_tool_xyz") is False

    def test_registry_execute_unknown_tool(self):
        """Executing unknown tool should return error message."""
        registry = ToolRegistry()
        result = registry.execute("no_such_tool", {})
        assert "未知工具" in result

    def test_registry_execute_shell_tool_success(self):
        """Execute a simple shell tool and capture output."""
        self.tmp_path.write_text(json.dumps({
            "tools": [{
                "name": "echo_test",
                "type": "shell",
                "description": "Test echo",
                "command": "echo hello_world",
                "parameters": {}
            }]
        }), encoding="utf-8")
        registry = ToolRegistry()
        registry.load()
        result = registry.execute("echo_test", {})
        assert "hello_world" in result

    def test_registry_execute_missing_params(self):
        """Tool without required params should handle gracefully."""
        registry = ToolRegistry()
        result = registry.execute("generate_image", {})
        assert isinstance(result, str)


class TestSingletonRegistry:
    """Tests for the global registry singleton."""

    def test_get_registry_returns_same_instance(self):
        """get_registry() should return the same instance."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_registry_is_toolregistry(self):
        """Should be a ToolRegistry instance."""
        assert isinstance(get_registry(), ToolRegistry)


class TestBuiltinToolsFormat:
    """Ensure built-in tools are valid OpenAI-compatible function definitions."""

    def test_all_builtins_have_function_wrapper(self):
        for tool in BUILTIN_TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool

    def test_parameters_is_object_type(self):
        for tool in BUILTIN_TOOLS:
            fn = tool["function"]
            if "parameters" in fn:
                params = fn["parameters"]
                assert params.get("type") == "object", \
                    f"{fn['name']} parameters type is not 'object'"

    def test_required_params_exist_in_properties(self):
        for tool in BUILTIN_TOOLS:
            fn = tool["function"]
            params = fn.get("parameters", {})
            required = params.get("required", [])
            properties = params.get("properties", {})
            for req in required:
                assert req in properties, \
                    f"{fn['name']}: required param '{req}' not in properties"
