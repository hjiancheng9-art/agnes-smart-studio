"""RED phase tests for core/patch.py.

Tests: PatchEngine, apply, rollback_last, PatchError.
"""

from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# PatchEngine construction
# ---------------------------------------------------------------------------


class TestPatchEngineConstruction:
    """PatchEngine initialization."""

    def test_default_root(self):
        from core.patch import ROOT, PatchEngine
        pe = PatchEngine()
        assert pe.root == ROOT

    def test_custom_root(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        assert pe.root == tmp_path

    def test_backups_empty_initially(self):
        from core.patch import PatchEngine
        pe = PatchEngine()
        assert pe._backups == {}
        assert pe._modified == set()


# ---------------------------------------------------------------------------
# PatchError
# ---------------------------------------------------------------------------


class TestPatchError:
    """PatchError exception."""

    def test_is_exception(self):
        from core.patch import PatchError
        err = PatchError("test message")
        assert isinstance(err, Exception)

    def test_stores_file_and_line(self):
        from core.patch import PatchError
        err = PatchError("msg", file="test.py", line=42)
        assert err.file == "test.py"
        assert err.line == 42

    def test_default_file_and_line(self):
        from core.patch import PatchError
        err = PatchError("msg")
        assert err.file == ""
        assert err.line == 0


# ---------------------------------------------------------------------------
# PatchEngine apply
# ---------------------------------------------------------------------------


class TestPatchEngineAddFile:
    """Test add_file operations."""

    def test_add_new_file(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        patch = f"""*** Add File: {tmp_path}/hello.py
+print("hello world")
"""
        result = pe.apply(patch, verify=False)
        assert result["success"] is True
        assert (tmp_path / "hello.py").exists()
        content = (tmp_path / "hello.py").read_text()
        assert "hello world" in content

    def test_add_file_with_multi_lines(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Add File: test.txt\n"
            "+line1\n"
            "+line2\n"
            "+line3\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is True
        content = (tmp_path / "test.txt").read_text().strip().split("\n")
        assert len(content) == 3

    def test_add_file_syntax_verify(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        # Invalid Python syntax
        patch = (
            "*** Add File: broken.py\n"
            "+def foo(\n"
        )
        result = pe.apply(patch, verify=True)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Update file operations
# ---------------------------------------------------------------------------


class TestPatchEngineUpdateFile:
    """Test update_file operations."""

    def test_update_single_context_match(self, tmp_path):
        from core.patch import PatchEngine
        test_file = tmp_path / "target.py"
        test_file.write_text("old_value = 1\nother = 2\n", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Update File: target.py\n"
            "@@ old_value = 1\n"
            "+new_value = 42\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is True
        content = test_file.read_text()
        assert "new_value = 42" in content
        assert "old_value = 1" not in content

    def test_update_syntax_verify_failure(self, tmp_path):
        from core.patch import PatchEngine
        test_file = tmp_path / "target.py"
        test_file.write_text("x = 1\n", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Update File: target.py\n"
            "@@ x = 1\n"
            "+def broken(\n"
        )
        result = pe.apply(patch, verify=True)
        assert result["success"] is False

    def test_update_context_not_found(self, tmp_path):
        from core.patch import PatchEngine
        test_file = tmp_path / "target.py"
        test_file.write_text("x = 1\n", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Update File: target.py\n"
            "@@ nonexistent_context_line\n"
            "+y = 2\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is False

    def test_update_file_not_found(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Update File: missing.py\n"
            "@@ context\n"
            "+something\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is False

    def test_update_with_line_number_anchor(self, tmp_path):
        from core.patch import PatchEngine
        test_file = tmp_path / "target.py"
        test_file.write_text("first\nsecond\nthird\n", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Update File: target.py\n"
            "@@ 2 second\n"
            "+replaced\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is True
        content = test_file.read_text()
        assert "replaced" in content


# ---------------------------------------------------------------------------
# Delete file operations
# ---------------------------------------------------------------------------


class TestPatchEngineDeleteFile:
    """Test delete_file operations."""

    def test_delete_existing_file(self, tmp_path):
        from core.patch import PatchEngine
        test_file = tmp_path / "remove_me.txt"
        test_file.write_text("delete me", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Delete File: remove_me.txt\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is True
        assert not test_file.exists()

    def test_delete_missing_file_is_ok(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        patch = (
            "*** Delete File: nonexistent.txt\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Multi-operation patches
# ---------------------------------------------------------------------------


class TestPatchEngineMultiOp:
    """Multiple operations in one patch."""

    def test_add_and_update(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        # First add a file
        patch_add = (
            "*** Add File: a.py\n"
            "+x = 1\n"
        )
        pe.apply(patch_add, verify=False)
        # Then update + add in same patch
        patch_multi = (
            "*** Update File: a.py\n"
            "@@ x = 1\n"
            "+x = 999\n"
            "*** Add File: b.py\n"
            "+y = 2\n"
        )
        result = pe.apply(patch_multi, verify=False)
        assert result["success"] is True
        assert (tmp_path / "a.py").read_text().strip() == "x = 999"
        assert (tmp_path / "b.py").read_text().strip() == "y = 2"

    def test_rollback_on_failure(self, tmp_path):
        from core.patch import PatchEngine
        # Create a valid file first
        test_file = tmp_path / "target.py"
        test_file.write_text("original\n", encoding="utf-8")

        pe = PatchEngine(root=tmp_path)
        # Multi-op: update succeeds but second op fails
        patch = (
            "*** Update File: target.py\n"
            "@@ original\n"
            "+modified\n"
            "*** Update File: missing.py\n"
            "@@ context\n"
            "+something\n"
        )
        result = pe.apply(patch, verify=False)
        assert result["success"] is False
        # target.py should be restored to original
        assert test_file.read_text().strip() == "original"


# ---------------------------------------------------------------------------
# apply / rollback_last convenience functions
# ---------------------------------------------------------------------------


class TestApplyConvenience:
    """Module-level apply function."""

    def test_apply_exists(self):
        from core.patch import apply
        assert callable(apply)

    def test_apply_delegates_to_engine(self):
        from core.patch import apply
        with mock.patch("core.patch.PatchEngine") as MockEngine:
            mock_instance = mock.MagicMock()
            mock_instance.apply.return_value = {"success": True, "files_modified": 1, "results": []}
            MockEngine.return_value = mock_instance
            result = apply("*** Add File: test.txt\n+hello\n", verify=False)
            assert result["success"] is True


class TestRollbackLast:
    """Module-level rollback_last function."""

    def test_exists(self):
        from core.patch import rollback_last
        assert callable(rollback_last)

    def test_nothing_to_undo_when_empty(self):
        # Simulate empty state
        import core.patch as p
        from core.patch import rollback_last
        with mock.patch.object(p, "_LAST_BACKUPS", {}), mock.patch.object(p, "_LAST_ADDED", set()):
            result = rollback_last()
            assert result["success"] is False
            assert "nothing_to_undo" in result["reason"]


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


class TestPatchPathValidation:
    """Path resolution and validation."""

    def test_absolute_path_within_root(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        resolved = pe._resolve_path(str(tmp_path / "sub" / "file.py"))
        assert resolved == (tmp_path / "sub" / "file.py").resolve()

    def test_path_outside_root_raises(self, tmp_path):
        from core.patch import PatchEngine
        pe = PatchEngine(root=tmp_path)
        with pytest.raises(Exception):
            # Try to access a path clearly outside root
            pe._resolve_path(str(tmp_path / ".." / ".." / "etc" / "passwd"))
