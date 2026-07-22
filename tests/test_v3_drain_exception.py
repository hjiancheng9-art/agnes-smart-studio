"""Test that _drain_and_reduce_locked uses queue.Empty/Empty not bare Exception."""

import ast
import pathlib

APP_PATH = pathlib.Path(__file__).parent.parent / "ui" / "v3" / "app.py"


def test_drain_uses_queue_empty():
    """_drain_and_reduce_locked must catch queue.Empty/Empty, not bare Exception."""
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class DrainVisitor(ast.NodeVisitor):
        def __init__(self):
            self.found = False
            self.bare_except = None

        def visit_FunctionDef(self, node):
            if node.name == "_drain_and_reduce_locked":
                for child in ast.walk(node):
                    if isinstance(child, ast.ExceptHandler):
                        if child.type is None:
                            self.bare_except = child.lineno
                        elif isinstance(child.type, ast.Attribute):
                            if child.type.attr == "Empty":
                                self.found = True
                        elif isinstance(child.type, ast.Name):
                            if child.type.id == "Empty":
                                self.found = True
            self.generic_visit(node)

    v = DrainVisitor()
    v.visit(tree)
    assert v.found, (
        f"Expected 'except Empty:' or 'except queue.Empty:' in _drain_and_reduce_locked, got bare except at line {v.bare_except}"
    )
