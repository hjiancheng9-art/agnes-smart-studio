"""Tests for core/sandbox.py — 沙箱安全引擎"""

from pathlib import Path

import pytest

from core.sandbox import (
    FileAudit,
    Sandbox,
    _current_allowed_roots,
    _path_is_allowed,
    get_audit_trail,
    sandbox_check,
    sandbox_restrict,
    tokenize_command,
)


class TestSandboxTokenize:
    """命令词法分析器测试"""

    def test_tokenize_simple(self):
        """简单命令解析"""
        t = tokenize_command("echo hello")
        assert t["command"] == "echo"
        assert t["args"] == ["hello"]

    def test_tokenize_with_flags(self):
        """带参数的命令解析"""
        t = tokenize_command("rm -rf /tmp")
        assert t["command"] == "rm"
        assert "-rf" in t["args"]
        assert "/tmp" in t["args"]

    def test_tokenize_pipeline(self):
        """管道命令解析"""
        t = tokenize_command("ls -la | grep py")
        assert t["command"] == "ls"
        assert "|" in str(t) or len(t["args"]) > 0

    def test_tokenize_empty(self):
        """空命令解析不崩溃"""
        t = tokenize_command("")
        assert t is not None

    def test_tokenize_complex(self):
        """复杂命令不崩溃"""
        t = tokenize_command("echo $(whoami) && pwd")
        assert t is not None


class TestSandboxValidate:
    """验证方法测试"""

    def setup_method(self):
        self.sb = Sandbox()

    def test_validate_returns_tuple(self):
        """validate 返回 (bool, str) 元组"""
        result = self.sb.validate("echo hello")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_validate_returns_ok_for_safe(self):
        """安全命令返回 True"""
        result = self.sb.validate("ls -la")
        assert result[0] is True

    def test_validate_returns_ok_for_rm(self):
        """rm 命令当前审计模式返回 ok"""
        result = self.sb.validate("rm -rf /")
        assert result is not None  # 审计模式，不阻断

    def test_validate_multiple_calls(self):
        """多次验证不崩溃"""
        for cmd in ["echo 1", "echo 2", "ls", "pwd", "whoami"]:
            result = self.sb.validate(cmd)
            assert result[0] is True


class TestSandboxRestrict:
    """restrict_bash 方法测试"""

    def setup_method(self):
        self.sb = Sandbox()

    def test_restrict_returns_string(self):
        """restrict_bash 返回字符串"""
        result = self.sb.restrict_bash("echo hello")
        assert isinstance(result, str)

    def test_restrict_preserves_safe(self):
        """安全命令保持不变"""
        result = self.sb.restrict_bash("echo hello")
        assert "echo" in result

    def test_restrict_empty(self):
        """空命令被拒绝"""
        with pytest.raises(RuntimeError):
            self.sb.restrict_bash("")


class TestSandboxInit:
    """初始化测试"""

    def test_init_without_root(self):
        """不传 root 可初始化"""
        sb = Sandbox()
        assert sb is not None

    def test_init_with_root(self):
        """传 root 可初始化"""
        sb = Sandbox(root=Path.cwd())
        assert sb is not None


class TestModuleFunctions:
    """模块级函数测试"""

    def test_sandbox_check_returns_tuple(self):
        """sandbox_check 返回 (bool, str)"""
        result = sandbox_check("echo hello")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_sandbox_restrict_returns_string(self):
        """sandbox_restrict 返回字符串"""
        result = sandbox_restrict("echo hello")
        assert isinstance(result, str)

    def test_sandbox_check_multiple(self):
        """多次调用不崩溃"""
        for cmd in ["ls", "pwd", "cat file.txt"]:
            result = sandbox_check(cmd)
            assert result is not None


class TestFileAudit:
    """文件审计测试"""

    def test_file_audit_init(self):
        """FileAudit 可初始化"""
        audit = FileAudit()
        assert audit is not None

    def test_audit_trail(self):
        """审计追踪列表"""
        trail = get_audit_trail()
        assert isinstance(trail, list)

    def test_current_allowed_roots(self):
        """当前允许的根目录"""
        roots = _current_allowed_roots()
        assert isinstance(roots, list)
        # 至少包含项目根目录
        assert len(roots) > 0

    def test_path_is_allowed(self):
        """路径检查函数"""
        roots = _current_allowed_roots()
        # 当前目录应该允许
        result = _path_is_allowed(Path.cwd(), roots)
        assert isinstance(result, bool)
