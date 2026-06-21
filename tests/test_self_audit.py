"""Tests for core.self_audit — comprehensive codebase scanning."""


import pytest


@pytest.fixture
def audit_project(tmp_path):
    """Create a project with known issues for AuditEngine to find."""
    # Wildcard import (medium severity)
    (tmp_path / "wildcard.py").write_text(
        'from os import *\n', encoding="utf-8")
    # Bare except (high severity)
    (tmp_path / "bare_except.py").write_text(
        'try:\n    pass\nexcept:\n    pass\n', encoding="utf-8")
    # Clean file
    (tmp_path / "clean.py").write_text(
        'import os\n\n\ndef hello():\n    return "hi"\n', encoding="utf-8")
    # Empty file (medium severity)
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    # Invalid tools.json (critical)
    (tmp_path / "tools.json").write_text("{invalid json", encoding="utf-8")
    # skills dir with a broken skill
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "bad.skill.json").write_text("{broken", encoding="utf-8")
    (skills / "empty.skill.json").write_text("", encoding="utf-8")
    return tmp_path


class TestAuditEngine:
    """AuditEngine scans a project for issues."""

    def test_scan_returns_report(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        assert isinstance(report, dict)
        assert "total_findings" in report
        assert "by_severity" in report
        assert "findings" in report

    def test_finds_wildcard_imports(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        imports = [f for f in report["findings"] if f.get("category") == "imports"]
        assert len(imports) >= 1
        assert any("wildcard" in f["title"].lower() or "import *" in f.get("detail", "") for f in imports)

    def test_finds_bare_except(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        exceptions = [f for f in report["findings"] if f.get("category") == "exceptions"]
        assert len(exceptions) >= 1

    def test_finds_empty_files(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        files = [f for f in report["findings"] if f.get("category") == "files"]
        empty_findings = [f for f in files if "empty" in f["title"].lower()]
        assert len(empty_findings) >= 1

    def test_finds_invalid_tools_json(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        config = [f for f in report["findings"] if f.get("category") == "config"]
        assert len(config) >= 1
        assert any("tools.json" in f.get("file", "") for f in config)

    def test_finds_bad_skill_json(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        skills = [f for f in report["findings"] if f.get("category") == "skills"]
        assert len(skills) >= 2  # bad JSON + empty

    def test_severity_counts(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        sev = report["by_severity"]
        total = sum(sev.values())
        assert total == report["total_findings"]
        assert total > 0

    def test_clean_project_no_findings(self, tmp_path):
        from core.self_audit import AuditEngine
        (tmp_path / "clean.py").write_text(
            'import os\n\n\ndef hello():\n    return "hi"\n', encoding="utf-8")
        engine = AuditEngine(root=tmp_path)
        report = engine.scan()
        # May still find encoding/git findings, but no import/exception issues
        imports = [f for f in report["findings"] if f.get("category") == "imports"]
        assert imports == []

    def test_default_root(self):
        from core.self_audit import AuditEngine, ROOT
        engine = AuditEngine()
        assert engine.root == ROOT

    def test_audit_function(self):
        from core.self_audit import audit
        report = audit()
        assert isinstance(report, dict)
        assert "findings" in report


class TestReportStructure:
    """Report structure is consistent."""

    def test_finding_has_required_fields(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        for finding in report["findings"]:
            assert "category" in finding
            assert "severity" in finding
            assert "title" in finding

    def test_severity_values(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        valid_severities = {"critical", "high", "medium", "low", "info"}
        for finding in report["findings"]:
            assert finding["severity"] in valid_severities

    def test_auto_fixable_count(self, audit_project):
        from core.self_audit import AuditEngine
        engine = AuditEngine(root=audit_project)
        report = engine.scan()
        assert "auto_fixable" in report
        assert isinstance(report["auto_fixable"], int)
        assert report["auto_fixable"] <= report["total_findings"]


class TestSkipDirs:
    """AuditEngine skips known non-source directories."""

    def test_skips_pycache(self, tmp_path):
        from core.self_audit import AuditEngine
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        # Put a file with issues in __pycache__
        (cache / "cached.py").write_text('from os import *\n', encoding="utf-8")
        engine = AuditEngine(root=tmp_path)
        report = engine.scan()
        imports = [f for f in report["findings"] if f.get("category") == "imports"]
        assert imports == []  # skipped

    def test_skips_git_dir(self, tmp_path):
        from core.self_audit import AuditEngine
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "empty.py").write_text("", encoding="utf-8")
        engine = AuditEngine(root=tmp_path)
        report = engine.scan()
        files = [f for f in report["findings"]
                 if f.get("category") == "files" and ".git" in f.get("file", "")]
        assert files == []
