"""Git workflow automation tools.

Extends basic git commands with full workflow:
- Branch management (create, switch, list, delete)
- Push/pull with remote
- PR creation and merge via gh CLI
- Diff and log with formatting
- Stash management
- Tag management
- Merge conflict detection
"""

import json
import subprocess

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "GIT_WORKFLOW_EXECUTOR_MAP",
    "GIT_WORKFLOW_TOOL_DEFS",
    "execute_git_branch",
    "execute_git_conflict_check",
    "execute_git_pr_create",
    "execute_git_pr_merge",
    "execute_git_pull",
    "execute_git_push",
    "execute_git_stash",
    "execute_git_tag",
    "execute_git_worktree",
    "git_add_commit",
    "git_diff",
    "git_log",
    "git_status",
]


def _run_git(args: list[str], cwd: str = "") -> dict:
    """Run a git command and return structured result."""
    cmd = ["git", *args]
    try:
        r = run_subprocess(cmd, cwd=cwd or None, timeout=30)
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip() if r.stdout else "",
            "stderr": r.stderr.strip() if r.stderr else "",
            "exit_code": r.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "error": "git not found"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "git command timed out"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"success": False, "error": str(e)}


def _run_gh(args: list[str], cwd: str = "") -> dict:
    """Run a gh CLI command."""
    cmd = ["gh", *args]
    try:
        r = run_subprocess(cmd, cwd=cwd or None, timeout=30)
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip() if r.stdout else "",
            "stderr": r.stderr.strip() if r.stderr else "",
            "exit_code": r.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "error": "gh CLI not found. Install from https://cli.github.com/"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"success": False, "error": str(e)}


# ======================================================================
# Tool executors
# ======================================================================


def execute_git_branch(name: str = "", action: str = "list", base: str = "") -> str:
    """Manage git branches.

    action: list, create, switch, delete, current
    """
    if action == "list":
        r = _run_git(["branch", "-a", "--format=%(refname:short) %(objectname:short) %(subject)"])
        if r["success"]:
            branches = [line for line in r["stdout"].split("\n") if line.strip()]
            return json.dumps({"branches": branches, "count": len(branches)}, ensure_ascii=False, indent=2)
        return json.dumps(r, ensure_ascii=False)

    if action == "create":
        if not name:
            return json.dumps({"error": "branch name required"})
        args = ["checkout", "-b", name]
        if base:
            args.append(base)
        r = _run_git(args)
        return json.dumps({"created": name, "base": base or "current", **r}, ensure_ascii=False)

    if action == "switch":
        if not name:
            return json.dumps({"error": "branch name required"})
        r = _run_git(["checkout", name])
        return json.dumps({"switched": name, **r}, ensure_ascii=False)

    if action == "delete":
        if not name:
            return json.dumps({"error": "branch name required"})
        r = _run_git(["branch", "-d", name])
        return json.dumps({"deleted": name, **r}, ensure_ascii=False)

    if action == "current":
        r = _run_git(["branch", "--show-current"])
        return json.dumps({"current_branch": r["stdout"] if r["success"] else ""}, ensure_ascii=False)

    return json.dumps({"error": f"unknown action: {action}"})


def execute_git_push(remote: str = "origin", branch: str = "", force: bool = False, force_with_lease: bool = False, tags: bool = False) -> str:
    """Push commits to remote.

    安全约束（P1-15）：force / force_with_lease 会重写远端历史，属于不可逆操作。
    走 list 形式的 subprocess 绕过了 sandbox 字符串检测，故在此
    执行器层面二次拦截：force 必须由调用方（ChatSession._dispatch_tool
    的高风险确认机制）显式确认后才传到这里；这里若直接收到 force=True，
    返回错误字符串而非执行。
    """
    if force or force_with_lease:
        return json.dumps(
            {
                "error": "force push 需要用户确认。请通过交互确认后再执行。",
                "needs_confirm": True,
                "tool": "git_push",
                "args": {"remote": remote, "branch": branch, "force": force or force_with_lease, "tags": tags},
            },
            ensure_ascii=False,
        )
    args = ["push", remote]
    if branch:
        args.append(branch)
    if tags:
        args.append("--tags")

    r = _run_git(args)
    return json.dumps(
        {
            "pushed": r["success"],
            "remote": remote,
            "branch": branch or "current",
            "output": r.get("stdout", "") or r.get("stderr", ""),
        },
        ensure_ascii=False,
    )


