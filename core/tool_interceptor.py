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
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "*.pem",
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


# ── CDP ChatGPT 门控 ──────────────────────────────────


def _gate_cdp_chatgpt(args: dict) -> tuple[bool, str]:
    """CDP ChatGPT 调用前检查。返回 (blocked, reason)。"""
    question = (
        args.get("question")
        or args.get("text")
        or args.get("prompt")
        or args.get("message")
        or args.get("query")
        or args.get("input")
        or ""
    )

    # 1. 空/太短/纯重复 → 拦截
    q_str = str(question).strip()
    if not q_str or len(q_str) < 15:
        return True, "CDP ChatGPT: 问题太短，DeepSeek 自己能答"
    if len(set(q_str)) < 5:  # 纯重复字符
        return True, "CDP ChatGPT: 无效输入"

    # 2. 琐碎问题 → 拦截
    trivial_patterns = [
        "你好",
        "hello",
        "hi",
        "谢谢",
        "thanks",
        "ok",
        "好的",
        "是什么",
        "什么意思",
        "怎么用",
        "几点",
        "今天.*日期",
        "现在.*时间",
        "什么是",
        "解释一下",
    ]
    import re

    q_lower = str(question).lower().strip()
    for pat in trivial_patterns:
        if re.search(pat, q_lower) and len(q_lower) < 60:
            return True, "CDP ChatGPT: 简单问题 DeepSeek 自己能答"

    # 3. 代码/文件操作 → 拦截（DeepSeek 更擅长）
    code_patterns = [
        r"(写|改|修|加|删|实现|重构).{0,10}(代码|函数|文件|模块|类)",
        r"(bug|error|报错|出错|异常|崩溃)",
        r"(运行|执行|测试|部署|安装|配置)",
        r"(read_file|write_file|edit_file|search_files|git_)",
    ]
    for pat in code_patterns:
        if re.search(pat, q_lower):
            return True, "CDP ChatGPT: 代码操作 DeepSeek 自己更擅长，直接用工具"

    # 4. 浏览器健康预检（使用公开 API，不访问私有状态）
    try:
        from core.cdp_browser import is_connected

        if not is_connected():
            pass  # browser 未连接，但不拦截 — 让调用方自行决定
    except (ImportError, RuntimeError):
        pass

    return False, ""


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

            # 1.5 CDP ChatGPT 门控：避免无意义调用
            if tool_name == "cdp_ask_chatgpt":
                blocked, reason = _gate_cdp_chatgpt(args)
                if blocked:
                    return reason

            # 2. 方法论合规检查
            try:
                from core.methodology import get_methodology_state, methodology_pre_check

                state = get_methodology_state()
                allowed, reason = methodology_pre_check(tool_name, args, state)
                if not allowed:
                    return reason

                # C/D 级加固：所有写操作 + git 操作均需确认 Plan
                # （methodology_pre_check 已做此检查，此处保留作为双重保险）
                from core.constraints import WRITE_TOOLS
                from core.methodology import TaskLevel

                if state.task_level in (TaskLevel.C, TaskLevel.D):
                    if tool_name in WRITE_TOOLS or tool_name.startswith("git_"):
                        if not state.plan_exists:
                            level_name = "C" if state.task_level == TaskLevel.C else "D"
                            return f"{level_name} 级任务: 未确认 Plan，{tool_name} 被拦截（使用 /plan 先制定计划）"
            except ImportError:
                pass

            return None  # None means proceed

        register_hook(HookType.PRE_TOOL_USE, _hook, priority=100)
    except ImportError:
        pass
