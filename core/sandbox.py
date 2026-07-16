"""Sandbox security engine -- tool execution guardrails.

Restricts shell command execution with path allowlists, command denylists,
and destructive operation detection.

设计原则（v2 修订）:
    1. **CWD 自动信任**: 用户在哪个目录启动 crux，该目录即合法工作根。
       不再"只信任 crux 安装目录"——这会把用户自己项目的所有操作误杀。
    2. **路径匹配用 is_relative_to**: 替代 startswith，修前缀匹配坑
       (C:\\foo 不应被当作 C:\\foobar 的祖先)。
    3. **跨平台临时目录**: 用 tempfile.gettempdir() 而非硬编码 /tmp。
    4. **危险模式仍是第一道闸**: 路径白名单只防"读外部敏感文件"，
       不防"在自己工作区搞破坏"——后者由 DANGEROUS_PATTERNS 兜底。
"""

import os
import re
import sys
import tempfile
from pathlib import Path

__all__ = [
    "ALLOWED_ROOTS",
    "DANGEROUS_PATTERNS",
    "ROOT",
    "FileAudit",
    "Sandbox",
    "get_audit_trail",
    "sandbox_check",
    "sandbox_restrict",
    "tokenize_command",
]

ROOT = Path(__file__).resolve().parent.parent


# Always blocked — no path context can make these safe
ALWAYS_DANGEROUS = [
    r">\s*/dev/",
    r"mkfs\.",
    r"dd\s+if=",
    r"curl.*\|\s*(/.*)?(ba)?sh",
    r"curl.*\|\s*(sudo\s+)?(/.*)?(ba)?sh",
    r"curl.*\|\s*\.\s+/dev/stdin",
    r"wget.*\|\s*(ba)?sh",
    r":\(\)\s*\{\s*:\|:&\s*\}\s*;:",  # fork bomb
    r"\bformat\s+[A-Za-z]:",
    r"\bdiskpart",
    r"\bcipher\s*/w",
    r"\bpowershell.*-enc\s+[A-Za-z0-9]",
    r"reg\s+delete.*/f",
]
# Path-aware — blocked only when targeting external paths
PATH_AWARE_DANGEROUS = [
    r"\brm\s+(-rf?|--recursive)",
    r"\brmdir\s+[/\-]?s",
    r"\bdel\s+[/\\]?[sfq]",
    r"\berase\s+[/\\]?[sfq]",
    r"chmod\s+777",
]
DANGEROUS_PATTERNS = ALWAYS_DANGEROUS + PATH_AWARE_DANGEROUS  # backward compat


def _normalize_path(p: Path) -> Path:
    r"""规范化路径用于比较：resolve + 大小写归一(Windows) + 斜杠统一。

    resolve() 在 Windows 上会自动把 / 转 \ 并补绝对路径，
    但对不存在的路径不抛错（用于校验用户输入的任意路径）。
    """
    try:
        # strict=False（默认）：路径不存在也不抛错，适合校验场景
        return p.resolve()
    except (OSError, RuntimeError):
        # resolve 在某些边界（UNC 路径、符号链接环）会失败，降级用原值
        return p


def _build_allowed_roots() -> list[Path]:
    """构建允许的根目录列表（Path 形式，已规范化）。

    包含三类信任源：
      1. crux 自身安装目录及其 output/tmp 子目录（管理 crux 自己的产物）
      2. 当前工作目录 CWD（用户启动 crux 的地方 = 用户自己的项目）
      3. 系统临时目录（跨平台）

    可通过 CRUX_ALLOWED_ROOTS 环境变量覆盖（逗号分隔的绝对路径），
    设置后则 *只* 信任环境变量列出的目录（用于 CI/受控环境锁定）。
    """
    env_roots = os.environ.get("CRUX_ALLOWED_ROOTS", "")
    if env_roots:
        # 环境变量覆盖模式：完全替换默认列表
        raw = [r.strip() for r in env_roots.split(",") if r.strip()]
    else:
        raw = [
            str(ROOT),
            str(ROOT / "output"),
            str(ROOT / "tmp"),
            os.getcwd(),  # ← 关键修复：CWD 自动信任
            str(Path.home()),  # ← 用户主目录，覆盖所有用户项目
            tempfile.gettempdir(),  # ← 跨平台临时目录（替代硬编码 /tmp）
        ]
    return [_normalize_path(Path(r)) for r in raw]


# 模块加载时计算一次静态部分；CWD 部分每次校验时动态刷新（用户可能 cd）
_STATIC_ALLOWED_ROOTS = _build_allowed_roots()


def _current_allowed_roots() -> list[Path]:
    """返回当前生效的允许根列表（每次构建新列表，不修改静态配置）。

    CWD 可能随会话变化（用户在 REPL 里 cd），所以每次校验都重新拿 os.getcwd()。
    环境变量覆盖模式下不追加 CWD（用户已显式锁定信任域）。
    """
    if os.environ.get("CRUX_ALLOWED_ROOTS", ""):
        return list(_STATIC_ALLOWED_ROOTS)  # 锁定模式，返回副本
    # 非锁定模式：构建包含当前 CWD 的新列表（不污染静态配置）
    roots = list(_STATIC_ALLOWED_ROOTS)
    try:
        cwd = _normalize_path(Path.cwd())
    except OSError:
        return roots  # CWD 不可用（如目录已被删除）
    if cwd not in roots:
        roots.append(cwd)
    return roots


