"""Tests for the ToolRegistry — builtin tool definitions, registration, and loading.

These tests validate the tool registry and tool definition structures
without requiring actual HTTP calls or external services.
"""

from core.tools import (
    BUILTIN_TOOLS,
    COMFYUI_TOOL_DEFS,
    PIPELINE_TOOL_DEFS,
    ToolRegistry,
    get_registry,
)


class TestBuiltinTools:
    """BUILTIN_TOOLS should have valid structure."""

    def test_builtin_tools_not_empty(self):
        assert len(BUILTIN_TOOLS) >= 3

    def test_each_tool_has_name_and_params(self):
        for tool in BUILTIN_TOOLS:
            fn = tool.get("function", {})
            assert "name" in fn, f"Tool missing name: {fn}"
            assert "parameters" in fn, f"Tool {fn['name']} missing parameters"
            params = fn["parameters"]
            assert "properties" in params

    def test_generate_image_tool_structure(self):
        tool = next((t for t in BUILTIN_TOOLS if t["function"]["name"] == "generate_image"), None)
        assert tool is not None
        params = tool["function"]["parameters"]["properties"]
        assert "prompt" in params

    def test_generate_video_tool_structure(self):
        tool = next((t for t in BUILTIN_TOOLS if t["function"]["name"] == "generate_video"), None)
        assert tool is not None
        params = tool["function"]["parameters"]["properties"]
        assert "prompt" in params

    def test_multi_agent_tool_structure(self):
        tool = next((t for t in BUILTIN_TOOLS if t["function"]["name"] == "multi_agent"), None)
        assert tool is not None
        params = tool["function"]["parameters"]["properties"]
        assert "goal" in params


class TestComfyuiToolDefs:
    def test_comfyui_tools_defined(self):
        assert isinstance(COMFYUI_TOOL_DEFS, list)
        assert len(COMFYUI_TOOL_DEFS) > 0

    def test_each_comfyui_tool_has_function_block(self):
        for tool in COMFYUI_TOOL_DEFS:
            fn = tool.get("function", {})
            assert "name" in fn


class TestPipelineToolDefs:
    def test_pipeline_tools_defined(self):
        assert isinstance(PIPELINE_TOOL_DEFS, list)

    def test_each_pipeline_tool_has_name(self):
        for tool in PIPELINE_TOOL_DEFS:
            fn = tool.get("function", {})
            assert "name" in fn


class TestToolRegistryInit:
    def test_get_registry_returns_instance(self):
        reg = get_registry()
        assert isinstance(reg, ToolRegistry)

    def test_get_registry_singleton(self):
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_registry_has_definitions_property(self):
        reg = get_registry()
        assert hasattr(reg, "definitions")
        assert isinstance(reg.definitions, list)
        assert len(reg.definitions) >= 3  # generate_image, generate_video, multi_agent

    def test_registry_has_tool_names(self):
        reg = get_registry()
        names = reg.tool_names
        assert isinstance(names, list)
        assert "generate_image" in names
        assert "generate_video" in names

    def test_registry_has_execute(self):
        reg = get_registry()
        assert hasattr(reg, "execute")
        assert callable(reg.execute)


class TestToolRegistryLoad:
    def test_load_basic(self):
        reg = ToolRegistry()
        count = reg.load()
        assert count >= 3  # generate_image, generate_video, multi_agent

    def test_load_twice_rebuilds(self):
        reg = ToolRegistry()
        count1 = reg.load()
        count2 = reg.load()
        assert count1 == count2  # should be deterministic

    def test_load_browser_adds_more(self):
        reg = ToolRegistry()
        base = reg.load()
        count = reg.load(browser=True)
        assert count >= base

    def test_load_mcp_adds_more(self):
        reg = ToolRegistry()
        base = reg.load()
        count = reg.load(mcp=True)
        assert count >= base

    def test_has_method_works(self):
        reg = ToolRegistry()
        reg.load()
        # builtin tools don't have executors in ToolRegistry (handled by ChatSession)
        # but externally-loaded tools do
        assert reg.has("generate_image") is False  # builtin, no executor in registry
        assert reg.has("nonexistent_tool_xyz") is False


class TestToolDefinitionsJSON:
    """Validate tools.json structure (the external config file)."""

    def test_tools_json_exists(self):
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "tools.json"
        assert path.exists()

    def test_tools_json_valid(self):
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "tools.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "tools" in data
        assert isinstance(data["tools"], list)
