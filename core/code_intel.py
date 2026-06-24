"""Code intelligence - AST parsing, symbol indexing, semantic search.

Provides tools for understanding code structure:
- AST analysis (functions, classes, imports)
- Symbol indexing (fast lookup by name)
- Code search (smarter than grep: understands scope, not just text)
- Dependency graph (what imports what)

Uses Python's built-in ast module for Python files.
Uses regex-based structured parsing for JavaScript, TypeScript, Go, and Rust files.
"""

import ast
import json
import os
import re
from pathlib import Path

__all__ = [
    "CODE_INTELLIGENCE_EXECUTOR_MAP",
    "CODE_INTELLIGENCE_TOOL_DEFS",
    "CodeAnalyzer",
    "SymbolIndex",
    "analyze_regex_based",
    "execute_code_analyze",
    "execute_find_references",
    "execute_find_symbol",
    "execute_search_symbols",
    "execute_graph_neighbors",
    "execute_graph_ancestors",
    "execute_graph_descendants",
    "get_index",
    "refresh_index",
]

# ======================================================================
# Multi-language regex-based analysis (JS/TS/Go/Rust)
# ======================================================================

# Language patterns: (function_pattern, class_pattern, import_pattern)
_LANG_PATTERNS = {
    ".js": {
        "function": re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
        "arrow": re.compile(
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.MULTILINE
        ),
        "class": re.compile(r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?", re.MULTILINE),
        "import": re.compile(r'import\s+.*?\s+from\s+["\']([^"\']+)["\']', re.MULTILINE),
    },
    ".jsx": None,  # reuse .js patterns
    ".ts": {
        "function": re.compile(
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)", re.MULTILINE
        ),
        "arrow": re.compile(
            r"(?:export\s+)?(?:const|let)\s+(\w+)\s*(?::\s*[^=]+)?=\s*(?:async\s*)?\(([^)]*)\)\s*=>", re.MULTILINE
        ),
        "class": re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?", re.MULTILINE),
        "import": re.compile(r'import\s+.*?\s+from\s+["\']([^"\']+)["\']', re.MULTILINE),
        "interface": re.compile(r"(?:export\s+)?interface\s+(\w+)", re.MULTILINE),
        "type": re.compile(r"(?:export\s+)?type\s+(\w+)\s*=", re.MULTILINE),
    },
    ".tsx": None,  # reuse .ts patterns
    ".go": {
        "function": re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)", re.MULTILINE),
        "struct": re.compile(r"^type\s+(\w+)\s+struct\s*\{", re.MULTILINE),
        "interface": re.compile(r"^type\s+(\w+)\s+interface\s*\{", re.MULTILINE),
        "import": re.compile(r'^\s*"([^"]+)"', re.MULTILINE),
    },
    ".rs": {
        "function": re.compile(r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)", re.MULTILINE),
        "struct": re.compile(r"(?:pub\s+)?struct\s+(\w+)", re.MULTILINE),
        "enum": re.compile(r"(?:pub\s+)?enum\s+(\w+)", re.MULTILINE),
        "trait": re.compile(r"(?:pub\s+)?trait\s+(\w+)", re.MULTILINE),
        "impl": re.compile(r"impl(?:<[^>]*>)?\s+(\w+)", re.MULTILINE),
        "use": re.compile(r"use\s+([^;]+);", re.MULTILINE),
    },
}


def _get_lang_patterns(suffix: str):
    """Get regex patterns for a file extension, resolving aliases."""
    if suffix not in _LANG_PATTERNS:
        return None
    patterns = _LANG_PATTERNS[suffix]
    if patterns is None:
        # Resolve alias: .jsx -> .js, .tsx -> .ts
        base = ".js" if suffix in (".jsx",) else ".ts"
        patterns = _LANG_PATTERNS[base]
    return patterns


