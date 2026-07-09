"""Tests for core/code_intel.py — 代码智能"""

from core.code_intel import CodeAnalyzer, SymbolIndex, analyze_regex_based


class TestCodeAnalyzer:
    def test_analyze_python(self):
        ca = CodeAnalyzer()
        result = ca.analyze_python("core/code_intel.py")
        assert isinstance(result, dict)
        assert "file" in result or "functions" in result

    def test_analyze_nonexistent(self):
        ca = CodeAnalyzer()
        result = ca.analyze_python("/nonexistent/file.py")
        # 不应崩溃
        assert result is not None or isinstance(result, dict)

    def test_analyze_regex_based(self):
        result = analyze_regex_based("core/code_intel.py", {"classes": r"class \w+"})
        assert isinstance(result, dict)


class TestSymbolIndex:
    def test_create(self):
        si = SymbolIndex()
        assert si is not None

    def test_index_file(self):
        si = SymbolIndex()
        si.index_file("core/code_intel.py")
        assert True

    def test_lookup(self):
        si = SymbolIndex()
        si.index_file("core/code_intel.py")
        results = si.lookup("CodeAnalyzer")
        assert isinstance(results, list)

    def test_search(self):
        si = SymbolIndex()
        si.index_file("core/code_intel.py")
        results = si.search("Analyzer")
        assert isinstance(results, list)

    def test_search_empty(self):
        si = SymbolIndex()
        results = si.search("__nonexistent_symbol_xyz__")
        assert isinstance(results, list)
