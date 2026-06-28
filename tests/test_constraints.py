"""Tests for core/constraints.py — security, disk, tool group definitions."""

import pytest
from core.constraints import (
    DANGEROUS_ARGS_PATTERN,
    HIGH_RISK_TOOLS,
    LONG_RUNNING_TOOLS,
    PROJECT_SKIP_DIRS,
    WRITE_TOOLS,
    is_tool_high_risk,
)


class TestHighRiskTools:
    def test_frozenset_immutable(self):
        assert isinstance(HIGH_RISK_TOOLS, frozenset)

    def test_contains_git_operations(self):
        assert "git_push" in HIGH_RISK_TOOLS
        assert "git_add_commit" in HIGH_RISK_TOOLS

    def test_contains_destructive_github(self):
        assert "git_pr_merge" in HIGH_RISK_TOOLS
        assert "git_tag" in HIGH_RISK_TOOLS


class TestDangerousArgsPattern:
    def test_matches_rm_rf(self):
        assert DANGEROUS_ARGS_PATTERN.search("rm -rf /")

    def test_matches_rm_with_options(self):
        assert DANGEROUS_ARGS_PATTERN.search("rm -fr /tmp/stuff")

    def test_matches_del_force(self):
        assert DANGEROUS_ARGS_PATTERN.search("del /f /q C:\\windows")

    def test_matches_drop_table(self):
        assert DANGEROUS_ARGS_PATTERN.search("drop table users")

    def test_matches_drop_database(self):
        assert DANGEROUS_ARGS_PATTERN.search("drop database production")

    def test_matches_truncate(self):
        assert DANGEROUS_ARGS_PATTERN.search("truncate table logs")

    def test_matches_format_drive(self):
        assert DANGEROUS_ARGS_PATTERN.search("format C:")

    def test_no_match_safe_command(self):
        assert not DANGEROUS_ARGS_PATTERN.search("ls -la")

    def test_matches_rm_in_any_context(self):
        assert DANGEROUS_ARGS_PATTERN.search("echo 'rm -rf'")  # pattern matches regardless of context


class TestIsToolHighRisk:
    def test_named_high_risk_tool(self):
        assert is_tool_high_risk("git_push", {}) is True
        assert is_tool_high_risk("git_pr_merge", {}) is True

    def test_safe_tool_false(self):
        assert is_tool_high_risk("read_file", {}) is False
        assert is_tool_high_risk("web_fetch", {}) is False

    def test_github_write_default_branch_no_branch_arg(self):
        assert is_tool_high_risk("github_write_file", {}) is True

    def test_github_write_default_branch_empty_branch(self):
        assert is_tool_high_risk("github_write_file", {"branch": ""}) is True

    def test_github_write_with_branch_is_safe(self):
        assert is_tool_high_risk("github_write_file", {"branch": "feature/x"}) is False

    def test_git_push_force(self):
        assert is_tool_high_risk("git_push", {"force": True}) is True

    def test_git_push_always_high_risk(self):
        assert is_tool_high_risk("git_push", {"force": False}) is True  # git_push is always in HIGH_RISK_TOOLS

    def test_git_worktree_remove_force(self):
        assert is_tool_high_risk("git_worktree", {"action": "remove", "force": True}) is True

    def test_git_worktree_remove_no_force_safe(self):
        assert is_tool_high_risk("git_worktree", {"action": "remove", "force": False}) is False

    def test_git_worktree_add_safe(self):
        assert is_tool_high_risk("git_worktree", {"action": "add"}) is False

    def test_git_branch_delete(self):
        assert is_tool_high_risk("git_branch", {"action": "delete"}) is True

    def test_git_branch_create_safe(self):
        assert is_tool_high_risk("git_branch", {"action": "create"}) is False

    def test_run_bash_dangerous_command(self):
        assert is_tool_high_risk("run_bash", {"command": "rm -rf /tmp"}) is True

    def test_run_bash_safe_command(self):
        assert is_tool_high_risk("run_bash", {"command": "ls -la"}) is False

    def test_empty_args_dict(self):
        assert is_tool_high_risk("read_file", {}) is False

    def test_nonexistent_tool_safe(self):
        assert is_tool_high_risk("nonexistent_tool", {}) is False


class TestProjectSkipDirs:
    def test_frozenset_immutable(self):
        assert isinstance(PROJECT_SKIP_DIRS, frozenset)

    def test_contains_git(self):
        assert ".git" in PROJECT_SKIP_DIRS

    def test_contains_pycache(self):
        assert "__pycache__" in PROJECT_SKIP_DIRS

    def test_contains_output(self):
        assert "output" in PROJECT_SKIP_DIRS

    def test_contains_node_modules(self):
        assert "node_modules" in PROJECT_SKIP_DIRS


class TestWriteTools:
    def test_contains_write_file(self):
        assert "write_file" in WRITE_TOOLS

    def test_contains_edit_file(self):
        assert "edit_file" in WRITE_TOOLS

    def test_contains_run_bash(self):
        assert "run_bash" in WRITE_TOOLS

    def test_no_read_tools(self):
        assert "read_file" not in WRITE_TOOLS


class TestLongRunningTools:
    def test_contains_web_fetch(self):
        assert "web_fetch" in LONG_RUNNING_TOOLS

    def test_contains_run_bash(self):
        assert "run_bash" in LONG_RUNNING_TOOLS

    def test_no_fast_tools(self):
        assert "read_file" not in LONG_RUNNING_TOOLS
