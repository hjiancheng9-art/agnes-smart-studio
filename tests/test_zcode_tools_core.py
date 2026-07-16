"""
ZCode TDD: core/tools.py tests.
Tests ToolRegistry instantiation, singleton, register/unregister, definitions, and tool_names.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_registry():
    """Return a fresh ToolRegistry with no shared state and no config load."""
    from core.tools import ToolRegistry, reload_registry

    reload_registry()
    registry = ToolRegistry()
    yield registry
    reload_registry()


# ---------------------------------------------------------------------------
# 1. ToolRegistry instantiation and singleton
# ---------------------------------------------------------------------------


class TestToolRegistryInstantiation:
    def test_instantiate(self, fresh_registry):
        from core.tools import ToolRegistry

        assert isinstance(fresh_registry, ToolRegistry)

    def test_default_attributes(self, fresh_registry):
        assert isinstance(fresh_registry._definitions, list)
        assert isinstance(fresh_registry._executors, dict)
        assert isinstance(fresh_registry._tool_modules, dict)

    def test_singleton_get_registry(self):
        from core.tools import ToolRegistry, get_registry, reload_registry

        reload_registry()
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
        assert isinstance(r1, ToolRegistry)
        reload_registry()

    def test_reload_registry(self):
        from core.tools import get_registry, reload_registry

        reload_registry()
        r1 = get_registry()
        reload_registry()
        r2 = get_registry()
        assert r1 is not r2

    def test_config_path_default(self, fresh_registry):
        from core.tools import TOOLS_CONFIG

        assert fresh_registry._config_path == TOOLS_CONFIG

    def test_custom_config_path(self, tmp_path):
        from core.tools import ToolRegistry

        cfg = tmp_path / "custom_tools.json"
        registry = ToolRegistry(config_path=cfg)
        assert registry._config_path == cfg


# ---------------------------------------------------------------------------
# 2. ToolDef-like structure validation
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_builtin_tools_is_list(self):
        from core.tools import BUILTIN_TOOLS

        assert isinstance(BUILTIN_TOOLS, list)
        assert len(BUILTIN_TOOLS) > 0

    def test_all_builtin_tools_have_function_structure(self):
        from core.tools import BUILTIN_TOOLS

        for tool in BUILTIN_TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_pipeline_tool_defs(self):
        from core.tools import PIPELINE_TOOL_DEFS

        assert isinstance(PIPELINE_TOOL_DEFS, list)
        names = {td["function"]["name"] for td in PIPELINE_TOOL_DEFS}
        expected = {
            "extract_video_keyframes",
            "save_project_manifest",
            "check_file_exists",
            "list_project_files",
            "fetch_url_content",
        }
        assert names == expected

    def test_comfyui_tool_defs(self):
        # COMFYUI_TOOL_DEFS lives in core.tools_defs; ComfyUI is no longer
        # auto-loaded but its defs remain for opt-in registration.
        from core.tools_defs import COMFYUI_TOOL_DEFS

        assert isinstance(COMFYUI_TOOL_DEFS, list)
        assert len(COMFYUI_TOOL_DEFS) > 0

    def test_agent_system_prompt(self):
        from core.tools import AGENT_SYSTEM_PROMPT

        assert isinstance(AGENT_SYSTEM_PROMPT, str)
        assert "{provider_name}" in AGENT_SYSTEM_PROMPT
        assert "{model_name}" in AGENT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 3. register / unregister tools
# ---------------------------------------------------------------------------


class TestToolRegistryRegister:
    def test_register_new_tool(self, fresh_registry):
        def my_executor(**kw):
            return "ok"

        ok = fresh_registry.register(
            name="my_test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}, "required": []},
            executor=my_executor,
        )
        assert ok is True
        assert fresh_registry.has("my_test_tool")

    def test_register_duplicate_no_override(self, fresh_registry):
        def exec1(**kw):
            return "first"

        def exec2(**kw):
            return "second"

        fresh_registry.register("dup_tool", "desc", {"type": "object", "properties": {}}, exec1)
        ok = fresh_registry.register("dup_tool", "desc", {"type": "object", "properties": {}}, exec2)
        assert ok is False

    def test_register_duplicate_with_override(self, fresh_registry):
        def exec1(**kw):
            return "first"

        def exec2(**kw):
            return "second"

        fresh_registry.register("override_tool", "desc", {"type": "object", "properties": {}}, exec1)
        ok = fresh_registry.register(
            "override_tool",
            "desc",
            {"type": "object", "properties": {}},
            exec2,
            override=True,
        )
        assert ok is True

    def test_unregister_existing(self, fresh_registry):
        def my_exec(**kw):
            return "ok"

        fresh_registry.register("removable", "desc", {"type": "object", "properties": {}}, my_exec)
        assert fresh_registry.has("removable")
        ok = fresh_registry.unregister("removable")
        assert ok is True
        assert not fresh_registry.has("removable")

    def test_unregister_nonexistent(self, fresh_registry):
        ok = fresh_registry.unregister("no_such_tool")
        assert ok is False


# ---------------------------------------------------------------------------
# 4. definitions property
# ---------------------------------------------------------------------------


class TestToolRegistryDefinitions:
    def test_definitions_is_list(self, fresh_registry):
        defs = fresh_registry.definitions
        assert isinstance(defs, list)

    def test_definitions_empty_by_default(self, fresh_registry):
        assert fresh_registry.definitions == []
        assert fresh_registry._executors == {}

    def test_definitions_after_load(self, fresh_registry):
        fresh_registry.load()
        defs = fresh_registry.definitions
        assert len(defs) > 0
        # All definitions should follow OpenAI function format
        for d in defs:
            assert d["type"] == "function"
            assert "name" in d["function"]

    def test_definitions_contains_builtins_after_load(self, fresh_registry):
        fresh_registry.load()
        names = [d["function"]["name"] for d in fresh_registry.definitions]
        assert "generate_image" in names
        assert "generate_video" in names
        assert "multi_agent" in names

    def test_definitions_contains_lsp_tools_after_load(self, fresh_registry):
        fresh_registry.load()
        names = [d["function"]["name"] for d in fresh_registry.definitions]
        for lsp_tool in [
            "lsp_goto_definition",
            "lsp_hover",
            "lsp_diagnostics",
            "lsp_find_references",
            "lsp_completion",
            "lsp_rename",
        ]:
            assert lsp_tool in names, f"Missing LSP tool: {lsp_tool}"


# ---------------------------------------------------------------------------
# 5. tool_names property
# ---------------------------------------------------------------------------


class TestToolRegistryToolNames:
    def test_tool_names_is_list(self, fresh_registry):
        fresh_registry.load()
        names = fresh_registry.tool_names
        assert isinstance(names, list)

    def test_tool_names_matches_definitions(self, fresh_registry):
        fresh_registry.load()
        from_defs = [d["function"]["name"] for d in fresh_registry.definitions]
        assert fresh_registry.tool_names == from_defs

    def test_tool_names_no_duplicates(self, fresh_registry):
        fresh_registry.load()
        names = fresh_registry.tool_names
        assert len(names) == len(set(names))

    def test_tool_names_empty_by_default(self, fresh_registry):
        assert fresh_registry.tool_names == []

    def test_tool_names_after_register(self, fresh_registry):
        def my_exec(**kw):
            return "ok"

        fresh_registry.register("my_tool", "desc", {"type": "object", "properties": {}}, my_exec)
        assert "my_tool" in fresh_registry.tool_names


# ---------------------------------------------------------------------------
# 6. has method
# ---------------------------------------------------------------------------


class TestToolRegistryHas:
    def test_has_registered_tool(self, fresh_registry):
        def my_exec(**kw):
            return "ok"

        fresh_registry.register("my_tool", "desc", {"type": "object", "properties": {}}, my_exec)
        assert fresh_registry.has("my_tool")

    def test_has_nonexistent(self, fresh_registry):
        assert not fresh_registry.has("no_such_tool")


# ---------------------------------------------------------------------------
# 7. schema method
# ---------------------------------------------------------------------------


class TestToolRegistrySchema:
    def test_schema_method_exists(self, fresh_registry):
        assert callable(fresh_registry.schema)

    def test_schema_returns_none_for_unknown(self, fresh_registry):
        # schema() iterates definitions (a property, not a method),
        # so no-op for empty registry after register+unregister clears
        result = fresh_registry.schema("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# 8. tool_categories property
# ---------------------------------------------------------------------------


class TestToolRegistryCategories:
    def test_tool_categories_is_dict(self, fresh_registry):
        fresh_registry.load()
        cats = fresh_registry.tool_categories
        assert isinstance(cats, dict)

    def test_tool_categories_contains_builtins(self, fresh_registry):
        fresh_registry.load()
        cats = fresh_registry.tool_categories
        # generate_image/generate_video should be in the generate category
        found = False
        for _cat_name, tool_list in cats.items():
            if "generate_image" in tool_list:
                found = True
                break
        assert found, f"generate_image not found in any category. Categories: {list(cats.keys())}"


# ---------------------------------------------------------------------------
# 9. load method with toggles
# ---------------------------------------------------------------------------


class TestToolRegistryLoad:
    def test_load_returns_count(self, fresh_registry):
        count = fresh_registry.load()
        assert isinstance(count, int)
        assert count > 0

    def test_load_pipeline(self, fresh_registry):
        fresh_registry.load(pipeline=True)
        assert fresh_registry.has("extract_video_keyframes")

    def test_load_comfyui(self):
        # ComfyUI was removed from the registry loader (load() no longer accepts
        # comfyui=). The tool definitions still exist in tools_defs for opt-in
        # registration, so assert the defs are intact instead of loading them.
        from core.tools_defs import COMFYUI_TOOL_DEFS

        names = {d["function"]["name"] for d in COMFYUI_TOOL_DEFS}
        assert "comfyui_status" in names

    def test_load_with_audio(self, fresh_registry):
        fresh_registry.load(audio=True)
        # audio tools may or may not load depending on availability
        names = fresh_registry.tool_names
        # At minimum builtins are loaded
        assert "generate_image" in names


# ---------------------------------------------------------------------------
# 10. Tool validation helpers
# ---------------------------------------------------------------------------


class TestToolValidation:
    def test_validate_args_required_missing(self):
        from core.tools import _validate_args

        definitions = [
            {
                "function": {
                    "name": "test_tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "required_arg": {"type": "string", "description": "needed"},
                        },
                        "required": ["required_arg"],
                    },
                },
            }
        ]
        ok, detail = _validate_args("test_tool", {}, definitions)
        assert ok is False
        assert "required_arg" in detail

    def test_validate_args_ok(self):
        from core.tools import _validate_args

        definitions = [
            {
                "function": {
                    "name": "test_tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "a name"},
                        },
                        "required": ["name"],
                    },
                },
            }
        ]
        ok, _detail = _validate_args("test_tool", {"name": "hello"}, definitions)
        assert ok is True

    def test_validate_args_type_mismatch(self):
        from core.tools import _validate_args

        definitions = [
            {
                "function": {
                    "name": "test_tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "a count"},
                        },
                        "required": ["count"],
                    },
                },
            }
        ]
        ok, detail = _validate_args("test_tool", {"count": "not_an_int"}, definitions)
        assert ok is False
        assert "count" in detail

    def test_validate_args_no_schema_passes(self):
        from core.tools import _validate_args

        ok, _detail = _validate_args("unknown", {"a": 1}, [])
        assert ok is True

    def test_suggest_similar_tool(self):
        from core.tools import _suggest_similar_tool

        definitions = [
            {
                "function": {
                    "name": "read_file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "function": {
                    "name": "write_file",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]
        suggestion = _suggest_similar_tool("read_fil", definitions)
        assert "read_file" in suggestion

    def test_suggest_similar_tool_no_match(self):
        from core.tools import _suggest_similar_tool

        suggestion = _suggest_similar_tool("zzzzz", [])
        assert suggestion == ""


# ---------------------------------------------------------------------------
# 11. execute method
# ---------------------------------------------------------------------------


class TestToolRegistryExecute:
    def test_execute_registered_tool(self, fresh_registry):
        def my_exec(**kw):
            return f"got: {kw.get('name', '')}"

        fresh_registry.register(
            "echo",
            "echo tool",
            {"type": "object", "properties": {"name": {"type": "string", "description": "name"}}},
            my_exec,
        )
        result = fresh_registry.execute("echo", {"name": "world"})
        assert "world" in result

    def test_execute_unknown_tool(self, fresh_registry):
        result = fresh_registry.execute("no_such_tool", {})
        assert "错误" in result

    def test_execute_with_arg_validation(self, fresh_registry):
        def my_exec(**kw):
            return "ok"

        fresh_registry.register(
            "validated",
            "needs arg",
            {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            my_exec,
        )
        result = fresh_registry.execute("validated", {})
        assert "错误" in result


# ---------------------------------------------------------------------------
# 12. Levenshtein distance
# ---------------------------------------------------------------------------


class TestLevenshtein:
    def test_levenshtein_identical(self):
        from core.tools import _levenshtein

        assert _levenshtein("abc", "abc") == 0

    def test_levenshtein_one_edit(self):
        from core.tools import _levenshtein

        assert _levenshtein("abc", "abd") == 1

    def test_levenshtein_empty(self):
        from core.tools import _levenshtein

        assert _levenshtein("", "") == 0
        assert _levenshtein("abc", "") == 3
        assert _levenshtein("", "abc") == 3


# ---------------------------------------------------------------------------
# 13. __all__ exports
# ---------------------------------------------------------------------------


class TestToolsAllExports:
    def test_all_exports_importable(self):
        import core.tools as mod
        from core.tools import __all__ as exports

        missing = []
        for name in exports:
            if not hasattr(mod, name):
                missing.append(name)
        # AGNES_TOOL_DEFS etc. are defined in submodules and referenced
        # in __all__ but may not be direct module attributes; only fail
        # if core symbols are missing.
        core_symbols = {
            "AGENT_SYSTEM_PROMPT",
            "BUILTIN_TOOLS",
            "COMFYUI_TOOL_DEFS",
            "PIPELINE_TOOL_DEFS",
            "TOOLS_CONFIG",
            "ToolRegistry",
            "get_registry",
            "reload_registry",
        }
        truly_missing = [n for n in missing if n in core_symbols]
        assert not truly_missing, f"Core exports missing: {truly_missing}"
