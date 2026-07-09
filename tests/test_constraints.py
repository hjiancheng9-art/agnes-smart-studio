"""Tests for core/constraints.py — 工程约束（唯一真源）"""

from core.constraints import (
    CONFIRMABLE_TOOLS,
    DANGEROUS_ARGS_PATTERN,
    HIGH_RISK_TOOLS,
    LONG_RUNNING_TOOLS,
    PROJECT_SKIP_DIRS,
    READONLY_TOOLS,
    WRITE_TOOLS,
)


class TestRiskTools:
    """高危工具配置测试"""

    def test_high_risk_is_frozenset(self):
        assert isinstance(HIGH_RISK_TOOLS, frozenset)

    def test_high_risk_non_empty(self):
        assert len(HIGH_RISK_TOOLS) > 0

    def test_high_risk_contains_git_ops(self):
        assert any("git" in t for t in HIGH_RISK_TOOLS)


class TestDangerousArgs:
    """危险参数模式测试"""

    def test_pattern_exists(self):
        assert DANGEROUS_ARGS_PATTERN is not None


class TestWriteTools:
    """写操作工具集测试"""

    def test_write_tools_is_frozenset(self):
        assert isinstance(WRITE_TOOLS, frozenset)

    def test_write_tools_contains_editors(self):
        assert "write_file" in WRITE_TOOLS
        assert "edit_file" in WRITE_TOOLS
        assert "run_bash" in WRITE_TOOLS

    def test_read_tools_not_in_write(self):
        for tool in ["read_file", "search_files", "list_files"]:
            assert tool not in WRITE_TOOLS


class TestReadonlyTools:
    """只读工具集测试"""

    def test_readonly_is_frozenset(self):
        assert isinstance(READONLY_TOOLS, frozenset)

    def test_readonly_contains_readers(self):
        assert "read_file" in READONLY_TOOLS
        assert "list_files" in READONLY_TOOLS

    def test_readonly_not_contains_writers(self):
        assert "write_file" not in READONLY_TOOLS
        assert "run_bash" not in READONLY_TOOLS

    def test_readonly_contains_many_tools(self):
        assert len(READONLY_TOOLS) > 10


class TestWriteReadonlyDisjoint:
    """读写工具集不重叠测试"""

    def test_disjoint(self):
        assert WRITE_TOOLS.isdisjoint(READONLY_TOOLS)


class TestLongRunningTools:
    """长时间运行工具集测试"""

    def test_long_running_is_frozenset(self):
        assert isinstance(LONG_RUNNING_TOOLS, frozenset)

    def test_long_running_non_empty(self):
        assert len(LONG_RUNNING_TOOLS) > 0


class TestConfirmableTools:
    """需确认工具集测试"""

    def test_confirmable_is_frozenset(self):
        assert isinstance(CONFIRMABLE_TOOLS, frozenset)

    def test_confirmable_non_empty(self):
        assert len(CONFIRMABLE_TOOLS) > 0


class TestSkipDirs:
    """跳过目录配置测试"""

    def test_skip_dirs_is_frozenset(self):
        assert isinstance(PROJECT_SKIP_DIRS, frozenset)

    def test_skips_node_modules(self):
        assert "node_modules" in PROJECT_SKIP_DIRS

    def test_skips_pycache(self):
        assert "__pycache__" in PROJECT_SKIP_DIRS

    def test_skips_git(self):
        assert ".git" in PROJECT_SKIP_DIRS