# ── Command tokenizer ───────────────────────────────────────


def tokenize_command(command: str) -> dict:
    """Tokenize a shell command into structural components using shlex."""
    import shlex

    try:
        parts = shlex.split(command, posix=True)
    except (ValueError, TypeError):
        parts = command.split()
    if not parts:
        return {"command": "", "args": []}
    return {"command": parts[0], "args": parts[1:], "raw": command}


# ── File Audit Trail ────────────────────────────────────────

_AUDIT_TRAIL: list[dict] = []


class FileAudit:
    """Lightweight file operation audit with hash verification."""

    @staticmethod
    def record(op: str, path: str, before_hash: str = "", after_hash: str = "") -> None:
        _AUDIT_TRAIL.append({"op": op, "path": path, "before": before_hash, "after": after_hash})


def get_audit_trail() -> list[dict]:
    return list(_AUDIT_TRAIL)


# 对外暴露的 ALLOWED_ROOTS（保持向后兼容，值为静态列表；
# 运行时校验请用 _current_allowed_roots() 以包含动态 CWD）
ALLOWED_ROOTS = _STATIC_ALLOWED_ROOTS


def _path_is_allowed(p: Path, roots: list[Path]) -> bool:
    """判断路径 p 是否在任一允许根之下（含本身相等）。

    用 is_relative_to 替代 startswith，避免前缀匹配坑：
    'C:\\foo' 不应被认为覆盖 'C:\\foobar'。
    """
    norm = _normalize_path(p)
    for root in roots:
        try:
            if norm == root or norm.is_relative_to(root):
                return True
        except (TypeError, ValueError):
            # is_relative_to 在老版本 Python 或跨盘符场景可能行为异常，降级
            if str(norm).lower() == str(root).lower() or str(norm).lower().startswith(str(root).lower() + os.sep):
                return True
    return False


# 跨平台超时命令
if sys.platform == "win32":
    # Windows: subprocess.run(..., timeout=N) 已提供超时保护
    # timeout 命令在 Windows 语法不同（/t /nobreak），不在命令层面包裹
    _TIMEOUT_WRAPPER = None
else:
    _TIMEOUT_WRAPPER = "timeout 120"


def _is_external_path(path_str: str, roots: list[Path]) -> bool:
    """Check if path is outside allowed roots (handles POSIX paths on Windows)."""
    if path_str.startswith("/") and sys.platform == "win32":
        return True
    p = Path(path_str)
    return p.is_absolute() and not _path_is_allowed(p, roots)


class Sandbox:
    """Validates shell commands before execution."""

    def __init__(self, root: Path | None = None) -> None:
        # root 参数保留向后兼容，但 v2 起实际信任域由 _current_allowed_roots() 决定
        self.root = root or ROOT

    def validate(self, command: str) -> tuple[bool, str]:
        """Check if a shell command is safe to execute.
        Returns (is_safe: bool, reason: str).
        """
        if not command or not command.strip():
            return False, "empty command"

        cmd_lower = command.lower().strip()

        roots = _current_allowed_roots()
        # Always dangerous patterns — blocked regardless
        for pattern in ALWAYS_DANGEROUS:
            if re.search(pattern, cmd_lower):
                return False, f"blocked dangerous pattern: {pattern[:40]}"
        # Path-aware patterns — only block if targeting external paths
        for pattern in PATH_AWARE_DANGEROUS:
            if re.search(pattern, cmd_lower):
                all_paths = re.findall(r"(?<!\S)/(?!\s)[^\s]+", command) + re.findall(
                    r"(?:[A-Za-z]:[\\/][^\s]+|\\\\[^\s]+)", command
                )
                # Filter flags (/F /S etc.) and relative fragments (/node_modules from ./node_modules)
                all_paths = [p for p in all_paths if len(p) > 2 and not p.startswith("/?")]
                if all_paths:
                    for p in all_paths:
                        if _is_external_path(p, roots):
                            return False, f"blocked destructive operation to external path: {p}"
                break  # relative paths → allowed within project

        # Check for absolute path references outside allowed roots
        # Unix 风格: /path/to/...
        # Windows 风格: C:\... / C:/... / \\host\share
        roots = _current_allowed_roots()
        unix_paths = re.findall(r"(/[^\s]+)", command)
        win_paths = re.findall(r"(?:[A-Za-z]:[\\/][^\s]+|\\\\[^\s]+)", command)
        for p in unix_paths + win_paths:
            p_obj = Path(p)
            if p_obj.is_absolute() and not _path_is_allowed(p_obj, roots):
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


# ── 模块级单例，避免每次调用都创建 Sandbox 实例 ──
_SANDBOX: Sandbox | None = None


def _get_sandbox() -> Sandbox:
    global _SANDBOX
    if _SANDBOX is None:
        _SANDBOX = Sandbox()
    return _SANDBOX


def sandbox_check(command: str) -> tuple[bool, str]:
    return _get_sandbox().validate(command)


def sandbox_restrict(command: str) -> str:
    return _get_sandbox().restrict_bash(command)
