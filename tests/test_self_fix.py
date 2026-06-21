"""Tests for core.self_fix — auto-repair engine."""



class TestFixResult:
    def test_basic_result(self):
        from core.self_fix import FixResult
        r = FixResult("fix_1", True, "BOM stripped")
        assert r.finding_id == "fix_1"
        assert r.success is True
        assert r.message == "BOM stripped"
        assert r.backup_path is None

    def test_with_backup(self):
        from core.self_fix import FixResult
        r = FixResult("fix_2", False, "failed", "/tmp/backup")
        assert r.backup_path == "/tmp/backup"


class TestSelfFixEngine:
    def _make_engine(self, root):
        from core.self_fix import SelfFixEngine
        return SelfFixEngine(root=root)

    def test_fix_bom(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "bom_file.py"
        content = b"\xef\xbb\xbfprint('hello')"
        f.write_bytes(content)
        findings = [{
            "category": "files",
            "title": "BOM detected",
            "file": "bom_file.py",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert len(results) == 1
        assert results[0].success is True
        assert "BOM" in results[0].message
        # File should no longer have BOM
        assert f.read_bytes()[:3] != b"\xef\xbb\xbf"

    def test_fix_bom_dry_run(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "bom_file.py"
        f.write_bytes(b"\xef\xbb\xbfprint('hello')")
        findings = [{
            "category": "files",
            "title": "BOM detected",
            "file": "bom_file.py",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings, dry_run=True)
        assert results[0].success is True
        assert "Would strip" in results[0].message
        # File unchanged
        assert f.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_fix_empty_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        findings = [{
            "category": "files",
            "title": "Empty file",
            "file": "empty.py",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert results[0].success is True
        assert f.read_text(encoding="utf-8") != ""

    def test_fix_empty_json_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "empty.json"
        f.write_text("", encoding="utf-8")
        findings = [{
            "category": "files",
            "title": "Empty file",
            "file": "empty.json",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert results[0].success is True
        content = f.read_text(encoding="utf-8").strip()
        assert content == "{}"

    def test_fix_nonexistent_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        findings = [{
            "category": "files",
            "title": "BOM detected",
            "file": "nonexistent.py",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert results[0].success is False
        assert "not found" in results[0].message.lower()

    def test_wildcard_import_requires_manual(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "wildcard.py"
        f.write_text("from os import *\n", encoding="utf-8")
        findings = [{
            "category": "imports",
            "title": "Wildcard import",
            "file": "wildcard.py",
            "line": 1,
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert results[0].success is False
        assert "manual review" in results[0].message.lower()

    def test_unfixable_category(self, tmp_path):
        engine = self._make_engine(tmp_path)
        findings = [{
            "category": "network",
            "title": "Network issue",
            "auto_fix": False,
        }]
        results = engine.fix_all(findings)
        assert len(results) == 0

    def test_unknown_fix_type(self, tmp_path):
        engine = self._make_engine(tmp_path)
        findings = [{
            "category": "files",
            "title": "Something unknown",
            "file": "test.py",
            "auto_fix": True,
        }]
        results = engine.fix_all(findings)
        assert results[0].success is False

    def test_rollback_on_failure(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "rollback_test.py"
        f.write_text("# original\nx = 1\n", encoding="utf-8")
        findings = [
            {
                "category": "files",
                "title": "BOM detected",
                "file": "nonexistent.py",
                "auto_fix": True,
            },
        ]
        engine.fix_all(findings)
        # Original file should still exist
        assert "original" in f.read_text(encoding="utf-8")

    def test_empty_findings(self, tmp_path):
        engine = self._make_engine(tmp_path)
        results = engine.fix_all([])
        assert results == []

    def test_print_results(self, tmp_path, capsys):
        from core.self_fix import FixResult
        engine = self._make_engine(tmp_path)
        engine.results = [
            FixResult("f1", True, "ok"),
            FixResult("f2", False, "fail"),
        ]
        engine.print_results()
        captured = capsys.readouterr()
        assert "1 fixed" in captured.out
        assert "1 failed" in captured.out


class TestAutoFixFunction:
    def test_auto_fix_is_callable(self):
        from core.self_fix import auto_fix
        assert callable(auto_fix)
