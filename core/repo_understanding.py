# core/repo_understanding.py
"""P9: Project Intelligence Layer / Repo Understanding OS.

Gives CRUX a structured understanding of the codebase — like an experienced
developer who knows the project layout, module relationships, call graphs,
and can do intent-aware search across the entire repo.

Modules:
  RepoIndex       — scans project, builds a searchable index of files + symbols
  RepoGraph       — extracts import/dependency/call relationships between files
  ProjectContext  — assembles a structured snapshot of the project for LLM consumption
  IntentSearch    — semantic code search by intent, not just keyword
  ChangeAnalyzer  — change impact analysis before file operations
"""

from __future__ import annotations

import ast
import logging
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────

DEFAULT_EXCLUDES = {
    "__pycache__", ".git", ".crux", ".claude", ".codebuddy",
    "node_modules", ".venv", "venv", "env", ".env",
    ".pytest_cache", ".mypy_cache",
    "*.pyc", "*.pyo", "*.egg-info", "dist", "build",
}


# ═══════════════════════════════════════════════════════════════════
# 1. RepoIndex — file + symbol index
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FileEntry:
    """A single file in the project index."""
    path: str
    relative_path: str
    size: int
    lines: int
    extension: str
    last_modified: float
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    is_test: bool = False


@dataclass
class SymbolEntry:
    """A symbol defined somewhere in the repo."""
    name: str
    kind: str  # "class", "function", "variable"
    file_path: str
    line: int
    docstring: str = ""
    signature: str = ""


@dataclass
class RepoIndexSnapshot:
    """A point-in-time snapshot of the repo index."""
    files: dict[str, FileEntry] = field(default_factory=dict)
    symbols: dict[str, list[SymbolEntry]] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0
    build_time_ms: float = 0.0
    timestamp: float = 0.0
    root: str = ""

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "build_time_ms": round(self.build_time_ms, 1),
            "timestamp": self.timestamp,
            "root": self.root,
            "files": {
                p: {
                    "path": f.relative_path,
                    "lines": f.lines,
                    "classes": f.classes[:5],
                    "functions": f.functions[:5],
                    "imports": f.imports[:10],
                    "is_test": f.is_test,
                }
                for p, f in self.files.items()
            },
            "symbol_count": len(self.symbols),
        }


