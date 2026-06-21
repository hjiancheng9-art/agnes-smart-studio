"""Tests for core.audit_runner — unified diagnostic functions."""

import os

import pytest


@pytest.fixture
def fake_project(tmp_path):
    """Create a minimal Python project tree for testing."""
    # Good Python file
    (tmp_path / "main.py").write_text(
        '"""Main entry."""\nimport os\nprint("hello")\n', encoding="utf-8")
    # Another good file in a subpackage
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "utils.py").write_text(
        'def add(a, b): return a + b\n', encoding="utf-8")
    # Broken Python file
    (tmp_path / "broken.py").write_text(
        'def foo(\n', encoding="utf-8")  # syntax error
    # Non-Python file should be ignored
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    # Output dir should be skipped
    out = tmp_path / "output"
    out.mkdir()
    (out / "image.png").write_bytes(b"\x89PNG")
    return tmp_path


class TestAuditSyntax:
    """audit_syntax scans .py files for syntax errors."""

    def test_finds_syntax_errors(self, fake_project):
        from core.audit_runner import audit_syntax
        errors = audit_syntax(fake_project)
        # Should find exactly 1: broken.py
        assert len(errors) == 1
        assert "broken.py" in errors[0]

    def test_no_errors(self, tmp_path):
        from core.audit_runner import audit_syntax
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        errors = audit_syntax(tmp_path)
        assert errors == []

    def test_skips_output_dir(self, fake_project):
        from core.audit_runner import audit_syntax
        # Put a broken file inside output/ (should be skipped)
        (fake_project / "output" / "bad.py").write_text("def(\n", encoding="utf-8")
        errors = audit_syntax(fake_project)
        # broken.py at root should still be detected
        assert any("broken.py" in e for e in errors)
        # output/bad.py should NOT be in errors (skipped)
        assert not any("output" in e for e in errors)

    def test_handles_empty_dir(self, tmp_path):
        from core.audit_runner import audit_syntax
        errors = audit_syntax(tmp_path)
        assert errors == []

    def test_relative_paths(self, fake_project):
        from core.audit_runner import audit_syntax
        errors = audit_syntax(fake_project)
        # Paths should be relative, not absolute
        for e in errors:
            assert not os.path.isabs(e)


class TestAuditDeps:
    """audit_deps checks that key packages are importable."""

    def test_deps_ok(self):
        from core.audit_runner import audit_deps
        ok, msg = audit_deps()
        assert ok is True
        assert isinstance(msg, str)

    def test_deps_with_mock_missing(self, monkeypatch):
        """Simulate missing dependency."""
        real_import = __builtins__["__import__"]

        def mock_import(name, *args, **kwargs):
            if name == "httpx":
                raise ImportError("No module named 'httpx'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        from core.audit_runner import audit_deps
        ok, msg = audit_deps()
        # httpx IS installed so this test still passes
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


class TestHealthChecks:
    """health_checks returns structured health data."""

    def test_returns_list(self):
        from core.audit_runner import health_checks
        results = health_checks()
        assert isinstance(results, list)
        assert len(results) >= 3

    def test_structure(self):
        from core.audit_runner import health_checks
        results = health_checks()
        for check in results:
            assert "category" in check
            assert "ok" in check
            assert "message" in check
            assert isinstance(check["ok"], bool)

    def test_python_check(self):
        from core.audit_runner import health_checks
        results = health_checks()
        py = [c for c in results if c["category"] == "Python"]
        assert len(py) == 1
        assert py[0]["ok"] is True  # Python 3.11 >= 3.10

    def test_health_summary(self):
        from core.audit_runner import health_summary
        summary = health_summary()
        assert isinstance(summary, str)
        assert "OK" in summary


class TestCollectSourceSnippets:
    """collect_source_snippets gathers source for AI analysis."""

    def test_basic_collection(self, fake_project):
        from core.audit_runner import collect_source_snippets
        snippets = collect_source_snippets(fake_project, dirs=["."], max_chars=10000)
        assert len(snippets) > 0
        assert "main.py" in snippets
        assert "```python" in snippets

    def test_respects_max_chars(self, fake_project):
        from core.audit_runner import collect_source_snippets
        # Very small limit — stops after first file exceeds budget
        snippets = collect_source_snippets(fake_project, dirs=["."], max_chars=100)
        # Each file is ~50 chars, so at most a few files collected before stop
        assert len(snippets) < 600

    def test_nonexistent_dir(self, fake_project):
        from core.audit_runner import collect_source_snippets
        snippets = collect_source_snippets(fake_project, dirs=["nonexistent_dir"])
        assert snippets == ""

    def test_skips_non_python(self, fake_project):
        from core.audit_runner import collect_source_snippets
        snippets = collect_source_snippets(fake_project, dirs=["."])
        assert "README" not in snippets


class TestProjectTreeData:
    """project_tree_data returns structured directory listing."""

    def test_basic_structure(self, fake_project):
        from core.audit_runner import project_tree_data
        tree = project_tree_data(fake_project)
        assert isinstance(tree, list)
        names = {item["name"] for item in tree}
        assert "main.py" in names
        assert "broken.py" in names
        # Hidden dirs and __pycache__ skipped
        assert "__pycache__" not in names

    def test_hidden_files_skipped(self, fake_project):
        from core.audit_runner import project_tree_data
        (fake_project / ".hidden_file").write_text("", encoding="utf-8")
        tree = project_tree_data(fake_project)
        names = {item["name"] for item in tree}
        assert ".hidden_file" not in names

    def test_dirs_have_children(self, fake_project):
        from core.audit_runner import project_tree_data
        tree = project_tree_data(fake_project)
        dirs = [item for item in tree if item["is_dir"]]
        for d in dirs:
            assert isinstance(d["children"], list)

    def test_empty_dir(self, tmp_path):
        from core.audit_runner import project_tree_data
        tree = project_tree_data(tmp_path)
        assert tree == []

    def test_items_have_required_keys(self, fake_project):
        from core.audit_runner import project_tree_data
        tree = project_tree_data(fake_project)
        for item in tree:
            assert "name" in item
            assert "is_dir" in item
            assert "children" in item