def execute_git_pull(remote: str = "origin", branch: str = "", rebase: bool = False) -> str:
    """Pull from remote."""
    args = ["pull", remote]
    if branch:
        args.append(branch)
    if rebase:
        args.append("--rebase")

    r = _run_git(args)
    return json.dumps(
        {
            "pulled": r["success"],
            "output": r.get("stdout", "") or r.get("stderr", ""),
        },
        ensure_ascii=False,
    )


def execute_git_pr_create(title: str = "", body: str = "", base: str = "", head: str = "", draft: bool = False) -> str:
    """Create a pull request via gh CLI."""
    args = ["pr", "create", "--fill"]
    if title:
        args.extend(["--title", title])
    if body:
        args.extend(["--body", body])
    if base:
        args.extend(["--base", base])
    if head:
        args.extend(["--head", head])
    if draft:
        args.append("--draft")

    r = _run_gh(args)
    return json.dumps(
        {
            "created": r["success"],
            "pr_url": r.get("stdout", "") if r["success"] else "",
            "error": r.get("stderr", "") if not r["success"] else "",
        },
        ensure_ascii=False,
    )


def execute_git_pr_merge(pr_number: int = 0, method: str = "squash", delete_branch: bool = True) -> str:
    """Merge a pull request via gh CLI.

    method: squash, merge, or rebase
    """
    if not pr_number:
        return json.dumps({"error": "pr_number required"})
    if method not in ("squash", "merge", "rebase"):
        return json.dumps({"error": f"invalid merge method: {method}. Use squash, merge, or rebase."})

    args = ["pr", "merge", str(pr_number), f"--{method}"]
    if delete_branch:
        args.append("--delete-branch")

    r = _run_gh(args)
    return json.dumps(
        {
            "merged": r["success"],
            "pr_number": pr_number,
            "method": method,
            "output": r.get("stdout", "") or r.get("stderr", ""),
        },
        ensure_ascii=False,
    )


def execute_git_stash(action: str = "list", message: str = "") -> str:
    """Manage git stash.

    action: list, push, pop, apply, drop, clear
    """
    if action == "list":
        r = _run_git(["stash", "list"])
        return json.dumps({"stashes": r["stdout"].split("\n") if r["stdout"] else [], **r}, ensure_ascii=False)
    if action == "push":
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        r = _run_git(args)
        return json.dumps({"stashed": r["success"], **r}, ensure_ascii=False)
    if action == "pop":
        r = _run_git(["stash", "pop"])
        return json.dumps({"popped": r["success"], **r}, ensure_ascii=False)
    if action == "apply":
        r = _run_git(["stash", "apply"])
        return json.dumps({"applied": r["success"], **r}, ensure_ascii=False)
    if action == "drop":
        r = _run_git(["stash", "drop"])
        return json.dumps({"dropped": r["success"], **r}, ensure_ascii=False)
    if action == "clear":
        r = _run_git(["stash", "clear"])
        return json.dumps({"cleared": r["success"], **r}, ensure_ascii=False)

    return json.dumps({"error": f"unknown action: {action}"})


