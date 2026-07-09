"""RED phase tests for core/code_intel.py and core/rag.py.

Code Intelligence: AST analysis, symbol indexing, knowledge-graph, cross-language support.
RAG: TF-IDF tokenization, indexing, semantic search, caching.
"""

import json
import os
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# code_intel.py tests
# ---------------------------------------------------------------------------

CODING_RULES_SKIP = True  # ASCII-only, UTF-8


class TestCodeAnalyzerPython:
    """AST-based Python analysis via CodeAnalyzer."""

    def test_analyze_python_extracts_functions(self):
        """Functions found with name, line, args, docstring, is_async."""
        from core.code_intel import CodeAnalyzer

        src = '''
def hello(name):
    """Greet."""
    return f"Hello {name}"

async def fetch(url):
    return url
'''
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = CodeAnalyzer.analyze_python(path)
            assert "error" not in result
            funcs = {fn["name"]: fn for fn in result["functions"]}
            assert "hello" in funcs, result
            assert funcs["hello"]["line"] == 2  # 1-based
            assert funcs["hello"]["args"] == ["name"]
            assert "Greet" in funcs["hello"]["docstring"]
            assert not funcs["hello"]["is_async"]
            assert "fetch" in funcs
            assert funcs["fetch"]["is_async"]
            assert result["function_count"] >= 2
        finally:
            os.unlink(path)

    def test_analyze_python_extracts_classes_and_methods(self):
        from core.code_intel import CodeAnalyzer

        src = '''
class Dog:
    """A good dog."""
    def bark(self):
        pass

class Cat:
    def meow(self):
        pass
    def sleep(self):
        pass
'''
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = CodeAnalyzer.analyze_python(path)
            assert result["class_count"] == 2
            classes = {c["name"]: c for c in result["classes"]}
            assert "Dog" in classes
            assert classes["Dog"]["methods"] == ["bark"]
            assert "A good dog" in classes["Dog"]["docstring"]
            assert "Cat" in classes
            assert set(classes["Cat"]["methods"]) == {"meow", "sleep"}
        finally:
            os.unlink(path)

    def test_analyze_python_extracts_imports(self):
        from core.code_intel import CodeAnalyzer

        src = """
import os
import sys as system
from pathlib import Path
from collections import Counter, defaultdict
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = CodeAnalyzer.analyze_python(path)
            imports = {(imp["module"], imp.get("name", "")) for imp in result["imports"]}
            assert ("os", "os") in imports
            assert ("sys", "system") in imports
            assert any(m == "pathlib" for m, _ in imports)
            assert any(m == "collections" for m, _ in imports)
        finally:
            os.unlink(path)

    def test_analyze_python_syntax_error_graceful(self):
        from core.code_intel import CodeAnalyzer

        src = "def broken("
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = CodeAnalyzer.analyze_python(path)
            assert "error" in result
        finally:
            os.unlink(path)

    def test_find_symbol_definition_finds_function(self):
        from core.code_intel import CodeAnalyzer

        src = """
def target_func(x, y):
    return x + y
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            found = CodeAnalyzer.find_symbol_definition(path, "target_func")
            assert found is not None
            assert found["type"] == "function"
            assert found["args"] == ["x", "y"]
        finally:
            os.unlink(path)

    def test_find_symbol_definition_finds_class(self):
        from core.code_intel import CodeAnalyzer

        src = """
class TargetClass:
    def method_a(self): pass
    def method_b(self): pass
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            found = CodeAnalyzer.find_symbol_definition(path, "TargetClass")
            assert found is not None
            assert found["type"] == "class"
            assert "method_a" in found["methods"]
        finally:
            os.unlink(path)

    def test_find_symbol_definition_returns_none_for_missing(self):
        from core.code_intel import CodeAnalyzer

        src = "x = 1"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            assert CodeAnalyzer.find_symbol_definition(path, "nonexistent") is None
        finally:
            os.unlink(path)

    def test_find_references_finds_all_mentions(self):
        from core.code_intel import CodeAnalyzer

        src = """my_var = 1
