"""Tests for core/tool_router.py — internal + MCP tool routing."""

import asyncio

import pytest

from core.tool_router import (
    register_internal,
    register_mcp_tools,
    list_all_tools,
    find_tool,
    get_tool_schema,
    get_tool_router,
)


class TestRegisterAndList:
    """Registration and listing — pure logic, no I/O dependencies."""

    def test_register_internal_adds_handler(self):
        def my_handler(**kw):
            return {"ok": True, **kw}
        register_internal("test_handler_1", my_handler)
        # _internal_tools are runtime handlers, not in tools.json listing.
        # Verify by calling the tool instead.
        from core.tool_router import call_tool
        result = asyncio.run(call_tool("test_handler_1", {"x": 1}))
        assert result["success"] is True
        assert result["result"] == {"ok": True, "x": 1}

    def test_register_mcp_tools_counts_correctly(self):
        n = register_mcp_tools("test_server", [
            {"name": "tool_a", "description": "A"},
            {"name": "tool_b", "description": "B", "inputSchema": {"type": "object"}},
        ])
        assert n == 2

    def test_register_mcp_tools_appear_in_list(self):
        register_mcp_tools("srv", [
            {"name": "echo", "description": "Echoes input"},
        ])
        tools = list_all_tools()
        mcp_tools = [t for t in tools if t.get("source") == "mcp" and t["name"] == "mcp.srv.echo"]
        assert len(mcp_tools) == 1
        assert mcp_tools[0]["server"] == "srv"
        assert mcp_tools[0]["description"] == "Echoes input"

    def test_list_all_tools_includes_internal_tools(self):
        tools = list_all_tools()
        internal = [t for t in tools if t.get("source") == "internal"]
        # tools.json must have at least a few entries
        assert len(internal) >= 5
        # Verify internal tools have expected shape
        for t in internal:
            assert "name" in t
            assert "description" in t
            assert "source" in t

    def test_list_all_tools_includes_both_sources(self):
        register_mcp_tools("dual_test", [{"name": "dual_tool"}])
        tools = list_all_tools()
        sources = {t.get("source") for t in tools}
        assert "internal" in sources
        assert "mcp" in sources


class TestFindTool:
    """Tool lookup — exact and fuzzy matching."""

    def test_find_exact_internal_tool(self):
        # "read_file" is a guaranteed internal tool
        result = find_tool("read_file")
        assert result is not None
        assert result["name"] == "read_file"
        assert result["source"] == "internal"

    def test_find_exact_mcp_tool(self):
        register_mcp_tools("finder", [{"name": "search", "description": "search"}])
        result = find_tool("mcp.finder.search")
        assert result is not None
        assert result["name"] == "mcp.finder.search"
        assert result["source"] == "mcp"
        assert result["server"] == "finder"

    def test_find_fuzzy_without_prefix(self):
        register_mcp_tools("fuzzy", [{"name": "unique_tool_name_xyz", "description": "X"}])
        # Should find by suffix match
        result = find_tool("unique_tool_name_xyz")
        assert result is not None
        assert "unique_tool_name_xyz" in result["name"]

    def test_find_nonexistent_returns_none(self):
        result = find_tool("this_tool_does_not_exist_12345")
        assert result is None

    def test_find_empty_name(self):
        result = find_tool("")
        assert result is None


class TestGetToolSchema:
    """Schema retrieval — tools.json and registry fallback."""

    def test_get_schema_for_known_tool(self):
        schema = get_tool_schema("read_file")
        assert schema is not None
        assert isinstance(schema, dict)
        # tools.json returns flat parameter definitions: {"path": {...}, "offset": {...}}
        assert len(schema) > 0
        # Each value should be a parameter definition dict
        for k, v in schema.items():
            assert isinstance(v, dict), f"Parameter {k} definition should be dict"
            assert "type" in v or "description" in v, f"Parameter {k} missing type/description"

    def test_get_schema_for_nonexistent_tool(self):
        schema = get_tool_schema("__no_such_tool_ever__")
        assert schema is None or schema == {}

    def test_get_schema_for_mcp_tool(self):
        register_mcp_tools("schema_srv", [{
            "name": "schema_test",
            "description": "T",
            "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
        }])
        schema = get_tool_schema("mcp.schema_srv.schema_test")
        assert schema is not None
        assert "type" in schema

    def test_get_schema_returns_dict(self):
        for name in ["read_file", "search_files", "run_bash"]:
            schema = get_tool_schema(name)
            if schema is None:
                continue
            assert isinstance(schema, dict), f"Schema for {name} should be dict"


class TestGetToolRouter:
    """Compatibility wrapper."""

    def test_returns_dict_with_all_keys(self):
        router = get_tool_router()
        assert isinstance(router, dict)
        for key in ["list", "find", "call", "register", "index_mcp"]:
            assert key in router, f"Missing key: {key}"

    def test_all_values_are_callable(self):
        router = get_tool_router()
        for key, val in router.items():
            assert callable(val), f"{key} should be callable"


class TestCallInternal:
    """call_tool — internal tool dispatch (requires register + call)."""

    @pytest.mark.asyncio
    async def test_call_registered_internal_tool(self):
        from core.tool_router import call_tool

        def echo_handler(**kw):
            return f"echo: {kw}"

        register_internal("echo_test_abc", echo_handler)
        result = await call_tool("echo_test_abc", {"msg": "hello"})
        assert result["success"] is True
        assert "echo" in str(result["result"])
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self):
        from core.tool_router import call_tool

        result = await call_tool("__absolutely_not_a_tool__", {"x": 1})
        assert result["success"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_call_tool_with_none_arguments(self):
        from core.tool_router import call_tool

        def no_arg_handler(**kw):
            return "ok"

        register_internal("no_arg_test", no_arg_handler)
        result = await call_tool("no_arg_test", None)
        assert result["success"] is True
        assert result["result"] == "ok"

    @pytest.mark.asyncio
    async def test_call_tool_handler_raising_exception(self):
        from core.tool_router import call_tool

        def crash_handler(**kw):
            raise RuntimeError("intentional crash for testing")

        register_internal("crash_test", crash_handler)
        result = await call_tool("crash_test", {})
        assert result["success"] is False
        assert "intentional crash" in result["error"]