def analyze_regex_based(file_path: str, patterns: dict) -> dict:
    """Analyze a source file using regex patterns.

    Generic parser for JS/TS/Go/Rust: extracts functions, classes/structs, imports.
    """
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        return {"error": str(e), "file": file_path}

    functions = []
    classes = []
    imports = []

    # Functions (named + arrow)
    func_pattern = patterns.get("function")
    if func_pattern:
        for m in func_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            functions.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                    "docstring": "",
                    "is_async": "async" in m.group(0),
                }
            )

    # Arrow functions (JS/TS only)
    arrow_pattern = patterns.get("arrow")
    if arrow_pattern:
        for m in arrow_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            functions.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "args": [a.strip() for a in m.group(2).split(",") if a.strip()],
                    "docstring": "",
                    "is_async": "async" in m.group(0),
                }
            )

    # Classes / structs / traits / interfaces
    class_pattern = patterns.get("class")
    if class_pattern:
        for m in class_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "class",
                }
            )

    struct_pattern = patterns.get("struct")
    if struct_pattern:
        for m in struct_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "struct",
                }
            )

    # Go interfaces
    iface_pattern = patterns.get("interface")
    if iface_pattern:
        for m in iface_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "interface",
                }
            )

    # Rust enums and traits
    enum_pattern = patterns.get("enum")
    if enum_pattern:
        for m in enum_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "enum",
                }
            )

    trait_pattern = patterns.get("trait")
    if trait_pattern:
        for m in trait_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "trait",
                }
            )

    # TS type aliases
    type_pattern = patterns.get("type")
    if type_pattern:
        for m in type_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            classes.append(
                {
                    "name": m.group(1),
                    "line": line,
                    "methods": [],
                    "docstring": "",
                    "type": "type_alias",
                }
            )

    # Imports / use statements
    import_pattern = patterns.get("import") or patterns.get("use")
    if import_pattern:
        for m in import_pattern.finditer(source):
            line = source[: m.start()].count("\n") + 1
            imports.append({"module": m.group(1), "line": line, "name": m.group(1)})

    return {
        "file": file_path,
        "language": Path(file_path).suffix.lstrip("."),
        "lines": len(source.split("\n")),
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "function_count": len(functions),
        "class_count": len(classes),
    }


# ======================================================================
# AST-based code analysis (Python)
# ======================================================================


class CodeAnalyzer:
    """Analyze Python source files using the ast module."""

    @staticmethod
    def analyze_python(file_path: str) -> dict:
        """Analyze a Python file and extract structure.

        Returns dict with: functions, classes, imports, complexity.
        """
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            return {"error": str(e), "file": file_path}
        except (OSError, UnicodeDecodeError) as e:
            return {"error": str(e), "file": file_path}

        functions = []
        classes = []
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                returns = ast.dump(node.returns) if node.returns else None
                functions.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "args": args,
                        "returns": returns,
                        "docstring": (ds[:200] if (ds := ast.get_docstring(node, clean=True)) else ""),
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        # 知识图谱用：本函数体里调用了哪些（callee 名, 调用行）
                        "calls": CodeAnalyzer._extract_calls(node),
                    }
                )

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
                classes.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                        "docstring": (ds[:200] if (ds := ast.get_docstring(node, clean=True)) else ""),
                    }
                )

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "line": node.lineno, "name": alias.asname or alias.name})

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({"module": module, "line": node.lineno, "name": alias.name, "from": True})

        return {
            "file": file_path,
            "lines": len(source.split("\n")),
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "function_count": len(functions),
            "class_count": len(classes),
        }

    @staticmethod
    def _extract_calls(func_node: ast.AST) -> list[tuple[str, int]]:
        """从函数节点体内抽取被调用的名字，供知识图谱 calls 边使用。

        规则（仅收简单形式，复杂表达式跳过以控噪）：
        - 直接调用 ``foo()``         → 'foo'
        - 方法调用 ``obj.bar()``     → 'bar'（只取方法名）
        - 动态调用 ``getattr(x)()``  跳过
        返回去重后的 [(callee_name, call_line), ...]。
        """
        seen: set[tuple[str, int]] = set()
        calls: list[tuple[str, int]] = []
        for sub in ast.walk(func_node):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            callee: str | None = None
            if isinstance(f, ast.Name):
                callee = f.id
            elif isinstance(f, ast.Attribute):
                callee = f.attr
            if callee and callee not in {"self", "cls"}:
                key = (callee, getattr(sub, "lineno", 0))
                if key not in seen:
                    seen.add(key)
                    calls.append(key)
        return calls

    @staticmethod
    def find_symbol_definition(file_path: str, symbol_name: str) -> dict | None:
        """Find where a symbol (function/class) is defined in a file.

        Returns dict with name, line, type (function/class), or None.
        """
        result = CodeAnalyzer.analyze_python(file_path)
        if "error" in result:
            return None

        for fn in result.get("functions", []):
            if fn["name"] == symbol_name:
                return {
                    "name": fn["name"],
                    "line": fn["line"],
                    "type": "function",
                    "file": file_path,
                    "args": fn.get("args", []),
                }

        for cls in result.get("classes", []):
            if cls["name"] == symbol_name:
                return {
                    "name": cls["name"],
                    "line": cls["line"],
                    "type": "class",
                    "file": file_path,
                    "methods": cls.get("methods", []),
                }

        return None

    @staticmethod
    def find_references(file_path: str, symbol_name: str) -> list[dict]:
        """Find all references to a symbol in a file (text-based, not AST-based).

        Returns list of {line, context} dicts.
        """
        try:
            lines = Path(file_path).read_text(encoding="utf-8", errors="replace").split("\n")
        except (OSError, UnicodeDecodeError):
            return []

        refs = []
        # Match symbol as a word boundary
        pattern = re.compile(r"\b" + re.escape(symbol_name) + r"\b")

        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                refs.append(
                    {
                        "file": file_path,
                        "line": i,
                        "context": line.strip()[:120],
                    }
                )

        return refs


