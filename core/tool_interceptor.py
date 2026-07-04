"""PreToolUse safety interceptor — block dangerous commands before execution.

Mirrors Claude Code's block_dangerous.py hook: intercepts destructive bash commands
and sensitive file writes before they reach the shell.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Patterns that are ALWAYS blocked
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "rm -rf / is blocked"),
    (r"rm\s+-rf\s+~[/\s]", "rm -rf ~ is blocked"),
    (r">\s*/dev/sda", "direct disk write is blocked"),
    (r"mkfs\.", "filesystem format is blocked"),
    (r"dd\s+if=.*of=/dev/", "dd to block device is blocked"),
    (r"chmod\s+777\s+/", "chmod 777 on root is blocked"),
    (r"git\s+push\s+--force.*main", "force push to main is blocked"),
    (r"git\s+push\s+--force.*master", "force push to master is blocked"),
    (r"git\s+push\s+-f\s+origin\s+main", "force push to main is blocked"),
]

# Patterns that trigger a WARNING but are not blocked
_WARNED_PATTERNS: list[tuple[str, str]] = [
    (r"pip\s+uninstall", "pip uninstall can break dependencies"),
    (r"npm\s+uninstall", "npm uninstall can break dependencies"),
    (r"git\s+reset\s+--hard", "git reset --hard discards uncommitted changes"),
    (r"git\s+clean\s+-[fdx]{1,3}", "git clean deletes untracked files"),
]

# Files that should NEVER be written to
_PROTECTED_FILES: set[str] = {
    ".env", ".env.local", ".env.production",
    "credentials.json", "service-account.json",
    "id_rsa", "id_ed25519", "*.pem",
}


def intercept_tool(tool_name: str, args: dict) -> tuple[bool, str]:
    """Check a tool call before execution. Returns (allowed, reason)."""
    # Bash command interception
    if tool_name == "run_bash":
        cmd = args.get("command", args.get("cmd", ""))
        if not cmd:
            return True, ""

        # Check blocked patterns
        for pattern, reason in _BLOCKED_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False, f"BLOCKED: {reason}"

        # Check warned patterns
        for pattern, reason in _WARNED_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, f"WARNING: {reason}"

    # File write interception
    if tool_name in ("write_file", "edit_file", "patch_file"):
        path = args.get("file_path", args.get("target", args.get("path", "")))
        if path:
            fname = Path(path).name
            for protected in _PROTECTED_FILES:
                if fname == protected or (protected.startswith("*") and fname.endswith(protected[1:])):
                    return False, f"BLOCKED: cannot write to protected file: {fname}"

    return True, ""


# ── Hook integration ───────────────────────────────────

def register_tool_interceptor():
    """Register the interceptor as a PRE_TOOL_USE hook."""
    try:
        from core.hooks import HookType, register_hook

        def _hook(tool_name: str, args: dict, **kw):
            # 1. 安全拦截（危险命令/受保护文件）
            allowed, reason = intercept_tool(tool_name, args)
            if not allowed:
                return reason

            # 2. 方法论合规检查
            try:
                from core.methodology import get_methodology_state, methodology_pre_check

                state = get_methodology_state()
                allowed, reason = methodology_pre_check(tool_name, args, state)
                if not allowed:
                    return reason

                # D 级加固：所有写操作 + git 操作均需确认
                from core.constraints import WRITE_TOOLS
                from core.methodology import TaskLevel

                if (state.task_level == TaskLevel.D
                        and (tool_name in WRITE_TOOLS or tool_name.startswith("git_"))
                        and not state.plan_exists):
                    return f"D 级任务: 未确认 Plan，{tool_name} 被拦截"
            except ImportError:
                pass

            return None  # None means proceed

        register_hook(HookType.PRE_TOOL_USE, _hook, priority=100)
    except ImportError:
        pass