result = my_var + 1
print(my_var)
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            refs = CodeAnalyzer.find_references(path, "my_var")
            assert len(refs) >= 3
            assert all(r["file"] == path for r in refs)
        finally:
            os.unlink(path)

    def test_find_references_word_boundary_respected(self):
        from core.code_intel import CodeAnalyzer

        src = "short_val = 1"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            refs = CodeAnalyzer.find_references(path, "val")
            assert len(refs) == 0
        finally:
            os.unlink(path)

    def test_extract_calls_records_callees(self):
        from core.code_intel import CodeAnalyzer

        src = """
def outer():
    inner()
    result = helper(x)
    obj.method()
    self.skip()
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = CodeAnalyzer.analyze_python(path)
            outer_fn = next(fn for fn in result["functions"] if fn["name"] == "outer")
            calls = outer_fn.get("calls", [])
            callee_names = [c[0] for c in calls]
            assert "inner" in callee_names
            assert "helper" in callee_names
            assert "method" in callee_names
            assert "self" not in callee_names
        finally:
            os.unlink(path)


class TestRegexBasedAnalysis:
    """Multi-language regex analysis."""

    def test_analyze_javascript(self):
        from core.code_intel import _LANG_PATTERNS, analyze_regex_based

        src = """
function greet(name) {
    return "Hello " + name;
}

const add = (a, b) => a + b;

class Animal {
    speak() {}
}
"""
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = analyze_regex_based(path, _LANG_PATTERNS[".js"])
            assert "error" not in result
            func_names = {fn["name"] for fn in result["functions"]}
            assert "greet" in func_names
            assert "add" in func_names
            class_names = {c["name"] for c in result["classes"]}
            assert "Animal" in class_names
        finally:
            os.unlink(path)

    def test_analyze_typescript(self):
        from core.code_intel import _LANG_PATTERNS, analyze_regex_based

        src = """
async function fetchData<T>(url: string): Promise<T> {
    return fetch(url);
}

interface User {
    name: string;
}
"""
        with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = analyze_regex_based(path, _LANG_PATTERNS[".ts"])
            assert "error" not in result
            assert any(fn["name"] == "fetchData" and fn["is_async"] for fn in result["functions"])
            class_entries = {c["name"]: c for c in result["classes"]}
            assert "User" in class_entries
            assert class_entries["User"]["type"] == "interface"
        finally:
            os.unlink(path)

    def test_analyze_go(self):
        from core.code_intel import _LANG_PATTERNS, analyze_regex_based

        src = """
package main

func Add(a, b int) int {
    return a + b
}

type Server struct {
    port int
}

type Reader interface {
    Read([]byte) (int, error)
}
"""
        with tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = analyze_regex_based(path, _LANG_PATTERNS[".go"])
            assert "error" not in result
            assert any(fn["name"] == "Add" for fn in result["functions"])
            class_entries = {c["name"]: c for c in result["classes"]}
            assert "Server" in class_entries
            assert class_entries["Server"]["type"] == "struct"
            assert "Reader" in class_entries
            assert class_entries["Reader"]["type"] == "interface"
        finally:
            os.unlink(path)

    def test_analyze_rust(self):
        from core.code_intel import _LANG_PATTERNS, analyze_regex_based

        src = """
pub fn calculate(x: i32, y: i32) -> i32 {
    x + y
}

pub struct Point {
    pub x: f64,
    pub y: f64,
}

pub enum Color {
    Red,
    Green,
}

