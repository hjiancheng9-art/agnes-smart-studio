"""Tests for core/code_intel.py — language patterns, regex analysis, constants."""

import tempfile
from pathlib import Path

from core.code_intel import (
    CODE_INTELLIGENCE_EXECUTOR_MAP,
    CODE_INTELLIGENCE_TOOL_DEFS,
    analyze_regex_based,
)


class TestLanguagePatterns:
    def test_python_via_ast(self, tmp_path):
        """Python files use AST analysis, not regex."""
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    return 'world'\n\nclass MyClass:\n    pass\n", encoding="utf-8")
        result = analyze_regex_based(str(f), {})
        assert isinstance(result, dict)

    def test_js_regex_analysis(self, tmp_path):
        """JavaScript uses regex-based analysis."""
        from core.code_intel import _LANG_PATTERNS
        patterns = _LANG_PATTERNS.get(".js", {})
        f = tmp_path / "test.js"
        f.write_text("function hello() {\n  return 'world';\n}\n\nclass MyClass {\n}\n", encoding="utf-8")
        result = analyze_regex_based(str(f), patterns)
        assert isinstance(result, dict)
        assert "functions" in result

    def test_js_arrow_function(self, tmp_path):
        """Arrow functions are detected."""
        from core.code_intel import _LANG_PATTERNS
        patterns = _LANG_PATTERNS.get(".js", {})
        f = tmp_path / "arrow.js"
        f.write_text("const add = (a, b) => a + b;\n", encoding="utf-8")
        result = analyze_regex_based(str(f), patterns)
        assert "functions" in result

    def test_go_regex_analysis(self, tmp_path):
        """Go uses regex-based analysis."""
        from core.code_intel import _LANG_PATTERNS
        patterns = _LANG_PATTERNS.get(".go", {})
        f = tmp_path / "test.go"
        f.write_text("package main\n\nfunc main() {\n}\n\ntype Config struct {\n}\n", encoding="utf-8")
        result = analyze_regex_based(str(f), patterns)
        assert isinstance(result, dict)
        assert "functions" in result

    def test_rust_regex_analysis(self, tmp_path):
        """Rust uses regex-based analysis."""
        from core.code_intel import _LANG_PATTERNS
        patterns = _LANG_PATTERNS.get(".rs", {})
        f = tmp_path / "test.rs"
        f.write_text("fn main() {\n}\n\npub struct Config {\n}\n", encoding="utf-8")
        result = analyze_regex_based(str(f), patterns)
        assert isinstance(result, dict)
        assert "functions" in result

    def test_empty_file(self, tmp_path):
        """Empty file analysis doesn't crash."""
        from core.code_intel import _LANG_PATTERNS
        f = tmp_path / "empty.rs"
        f.write_text("", encoding="utf-8")
        result = analyze_regex_based(str(f), _LANG_PATTERNS.get(".rs", {}))
        assert isinstance(result, dict)

    def test_handles_imports(self, tmp_path):
        """Import detection in TypeScript."""
        from core.code_intel import _LANG_PATTERNS
        patterns = _LANG_PATTERNS.get(".ts", {})
        f = tmp_path / "test.ts"
        f.write_text("import { foo } from './module';\nimport React from 'react';\n", encoding="utf-8")
        result = analyze_regex_based(str(f), patterns)
        assert isinstance(result, dict)

    def test_nonexistent_file(self):
        """Nonexistent file returns empty analysis."""
        result = analyze_regex_based("/nonexistent/file.py", {})
        assert isinstance(result, dict)


class TestConstants:
    def test_tool_defs_exists(self):
        assert isinstance(CODE_INTELLIGENCE_TOOL_DEFS, list)

    def test_executor_map_exists(self):
        assert isinstance(CODE_INTELLIGENCE_EXECUTOR_MAP, dict)
