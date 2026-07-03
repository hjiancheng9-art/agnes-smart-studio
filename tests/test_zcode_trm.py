"""RED phase tests for core/tool_registry_mesh.py.

TRM: Tool Registry Mesh — categories, discovery, routing, caching, singletons.
"""

import json
import time
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestTRMConstants:
    """CATEGORY_META and BRIDGES definitions."""

    def test_category_meta_has_all_intents(self):
        from core.tool_registry_mesh import CATEGORY_META

        expected = {"search", "review", "execute", "think", "generate", "status"}
        assert set(CATEGORY_META.keys()) == expected

    def test_bridges_defined(self):
        from core.tool_registry_mesh import BRIDGES

        assert "codex" in BRIDGES
        assert "kimi" in BRIDGES
        assert "qoder" in BRIDGES
        assert "codebuddy" in BRIDGES
        assert "zcode" in BRIDGES
        assert "claude-code" in BRIDGES

    def test_bridges_have_script(self):
        from core.tool_registry_mesh import BRIDGES

        for name, cfg in BRIDGES.items():
            assert "script" in cfg, f"Bridge '{name}' missing 'script'"

    def test_crux_builtin_tools_have_required_fields(self):
        from core.tool_registry_mesh import CRUX_BUILTIN_TOOLS

        for t in CRUX_BUILTIN_TOOLS:
            assert "name" in t
            assert "category" in t
            assert "source" in t


# ---------------------------------------------------------------------------
# ToolEntry data model
# ---------------------------------------------------------------------------


class TestToolEntry:
    """ToolEntry dataclass."""

    def test_display_format(self):
        from core.tool_registry_mesh import ToolEntry

        entry = ToolEntry(name="test_tool", description="A test", source="crux", category="search")
        d = entry.display
        assert "test_tool" in d
        assert "search" in d
        assert "crux" in d

    def test_matches_by_name(self):
        from core.tool_registry_mesh import ToolEntry

        entry = ToolEntry(name="find_symbol", description="Search for symbols", source="crux", category="search")
        assert entry.matches("find")
        assert entry.matches("symbol")
        assert not entry.matches("generate")

    def test_matches_by_description(self):
        from core.tool_registry_mesh import ToolEntry

        entry = ToolEntry(name="tool_x", description="Generate images", source="crux", category="generate")
        assert entry.matches("images")
        assert entry.matches("generate")

    def test_matches_case_insensitive(self):
        from core.tool_registry_mesh import ToolEntry

        entry = ToolEntry(name="MyTool", description="", source="crux", category="unknown")
        assert entry.matches("mytool")
        assert entry.matches("MYTOOL")


# ---------------------------------------------------------------------------
# RouteResult data model
# ---------------------------------------------------------------------------


class TestRouteResult:
    """RouteResult dataclass."""

    def test_defaults(self):
        from core.tool_registry_mesh import RouteResult

        rr = RouteResult(tool="", source="", result=None, error="", fallback_used=False, latency_ms=0)
        assert rr.tool == ""
        assert rr.error == ""
        assert not rr.fallback_used


# ---------------------------------------------------------------------------
# ToolRegistryMesh initialization and registration
# ---------------------------------------------------------------------------


