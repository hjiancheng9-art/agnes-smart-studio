"""Tests for core/patch.py — 结构化补丁引擎"""

import os

import pytest

from core.patch import ROOT, PatchEngine, PatchError, apply, rollback_last

PROJ = ROOT / ".crux" / "patch_test"


def _path(name):
    return str(PROJ / name)


def _write(name, content):
    PROJ.mkdir(parents=True, exist_ok=True)
    p = _path(name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(autouse=True)
def _clean():
    yield
    import shutil

    if PROJ.exists():
        shutil.rmtree(PROJ, ignore_errors=True)


class TestPatchEngine:
    """结构化补丁全链路测试"""

    def setup_method(self):
        self.engine = PatchEngine()

    def test_apply_update(self):
        path = _write("a.txt", "hello world\nold line\nbye")
        patch = f"*** Update File: {path}\n@@ old line\n-old line\n+new line"
        result = self.engine.apply(patch)
        assert result["success"] is True
        assert "new line" in _read(path)

    def test_apply_add_file(self):
        path = _path("new_file.py")
        patch = f"*** Add File: {path}\n+def hello():\n+    return 'world'"
        result = self.engine.apply(patch)
        assert result["success"] is True
        assert os.path.exists(path)

    def test_apply_delete_file(self):
        path = _write("to_del.txt", "delete me")
        patch = f"*** Delete File: {path}"
        result = self.engine.apply(patch)
        assert isinstance(result, dict)

    def test_apply_returns_dict(self):
        path = _write("b.txt", "hello")
        patch = f"*** Update File: {path}\n@@ hello\n-hello\n+world"
        result = self.engine.apply(patch)
        assert result["success"] is True

    def test_apply_empty_returns_ok(self):
        result = self.engine.apply("")
        assert isinstance(result, dict)

    def test_apply_invalid_returns_ok(self):
        result = self.engine.apply("not a valid patch")
        assert isinstance(result, dict)


class TestApplyStandalone:
    """模块级 apply 函数"""

    def test_apply(self):
        path = _write("c.txt", "x = 1\n")
        patch = f"*** Update File: {path}\n@@ x = 1\n-x = 1\n+x = 2"
        result = apply(patch)
        assert isinstance(result, dict)


class TestRollbackLast:
    """模块级 rollback_last"""

    def test_rollback_returns_dict(self):
        result = rollback_last()
        assert isinstance(result, dict)


class TestPatchError:
    """PatchError 异常"""

    def test_is_exception(self):
        assert issubclass(PatchError, Exception)

    def test_message(self):
        err = PatchError("测试错误")
        assert "测试错误" in str(err)
