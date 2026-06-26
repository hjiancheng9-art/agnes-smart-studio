"""Unit tests for core/git_workflow.py — Git 自动化工作流分发器。

git_workflow.py 的所有操作都通过 _run() 调用 git 子进程。
通过 monkeypatch _run 为假实现，断言：
- 传给 git 的参数是否正确（动作分发）
- 返回值的格式化逻辑（成功/失败消息）
- 安全契约（safe_autocommit 在 clean 时不 commit）

不触达真实 git 仓库。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.git_workflow import GitWorkflow, git_autocommit, git_snapshot, git_status

# ── 辅助：构造 mock _run ──────────────────────────────────────────


class FakeRun:
    """可编程的 _run 替身：按预设返回 (code, out, err)，并记录调用参数。"""

    def __init__(self, returns=None, default=(0, "", "")):
        # returns: dict[args_tuple] = (code, out, err)
        self.returns = returns or {}
        self.default = default
        self.calls = []  # 记录每次调用的 args

    def __call__(self, *args, capture=True):
        self.calls.append(args)
        # 用 args 的首个关键词作为查找键（status/add/commit/...）
        key = args[0] if args else ""
        if key in self.returns:
            return self.returns[key]
        return self.default


@pytest.fixture
def wf():
    """一个 root 指向 tmp 的 GitWorkflow 实例（_run 由各测试自行 patch）。"""
    return GitWorkflow(root=Path("."))


# ── status / diff ─────────────────────────────────────────────────


def test_status_returns_stdout_when_dirty(wf, monkeypatch):
    """status 有输出时返回 stdout。"""
    fake = FakeRun(returns={"status": (0, " M file.py", "")})
    monkeypatch.setattr(wf, "_run", fake)
    assert wf.status() == " M file.py"
    assert fake.calls[0] == ("status", "--short")


def test_status_returns_clean_marker_when_empty(wf, monkeypatch):
    """status 无输出时返回 '(clean)' 标记。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    assert wf.status() == "(clean)"


def test_diff_uses_stat_flag(wf, monkeypatch):
    """diff 应调用 git diff --stat。"""
    fake = FakeRun(default=(0, "1 file changed", ""))
    monkeypatch.setattr(wf, "_run", fake)
    assert wf.diff() == "1 file changed"
    assert fake.calls[0] == ("diff", "--stat")


def test_diff_empty_returns_no_changes_marker(wf, monkeypatch):
    """diff 无输出时返回 '(no changes)'。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    assert wf.diff() == "(no changes)"


# ── stage_all / commit ────────────────────────────────────────────


def test_stage_all_success_message(wf, monkeypatch):
    """stage_all 成功返回 'all changes staged'。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    assert wf.stage_all() == "all changes staged"
    assert fake.calls[0] == ("add", "-A")


def test_stage_all_failure_returns_error(wf, monkeypatch):
    """stage_all 失败时返回 'error: <stderr>'。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(1, "", "permission denied")))
    result = wf.stage_all()
    assert "error" in result
    assert "permission denied" in result


def test_commit_returns_stdout(wf, monkeypatch):
    """commit 成功返回 git stdout。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "[main abc1234] msg", "")))
    assert wf.commit("msg") == "[main abc1234] msg"


def test_commit_failure_returns_stderr(wf, monkeypatch):
    """commit 失败时返回 stderr。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(1, "", "nothing to commit")))
    assert "nothing to commit" in wf.commit("msg")


# ── create_branch ─────────────────────────────────────────────────


def test_create_branch_sanitizes_name(wf, monkeypatch):
    """分支名应小写 + 空格转连字符 + 截断到 50 字符。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    wf.create_branch("Feature Add Login Page")
    args = fake.calls[0]
    assert args == ("checkout", "-b", "feature-add-login-page")


def test_create_branch_truncates_long_name(wf, monkeypatch):
    """超长分支名应截断到 50 字符。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    long_name = "a" * 80
    wf.create_branch(long_name)
    safe = fake.calls[0][2]
    assert len(safe) == 50


def test_create_branch_success_message(wf, monkeypatch):
    """创建成功返回含分支名的消息。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    result = wf.create_branch("newbranch")
    assert "newbranch" in result
    assert "created" in result


def test_create_branch_failure_returns_error(wf, monkeypatch):
    """分支已存在等失败时返回 stderr。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(1, "", "already exists")))
    assert "already exists" in wf.create_branch("dup")


# ── current_branch / log ──────────────────────────────────────────


def test_current_branch_returns_name(wf, monkeypatch):
    """current_branch 返回 git branch --show-current 的输出。"""
    fake = FakeRun(default=(0, "main", ""))
    monkeypatch.setattr(wf, "_run", fake)
    assert wf.current_branch() == "main"
    assert fake.calls[0] == ("branch", "--show-current")


def test_current_branch_empty_returns_unknown(wf, monkeypatch):
    """空输出（detached HEAD 等）返回 'unknown'。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    assert wf.current_branch() == "unknown"


def test_log_passes_n_and_oneline(wf, monkeypatch):
    """log 应传 -n --oneline --decorate。"""
    fake = FakeRun(default=(0, "abc1234 msg", ""))
    monkeypatch.setattr(wf, "_run", fake)
    result = wf.log(3)
    assert "abc1234" in result
    args = fake.calls[0]
    assert args[0] == "log"
    assert "-3" in args
    assert "--oneline" in args
    assert "--decorate" in args