class TestToolRegistryMeshInit:
    """TRM lifecycle."""

    def test_init_empty_state(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm.tool_count == 0
        assert trm._discovered is False

    def test_register_crux_builtins_on_discover(self):
        from core.tool_registry_mesh import ToolRegistryMesh, CRUX_BUILTIN_TOOLS

        trm = ToolRegistryMesh()
        # Don't actually spawn bridges in test
        with mock.patch.object(trm, "_discover_bridge", return_value=[]):
            count = trm.discover_all(timeout=0.1)
            assert count >= len(CRUX_BUILTIN_TOOLS)

    def test_discover_all_sets_flag(self):
        from core.tool_registry_mesh import ToolRegistryMesh
        from core.tool_registry_mesh import CRUX_BUILTIN_TOOLS as BUILTINS

        trm = ToolRegistryMesh()
        with mock.patch.object(trm, "_discover_bridge", return_value=[]):
            trm.discover_all(timeout=0.1)
            assert trm._discovered is True
            assert trm.tool_count >= len(BUILTINS)

    def test_register_prevents_duplicates(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        entry1 = ToolEntry(name="dup_tool", description="first", source="crux", category="search")
        entry2 = ToolEntry(name="dup_tool", description="second", source="codex", category="execute")
        trm._register(entry1)
        trm._register(entry2)
        assert trm._tools["dup_tool"].description == "first"

    def test_find_all(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="t1", description="", source="crux", category="search"))
        trm._register(ToolEntry(name="t2", description="", source="codex", category="execute"))
        trm._rebuild_indexes()
        assert len(trm.find()) == 2

    def test_find_by_category(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="search_tool", description="", source="crux", category="search"))
        trm._register(ToolEntry(name="exec_tool", description="", source="codex", category="execute"))
        trm._rebuild_indexes()
        results = trm.find(category="search")
        assert len(results) == 1
        assert results[0].name == "search_tool"

    def test_find_by_source(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="t1", description="", source="crux", category="search"))
        trm._register(ToolEntry(name="t2", description="", source="codex", category="search"))
        trm._rebuild_indexes()
        results = trm.find(source="codex")
        assert len(results) == 1
        assert results[0].name == "t2"

    def test_get_existing(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="known", description="", source="crux", category="search"))
        assert trm.get("known") is not None
        assert trm.get("unknown") is None

    def test_categories_property(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="t1", description="", source="crux", category="search"))
        trm._register(ToolEntry(name="t2", description="", source="crux", category="execute"))
        trm._register(ToolEntry(name="t3", description="", source="crux", category="search"))
        trm._rebuild_indexes()
        cats = trm.categories
        assert cats["search"] == 2
        assert cats["execute"] == 1

    def test_sources_property(self):
        from core.tool_registry_mesh import ToolRegistryMesh, ToolEntry

        trm = ToolRegistryMesh()
        trm._register(ToolEntry(name="t1", description="", source="crux", category="search"))
        trm._register(ToolEntry(name="t2", description="", source="codex", category="search"))
        trm._rebuild_indexes()
        srcs = trm.sources
        assert srcs["crux"] >= 1
        assert srcs["codex"] >= 1


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestClassification:
    """Tool classification from name + description."""

    def test_classify_search_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("find_symbol", "") == "search"
        assert trm._classify("glob_files", "") == "search"
        assert trm._classify("grep_code", "") == "search"
        assert trm._classify("read_file", "") == "search"

    def test_classify_review_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("code_review", "") == "review"
        assert trm._classify("audit_security", "") == "review"

    def test_classify_execute_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("exec_code", "") == "execute"
        assert trm._classify("write_file", "") == "execute"
        assert trm._classify("edit_config", "") == "execute"
        assert trm._classify("build_project", "") == "execute"

    def test_classify_think_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("plan_tasks", "") == "think"
        assert trm._classify("architect_design", "") == "think"
        assert trm._classify("deliberate_options", "") == "think"
        assert trm._classify("deep_analyze", "") == "think"

    def test_classify_generate_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("generate_image", "") == "generate"
        assert trm._classify("create_video", "") == "generate"
        assert trm._classify("render_scene", "") == "generate"

    def test_classify_status_keywords(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("check_health", "") == "status"
        assert trm._classify("login_status", "") == "status"

    def test_classify_unknown_default(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm._classify("weird_tool_name", "") == "unknown"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouting:
    """Route intent to tools."""

    def test_route_unknown_intent_returns_error(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        # No discovery needed
        result = trm.route("nonexistent_intent")
        assert result.error != ""
        assert "Unknown intent" in result.error

    def test_route_with_registered_callback(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm.discover_all = mock.MagicMock()  # skip discovery
        trm._tools["my_tool"] = type("Entry", (), {
            "name": "my_tool", "source": "test", "category": "search"
        })()

        called = []
        def my_callback(**kw):
            called.append(kw)
            return {"success": True}
        trm.register_callback("my_tool", my_callback)

        from core.tool_registry_mesh import CATEGORY_META
        CATEGORY_META["search"]["order"] = ["my_tool"]

        result = trm.route("search", query="test query")
        assert result.result is not None
        # May fail if growth engine is unavailable; callback should be called
        # in happy path

    def test_route_all_failed_returns_error(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm.discover_all = mock.MagicMock()

        from core.tool_registry_mesh import CATEGORY_META
        CATEGORY_META["search"]["order"] = ["nonexistent_tool"]

        result = trm.route("search")
        assert result.error != ""

    def test_get_optimized_candidates_static_fallback(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        candidates = ToolRegistryMesh._get_optimized_candidates("generate", ["gen_img", "gen_vid"])
        assert candidates == ["gen_img", "gen_vid"]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestTRMCache:
    """In-memory cache operations."""

    def test_cache_set_and_get(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm.cache_set("key1", {"data": 42})
        val = trm.cache_get("key1")
        assert val == {"data": 42}

    def test_cache_get_missing(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        assert trm.cache_get("nonexistent") is None

    def test_cache_expiry(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm._cache_ttl = -1  # immediate expiry
        trm.cache_set("key1", "val")
        assert trm.cache_get("key1") is None

    def test_cache_clear(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm.cache_set("a", 1)
        trm.cache_set("b", 2)
        n = trm.cache_clear()
        assert n == 2
        assert trm.cache_get("a") is None


# ---------------------------------------------------------------------------
# Display and as_text
# ---------------------------------------------------------------------------


class TestTRMDisplay:
    """Catalog display methods."""

    def test_as_text_without_discovery(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm._discovered = True  # skip discovery
        text = trm.as_text()
        assert "TRM:" in text
        assert "Categories" in text or "tools" in text

    def test_print_catalog_noop(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        trm._discovered = True
        # Should not raise
        trm.print_catalog()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestTRMSingleton:
    """get_trm singleton pattern."""

    def test_get_trm_returns_same_instance(self):
        from core.tool_registry_mesh import get_trm

        trm1 = get_trm()
        trm2 = get_trm()
        assert trm1 is trm2

    def test_get_trm_returns_ToolRegistryMesh(self):
        from core.tool_registry_mesh import get_trm, ToolRegistryMesh

        trm = get_trm()
        assert isinstance(trm, ToolRegistryMesh)


# ---------------------------------------------------------------------------
# _read_line
# ---------------------------------------------------------------------------


class TestReadLine:
    """Subprocess line reading."""

    def test_read_line_timeout(self):
        from core.tool_registry_mesh import ToolRegistryMesh
        import subprocess
        import sys
        import time

        # Launch a Python that sleeps then prints
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10); print('too late')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            result = ToolRegistryMesh._read_line(proc, timeout=0.5)
            assert result is None
        finally:
            proc.kill()


# ---------------------------------------------------------------------------
# _raw_to_entry
# ---------------------------------------------------------------------------


class TestRawToEntry:
    """Converting raw tool JSON to ToolEntry."""

    def test_raw_to_entry_sets_fields(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        raw = {
            "name": "test_tool",
            "description": "A test tool for searching",
            "inputSchema": {"type": "object", "properties": {}},
        }
        entry = trm._raw_to_entry(raw, "test_source")
        assert entry.name == "test_tool"
        assert entry.source == "test_source"
        assert entry.category == "search"  # from description

    def test_raw_to_entry_with_missing_fields(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        entry = trm._raw_to_entry({}, "minimal")
        assert entry.name == "unknown"
        assert entry.source == "minimal"


# ---------------------------------------------------------------------------
# register_callback
# ---------------------------------------------------------------------------


class TestRegisterCallback:
    """Callback registration for tool execution."""

    def test_register_and_call(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()
        results = []

        def handler(**kw):
            results.append(kw)
            return {"ok": True}

        trm.register_callback("cb_tool", handler)
        assert "cb_tool" in trm._callbacks

        out = trm._call_tool("cb_tool", {"x": 1})
        assert len(results) == 1
        assert results[0] == {"x": 1}
        assert out == {"ok": True}

    def test_callback_exception_returns_none(self):
        from core.tool_registry_mesh import ToolRegistryMesh

        trm = ToolRegistryMesh()

        def broken(**kw):
            raise RuntimeError("boom")

        trm.register_callback("broken_tool", broken)
        result = trm._call_tool("broken_tool", {})
        assert result is None