pub trait Drawable {
    fn draw(&self);
}
"""
        with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = analyze_regex_based(path, _LANG_PATTERNS[".rs"])
            assert "error" not in result
            assert any(fn["name"] == "calculate" for fn in result["functions"])
            class_entries = {c["name"]: c for c in result["classes"]}
            assert class_entries["Point"]["type"] == "struct"
            assert class_entries["Color"]["type"] == "enum"
            assert class_entries["Drawable"]["type"] == "trait"
        finally:
            os.unlink(path)

    def test_file_not_found_returns_error(self):
        from core.code_intel import _LANG_PATTERNS, analyze_regex_based

        result = analyze_regex_based("/nonexistent/path.js", _LANG_PATTERNS[".js"])
        assert "error" in result

    def test_get_lang_patterns_resolves_aliases(self):
        from core.code_intel import _get_lang_patterns

        jsx_pats = _get_lang_patterns(".jsx")
        assert jsx_pats is not None
        assert "function" in jsx_pats

        tsx_pats = _get_lang_patterns(".tsx")
        assert tsx_pats is not None
        assert "interface" in tsx_pats

        assert _get_lang_patterns(".unknown") is None


class TestSymbolIndex:
    """Project-wide symbol indexing."""

    def test_index_file_python(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = """
def hello():
    pass