def execute_git_conflict_check() -> str:
    """Check for merge conflicts in working tree."""
    r = _run_git(["diff", "--name-only", "--diff-filter=U"])
    if r["success"]:
        conflicts = [f for f in r["stdout"].split("\n") if f.strip()]
        return json.dumps(
            {
                "has_conflicts": len(conflicts) > 0,
                "conflicted_files": conflicts,
                "count": len(conflicts),
            },
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(r, ensure_ascii=False)


def execute_git_tag(name: str = "", action: str = "list", message: str = "") -> str:
    """Manage git tags.

    action: list, create, delete
    """
    if action == "list":
        r = _run_git(["tag", "-l", "--sort=-creatordate"])
        tags = r["stdout"].split("\n")[:20] if r["stdout"] else []
        return json.dumps({"tags": tags, **r}, ensure_ascii=False)
    if action == "create":
        if not name:
            return json.dumps({"error": "tag name required"})
        args = ["tag", name]
        if message:
            args.extend(["-a", "-m", message])
        r = _run_git(args)
        return json.dumps({"created": name, **r}, ensure_ascii=False)
    if action == "delete":
        if not name:
            return json.dumps({"error": "tag name required"})
        r = _run_git(["tag", "-d", name])
        return json.dumps({"deleted": name, **r}, ensure_ascii=False)

    return json.dumps({"error": f"unknown action: {action}"})


def execute_git_worktree(
    action: str = "list", path: str = "", branch: str = "", base: str = "", force: bool = False
) -> str:
    """Manage git worktrees.

    action: list, add, remove, prune
    - list: list all worktrees
    - add: create a new worktree at <path> on <branch> (created from <base> if specified)
    - remove: remove worktree at <path>
    - prune: prune deleted worktree directories
    """
    if action == "list":
        r = _run_git(["worktree", "list", "--porcelain"])
        if r["success"]:
            worktrees = []
            current = {}
            for line in r["stdout"].split("\n"):
                if not line.strip():
                    if current:
                        worktrees.append(current)
                        current = {}
                elif line.startswith("worktree "):
                    current["path"] = line[len("worktree ") :]
                elif line.startswith("HEAD "):
                    current["head"] = line[len("HEAD ") :]
                elif line.startswith("branch "):
                    current["branch"] = line[len("branch ") :]
                elif line == "bare":
                    current["bare"] = True
                elif line == "detached":
                    current["detached"] = True
            if current:
                worktrees.append(current)
            return json.dumps({"worktrees": worktrees, "count": len(worktrees)}, ensure_ascii=False, indent=2)
        return json.dumps(r, ensure_ascii=False)

    if action == "add":
        if not path:
            return json.dumps({"error": "path required for add"})
        args = ["worktree", "add"]
        if force:
            args.append("--force")
        if branch:
            args.extend(["-b", branch])
            if base:
                args.append(base)
            args.append(path)
        else:
            args.append(path)
        r = _run_git(args)
        return json.dumps(
            {
                "added": r["success"],
                "path": path,
                "branch": branch or "default",
                "base": base or "current",
                "output": r.get("stdout", "") or r.get("stderr", ""),
            },
            ensure_ascii=False,
        )

    if action == "remove":
        if not path:
            return json.dumps({"error": "path required for remove"})
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(path)
        r = _run_git(args)
        return json.dumps(
            {
                "removed": r["success"],
                "path": path,
                "output": r.get("stdout", "") or r.get("stderr", ""),
            },
            ensure_ascii=False,
        )

    if action == "prune":
        r = _run_git(["worktree", "prune"])
        return json.dumps({"pruned": r["success"], **r}, ensure_ascii=False)

    return json.dumps({"error": f"unknown action: {action}"})


# ======================================================================
# Tool definitions
# ======================================================================

GIT_WORKFLOW_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "Manage git branches: list all, create new, switch to, delete, or show current branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name (for create/switch/delete)"},
                    "action": {
                        "type": "string",
                        "description": "list, create, switch, delete, current (default: list)",
                    },
                    "base": {"type": "string", "description": "Base branch for create (default: current)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push commits to remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name (default: origin)"},
                    "branch": {"type": "string", "description": "Branch to push (default: current)"},
                    "force": {"type": "boolean", "description": "Force push (default: false)"},
                    "tags": {"type": "boolean", "description": "Push tags too (default: false)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_pull",
            "description": "Pull from remote repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "description": "Remote name (default: origin)"},
                    "branch": {"type": "string", "description": "Branch to pull (default: current)"},
                    "rebase": {"type": "boolean", "description": "Use rebase instead of merge (default: false)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_pr_create",
            "description": "Create a pull request on GitHub via gh CLI. Requires gh to be installed and authenticated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title (empty = use commit message)"},
                    "body": {"type": "string", "description": "PR description"},
                    "base": {"type": "string", "description": "Base branch (default: repo default)"},
                    "head": {"type": "string", "description": "Head branch (default: current)"},
                    "draft": {"type": "boolean", "description": "Create as draft PR (default: false)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_pr_merge",
            "description": "Merge a pull request on GitHub via gh CLI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer", "description": "PR number to merge"},
                    "method": {"type": "string", "description": "squash, merge, or rebase (default: squash)"},
                    "delete_branch": {"type": "boolean", "description": "Delete branch after merge (default: true)"},
                },
                "required": ["pr_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_stash",
            "description": "Manage git stash: list, push, pop, apply, drop, or clear stashed changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "list, push, pop, apply, drop, clear (default: list)"},
                    "message": {"type": "string", "description": "Stash message (for push)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_conflict_check",
            "description": "Check for merge conflicts in the working tree. Returns list of conflicted files.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_tag",
            "description": "Manage git tags: list, create annotated, or delete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tag name"},
                    "action": {"type": "string", "description": "list, create, delete (default: list)"},
                    "message": {"type": "string", "description": "Annotation message (for create)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_worktree",
            "description": "Manage git worktrees: list all, add a new isolated worktree, remove, or prune. Worktrees allow working on multiple branches simultaneously in separate directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "list, add, remove, prune (default: list)"},
                    "path": {
                        "type": "string",
                        "description": "Directory path for the worktree (required for add/remove)",
                    },
                    "branch": {"type": "string", "description": "New branch name to create in this worktree (for add)"},
                    "base": {
                        "type": "string",
                        "description": "Base branch/commit for new worktree (for add, default: HEAD)",
                    },
                    "force": {"type": "boolean", "description": "Force operation even if exists (default: false)"},
                },
            },
        },
    },
]