def test_log_empty_returns_no_commits_marker(wf, monkeypatch):
    """空 log 返回 '(no commits)'。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    assert wf.log() == "(no commits)"


# ── safe_autocommit ───────────────────────────────────────────────


def test_safe_autocommit_skips_when_clean(wf, monkeypatch):
    """工作区 clean 时不应 commit（返回 committed=False）。"""
    fake = FakeRun(
        returns={
            "add": (0, "", ""),
            "status": (0, "", ""),  # clean
            "commit": (0, "[main x] msg", ""),
        }
    )
    monkeypatch.setattr(wf, "_run", fake)
    result = wf.safe_autocommit("auto save")
    assert result["committed"] is False
    assert "nothing to commit" in result["message"]
    # 不应调用 commit
    assert not any(c[0] == "commit" for c in fake.calls)


def test_safe_autocommit_commits_when_dirty(wf, monkeypatch):
    """工作区有改动时应 commit 并返回分支信息。"""
    fake = FakeRun(
        returns={
            "add": (0, "", ""),
            "status": (0, " M file.py", ""),
            "commit": (0, "[main abc1234] auto save", ""),
            "branch": (0, "main", ""),
        }
    )
    monkeypatch.setattr(wf, "_run", fake)
    result = wf.safe_autocommit("auto save")
    assert result["committed"] is True
    assert result["branch"] == "main"
    assert result["message"] == "auto save"
    assert "abc1234" in result["git_output"]


def test_safe_autocommit_never_pushes(wf, monkeypatch):
    """安全契约：safe_autocommit 永远不应触发 push。"""
    fake = FakeRun(
        returns={
            "add": (0, "", ""),
            "status": (0, " M f.py", ""),
            "commit": (0, "ok", ""),
            "branch": (0, "main", ""),
        }
    )
    monkeypatch.setattr(wf, "_run", fake)
    wf.safe_autocommit("msg")
    assert not any("push" in c for c in fake.calls)


# ── snapshot / restore_snapshot ───────────────────────────────────


def test_snapshot_default_label_has_auto_prefix(wf, monkeypatch):
    """不传 label 时应生成 'auto-<timestamp>' 标签。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    wf.snapshot()
    args = fake.calls[0]
    assert args[0] == "stash"
    assert args[1] == "push"
    msg = args[3]  # -m <label>
    assert msg.startswith("auto-")


def test_snapshot_explicit_label(wf, monkeypatch):
    """显式 label 应直接用于 stash message。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    wf.snapshot("before-refactor")
    assert fake.calls[0][3] == "before-refactor"


def test_snapshot_success_message(wf, monkeypatch):
    """成功时返回含 label 的消息。"""
    monkeypatch.setattr(wf, "_run", FakeRun(default=(0, "", "")))
    assert "saved" in wf.snapshot("mylabel")


def test_restore_snapshot_no_label_pops_latest(wf, monkeypatch):
    """不传 label 时执行 stash pop（最新）。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(wf, "_run", fake)
    result = wf.restore_snapshot()
    assert "restored" in result
    assert fake.calls[0] == ("stash", "pop")


def test_restore_snapshot_with_label_searches_list(wf, monkeypatch):
    """传 label 时先 stash list 找匹配，再 pop 对应索引。"""
    fake = FakeRun(
        returns={
            "stash": (0, "stash@{0}: On main: mylabel", ""),  # list 输出
        },
        default=(0, "", ""),
    )
    monkeypatch.setattr(wf, "_run", fake)
    result = wf.restore_snapshot("mylabel")
    # 第二次调用应是 stash pop stash@{0}
    assert fake.calls[1] == ("stash", "pop", "stash@{0}")
    assert "stash@{0}" in result


def test_restore_snapshot_label_not_found(wf, monkeypatch):
    """label 在 stash list 中找不到时返回 'not found'。"""
    monkeypatch.setattr(
        wf,
        "_run",
        FakeRun(
            returns={
                "stash": (0, "stash@{0}: other-label", ""),
            }
        ),
    )
    result = wf.restore_snapshot("mylabel")
    assert "not found" in result


# ── 模块级便捷函数 ────────────────────────────────────────────────


def test_git_status_module_function_returns_string(monkeypatch):
    """git_status() 模块级函数应返回 str。"""
    fake = FakeRun(default=(0, " M x.py", ""))
    monkeypatch.setattr(GitWorkflow, "_run", fake)
    assert isinstance(git_status(), str)


def test_git_autocommit_module_function_returns_dict(monkeypatch):
    """git_autocommit() 模块级函数应返回 dict。"""
    fake = FakeRun(returns={"status": (0, "", "")})  # clean
    monkeypatch.setattr(GitWorkflow, "_run", fake)
    result = git_autocommit("msg")
    assert isinstance(result, dict)
    assert result["committed"] is False


def test_git_snapshot_module_function_returns_string(monkeypatch):
    """git_snapshot() 模块级函数应返回 str。"""
    fake = FakeRun(default=(0, "", ""))
    monkeypatch.setattr(GitWorkflow, "_run", fake)
    assert isinstance(git_snapshot("lbl"), str)
