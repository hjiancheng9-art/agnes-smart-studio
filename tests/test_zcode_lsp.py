"""
ZCode TDD: core/lsp.py tests.
Tests language detection, LSPClient construction, tool definitions, and executor imports.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 1. Language detection
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_detect_python(self):
        from core.lsp import Language, detect_language
        assert detect_language("test.py") == Language.PYTHON

    def test_detect_typescript(self):
        from core.lsp import Language, detect_language
        assert detect_language("test.ts") == Language.TYPESCRIPT

    def test_detect_javascript(self):
        from core.lsp import Language, detect_language
        assert detect_language("test.js") == Language.JAVASCRIPT

    def test_detect_go(self):
        from core.lsp import Language, detect_language
        assert detect_language("test.go") == Language.GO

    def test_detect_rust(self):
        from core.lsp import Language, detect_language
        assert detect_language("test.rs") == Language.RUST

    def test_detect_unknown_raises_valueerror(self):
        from core.lsp import detect_language
        with pytest.raises(ValueError, match="Cannot detect language"):
            detect_language("test.xyz")

    def test_detect_case_insensitive(self):
        from core.lsp import Language, detect_language
        assert detect_language("TEST.PY") == Language.PYTHON

    def test_detect_with_full_path(self):
        from core.lsp import Language, detect_language
        assert detect_language("/some/path/to/file.py") == Language.PYTHON


# ---------------------------------------------------------------------------
# 2. LSPClient construction
# ---------------------------------------------------------------------------

class TestLSPClientConstruction:
    def test_instantiate(self):
        from core.lsp import LSPClient
        client = LSPClient()
        assert client is not None
        assert hasattr(client, "_processes")
        assert hasattr(client, "_configs")

    def test_singleton_get_lsp_client(self):
        from core.lsp import LSPClient, get_lsp_client, reset_lsp_client
        reset_lsp_client()
        c1 = get_lsp_client()
        c2 = get_lsp_client()
        assert c1 is c2
        assert isinstance(c1, LSPClient)
        reset_lsp_client()

    def test_reset_lsp_client(self):
        from core.lsp import get_lsp_client, reset_lsp_client
        reset_lsp_client()
        c1 = get_lsp_client()
        reset_lsp_client()
        c2 = get_lsp_client()
        assert c1 is not c2
        reset_lsp_client()

    def test_default_configs_loaded(self):
        from core.lsp import LSPClient, Language
        client = LSPClient()
        for lang in Language:
            assert lang in client._configs, f"Missing config for {lang}"
            cfg = client._configs[lang]
            assert cfg.language == lang

    def test_language_enum_values(self):
        from core.lsp import Language
        assert Language.PYTHON.value == "python"
        assert Language.JAVASCRIPT.value == "javascript"
        assert Language.TYPESCRIPT.value == "typescript"
        assert Language.GO.value == "go"
        assert Language.RUST.value == "rust"


# ---------------------------------------------------------------------------
# 3. LSP_TOOL_DEFS structure and executor map
# ---------------------------------------------------------------------------

class TestLSPToolDefs:
    def test_tool_defs_is_list(self):
        from core.lsp import LSP_TOOL_DEFS
        assert isinstance(LSP_TOOL_DEFS, list)

    def test_tool_defs_count(self):
        from core.lsp import LSP_TOOL_DEFS
        assert len(LSP_TOOL_DEFS) == 6

    def test_tool_defs_have_required_structure(self):
        from core.lsp import LSP_TOOL_DEFS
        for td in LSP_TOOL_DEFS:
            assert td["type"] == "function"
            fn = td["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"
            assert "properties" in fn["parameters"]

    def test_tool_defs_names(self):
        from core.lsp import LSP_TOOL_DEFS
        names = {td["function"]["name"] for td in LSP_TOOL_DEFS}
        expected = {
            "lsp_goto_definition",
            "lsp_hover",
            "lsp_diagnostics",
            "lsp_find_references",
            "lsp_completion",
            "lsp_rename",
        }
        assert names == expected

    def test_executor_map_keys_match_tool_defs(self):
        from core.lsp import LSP_EXECUTOR_MAP, LSP_TOOL_DEFS
        tool_names = {td["function"]["name"] for td in LSP_TOOL_DEFS}
        executor_names = set(LSP_EXECUTOR_MAP.keys())
        assert tool_names == executor_names

    def test_executor_map_values_are_callable(self):
        from core.lsp import LSP_EXECUTOR_MAP
        for name, executor in LSP_EXECUTOR_MAP.items():
            assert callable(executor), f"Executor for {name} is not callable"


# ---------------------------------------------------------------------------
# 4. All 6 execute_lsp_* functions importable
# ---------------------------------------------------------------------------

class TestLSPExecutorsImportable:
    def test_execute_lsp_goto_definition(self):
        from core.lsp import execute_lsp_goto_definition
        assert callable(execute_lsp_goto_definition)

    def test_execute_lsp_hover(self):
        from core.lsp import execute_lsp_hover
        assert callable(execute_lsp_hover)

    def test_execute_lsp_diagnostics(self):
        from core.lsp import execute_lsp_diagnostics
        assert callable(execute_lsp_diagnostics)

    def test_execute_lsp_find_references(self):
        from core.lsp import execute_lsp_find_references
        assert callable(execute_lsp_find_references)

    def test_execute_lsp_completion(self):
        from core.lsp import execute_lsp_completion
        assert callable(execute_lsp_completion)

    def test_execute_lsp_rename(self):
        from core.lsp import execute_lsp_rename
        assert callable(execute_lsp_rename)

    def test_executors_return_json_without_server(self):
        """All executors return JSON error when no LSP server is running."""
        import json
        from core.lsp import (
            execute_lsp_diagnostics,
            execute_lsp_find_references,
            execute_lsp_goto_definition,
            execute_lsp_hover,
            execute_lsp_completion,
            execute_lsp_rename,
        )
        from core.lsp import reset_lsp_client
        reset_lsp_client()

        # goto_definition without file_path
        r = execute_lsp_goto_definition()
        d = json.loads(r)
        assert "error" in d

        # hover without file_path
        r = execute_lsp_hover()
        d = json.loads(r)
        assert "error" in d

        # diagnostics without file_path
        r = execute_lsp_diagnostics()
        d = json.loads(r)
        assert "error" in d

        # find_references without file_path
        r = execute_lsp_find_references()
        d = json.loads(r)
        assert "error" in d

        # completion without file_path
        r = execute_lsp_completion()
        d = json.loads(r)
        assert "error" in d

        # rename without file_path or new_name
        r = execute_lsp_rename()
        d = json.loads(r)
        assert "error" in d

        reset_lsp_client()
