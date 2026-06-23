"""Sandbox security engine -- tool execution guardrails.

Restricts shell command execution with path allowlists, command denylists,
and destructive operation detection.
"""

import re
import sys
from pathlib import Path

__all__ = [
    'ALLOWED_ROOTS', 'DANGEROUS_PATTERNS', 'ROOT', 'Sandbox', 'sandbox_check', 'sandbox_restrict',
]

ROOT = Path(__file__).resolve().parent.parent


# Dangerous command patterns (will be blocked entirely)
DANGEROUS_PATTERNS = [
    r"rm\s+(-rf?|--recursive)",    # recursive delete
    r">\s*/dev/",                    # write to device
    r"mkfs\.",                       # format filesystem
    r"dd\s+if=",                     # raw disk write
    r"chmod\s+777",                  # world-writable
    r"curl.*\|\s*(ba)?sh",          # pipe to shell
    r"wget.*\|\s*(ba)?sh",          # pipe to shell
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", # fork bomb
    r"git\s+push\s+--force",        # force push (destructive git)
    r"git\s+reset\s+--hard",        # hard reset (destructive git)
    # Windows 破坏性命令（跨平台覆盖）
    r"\brmdir\s+[/\-]?s",            # rmdir /s 递归删目录
    r"\bdel\s+[/\\]?[sfq]",          # del /s /f /q 强制删除
    r"\berase\s+[/\\]?[sfq]",        # erase /s /f /q
    r"\bformat\s+[A-Za-z]:",         # format X: 格式化盘
    r"\bdiskpart",                   # 磁盘分区操作
    r"\bcipher\s*/w",                # cipher /w 覆写删除
    r"\bcd\s+[A-Za-z]:[\\/]",        # cd 到绝对路径外（防止跳盘）
    r"\bpowershell.*-enc\s+[A-Za-z0-9]",  # powershell 编码命令（绕过审计）
    r"reg\s+delete.*/f",             # 注册表强删
]

# Allowed working directories for shell commands
ALLOWED_ROOTS = [
    str(ROOT),
    str(Path.home()),
    str(Path.home() / "tmp"),
    "/tmp",
]

# 跨平台超时命令
if sys.platform == "win32":
    # Windows: subprocess.run(..., timeout=N) 已提供超时保护
    # timeout 命令在 Windows 语法不同（/t /nobreak），不在命令层面包裹
    _TIMEOUT_WRAPPER = None
else:
    _TIMEOUT_WRAPPER = "timeout 120"


class Sandbox:
    """Validates shell commands before execution."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT

    def validate(self, command: str) -> tuple[bool, str]:
        """Check if a shell command is safe to execute.
        Returns (is_safe: bool, reason: str).
        """
        if not command or not command.strip():
            return False, "empty command"

        cmd_lower = command.lower().strip()

        # Check dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower):
                return False, f"blocked dangerous pattern: {pattern[:40]}"

        # Check for absolute path references outside allowed roots
        # Unix 风格: /path/to/...
        # Windows 风格: C:\... / C:/... / \\host\share
        unix_paths = re.findall(r"(/[^\s]+)", command)
        win_paths = re.findall(r"(?:[A-Za-z]:[\\/][^\s]+|\\\\[^\s]+)", command)
        for p in unix_paths + win_paths:
            p_obj = Path(p)
            if p_obj.is_absolute():
                allowed = any(
                    str(p_obj).startswith(root)
                    for root in ALLOWED_ROOTS
                )
                if not allowed:
                    return False, f"path outside allowed roots: {p}"

        return True, "ok"

    def restrict_bash(self, command: str) -> str:
        """Wrap a command in safety restrictions if possible.
        Returns modified command or raises RuntimeError.
        """
        ok, reason = self.validate(command)
        if not ok:
            raise RuntimeError(f"Sandbox rejected: {reason}")
        # 跨平台超时：Linux 用 timeout 命令包裹，Windows 依赖 subprocess.run(timeout=)
        if _TIMEOUT_WRAPPER and not command.startswith("timeout "):
            command = f"{_TIMEOUT_WRAPPER} {command}"
        return command


def sandbox_check(command: str) -> tuple[bool, str]:
    return Sandbox().validate(command)

def sandbox_restrict(command: str) -> str:
    return Sandbox().restrict_bash(command)