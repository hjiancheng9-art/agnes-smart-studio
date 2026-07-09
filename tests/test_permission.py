"""Tests for core/permission.py — 权限模式系统"""

import pytest

from core.permission import (
    PermissionMode,
    get_permission_manager,
    reset_permission_manager,
)


@pytest.fixture
def pm():
    """每个测试独立重置权限管理器"""
    reset_permission_manager()
    return get_permission_manager()


class TestPermissionModes:
    """权限模式枚举测试"""

    def test_modes_exist(self):
        assert PermissionMode.AUTO.value == "auto"
        assert PermissionMode.MANUAL.value == "manual"
        assert PermissionMode.YOLO.value == "yolo"

    def test_auto_is_default(self, pm):
        assert pm.mode == PermissionMode.AUTO

    def test_get_mode_name(self, pm):
        name = pm.get_mode_name()
        assert isinstance(name, str)
        assert len(name) > 0


class TestModeSwitching:
    """模式切换测试"""

    def test_set_yolo(self, pm):
        pm.set_mode(PermissionMode.YOLO)
        assert pm.mode == PermissionMode.YOLO

    def test_set_manual(self, pm):
        pm.set_mode(PermissionMode.MANUAL)
        assert pm.mode == PermissionMode.MANUAL

    def test_set_auto(self, pm):
        pm.set_mode(PermissionMode.AUTO)
        assert pm.mode == PermissionMode.AUTO

    def test_needs_confirmation_in_yolo(self, pm):
        pm.set_mode(PermissionMode.YOLO)
        assert not pm.needs_confirmation("write_file")

    def test_needs_confirmation_in_manual(self, pm):
        pm.set_mode(PermissionMode.MANUAL)
        assert pm.needs_confirmation("write_file")

    def test_needs_confirmation_in_auto_for_read(self, pm):
        pm.set_mode(PermissionMode.AUTO)
        assert not pm.needs_confirmation("read_file")

    def test_needs_confirmation_in_auto_for_write(self, pm):
        pm.set_mode(PermissionMode.AUTO)
        result = pm.needs_confirmation("write_file")
        assert isinstance(result, bool)

    def test_get_summary(self, pm):
        summary = pm.get_summary()
        assert isinstance(summary, dict)


class TestRememberForget:
    """记住/忘记选择测试"""

    def test_remember_allows(self, pm):
        pm.set_mode(PermissionMode.MANUAL)
        pm.remember("run_bash", allowed=True)
        # 记住后应不再需要确认
        assert not pm.needs_confirmation("run_bash")

    def test_forget_resets(self, pm):
        pm.set_mode(PermissionMode.MANUAL)
        pm.remember("run_bash", allowed=True)
        pm.forget("run_bash")
        assert pm.needs_confirmation("run_bash")

    def test_forget_non_existent(self, pm):
        pm.forget("nonexistent_tool")
        # 不应崩溃


class TestConfirmHook:
    """确认钩子测试"""

    def test_set_confirm_hook(self, pm):
        called = []
        pm.set_confirm_hook(lambda tool, args: called.append(tool))
        pm.request_confirmation("write_file", {"path": "/tmp"})
        assert called == ["write_file"]

    def test_request_confirmation_default(self, pm):
        result = pm.request_confirmation("write_file", {"path": "/tmp"})
        # 没有钩子时默认返回 True 或 False
        assert isinstance(result, bool)

    def test_on_mode_change(self, pm):
        called = []
        pm.on_mode_change(lambda mode: called.append(mode))
        pm.set_mode(PermissionMode.YOLO)
        assert PermissionMode.YOLO in called


class TestSingleton:
    """单例模式测试"""

    def test_get_permission_manager(self):
        pm1 = get_permission_manager()
        pm2 = get_permission_manager()
        assert pm1 is pm2

    def test_reset_changes_instance(self):
        pm1 = get_permission_manager()
        reset_permission_manager()
        pm2 = get_permission_manager()
        assert pm1 is not pm2