# ======================================================================
# Symbol Index - project-wide code indexing
# ======================================================================


class SymbolIndex:
    """Index symbols across a project for fast lookup.

    Builds an index of function/class definitions that can be searched
    by name. Much faster than grepping every time.
    """

    def __init__(self) -> None:
        self._index: dict[str, list[dict]] = {}  # symbol_name -> [locations]
        self._files_indexed: set[str] = set()
        self._file_mtimes: dict[str, float] = {}
        # 知识图谱（借鉴 graphify）：双向邻接表
        # node_id 形如 "symbol:<name>" / "file:<rel_path>" / "module:<dotted>"
        self._edges: dict[str, list[dict]] = {}  # src_id -> [{type, target, line}]
        self._reverse_edges: dict[str, list[dict]] = {}  # target_id -> [{type, src, line}]

    def index_file(self, file_path: str):
        """Index a single source file (Python, JS, TS, Go, Rust)."""
        path = Path(file_path)
        if not path.exists():
            return

        suffix = path.suffix
        patterns = _get_lang_patterns(suffix)
        if suffix != ".py" and patterns is None:
            return  # unsupported file type

        mtime = path.stat().st_mtime
        if file_path in self._files_indexed and self._file_mtimes.get(file_path) == mtime:
            return  # unchanged

        file_id = SymbolIndex._norm_file_id(file_path)
        # Remove old symbol entries + old edges for this file
        for symbol_locs in self._index.values():
            symbol_locs[:] = [loc for loc in symbol_locs if loc.get("file") != file_path]
        self._purge_file_edges(file_id)

        if suffix == ".py":
            result = CodeAnalyzer.analyze_python(file_path)
        else:
            assert patterns is not None  # guaranteed: non-py files always pass patterns
            result = analyze_regex_based(file_path, patterns)

        if "error" in result:
            return

        for fn in result.get("functions", []):
            self._index.setdefault(fn["name"], []).append(
                {
                    "file": file_path,
                    "line": fn["line"],
                    "type": "function",
                    "args": fn.get("args", []),
                }
            )
            sym_id = f"symbol:{fn['name']}"
            # defines 边: file -> symbol
            self._add_edge(file_id, sym_id, "defines", fn["line"])
            # calls 边: function -> symbol（仅 Python；正则解析的语言无 AST，跳过）
            if suffix == ".py" and fn.get("calls"):
                for callee, call_line in fn["calls"]:
                    self._add_edge(sym_id, f"symbol:{callee}", "calls", call_line)

        for cls in result.get("classes", []):
            self._index.setdefault(cls["name"], []).append(
                {
                    "file": file_path,
                    "line": cls["line"],
                    "type": cls.get("type", "class"),
                    "methods": cls.get("methods", []),
                }
            )
            cls_id = f"symbol:{cls['name']}"
            # defines 边: file -> class
            self._add_edge(file_id, cls_id, "defines", cls["line"])
            # contains 边: class -> method
            for m in cls.get("methods", []):
                self._add_edge(cls_id, f"symbol:{m}", "contains", cls["line"])

        # imports 边: file -> module（之前被丢弃，现在捞回）
        for imp in result.get("imports", []):
            self._add_edge(file_id, f"module:{imp['module']}", "imports", imp.get("line", 0))

        self._files_indexed.add(file_path)
        self._file_mtimes[file_path] = mtime

    def index_directory(self, dir_path: str, exclude: list[str] | None = None):
        """Index all source files in a directory tree (Python, JS, TS, Go, Rust)."""
        excluded: set[str] = set(exclude or [])
        excluded.update({".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "build", "dist"})

        supported_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"}

        for root, dirs, files in os.walk(dir_path):
            # Filter excluded dirs
            dirs[:] = [d for d in dirs if d not in excluded]

            for f in files:
                if Path(f).suffix in supported_exts:
                    self.index_file(os.path.join(root, f))

    def lookup(self, symbol_name: str) -> list[dict]:
        """Look up a symbol by name. Returns list of locations."""
        return self._index.get(symbol_name, [])

    # ── 知识图谱：边管理 + 查询（借鉴 graphify nodes/edges 模型）──

    def _add_edge(self, src: str, target: str, edge_type: str, line: int = 0) -> None:
        """登记一条边到双向邻接表（去重 src+target+type）。"""
        entry = {"type": edge_type, "target": target, "line": line}
        existing = self._edges.get(src, [])
        if not any(e["type"] == edge_type and e["target"] == target for e in existing):
            existing.append(entry)
            self._edges[src] = existing
        rev = {"type": edge_type, "src": src, "line": line}
        rev_existing = self._reverse_edges.get(target, [])
        if not any(e["type"] == edge_type and e["src"] == src for e in rev_existing):
            rev_existing.append(rev)
            self._reverse_edges[target] = rev_existing

    def _purge_file_edges(self, file_id: str) -> None:
        """重索引文件时，清掉所有以该 file 为源或被其 defines 的旧边。"""
        # 清正向（file 作为 src 的 defines/imports）
        self._edges.pop(file_id, None)
        # 清反向：file defines 出的 symbol 边，以及 file imports 的 module 边
        for tgt in list(self._reverse_edges.keys()):
            rev = self._reverse_edges[tgt]
            rev[:] = [e for e in rev if e["src"] != file_id]
            if not rev:
                del self._reverse_edges[tgt]

    @staticmethod
    def _norm_file_id(file_path: str) -> str:
        """文件路径归一化为 file_id：正斜杠 + 去掉 ./ 前缀，确保跨平台一致。"""
        p = Path(file_path)
        norm = str(p.as_posix())  # Windows 反斜杠 → 正斜杠
        if norm.startswith("./"):
            norm = norm[2:]
        return f"file:{norm}"

    @staticmethod
    def _normalize_node_id(node: str) -> str:
        """用户传入的节点名归一化为带前缀的 node_id。

        - 已有前缀 → 直接返回
        - 含路径分隔符或以已知后缀结尾 → file:<normalized path>
        - 含点且像 dotted module（如 core.chat）→ module:<dotted>
        - 其它 → symbol:<name>
        """
        if node.startswith(("symbol:", "file:", "module:")):
            return node
        if "/" in node or "\\" in node or node.endswith((".py", ".js", ".ts", ".go", ".rs")):
            return SymbolIndex._norm_file_id(node)
        # 形如 a.b.c 当作 module；但含路径分隔符的已被上面 file 分支接走
        if "." in node and len(node.split(".")) >= 2:
            return f"module:{node}"
        return f"symbol:{node}"

    def neighbors(self, node_id: str, edge_type: str | None = None, direction: str = "both") -> list[dict]:
        """直接邻接节点。direction: out(我指向谁)/in(谁指向我)/both。"""
        out_list = []
        for e in self._edges.get(node_id, []):
            if edge_type and e["type"] != edge_type:
                continue
            out_list.append({"node": e["target"], "type": e["type"], "direction": "out", "line": e.get("line", 0)})
        in_list = []
        for e in self._reverse_edges.get(node_id, []):
            if edge_type and e["type"] != edge_type:
                continue
            in_list.append({"node": e["src"], "type": e["type"], "direction": "in", "line": e.get("line", 0)})
        if direction == "out":
            return out_list
        if direction == "in":
            return in_list
        return out_list + in_list

    def ancestors(self, node_id: str, max_depth: int = 10) -> list[dict]:
        """BFS 逆向上游依赖（谁依赖我，递归）。去环。支撑"删除前搜索引用"。"""
        return self._bfs(node_id, reverse=True, max_depth=max_depth)

    def descendants(self, node_id: str, max_depth: int = 10) -> list[dict]:
        """BFS 顺向下游影响面（我依赖/影响谁，递归）。去环。支撑"重命名前列影响面"。"""
        return self._bfs(node_id, reverse=False, max_depth=max_depth)

    def _bfs(self, start: str, reverse: bool, max_depth: int) -> list[dict]:
        """通用 BFS。reverse=True 走 _reverse_edges（上游），False 走 _edges（下游）。"""
        adj = self._reverse_edges if reverse else self._edges
        neighbor_key = "src" if reverse else "target"
        results: list[dict] = []
        visited: set[str] = {start}
        frontier: list[tuple[str, int]] = [(start, 0)]
        while frontier:
            cur, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for e in adj.get(cur, []):
                nxt = e[neighbor_key]
                if nxt in visited:
                    continue
                visited.add(nxt)
                results.append({"node": nxt, "depth": depth + 1, "edge_type": e["type"], "via_line": e.get("line", 0)})
                frontier.append((nxt, depth + 1))
        return results

    def search(self, pattern: str) -> list[dict]:
        """Search for symbols matching a pattern (substring match)."""
        results = []
        regex = re.compile(pattern, re.IGNORECASE)
        for name, locs in self._index.items():
            if regex.search(name):
                for loc in locs:
                    results.append({"symbol": name, **loc})
        return results

    def get_all_symbols(self) -> dict[str, list[dict]]:
        """Get the full index."""
        return dict(self._index)

    @property
    def stats(self) -> dict:
        return {
            "files_indexed": len(self._files_indexed),
            "total_symbols": len(self._index),
            "total_locations": sum(len(v) for v in self._index.values()),
            "total_edges": sum(len(v) for v in self._edges.values()),
            "total_nodes": len(self._edges) + len(set(self._reverse_edges.keys()) - set(self._edges.keys())),
        }


# ======================================================================
# Singleton index — reused across tool calls (lazy + mtime cached)
# ======================================================================

_index: SymbolIndex | None = None


def get_index(root: str = ".") -> SymbolIndex:
    """Get or create the singleton SymbolIndex. Reuses cached mtime data."""
    global _index
    if _index is None:
        _index = SymbolIndex()
    _index.index_directory(root)
    return _index


def refresh_index(root: str = ".") -> SymbolIndex:
    """Force rebuild the singleton index (e.g. after edits)."""
    global _index
    _index = SymbolIndex()
    _index.index_directory(root)
    return _index


# ======================================================================
# Tool executors for integration with ToolRegistry
# ======================================================================


def execute_code_analyze(file_path: str = "") -> str:
    """Tool executor: analyze a source file's structure (Python, JS, TS, Go, Rust)."""
    if not file_path:
        return json.dumps({"error": "file_path required"}, ensure_ascii=False)

    suffix = Path(file_path).suffix
    if suffix == ".py":
        result = CodeAnalyzer.analyze_python(file_path)
    else:
        patterns = _get_lang_patterns(suffix)
        if patterns is None:
            return json.dumps(
                {"error": f"unsupported file type: {suffix}. Supported: .py, .js, .jsx, .ts, .tsx, .go, .rs"},
                ensure_ascii=False,
            )
        result = analyze_regex_based(file_path, patterns)

    return json.dumps(result, ensure_ascii=False, indent=2)


def execute_find_symbol(symbol: str = "", directory: str = ".") -> str:
    """Tool executor: find a symbol definition across a project."""
    if not symbol:
        return json.dumps({"error": "symbol name required"}, ensure_ascii=False)

    idx = get_index(directory or ".")
    locations = idx.lookup(symbol)
    if not locations:
        return json.dumps({"symbol": symbol, "found": False}, ensure_ascii=False)

    return json.dumps(
        {
            "symbol": symbol,
            "found": True,
            "locations": locations,
            "index_stats": idx.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


def execute_search_symbols(pattern: str = "", directory: str = ".") -> str:
    """Tool executor: search for symbols matching a pattern."""
    if not pattern:
        return json.dumps({"error": "pattern required"}, ensure_ascii=False)

    idx = get_index(directory or ".")
    results = idx.search(pattern)
    return json.dumps(
        {
            "pattern": pattern,
            "matches": len(results),
            "results": results[:30],
            "index_stats": idx.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


def execute_find_references(file_path: str = "", symbol: str = "") -> str:
    """Tool executor: find all references to a symbol in a file."""
    if not file_path or not symbol:
        return json.dumps({"error": "file_path and symbol required"}, ensure_ascii=False)

    refs = CodeAnalyzer.find_references(file_path, symbol)
    return json.dumps(
        {
            "file": file_path,
            "symbol": symbol,
            "references": refs,
            "count": len(refs),
        },
        ensure_ascii=False,
        indent=2,
    )


# ======================================================================
# Knowledge-graph query executors (借鉴 graphify nodes/edges 模型)
# ======================================================================


def execute_graph_neighbors(node: str = "", direction: str = "both", edge_type: str = "", directory: str = ".") -> str:
    """Tool executor: 查某节点的直接邻接（谁 import/call/contain/define 它）。"""
    if not node:
        return json.dumps({"error": "node required"}, ensure_ascii=False)

    idx = get_index(directory or ".")
    node_id = SymbolIndex._normalize_node_id(node)
    et = edge_type or None
    results = idx.neighbors(node_id, edge_type=et, direction=direction or "both")
    return json.dumps(
        {
            "node": node,
            "node_id": node_id,
            "found": len(results) > 0,
            "direction": direction,
            "results": results,
            "count": len(results),
            "index_stats": idx.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


def execute_graph_ancestors(node: str = "", directory: str = ".") -> str:
    """Tool executor: BFS 逆向上游依赖（谁依赖我，递归）。支撑"删除前搜索引用"。"""
    if not node:
        return json.dumps({"error": "node required"}, ensure_ascii=False)

    idx = get_index(directory or ".")
    node_id = SymbolIndex._normalize_node_id(node)
    results = idx.ancestors(node_id)
    return json.dumps(
        {
            "node": node,
            "node_id": node_id,
            "found": len(results) > 0,
            "results": results,
            "count": len(results),
            "index_stats": idx.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


def execute_graph_descendants(node: str = "", directory: str = ".") -> str:
    """Tool executor: BFS 顺向下游影响面（我依赖/影响谁，递归）。支撑"重命名前列影响面"。"""
    if not node:
        return json.dumps({"error": "node required"}, ensure_ascii=False)

    idx = get_index(directory or ".")
    node_id = SymbolIndex._normalize_node_id(node)
    results = idx.descendants(node_id)
    return json.dumps(
        {
            "node": node,
            "node_id": node_id,
            "found": len(results) > 0,
            "results": results,
            "count": len(results),
            "index_stats": idx.stats,
        },
        ensure_ascii=False,
        indent=2,
    )


# Tool definitions for ToolRegistry
CODE_INTELLIGENCE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "code_analyze",
            "description": "Analyze a source file's structure: list all functions, classes, imports, with line numbers and signatures. Supports Python (.py), JavaScript (.js/.jsx), TypeScript (.ts/.tsx), Go (.go), and Rust (.rs). Use this to understand code before modifying it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Python file to analyze",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "description": "Find where a function or class is defined across the project. Returns file path and line number. Much faster than searching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Function or class name to find",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Project directory to search (default: current dir)",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_symbols",
            "description": "Search for functions/classes matching a pattern (regex). Returns matching symbols with file locations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to match symbol names",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Project directory to search (default: current dir)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Find all references to a symbol (function/class/variable) in a file. Returns line numbers and context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File to search in",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol name to find references for",
                    },
                },
                "required": ["file_path", "symbol"],
            },
        },
    },
]

CODE_INTELLIGENCE_EXECUTOR_MAP = {
    "code_analyze": lambda **kw: execute_code_analyze(file_path=kw.get("file_path", "")),
    "find_symbol": lambda **kw: execute_find_symbol(symbol=kw.get("symbol", ""), directory=kw.get("directory", ".")),
    "search_symbols": lambda **kw: execute_search_symbols(
        pattern=kw.get("pattern", ""), directory=kw.get("directory", ".")
    ),
    "find_references": lambda **kw: execute_find_references(
        file_path=kw.get("file_path", ""), symbol=kw.get("symbol", "")
    ),
}
