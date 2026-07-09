"""Lightweight repo map — symbols, imports, tests, and git-aware file ranking.

GPT competitive analysis fix #2: "Build a repo map: symbols, imports, call graph,
recent files, test ownership." Enables multi-file awareness and targeted test loops.

Pattern: Aider's repo map — fast, no full AST parse, regex-based for speed.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories to skip during scanning
SKIP_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    "egg-info",
    "_archive",
    "output",
    "data",
    ".crux",
}

# File extensions to scan
PY_EXT = ".py"
SCAN_EXTS = {PY_EXT}


@dataclass
class FileSymbols:
    """Symbols extracted from a single source file."""

    path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    test_targets: list[str] = field(default_factory=list)  # modules this test file covers


@dataclass
class RepoMap:
    """Fast, regex-based codebase map. Updated incrementally."""

    symbols: dict[str, FileSymbols] = field(default_factory=dict)  # path → symbols
    recent_files: list[str] = field(default_factory=list)  # git-recent files
    file_count: int = 0
    _scanned: bool = False

    # ── Public API ──────────────────────────────────────────

    def scan(self, root: Path | None = None, max_files: int = 500) -> RepoMap:
        """Scan the repo for symbols. Returns self for chaining."""
        root = root or ROOT
        py_files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for f in filenames:
                if f.endswith(PY_EXT) and not f.startswith("_"):
                    py_files.append(os.path.join(dirpath, f))
            if len(py_files) >= max_files:
                break

        self.file_count = len(py_files)
        for fpath in py_files[:max_files]:
            rel = os.path.relpath(fpath, root).replace("\\", "/")
            syms = self._extract_symbols(fpath, rel)
            if syms.classes or syms.functions or syms.imports:
                self.symbols[rel] = syms

        self._load_recent_files()
        self._scanned = True
        return self

    def find_file(self, name: str) -> list[str]:
        """Find files containing a symbol (class, function, or basename)."""
        results = []
        name_lower = name.lower()
        for path, syms in self.symbols.items():
            basename_lower = os.path.basename(path).lower()
            stem_lower = os.path.splitext(basename_lower)[0]  # strip .py etc.
            if (
                name_lower in basename_lower
                or name_lower in stem_lower
                or name in syms.classes
                or name in syms.functions
            ):
                results.append(path)
        return results[:20]

    def get_imports(self, path: str) -> list[str]:
        """Get imports for a file — for tracing dependencies."""
        s = self.symbols.get(path)
        return s.imports if s else []

    def find_tests_for(self, source_path: str) -> list[str]:
        """Find test files that likely cover a given source file."""
        source_name = os.path.splitext(os.path.basename(source_path))[0]
        tests = []
        for path, syms in self.symbols.items():
            if "test" in path.lower() and source_name in path or source_name in syms.test_targets:
                tests.append(path)
        return tests[:10]

    def recent_changes(self, limit: int = 10) -> list[str]:
        """Return recently modified files (from git)."""
        return self.recent_files[:limit]

    def context_summary(self, max_items: int = 15) -> str:
        """One-shot context string for LLM prompts — key files and structure."""
        if not self._scanned:
            self.scan()

        lines = [f"Repo: {self.file_count} Python files scanned\n"]
        lines.append("Recent changes:")
        for f in self.recent_files[:5]:
            lines.append(f"  {f}")

        lines.append("\nKey modules:")
        # Show files with most symbols first
        ranked = sorted(self.symbols.items(), key=lambda x: len(x[1].functions) + len(x[1].classes), reverse=True)
        for path, syms in ranked[:max_items]:
            parts = []
            if syms.classes:
                parts.append(f"{len(syms.classes)} classes")
            if syms.functions:
                parts.append(f"{len(syms.functions)} funcs")
            lines.append(f"  {path} ({', '.join(parts)})")

        return "\n".join(lines)

    # ── Internal ────────────────────────────────────────────

    def _extract_symbols(self, fpath: str, rel: str) -> FileSymbols:
        """Extract classes, functions, and imports from a Python file."""
        syms = FileSymbols(path=rel)
        try:
            with open(fpath, encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return syms

        # AST-based extraction for reliability
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Fallback: regex-based for partially broken files
            return self._extract_symbols_regex(source, syms)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                syms.classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                syms.functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    syms.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                    syms.imports.append(node.module)

        # Detect test file → source file mapping
        if "test" in rel.lower():
            for imp in syms.imports:
                if imp.startswith("core.") or imp.startswith("ui.") or imp.startswith("utils."):
                    syms.test_targets.append(imp)

        return syms

    def _extract_symbols_regex(self, source: str, syms: FileSymbols) -> FileSymbols:
        """Fallback regex extraction for files with syntax errors."""
        syms.classes = re.findall(r"^class\s+(\w+)", source, re.MULTILINE)
        syms.functions = re.findall(r"^def\s+(\w+)", source, re.MULTILINE)
        syms.imports = re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE)
        return syms

    def _load_recent_files(self) -> None:
        """Get recently modified files from git log."""
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", "--pretty=format:", "-n", "20"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            if not result or result.stdout is None:
                return
            seen = set()
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.endswith(PY_EXT) and line not in seen:
                    self.recent_files.append(line)
                    seen.add(line)
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError, AttributeError):
            pass


# Singleton
_map: RepoMap | None = None


def get_repo_map() -> RepoMap:
    """Get or create the repo map singleton."""
    global _map
    if _map is None:
        _map = RepoMap().scan()
    return _map


def reset_repo_map() -> None:
    """Reset for testing."""
    global _map
    _map = None