class Greeter:
    def greet(self):
        hello()
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            locations = idx.lookup("hello")
            assert len(locations) == 1
            assert locations[0]["type"] == "function"
            locations = idx.lookup("Greeter")
            assert len(locations) == 1
            assert locations[0]["type"] == "class"
            assert "greet" in locations[0]["methods"]
        finally:
            os.unlink(path)

    def test_index_file_unchanged_skipped(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "def foo(): pass\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            assert len(idx._files_indexed) == 1
            # Second index of same file should skip (mtime unchanged)
            idx.index_file(path)
            assert len(idx._files_indexed) == 1
        finally:
            os.unlink(path)

    def test_index_file_javascript(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "function greet() {}\nconst add = () => {};\n"
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            assert len(idx.lookup("greet")) == 1
            assert len(idx.lookup("add")) == 1
        finally:
            os.unlink(path)

    def test_index_directory_discovers_files(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("def alpha(): pass\n")
            (Path(tmp) / "b.py").write_text("def beta(): pass\n")
            idx.index_directory(tmp)
            assert "alpha" in idx._index or idx.lookup("alpha")
            assert "beta" in idx._index or idx.lookup("beta")

    def test_index_directory_excludes_dirs(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "__pycache__").mkdir()
            (Path(tmp) / "__pycache__" / "cached.py").write_text("def cached(): pass\n")
            (Path(tmp) / "real.py").write_text("def real(): pass\n")
            idx.index_directory(tmp)
            assert idx.lookup("real"), "Real file should be indexed"
            assert not idx.lookup("cached"), "Cached file should be excluded"

    def test_lookup_missing_returns_empty(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        assert idx.lookup("nonexistent") == []

    def test_search_by_pattern(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("def test_foo(): pass\ndef test_bar(): pass\ndef helper(): pass\n")
            idx.index_directory(tmp)
            results = idx.search(r"test_")
            assert len(results) >= 2
            assert all("test_" in r["symbol"] for r in results)

    def test_stats_reflects_indexed_data(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "def a(): pass\ndef b(): pass\nclass C:\n    def d(self): pass\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            s = idx.stats
            assert s["files_indexed"] == 1
            assert s["total_symbols"] >= 2  # a, b, C
            assert s["total_locations"] >= 2
        finally:
            os.unlink(path)


class TestKnowledgeGraph:
    """Graph queries: neighbors, ancestors, descendants."""

    def test_neighbors_outgoing(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = """
class MyClass:
    def my_method(self):
        pass
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            nbrs = idx.neighbors("symbol:MyClass", direction="out")
            assert any(e["type"] == "contains" and e["node"] == "symbol:my_method" for e in nbrs)
        finally:
            os.unlink(path)

    def test_neighbors_incoming(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "def target(): pass\ndef caller():\n    target()\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            nbrs = idx.neighbors("symbol:target", direction="in")
            assert any(e["type"] == "calls" and e["node"] == "symbol:caller" for e in nbrs)
        finally:
            os.unlink(path)

    def test_neighbors_both(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "def target(): pass\ndef caller():\n    target()\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            nbrs = idx.neighbors("symbol:target")
            directions = {e["direction"] for e in nbrs}
            assert "in" in directions or "out" in directions
        finally:
            os.unlink(path)

    def test_neighbors_empty_for_unknown_node(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        assert idx.neighbors("symbol:nonexistent") == []

    def test_descendants_follows_edges(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = """
class Outer:
    def inner(self):
        pass
"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            desc = idx.descendants("symbol:Outer")
            assert any("inner" in d["node"] for d in desc)
        finally:
            os.unlink(path)

    def test_ancestors_finds_callers(self):
        from core.code_intel import SymbolIndex

        idx = SymbolIndex()
        src = "def low(): pass\ndef high():\n    low()\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            idx.index_file(path)
            anc = idx.ancestors("symbol:low")
            assert any("high" in a["node"] for a in anc)
        finally:
            os.unlink(path)

    def test_normalize_node_id(self):
        from core.code_intel import SymbolIndex

        assert SymbolIndex._normalize_node_id("symbol:foo") == "symbol:foo"
        assert SymbolIndex._normalize_node_id("file:bar.py") == "file:bar.py"
        assert SymbolIndex._normalize_node_id("foo") == "symbol:foo"
        assert SymbolIndex._normalize_node_id("core.chat") == "module:core.chat"

    def test_norm_file_id_cross_platform(self):
        from core.code_intel import SymbolIndex

        fid = SymbolIndex._norm_file_id("src\\core\\agent.py")
        assert fid.startswith("file:")
        assert "src/core/agent.py" in fid
        assert "\\" not in fid


class TestToolExecutors:
    """Tool executors return valid JSON."""

    def test_execute_code_analyze_python(self):
        from core.code_intel import execute_code_analyze

        src = "def foo(): pass\n"
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            f.flush()
            path = f.name
        try:
            result = json.loads(execute_code_analyze(file_path=path))
            assert "error" not in result
            assert result["function_count"] == 1
        finally:
            os.unlink(path)

    def test_execute_code_analyze_unsupported_type(self):
        from core.code_intel import execute_code_analyze

        result = json.loads(execute_code_analyze(file_path="doc.txt"))
        assert "error" in result

    def test_execute_find_symbol_requires_name(self):
        from core.code_intel import execute_find_symbol

        result = json.loads(execute_find_symbol(symbol=""))
        assert "error" in result

    def test_execute_search_symbols_requires_pattern(self):
        from core.code_intel import execute_search_symbols

        result = json.loads(execute_search_symbols(pattern=""))
        assert "error" in result

    def test_execute_find_references_requires_both_args(self):
        from core.code_intel import execute_find_references

        r = json.loads(execute_find_references(file_path="", symbol="x"))
        assert "error" in r

    def test_execute_graph_neighbors_requires_node(self):
        from core.code_intel import execute_graph_neighbors

        r = json.loads(execute_graph_neighbors(node=""))
        assert "error" in r

    def test_tool_defs_have_required_structure(self):
        from core.code_intel import CODE_INTELLIGENCE_TOOL_DEFS

        for td in CODE_INTELLIGENCE_TOOL_DEFS:
            assert td["type"] == "function"
            fn = td["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert "properties" in fn["parameters"]

    def test_executor_map_covers_tool_names(self):
        from core.code_intel import CODE_INTELLIGENCE_EXECUTOR_MAP, CODE_INTELLIGENCE_TOOL_DEFS

        tool_names = {td["function"]["name"] for td in CODE_INTELLIGENCE_TOOL_DEFS}
        assert tool_names.issubset(set(CODE_INTELLIGENCE_EXECUTOR_MAP.keys()))


# ---------------------------------------------------------------------------
# rag.py tests
# ---------------------------------------------------------------------------


class TestRAGTokenization:
    """TF-IDF tokenization correctness."""

    def test_tokenize_english_words(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        tokens = engine._tokenize("hello world foo_bar")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo_bar" in tokens

    def test_tokenize_short_words_filtered(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        tokens = engine._tokenize("a b c")
        # Single-char words filtered
        assert all(len(t) >= 2 for t in tokens)

    def test_tokenize_chinese_bigrams(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        tokens = engine._tokenize("你好世界")
        assert "你好" in tokens
        assert "好世" in tokens
        assert "世界" in tokens

    def test_tokenize_single_chinese_char(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        tokens = engine._tokenize("啊")
        assert "啊" in tokens

    def test_tokenize_mixed_cjk_ascii(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        tokens = engine._tokenize("hello 你好 world")
        assert "hello" in tokens
        assert "world" in tokens
        assert "你好" in tokens


class TestRAGEngine:
    """Indexing and search."""

    def test_index_project_builds_index(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index_project(force=True)
        assert len(engine.index["documents"]) > 0
        assert len(engine.index["idf"]) > 0
        assert engine.index["built_at"] > 0

    def test_search_returns_ranked_results(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index_project(force=True)
        results = engine.search("Python code", top_k=5)
        assert isinstance(results, list)
        if results:
            assert "file" in results[0]
            assert "score" in results[0]
            # Results should be sorted by score descending
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_search_with_preview_includes_lines(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index_project(force=True)
        results = engine.search_with_preview("agent", top_k=3, preview_lines=2)
        assert isinstance(results, list)
        if results:
            assert "preview" in results[0]

    def test_search_empty_query_returns_empty(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index = {"documents": {"a.py": {"tf": {}, "token_count": 0}}, "idf": {}, "built_at": 9999999999}
        results = engine.search("", top_k=5)
        assert results == []

    def test_query_vector_uses_tfidf(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index = {
            "documents": {"d1.py": {"tf": {"foo": 2}, "token_count": 10}},
            "idf": {"foo": 2.0},
            "built_at": 9999999999,
        }
        results = engine.search("foo", top_k=5)
        assert len(results) > 0

    def test_cosine_similarity_identical(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        vec = {"a": 0.5, "b": 0.3}
        sim = engine._cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 0.0001

    def test_cosine_similarity_orthogonal(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        sim = engine._cosine_similarity({"a": 1.0}, {"b": 1.0})
        assert abs(sim - 0.0) < 0.0001

    def test_cosine_similarity_zero_vector(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        sim = engine._cosine_similarity({}, {"a": 1.0})
        assert sim == 0.0

    def test_semantic_search_convenience(self):
        from core.rag import semantic_search

        result = semantic_search("test", top_k=1)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_index_codebase_convenience(self):
        from core.rag import index_codebase

        # Should not raise
        index_codebase()

    def test_try_load_cache_returns_false_for_missing(self):
        from core.rag import INDEX_FILE, RAGEngine

        # Temporarily move cache
        bak = None
        if INDEX_FILE.exists():
            bak = INDEX_FILE.read_bytes()
            INDEX_FILE.unlink()
        try:
            engine = RAGEngine()
            assert not engine._try_load_cache()
        finally:
            if bak is not None:
                INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
                INDEX_FILE.write_bytes(bak)


class TestRAGEdgeCases:
    """Edge cases and invariants."""

    def test_search_without_index_triggers_build(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index = {"documents": {}, "idf": {}, "built_at": 0}
        # search should trigger index_project on empty
        results = engine.search("anything")
        assert isinstance(results, list)

    def test_idf_formula_non_negative(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        engine.index_project(force=True)
        for term, val in engine.index["idf"].items():
            assert val > 0, f"IDF for '{term}' is {val}"

    def test_no_exception_on_unreadable_file(self):
        from core.rag import RAGEngine

        engine = RAGEngine()
        # Empty index simulates no documents indexed
        engine.index = {"documents": {}, "idf": {}, "built_at": 9999999999}
        # search on empty index triggers index_project which rebuilds; accept any result
        results = engine.search("query")
        assert isinstance(results, list)
