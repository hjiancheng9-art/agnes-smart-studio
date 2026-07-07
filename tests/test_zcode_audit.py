"""RED phase tests for core/audit_runner.py.

Tests: AuditRunner construction, audit_syntax, audit_deps, health_checks,
health_summary, collect_source_snippets, project_tree_data.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# audit_syntax
# ---------------------------------------------------------------------------


class TestAuditSyntax:
    """audit_syntax function."""

    def test_returns_list(self):
        from core.audit_runner import audit_syntax
        result = audit_syntax()
        assert isinstance(result, list)

    def test_returns_empty_for_valid_file(self, tmp_path):
        from core.audit_runner import audit_syntax
        # Create a valid Python file in tmp_path
        valid_py = tmp_path / "valid.py"
        valid_py.write_text("x = 1\ny = 2\n", encoding="utf-8")
        # Scan only our tmp_path
        result = audit_syntax(root=tmp_path)
        assert isinstance(result, list)
        assert "valid.py" not in [str(Path(p)) for p in result]

    def test_detects_syntax_error(self, tmp_path):
        from core.audit_runner import audit_syntax
        broken_py = tmp_path / "broken.py"
        broken_py.write_text("def broken(\n", encoding="utf-8")
        result = audit_syntax(root=tmp_path)
        # Should have at least one error
        str(Path("broken.py"))
        matching = [e for e in result if "broken.py" in str(e)]
        assert len(matching) >= 1

    def test_skips_non_py_files(self, tmp_path):
        from core.audit_runner import audit_syntax
        txt = tmp_path / "readme.txt"
        txt.write_text("not python", encoding="utf-8")
        result = audit_syntax(root=tmp_path)
        # Should not include .txt files as errors
        for e in result:
            assert "readme.txt" not in str(e)

    def test_accepts_str_root(self, tmp_path):
        from core.audit_runner import audit_syntax
        result = audit_syntax(root=str(tmp_path))
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# audit_deps
# ---------------------------------------------------------------------------


class TestAuditDeps:
    """audit_deps function."""

    def test_returns_tuple(self):
        from core.audit_runner import audit_deps
        result = audit_deps()
        assert isinstance(result, tuple)
        assert len(result) == 2
        ok, msg = result
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_current_env_deps_ok(self):
        from core.audit_runner import audit_deps
        ok, msg = audit_deps()
        # In our test environment, deps should be installed
        assert ok is True
        assert "installed" in msg.lower() or ok


# ---------------------------------------------------------------------------
# health_checks / health_summary
# ---------------------------------------------------------------------------


class TestHealthChecks:
    """health_checks and health_summary functions."""

    def test_health_checks_returns_list_of_dicts(self):
        from core.audit_runner import health_checks
        results = health_checks()
        assert isinstance(results, list)
        for entry in results:
            assert "category" in entry
            assert "ok" in entry
            assert "message" in entry

    def test_health_checks_includes_python_version(self):
        from core.audit_runner import health_checks
        results = health_checks()
        python_entry = [r for r in results if r["category"] == "Python"]
        assert len(python_entry) == 1
        assert python_entry[0]["ok"] is True  # Python >= 3.10

    def test_health_checks_includes_dependencies(self):
        from core.audit_runner import health_checks
        results = health_checks()
        deps_entry = [r for r in results if r["category"] == "Dependencies"]
        assert len(deps_entry) >= 1

    def test_health_summary_returns_string(self):
        from core.audit_runner import health_summary
        summary = health_summary()
        assert isinstance(summary, str)
        assert "OK" in summary
        assert "failed" in summary

    def test_health_summary_counts_match(self):
        from core.audit_runner import health_checks, health_summary
        checks = health_checks()
        ok_count = sum(1 for c in checks if c["ok"])
        summary = health_summary()
        assert f"{ok_count} OK" in summary


# ---------------------------------------------------------------------------
# collect_source_snippets
# ---------------------------------------------------------------------------


class TestCollectSourceSnippets:
    """collect_source_snippets function."""

    def test_returns_string(self):
        from core.audit_runner import collect_source_snippets
        result = collect_source_snippets()
        assert isinstance(result, str)

    def test_returns_markdown_format(self, tmp_path):
        from core.audit_runner import collect_source_snippets
        # Create a test core dir with a Python file
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        (core_dir / "test_mod.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")

        result = collect_source_snippets(root=tmp_path, dirs=["core"])
        assert "### core" in result  # path starts with core
        assert "```python" in result
        assert "def hello" in result

    def test_respects_max_chars(self, tmp_path):
        from core.audit_runner import collect_source_snippets
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        (core_dir / "big.py").write_text("x = " + "1" * 5000, encoding="utf-8")
        result = collect_source_snippets(root=tmp_path, dirs=["core"], max_chars=100)
        assert len(result) <= 5000  # reasonable bound

    def test_skips_missing_dirs(self, tmp_path):
        from core.audit_runner import collect_source_snippets
        result = collect_source_snippets(root=tmp_path, dirs=["nonexistent_dir"])
        assert result == ""


# ---------------------------------------------------------------------------
# project_tree_data
# ---------------------------------------------------------------------------


class TestProjectTreeData:
    """project_tree_data function."""

    def test_returns_list(self):
        from core.audit_runner import project_tree_data
        result = project_tree_data()
        assert isinstance(result, list)

    def test_entries_have_required_keys(self, tmp_path):
        from core.audit_runner import project_tree_data
        # Create some test structure
        (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()

        result = project_tree_data(root=tmp_path)
        for entry in result:
            assert "name" in entry
            assert "is_dir" in entry
            assert "children" in entry

    def test_skips_hidden_dirs(self, tmp_path):
        from core.audit_runner import project_tree_data
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        result = project_tree_data(root=tmp_path)
        names = [e["name"] for e in result]
        assert ".hidden/" not in names
        assert "visible/" in names

    def test_accepts_str_root(self, tmp_path):
        from core.audit_runner import project_tree_data
        result = project_tree_data(root=str(tmp_path))
        assert isinstance(result, list)
