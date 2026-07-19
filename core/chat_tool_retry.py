"""Tool retry pipeline — auto-heal, parameter fixup, and retry for tool execution.

Extracted from core/chat.py to keep ChatSession under 2000 lines.
All functions are pure and import-safe — they accept a session reference
rather than depending on ChatSession internals.
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import re as _re
import sys as _sys

logger = logging.getLogger("crux.tool_retry")

# ── Lightweight tool bus ──────────────────────────────────────────────


class _PipelineToolbus:
    """Lightweight tool bus for DeliberateWorkflow tool execution."""

    def __init__(self, dispatch_fn, tool_registry):
        self._dispatch = dispatch_fn
        self._registry = tool_registry

    async def call(self, tool_name: str, args: dict) -> str:
        """Async tool call (compatible with DeliberateWorkflow await)."""
        import asyncio

        result, _ = await asyncio.to_thread(self._dispatch, tool_name, _json.dumps(args))
        return str(result)

    def list_tools(self) -> list[str]:
        """Return list of available tool names."""
        try:
            return list(self._registry._executors.keys())
        except AttributeError:
            return []


# ── Error formatting ──────────────────────────────────────────────────


def format_tool_error(tool_name: str, raw_error: str) -> str:
    """Wrap technical tool errors with human-readable classification and suggestions."""
    err_lower = raw_error.lower()
    hint = ""
    if "timeout" in err_lower or "timed out" in err_lower:
        hint = "试试减少输入大小或拆分任务"
    elif "permission" in err_lower or "access denied" in err_lower:
        hint = "试试在安全目录运行，或检查文件权限"
    elif "not found" in err_lower or "no such file" in err_lower:
        hint = "检查文件路径是否正确，或者先创建它"
    elif "syntax" in err_lower or "syntaxerror" in err_lower:
        hint = "代码有语法错误，检查引号、括号是否匹配"
    elif "import" in err_lower or "modulenotfound" in err_lower:
        hint = "缺少依赖，试试 pip install <package>"
    elif "connection" in err_lower or "refused" in err_lower:
        hint = "网络连接失败，检查是否离线或服务未启动"
    elif "api key" in err_lower or "unauthorized" in err_lower:
        hint = "API key 未配置或已过期，运行 crux init 重新设置"
    suggestion = f"\n💡 {hint}" if hint else ""
    return f"[错误] {tool_name}: {raw_error[:300]}{suggestion}"


# ── Retry strategies ──────────────────────────────────────────────────


def _build_retry_strategies(tool_name: str, args: dict, error: str, sys_module=_sys) -> list[tuple[str, dict]]:
    """Build ordered fixup strategies based on tool type and error message."""
    strategies: list[tuple[str, dict]] = []

    if tool_name == "run_bash":
        cmd = args.get("command", "")
        # Strategy 1: strip bash -c wrapper
        bare = _re.sub(r'^bash\s+-c\s+["\']?(.+?)["\']?\s*$', r"\1", cmd.strip())
        if bare != cmd:
            strategies.append(("unwrap_bash", {**args, "command": bare}))
        # Strategy 2: drop POSIX single quotes (Windows)
        if sys_module.platform == "win32" and "'" in cmd:
            strategies.append(("strip_quotes", {**args, "command": cmd.replace("'", "")}))
        # Strategy 3: POSIX command → Windows equivalent
        if sys_module.platform == "win32":
            _cmd_name = cmd.strip().split()[0].lower() if cmd.strip() else ""
            _POSIX_MAP = {
                "head": lambda c: _re.sub(r"^head\s+", "more /p ", c) if c.startswith("head") else c,
                "tail": lambda c: _re.sub(r"^tail\s+", "more +99999 ", c) if c.startswith("tail") else c,
                "grep": lambda c: _re.sub(r"^grep\s+", "findstr ", c) if c.startswith("grep") else c,
                "cat": lambda c: _re.sub(r"^cat\s+", "type ", c) if c.startswith("cat") else c,
                "ls": lambda c: _re.sub(r"^ls\b", "dir", c) if c.startswith("ls") else c,
                "cp": lambda c: _re.sub(r"^cp\s+", "copy ", c) if c.startswith("cp") else c,
                "mv": lambda c: _re.sub(r"^mv\s+", "move ", c) if c.startswith("mv") else c,
                "rm": lambda c: _re.sub(r"^rm\s+", "del /f ", c) if c.startswith("rm") else c,
                "touch": lambda c: _re.sub(r"^touch\s+", "type nul > ", c) if c.startswith("touch") else c,
                "wc": lambda c: _re.sub(r"^wc\s+(.+)", r'find /c "\0" \1', c) if c.startswith("wc") else c,
            }
            if _cmd_name in _POSIX_MAP:
                try:
                    converted = _POSIX_MAP[_cmd_name](cmd)
                    if converted != cmd:
                        strategies.append(("posix_to_win", {**args, "command": converted}))
                except Exception:
                    import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        # Strategy 4: add .exe suffix for path commands
        if "/" in cmd or "\\" in cmd:
            _ext = _os.path.splitext(cmd.split()[0] if " " in cmd else cmd)[1]
            if not _ext and sys_module.platform == "win32":
                strategies.append(
                    ("add_exe", {**args, "command": cmd.replace(cmd.split()[0], cmd.split()[0] + ".exe", 1)})
                )

    elif tool_name == "pip_install":
        pkg = args.get("package", "")
        if "--retries" not in pkg:
            strategies.append(("add_retries", {**args, "package": f"{pkg} --retries 3"}))
        if "--timeout" not in pkg:
            strategies.append(("add_timeout", {**args, "package": f"{pkg} --timeout 60"}))

    elif tool_name == "run_python":
        code = args.get("code", "")
        if "try:" not in code[:100]:
            _wrapped = "try:\n" + code + "\nexcept Exception as _e:\n    print('Error:', _e)"
            strategies.append(("wrap_try", {**args, "code": _wrapped}))
        if code != code.lstrip():
            strategies.append(("strip_indent", {**args, "code": code.lstrip()}))

    elif tool_name == "run_test":
        cmd = args.get("command", args.get("args", ""))
        if "--tb" not in str(cmd):
            strategies.append(("cleaner_tb", {**args, "command": f"{cmd} --tb=short"}))
        if "--timeout" not in str(cmd):
            strategies.append(("add_timeout", {**args, "command": f"{cmd} --timeout=120"}))
        if "-x" not in str(cmd):
            strategies.append(("fail_fast", {**args, "command": f"{cmd} -x"}))

    return strategies


# ── Main retry entry point ────────────────────────────────────────────


def auto_retry_tool(session, tool_name: str, args_json: str, original_error: str, max_retries: int = 3):
    """Auto-retry a failed tool call with self-heal + parameter fixup strategies.

    Returns (tool_result, side_effects) — either the corrected result from a
    successful retry, or the original error if all strategies fail.
    """
    args = _json.loads(args_json) if isinstance(args_json, str) else (args_json or {})
    original_args = dict(args)

    # Step 0: Self-heal — auto-fix known issues before retrying
    try:
        from core.self_heal import SelfHealer

        healer = SelfHealer()
        healer.scan_syntax()
        healer.scan_silent_exceptions()
        fixed = healer.fix_silent_exceptions()
        healer.quick_fix()
        if fixed > 0:
            __import__("core.observability", fromlist=["metrics"]).metrics.increment("auto_retry.self_heal.fixes")
    except (ImportError, OSError):
        pass

    # Step 1: Parameter-level retry strategies
    strategies = _build_retry_strategies(tool_name, original_args, original_error)

    for strategy_label, adjusted_args in strategies:
        if adjusted_args == original_args:
            continue
        try:
            logging.getLogger("crux").info(
                "auto-retry [%s]: %s (was: %.80s)", strategy_label, tool_name, str(original_error)
            )
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
        try:
            result, sides = session._dispatch_tool(tool_name, _json.dumps(adjusted_args, ensure_ascii=False))
            result_str = str(result)
            if not result_str.startswith("[错误]") and not result_str.startswith("[自愈失败]"):
                try:
                    from core.observability import metrics as _m

                    _m.increment(f"auto_retry.{tool_name}.success")
                    _m.increment(f"auto_retry.strategy.{strategy_label}")
                except ImportError:
                    pass
                return result, sides
        except (OSError, ValueError, RuntimeError):
            continue

    return original_error, [("info", original_error)]