class RepoIndex:
    """Scans project directory, builds a searchable file + symbol index.

    Usage:
        index = RepoIndex()
        snapshot = index.build()  # full scan
        snapshot = index.incremental()  # only changed files
        symbol = index.find_symbol("UserModel")
        files = index.find_files_matching("auth")
    """

    def __init__(self, root: str | None = None, excludes: set[str] | None = None):
        self.root = root or os.getcwd()
        self.excludes = excludes or DEFAULT_EXCLUDES
        self._last_snapshot: RepoIndexSnapshot | None = None
        self._last_mtime: dict[str, float] = {}

    def build(self) -> RepoIndexSnapshot:
        """Full scan: index all files in the project."""
        start = time.time()
        snapshot = RepoIndexSnapshot(root=self.root, timestamp=time.time())
        root_path = Path(self.root)

        if not root_path.exists():
            logger.warning(f"Root path does not exist: {self.root}")
            return snapshot

        for filepath in root_path.rglob("*"):
            if not filepath.is_file():
                continue
            rel = filepath.relative_to(root_path)
            if self._is_excluded(rel):
                continue

            entry = self._index_file(filepath, rel)
            if entry:
                snapshot.files[entry.path] = entry
                snapshot.total_files += 1
                snapshot.total_lines += entry.lines
                self._last_mtime[entry.path] = entry.last_modified

                # Index symbols
                for cls in entry.classes:
                    key = cls.lower()
                    if key not in snapshot.symbols:
                        snapshot.symbols[key] = []
                    snapshot.symbols[key].append(SymbolEntry(
                        name=cls, kind="class",
                        file_path=entry.path, line=0,
                    ))
                for fn in entry.functions:
                    key = fn.lower()
                    if key not in snapshot.symbols:
                        snapshot.symbols[key] = []
                    snapshot.symbols[key].append(SymbolEntry(
                        name=fn, kind="function",
                        file_path=entry.path, line=0,
                    ))

        snapshot.build_time_ms = (time.time() - start) * 1000
        self._last_snapshot = snapshot
        logger.info(f"Indexed {snapshot.total_files} files ({snapshot.total_lines} lines) in {snapshot.build_time_ms:.0f}ms")
        return snapshot

    def incremental(self) -> RepoIndexSnapshot | None:
        """Only re-index changed files. Returns None if no changes."""
        if self._last_snapshot is None:
            return self.build()

        changed_files = []
        root_path = Path(self.root)
        for filepath in root_path.rglob("*"):
            if not filepath.is_file():
                continue
            rel = filepath.relative_to(root_path)
            if self._is_excluded(rel):
                continue
            mtime = filepath.stat().st_mtime
            if self._last_mtime.get(str(rel), 0) != mtime:
                changed_files.append((filepath, rel))

        if not changed_files:
            return None

        # Copy last snapshot and update changed files
        snapshot = RepoIndexSnapshot(
            files=dict(self._last_snapshot.files),
            symbols=dict(self._last_snapshot.symbols),
            total_files=self._last_snapshot.total_files,
            total_lines=self._last_snapshot.total_lines,
            timestamp=time.time(),
            root=self.root,
        )

        for filepath, rel in changed_files:
            old_entry = snapshot.files.get(str(rel))
            if old_entry:
                snapshot.total_lines -= old_entry.lines

            entry = self._index_file(filepath, rel)
            if entry:
                snapshot.files[entry.path] = entry
                snapshot.total_lines += entry.lines
                self._last_mtime[entry.path] = entry.last_modified

                # Update symbols for this file
                for key in list(snapshot.symbols.keys()):
                    snapshot.symbols[key] = [
                        s for s in snapshot.symbols[key]
                        if s.file_path != entry.path
                    ]
                    if not snapshot.symbols[key]:
                        del snapshot.symbols[key]

                for cls in entry.classes:
                    key = cls.lower()
                    if key not in snapshot.symbols:
                        snapshot.symbols[key] = []
                    snapshot.symbols[key].append(SymbolEntry(
                        name=cls, kind="class",
                        file_path=entry.path, line=0,
                    ))
                for fn in entry.functions:
                    key = fn.lower()
                    if key not in snapshot.symbols:
                        snapshot.symbols[key] = []
                    snapshot.symbols[key].append(SymbolEntry(
                        name=fn, kind="function",
                        file_path=entry.path, line=0,
                    ))
            else:
                # File deleted
                del snapshot.files[str(rel)]
                snapshot.total_files -= 1
                if old_entry:
                    for key in list(snapshot.symbols.keys()):
                        snapshot.symbols[key] = [
                            s for s in snapshot.symbols[key]
                            if s.file_path != str(rel)
                        ]
                        if not snapshot.symbols[key]:
                            del snapshot.symbols[key]

        self._last_snapshot = snapshot
        return snapshot

    def _is_excluded(self, rel: Path) -> bool:
        parts = rel.parts
        for part in parts:
            if part in self.excludes:
                return True
        ext = rel.suffix
        if ext not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".md",
                       ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
                       ".html", ".css", ".scss", ".sql", ".rb", ".java"):
            return True
        return False

    def _index_file(self, filepath: Path, rel: Path) -> FileEntry | None:
        try:
            stat = filepath.stat()
            text = filepath.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")

            entry = FileEntry(
                path=str(rel),
                relative_path=str(rel),
                size=stat.st_size,
                lines=len(lines),
                extension=rel.suffix,
                last_modified=stat.st_mtime,
                is_test="test_" in rel.name or "_test." in rel.name,
            )

            if rel.suffix == ".py":
                self._parse_python(text, entry)
            elif rel.suffix in (".js", ".ts", ".jsx", ".tsx"):
                self._parse_js_ts(text, entry)
            elif rel.suffix in (".go", ".rs"):
                self._parse_simple(text, entry)

            return entry
        except (OSError, UnicodeDecodeError):
            return None

    def _parse_python(self, text: str, entry: FileEntry):
        """Extract imports, classes, functions from Python source."""
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        entry.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        entry.imports.append(f"{module}.{alias.name}" if module else alias.name)
                elif isinstance(node, ast.ClassDef):
                    entry.classes.append(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entry.functions.append(node.name)
        except SyntaxError:
            pass

    def _parse_js_ts(self, text: str, entry: FileEntry):
        """Simple regex-based extraction for JS/TS."""
        # Imports
        for m in re.finditer(r'(?:import|require)\s*\(?\s*["\']([^"\']+)["\']', text):
            entry.imports.append(m.group(1))
        # Exports
        for m in re.finditer(r'(?:export\s+(?:default\s+)?)?(?:class|function|const|let|var)\s+(\w+)', text):
            name = m.group(1)
            if "class" in m.group():
                entry.classes.append(name)
            else:
                entry.functions.append(name)

    def _parse_simple(self, text: str, entry: FileEntry):
        """Simple parsing for Go/Rust."""
        for m in re.finditer(r'(?:func|fn|type|struct|impl)\s+(\w+)', text):
            entry.functions.append(m.group(1))
        for m in re.finditer(r'(?:import\s*\(?)\s*["\']([^"\']+)["\']', text):
            entry.imports.append(m.group(1))

    def find_symbol(self, name: str) -> list[SymbolEntry]:
        """Find all definitions matching a symbol name (case-insensitive)."""
        if self._last_snapshot is None:
            return []
        key = name.lower()
        return self._last_snapshot.symbols.get(key, [])

    def find_files_matching(self, query: str, max_results: int = 10) -> list[FileEntry]:
        """Find files matching a text query in path or content."""
        if self._last_snapshot is None:
            return []
        q = query.lower()
        results = []
        for f in self._last_snapshot.files.values():
            if q in f.relative_path.lower() or any(q in c.lower() for c in f.classes) or any(q in fn.lower() for fn in f.functions):
                results.append(f)
        return sorted(results, key=lambda x: x.lines)[:max_results]

    def project_summary(self, max_files: int = 20) -> str:
        """Human-readable project overview for LLM context."""
        if self._last_snapshot is None:
            return "(project not indexed)"
        snap = self._last_snapshot
        lines = [
            f"📁 Project: {snap.root.split(os.sep)[-1]}",
            f"   Files: {snap.total_files}  Lines: {snap.total_lines}",
            f"   Indexed: {snap.build_time_ms:.0f}ms",
        ]
        # Group by directory
        dirs: dict[str, list[str]] = defaultdict(list)
        for f in snap.files.values():
            parts = f.relative_path.split(os.sep)
            if len(parts) > 1:
                dirs[parts[0]].append(f.relative_path)
            else:
                dirs["root"].append(f.relative_path)

        lines.append(f"\n   Structure ({len(dirs)} dirs):")
        for d in sorted(dirs.keys())[:10]:
            files = dirs[d]
            lines.append(f"     {d}/  ({len(files)} files)")

        # Top symbols
        all_symbols = sorted(
            snap.symbols.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:15]
        if all_symbols:
            lines.append("\n   Key symbols:")
            for name, entries in all_symbols:
                types = set(e.kind for e in entries)
                files_shown = set(e.file_path.split(os.sep)[-1] for e in entries[:3])
                lines.append(f"     {name} ({', '.join(types)}) — {', '.join(files_shown)}")

        return "\n".join(lines)

    def context_for_llm(self) -> str:
        """Full context pack for LLM injection."""
        if self._last_snapshot is None:
            return ""
        return self.project_summary(max_files=30)


# ═══════════════════════════════════════════════════════════════════
# 2. RepoGraph — dependency / call graph
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Edge:
    """A directed edge in the repo graph."""
    source: str  # file path
    target: str  # file path or symbol
    kind: str    # "import", "call", "inherit", "reference"


@dataclass
class RepoGraph:
    """Dependency graph between files in the project.

    Builds on top of RepoIndex to extract relationships:
    - Which files import which
    - Which files define which symbols
    - Which files call which functions
    """
    nodes: set[str] = field(default_factory=set)
    edges: list[Edge] = field(default_factory=list)
    _adjacency: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @staticmethod
    def from_index(snapshot: RepoIndexSnapshot) -> RepoGraph:
        """Build a dependency graph from a RepoIndex snapshot."""
        graph = RepoGraph()
        for path, entry in snapshot.files.items():
            graph.nodes.add(path)
            for imp in entry.imports:
                # Map import to a file path
                target = _import_to_path(imp, snapshot)
                if target:
                    graph.edges.append(Edge(source=path, target=target, kind="import"))
                    graph._adjacency[path].add(target)
                    graph.nodes.add(target)

                # Also add symbol-level edges
                symbol_key = imp.split(".")[-1].lower()
                if symbol_key in snapshot.symbols:
                    for sym in snapshot.symbols[symbol_key]:
                        if sym.file_path != path:
                            graph.edges.append(Edge(
                                source=path, target=sym.file_path,
                                kind="reference",
                            ))
                            graph._adjacency[path].add(sym.file_path)

        return graph

    def dependencies_of(self, file_path: str, max_depth: int = 3) -> set[str]:
        """BFS upstream dependencies (what does this file depend on)."""
        visited: set[str] = set()
        queue = [file_path]
        for _ in range(max_depth):
            if not queue:
                break
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for dep in self._adjacency.get(current, []):
                if dep not in visited:
                    queue.append(dep)
        visited.discard(file_path)
        return visited

    def dependents_of(self, file_path: str, max_depth: int = 3) -> set[str]:
        """BFS downstream dependents (what depends on this file)."""
        reverse_adj: dict[str, set[str]] = defaultdict(set)
        for source, targets in self._adjacency.items():
            for target in targets:
                reverse_adj[target].add(source)

        visited: set[str] = set()
        queue = [file_path]
        for _ in range(max_depth):
            if not queue:
                break
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for dep in reverse_adj.get(current, []):
                if dep not in visited:
                    queue.append(dep)
        visited.discard(file_path)
        return visited

    def summary(self, file_path: str) -> str:
        """Human-readable dependency summary for a file."""
        deps = self.dependencies_of(file_path)
        dependents = self.dependents_of(file_path)
        lines = [f"📦 Dependencies for {file_path}:"]
        if deps:
            lines.append(f"   Depends on ({len(deps)} files):")
            for d in sorted(deps)[:10]:
                lines.append(f"     {d}")
            if len(deps) > 10:
                lines.append(f"     ... and {len(deps) - 10} more")
        else:
            lines.append("   No internal dependencies")
        if dependents:
            lines.append(f"   Depended by ({len(dependents)} files):")
            for d in sorted(dependents)[:10]:
                lines.append(f"     {d}")
            if len(dependents) > 10:
                lines.append(f"     ... and {len(dependents) - 10} more")
        else:
            lines.append("   No dependents (leaf file)")
        return "\n".join(lines)


def _import_to_path(imp: str, snapshot: RepoIndexSnapshot) -> str | None:
    """Try to map a Python import to a file path in the project."""
    # Direct match: "core.chat" -> "core/chat.py"
    candidate = imp.replace(".", "/") + ".py"
    if candidate in snapshot.files:
        return candidate
    # Try as module: "core" -> "core/__init__.py"
    candidate2 = imp.replace(".", "/") + "/__init__.py"
    if candidate2 in snapshot.files:
        return candidate2
    # Try just the last part
    parts = imp.split(".")
    for i in range(len(parts), 0, -1):
        sub = "/".join(parts[:i]) + ".py"
        if sub in snapshot.files:
            return sub
    return None


# ═══════════════════════════════════════════════════════════════════
# 3. Project Context Pack
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ProjectContextPack:
    """Structured snapshot of the project for LLM consumption.

    Composed by the ProjectOS from RepoIndex + RepoGraph.
    """
    project_name: str = ""
    summary: str = ""
    file_count: int = 0
    line_count: int = 0
    structure: str = ""
    key_symbols: str = ""
    active_file_context: str = ""
    dependency_context: str = ""

    def assemble(self) -> str:
        """Assemble into a compact context block for system prompt injection."""
        parts = [f"[Project Context: {self.project_name}]"]
        if self.summary:
            parts.append(self.summary)
        if self.structure:
            parts.append(self.structure)
        if self.key_symbols:
            parts.append(self.key_symbols)
        if self.active_file_context:
            parts.append(self.active_file_context)
        if self.dependency_context:
            parts.append(self.dependency_context)
        return "\n\n".join(parts)


class ProjectOS:
    """Unified Project Intelligence Layer — ties RepoIndex + RepoGraph together.

    Usage:
        os = ProjectOS()
        os.index()  # build index
        pack = os.context_pack(active_file="core/chat.py")  # context for LLM
        impact = os.analyze_change("core/chat.py")  # change impact
    """

    def __init__(self, root: str | None = None):
        resolved = os.path.abspath(root) if root else os.getcwd()
        self.indexer = RepoIndex(root=resolved)
        self.graph: RepoGraph | None = None
        self._last_snapshot: RepoIndexSnapshot | None = None

    def index(self) -> RepoIndexSnapshot:
        """Index the project (full scan)."""
        snap = self.indexer.build()
        self._last_snapshot = snap
        self.graph = RepoGraph.from_index(snap)
        return snap

    def quick_refresh(self) -> bool:
        """Quick incremental re-index. Returns True if changes were found."""
        snap = self.indexer.incremental()
        if snap:
            self._last_snapshot = snap
            self.graph = RepoGraph.from_index(snap)
            return True
        return False

    def context_pack(self, active_file: str = "", max_files_display: int = 20) -> ProjectContextPack:
        """Build a context pack for LLM injection."""
        if self._last_snapshot is None:
            self.index()

        snap = self._last_snapshot
        pack = ProjectContextPack(
            project_name=snap.root.split(os.sep)[-1],
            file_count=snap.total_files,
            line_count=snap.total_lines,
        )
        pack.summary = self.indexer.project_summary(max_files=max_files_display)

        # Active file details — normalize path separators
        normalized_active = active_file.replace("\\", "/")
        matched_file = None
        for fpath in snap.files:
            if fpath.replace("\\", "/") == normalized_active:
                matched_file = fpath
                break

        if matched_file:
            entry = snap.files[matched_file]
            pack.active_file_context = (
                f"   Active: {matched_file} ({entry.lines} lines, {len(entry.classes)} classes, {len(entry.functions)} functions)"
            )
            if self.graph:
                pack.dependency_context = self.graph.summary(matched_file)

        return pack

    def analyze_change(self, file_path: str) -> str:
        """Analyze the impact of changing a file."""
        if self.graph is None:
            self.index()

        lines = [f"🔍 Change Impact: {file_path}"]
        if self.graph:
            deps = self.graph.dependents_of(file_path)
            if deps:
                lines.append(f"   ⚠  {len(deps)} files depend on this — may need updates:")
                for d in sorted(deps)[:8]:
                    lines.append(f"      {d}")
                if len(deps) > 8:
                    lines.append(f"      ... and {len(deps) - 8} more")
            else:
                lines.append("   No other files depend on this (safe change)")
        return "\n".join(lines)

    def search(self, query: str) -> list[FileEntry]:
        """Intent-aware file search."""
        return self.indexer.find_files_matching(query)

    def find_symbol(self, name: str) -> list[SymbolEntry]:
        """Find symbol definitions across the repo."""
        return self.indexer.find_symbol(name)

    @property
    def is_indexed(self) -> bool:
        return self._last_snapshot is not None
