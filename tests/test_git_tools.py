"""Tests for core/git_tools.py — execute_git_pull, execute_git_stash, execute_git_conflict_check.

Follows test_git_workflow.py pattern: monkeypatch _run_git to avoid real git calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.git_tools import (
    execute_git_conflict_check,
    execute_git_pull,
    execute_git_push,
    execute_git_stash,
)

# ── 辅助：可编程 mock _run_git ──────────────────────────────────────────


class FakeRunGit:
    """模拟 _run_git：按预设返回 dict，记录每次调用参数。"""

    def __init__(self, returns=None, default=None):
        self.returns = returns or {}  # key: args_tuple -> dict
        self.default = default or {"success": True, "stdout": "", "stderr": "", "exit_code": 0}
        self.calls = []

    def __call__(self, args, cwd=""):
        self.calls.append((args, cwd))
        key = tuple(args)
        if key in self.returns:
            return self.returns[key]
        return dict(self.default)


# ── execute_git_pull ─────────────────────────────────────────────────────


class TestGitPull:
    """execute_git_pull 的参数拼接与返回值格式。"""

    def test_pull_default_remote_branch(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_pull())
        assert result["pulled"] is True
        assert fake.calls[0][0] == ["pull", "origin"]

    def test_pull_custom_remote(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        execute_git_pull(remote="upstream")
        assert fake.calls[0][0] == ["pull", "upstream"]

    def test_pull_with_branch(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        execute_git_pull(remote="origin", branch="main")
        assert fake.calls[0][0] == ["pull", "origin", "main"]

    def test_pull_with_rebase(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        execute_git_pull(rebase=True)
        assert fake.calls[0][0] == ["pull", "origin", "--rebase"]

    def test_pull_with_branch_and_rebase(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        execute_git_pull(remote="upstream", branch="dev", rebase=True)
        assert fake.calls[0][0] == ["pull", "upstream", "dev", "--rebase"]

    def test_pull_failure(self, monkeypatch):
        fake = FakeRunGit(default={"success": False, "stdout": "", "stderr": "connection refused", "exit_code": 128})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_pull())
        assert result["pulled"] is False
        assert "connection refused" in result["output"]

    def test_pull_output_from_stdout(self, monkeypatch):
        fake = FakeRunGit(default={"success": True, "stdout": "Already up to date.", "stderr": "", "exit_code": 0})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_pull())
        assert "Already up to date" in result["output"]


# ── execute_git_stash ────────────────────────────────────────────────────


class TestGitStash:
    """execute_git_stash 的动作分发与返回格式。"""

    def test_stash_list(self, monkeypatch):
        fake = FakeRunGit(
            default={
                "success": True,
                "stdout": "stash@{0}: WIP on main: abc1234 fix bug\nstash@{1}: WIP on dev: def5678 wip",
                "stderr": "",
                "exit_code": 0,
            }
        )
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="list"))
        assert len(result["stashes"]) == 2
        assert "fix bug" in result["stashes"][0]
        assert fake.calls[0][0] == ["stash", "list"]

    def test_stash_push_default(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="push"))
        assert result["stashed"] is True
        assert fake.calls[0][0] == ["stash", "push"]

    def test_stash_push_with_message(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="push", message="before refactor"))
        assert result["stashed"] is True
        assert fake.calls[0][0] == ["stash", "push", "-m", "before refactor"]

    def test_stash_pop(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="pop"))
        assert result["popped"] is True
        assert fake.calls[0][0] == ["stash", "pop"]

    def test_stash_apply(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="apply"))
        assert result["applied"] is True
        assert fake.calls[0][0] == ["stash", "apply"]

    def test_stash_drop(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="drop"))
        assert result["dropped"] is True
        assert fake.calls[0][0] == ["stash", "drop"]

    def test_stash_clear(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="clear"))
        assert result["cleared"] is True
        assert fake.calls[0][0] == ["stash", "clear"]

    def test_stash_unknown_action(self, monkeypatch):
        result = json.loads(execute_git_stash(action="nonexistent"))
        assert "unknown action" in result.get("error", "")

    def test_stash_pop_failure(self, monkeypatch):
        fake = FakeRunGit(default={"success": False, "stdout": "", "stderr": "No stash found.", "exit_code": 1})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash(action="pop"))
        assert result["popped"] is False
        assert "No stash found" in result.get("stderr", "")

    def test_stash_default_action_is_list(self, monkeypatch):
        """不传 action 时默认应是 list。"""
        fake = FakeRunGit(default={"success": True, "stdout": "", "stderr": "", "exit_code": 0})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_stash())
        # 默认 action="list"，应走 stash list 分支
        assert fake.calls[0][0] == ["stash", "list"]
        assert "stashes" in result


# ── execute_git_conflict_check ───────────────────────────────────────────


class TestGitConflictCheck:
    """execute_git_conflict_check 的冲突检测与返回格式。"""

    def test_no_conflicts(self, monkeypatch):
        fake = FakeRunGit(default={"success": True, "stdout": "", "stderr": "", "exit_code": 0})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_conflict_check())
        assert result["has_conflicts"] is False
        assert result["count"] == 0
        assert result["conflicted_files"] == []

    def test_with_conflicts(self, monkeypatch):
        fake = FakeRunGit(
            default={
                "success": True,
                "stdout": "src/main.py\ntests/test_main.py",
                "stderr": "",
                "exit_code": 0,
            }
        )
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_conflict_check())
        assert result["has_conflicts"] is True
        assert result["count"] == 2
        assert "src/main.py" in result["conflicted_files"]
        assert "tests/test_main.py" in result["conflicted_files"]

    def test_git_command_failure_handles_gracefully(self, monkeypatch):
        """git 命令失败（非零 exit_code）时应返回原始错误 dict，不崩溃。"""
        fake = FakeRunGit(default={"success": False, "stdout": "", "stderr": "not a git repo", "exit_code": 128})
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_conflict_check())
        # 失败时直接返回 _run_git 的原始 dict
        assert result["success"] is False
        assert "not a git repo" in result.get("stderr", "")

    def test_uses_diff_filter_U_flag(self, monkeypatch):
        """应调用 git diff --name-only --diff-filter=U（U = Unmerged）。"""
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        execute_git_conflict_check()
        assert fake.calls[0][0] == ["diff", "--name-only", "--diff-filter=U"]

    def test_blank_lines_filtered_out(self, monkeypatch):
        """输出中的空白行应被过滤掉，不计入冲突数。"""
        fake = FakeRunGit(
            default={
                "success": True,
                "stdout": "file_a.py\n\nfile_b.py\n   \n",
                "stderr": "",
                "exit_code": 0,
            }
        )
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_conflict_check())
        assert result["count"] == 2
        assert result["conflicted_files"] == ["file_a.py", "file_b.py"]


# ── execute_git_push 安全契约 ───────────────────────────────────────────


class TestGitPushSafety:
    """execute_git_push 的 force 参数二次拦截。"""

    def test_push_force_is_blocked_by_executor_level_gate(self, monkeypatch):
        """force=True 且无显式确认时，执行器应拒绝。"""
        # execute_git_push 内部检查 force 是否被显式确认——这里直接传 True 应被拦截
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_push(force=True))
        # 安全门应拒绝 force
        assert result.get("pushed") is False or "确认" in str(result)

    def test_push_normal_succeeds(self, monkeypatch):
        fake = FakeRunGit()
        monkeypatch.setattr("core.git_tools._run_git", fake)
        result = json.loads(execute_git_push())
        assert result.get("pushed") is True
