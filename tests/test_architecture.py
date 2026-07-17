"""Architecture constraint tests — prevent cross-layer imports per ChatGPT audit."""

from __future__ import annotations

import ast
import os


def _imports_of(file_path: str) -> set[str]:
    """Extract all imported module names from a Python file."""
    with open(file_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports


class TestArchitectureBoundaries:
    """Verify domain/ doesn't import UI, runtime, or provider layers."""

    def test_domain_no_ui_imports(self):
        for f in os.listdir("domain"):
            if f.endswith(".py"):
                imps = _imports_of(f"domain/{f}")
                assert "ui" not in imps, f"domain/{f} imports ui"
                assert "core" not in imps, f"domain/{f} imports core"

    def test_runtime_no_provider_imports(self):
        """runtime/ should not import specific providers."""
        for f in os.listdir("runtime"):
            if f.endswith(".py"):
                imps = _imports_of(f"runtime/{f}")
                assert "provider" not in imps, f"runtime/{f} imports provider"
                assert "client" not in imps, f"runtime/{f} imports client"

    def test_prompts_no_runtime_imports(self):
        """prompts/ should be pure text assembly, not depend on runtime."""
        for f in os.listdir("prompts"):
            if f.endswith(".py"):
                imps = _imports_of(f"prompts/{f}")
                assert "runtime" not in imps, f"prompts/{f} imports runtime"

    def test_domain_no_provider_imports(self):
        """domain/ must not import provider or client infrastructure."""
        for f in os.listdir("domain"):
            if f.endswith(".py"):
                imps = _imports_of(f"domain/{f}")
                assert "provider" not in imps, f"domain/{f} imports provider"
                assert "client" not in imps, f"domain/{f} imports client"

    def test_tools_no_chat_import(self):
        """tools.py must not import ChatSession (circular dependency risk)."""
        if os.path.exists("core/tools.py"):
            imps = _imports_of("core/tools.py")
            assert "chat" not in imps, "core/tools.py imports chat (circular dep!)"