GIT_WORKFLOW_EXECUTOR_MAP = {
    "git_branch": lambda **kw: execute_git_branch(
        name=kw.get("name", ""), action=kw.get("action", "list"), base=kw.get("base", "")
    ),
    "git_push": lambda **kw: execute_git_push(
        remote=kw.get("remote", "origin"),
        branch=kw.get("branch", ""),
        force=kw.get("force", False),
        tags=kw.get("tags", False),
    ),
    "git_pull": lambda **kw: execute_git_pull(
        remote=kw.get("remote", "origin"), branch=kw.get("branch", ""), rebase=kw.get("rebase", False)
    ),
    "git_pr_create": lambda **kw: execute_git_pr_create(
        title=kw.get("title", ""),
        body=kw.get("body", ""),
        base=kw.get("base", ""),
        head=kw.get("head", ""),
        draft=kw.get("draft", False),
    ),
    "git_pr_merge": lambda **kw: execute_git_pr_merge(
        pr_number=kw.get("pr_number", 0), method=kw.get("method", "squash"), delete_branch=kw.get("delete_branch", True)
    ),
    "git_stash": lambda **kw: execute_git_stash(action=kw.get("action", "list"), message=kw.get("message", "")),
    "git_conflict_check": lambda **kw: execute_git_conflict_check(),
    "git_tag": lambda **kw: execute_git_tag(
        name=kw.get("name", ""), action=kw.get("action", "list"), message=kw.get("message", "")
    ),
    "git_worktree": lambda **kw: execute_git_worktree(
        action=kw.get("action", "list"),
        path=kw.get("path", ""),
        branch=kw.get("branch", ""),
        base=kw.get("base", ""),
        force=kw.get("force", False),
    ),
}

# ════════════════════════════════════════════════════════════
#  安全 git 快捷包装 — 供 tools.json python 类型使用
#  全部用 list 传参，无 shell=True
# ════════════════════════════════════════════════════════════


def git_status() -> str:
    """git status --short 的安全包装。"""

    r = run_subprocess(["git", "status", "--short"], timeout=10)
    return r.stdout.strip() or r.stderr.strip() or "not a git repo"


def git_diff() -> str:
    """git diff --stat 的安全包装。"""

    r = run_subprocess(["git", "diff", "--stat"], timeout=10)
    return r.stdout.strip() or r.stderr.strip() or "no changes"


def git_log() -> str:
    """git log --oneline -10 的安全包装。"""

    r = run_subprocess(["git", "log", "--oneline", "-10"], timeout=10)
    return r.stdout.strip() or r.stderr.strip() or "not a git repo"


def git_add_commit(message: str) -> str:
    """git add -A && git commit -m 的安全包装。用列表传参防注入。"""

    # Step 1: git add -A
    r1 = run_subprocess(["git", "add", "-A"], timeout=30)
    if r1.returncode != 0:
        return f"[错误] git add 失败: {r1.stderr.strip()}"
    # Step 2: git commit -m (message 作列表元素，不会被 shell 解析)
    r2 = run_subprocess(["git", "commit", "-m", message], timeout=30)
    if r2.returncode == 0:
        return r2.stdout.strip() or "已提交"
    if "nothing to commit" in (r2.stdout + r2.stderr):
        return "no changes to commit"
    return f"[错误] commit 失败: {r2.stderr.strip() or r2.stdout.strip()}"
