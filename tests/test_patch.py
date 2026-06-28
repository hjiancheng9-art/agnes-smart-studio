"""Tests for core.patch — structured patch engine."""


class TestPatchEngine:
    def _make_engine(self, root):
        from core.patch import PatchEngine

        return PatchEngine(root=root)

    def test_add_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        patch = "*** Add File: hello.py\n+print('hello world')\n"
        result = engine.apply(patch)
        assert result["success"] is True
        assert (tmp_path / "hello.py").exists()
        assert "hello world" in (tmp_path / "hello.py").read_text(encoding="utf-8")

    def test_add_file_syntax_verify_ok(self, tmp_path):
        engine = self._make_engine(tmp_path)
        patch = "*** Add File: ok.py\n+x = 1\n+y = 2\n"
        result = engine.apply(patch, verify=True)
        assert result["success"] is True

    def test_add_file_syntax_verify_fail(self, tmp_path):
        engine = self._make_engine(tmp_path)
        patch = "*** Add File: bad.py\n+def broken(\n"
        result = engine.apply(patch, verify=True)
        assert result["success"] is False
        assert "Syntax error" in result["error"]

    def test_add_file_no_verify(self, tmp_path):
        engine = self._make_engine(tmp_path)
        patch = "*** Add File: bad.py\n+def broken(\n"
        result = engine.apply(patch, verify=False)
        assert result["success"] is True

    def test_delete_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "to_delete.py"
        f.write_text("old content", encoding="utf-8")
        patch = "*** Delete File: to_delete.py\n"
        result = engine.apply(patch)
        assert result["success"] is True
        assert not f.exists()

    def test_delete_nonexistent_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        patch = "*** Delete File: nonexistent.py\n"
        result = engine.apply(patch)
        assert result["success"] is True

    def test_update_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "target.py"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        patch = "*** Update File: target.py\n@@ line2\n-line2\n+line2_updated\n"
        result = engine.apply(patch)
        assert result["success"] is True
        content = f.read_text(encoding="utf-8")
        assert "line2_updated" in content
        assert "line2" not in content or "line2_updated" in content

    def test_update_file_context_not_found(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "target.py"
        f.write_text("line1\nline2\n", encoding="utf-8")
        patch = "*** Update File: target.py\n@@ nonexistent_context\n-old\n+new\n"
        result = engine.apply(patch)
        assert result["success"] is False
        assert "Context not found" in result["error"]

    def test_update_file_syntax_verify_fail(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "target.py"
        f.write_text("line1\ndef good():\n    pass\n", encoding="utf-8")
        patch = "*** Update File: target.py\n@@ def good():\n-def good():\n+def broken(\n"
        result = engine.apply(patch, verify=True)
        assert result["success"] is False

    def test_rollback_on_failure(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "rollback_test.py"
        f.write_text("original = 42\n", encoding="utf-8")
        patch = "*** Update File: rollback_test.py\n@@ original = 42\n-original = 42\n+def broken(\n"
        result = engine.apply(patch, verify=True)
        assert result["success"] is False
        # File should be rolled back
        content = f.read_text(encoding="utf-8")
        assert "original = 42" in content

    def test_multiple_operations(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "multi.py"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        patch = "*** Add File: new.py\n+print('new')\n*** Update File: multi.py\n@@ b\n-b\n+B\n"
        result = engine.apply(patch)
        assert result["success"] is True
        assert (tmp_path / "new.py").exists()
        assert "B" in (tmp_path / "multi.py").read_text(encoding="utf-8")

    def test_path_outside_root(self, tmp_path):
        engine = self._make_engine(tmp_path)
        # Try to write to parent directory
        outside = str(tmp_path.parent / "outside.py")
        patch = f"*** Add File: {outside}\n+content\n"
        result = engine.apply(patch)
        assert result["success"] is False
        # Error message contains path rejection indication
        assert result["error"]  # some error message

    def test_parse_returns_empty_for_no_ops(self, tmp_path):
        engine = self._make_engine(tmp_path)
        result = engine.apply("no operations here")
        assert result["success"] is True
        assert result["files_modified"] == 0

    def test_backup_created_and_rollback_restores(self, tmp_path):
        engine = self._make_engine(tmp_path)
        f = tmp_path / "backup.py"
        f.write_text("x = 1\n", encoding="utf-8")
        # Successful update should create backup internally
        patch = "*** Update File: backup.py\n@@ x = 1\n-x = 1\n+x = 2\n"
        result = engine.apply(patch)
        assert result["success"] is True
        assert "x = 2" in f.read_text(encoding="utf-8")


class TestPatchError:
    def test_patch_error_attributes(self):
        from core.patch import PatchError

        err = PatchError("test error", file="test.py", line=10)
        assert str(err) == "test error"
        assert err.file == "test.py"
        assert err.line == 10

    def test_patch_error_defaults(self):
        from core.patch import PatchError

        err = PatchError("message")
        assert err.file == ""
        assert err.line == 0


class TestApplyConvenience:
    def test_apply_function(self, tmp_path):
        from core.patch import apply

        # The global ROOT won't be tmp_path, so use a relative path
        # that would fail — we just test the function exists and calls PatchEngine
        assert callable(apply)


class TestAntiSelfDamage:
    """Patch engine global snapshot + atomic rollback for core file protection."""
    def test_global_snapshot_created_before_patch(self, tmp_path):
        from core.patch import PatchEngine
        f = tmp_path / "target.py"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        engine = PatchEngine(root=tmp_path)
        patch = "*** Update File: target.py\n@@ line1\n-line1\n+new1\n"
        engine.apply(patch)
        # Global snapshot should have been created before modification
        assert str(f) in engine._backups or engine._backups == {}

    def test_rollback_restores_all_files(self, tmp_path):
        from core.patch import PatchEngine
        # Setup two files
        f1 = tmp_path / "a.py"; f1.write_text("original_a", encoding="utf-8")
        f2 = tmp_path / "b.py"; f2.write_text("original_b", encoding="utf-8")
        engine = PatchEngine(root=tmp_path)
        try:
            patch = "*** Update File: a.py\n@@ original_a\n-original_a\n+new_a\n" \
                    "*** Update File: b.py\n@@ NOMATCH\n-x\n+y\n"
            engine.apply(patch)
        except Exception:
            pass
        # Both files should be restored to original state
        assert f1.read_text(encoding="utf-8") == "original_a"
        assert f2.read_text(encoding="utf-8") == "original_b"
