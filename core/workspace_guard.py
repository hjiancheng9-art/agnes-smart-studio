"""
CRUX Workspace Guard — 防止工具把自身仓库当项目 workspace

用法:
  guard = WorkspaceGuard(cwd)
  guard.check()  # 如果 cwd 是 CRUX 自身仓库，打印警告

环境变量:
  CRUX_WORKSPACE  — 显式指定目标项目路径
  --workspace     — CLI 参数（优先级高于环境变量）
"""

import os
from pathlib import Path

# ── 缓存：避免重复调用 resolve_workspace 时多次打印 WARNING ──
_cached_workspace: Path | None = None


def reset_workspace_guard() -> None:
    """Reset the cached workspace path (for test isolation)."""
    global _cached_workspace
    _cached_workspace = None


def get_crux_root() -> Path:
    """返回 CRUX 工具自身的根目录"""
    return Path(__file__).resolve().parent.parent


def is_crux_self(path: Path) -> bool:
    """检查 path 是否是 CRUX 自身仓库"""
    crux_root = get_crux_root()
    try:
        return path.resolve() == crux_root.resolve()
    except Exception:
        return False


_PROJECT_MARKERS = (
    ".git",
    ".crux_memory",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "CMakeLists.txt",
    "setup.py",
    "setup.cfg",
    "pytest.ini",
    ".env",
)

_SKIP_PATH_PARTS = frozenset(
    {
        "Windows",
        "System32",
        "system32",
        "Python",
        "Python311",
        "Python312",
        "Python313",
        "Python314",
        "Program Files",
        "Program Files (x86)",
        "nodejs",
        "AppData",
        "WinSxS",
        "Microsoft",
        "Local",
        "Roaming",
        "kimi-code",
        ".codex",
        "chocolatey",
        "ffmpeg",
        ".local",
        "bin",
        "Scripts",
    }
)


def _is_valid_project_dir(p: Path) -> bool:
    """Check if path looks like a valid project directory."""
    if not p.exists() or not p.is_dir():
        return False
    if is_crux_self(p):
        return False
    # Skip system/Python/tool directories
    parts = set(p.parts)
    if parts & _SKIP_PATH_PARTS:
        return False
    # Must have at least one project marker
    return any((p / m).exists() for m in _PROJECT_MARKERS)


def _detect_parent_project() -> Path | None:
    """Try to detect the actual project directory from parent processes.

    When CRUX runs as an MCP server, its cwd is the CRUX install dir.
    Walk up the process tree to find the actual project workspace.
    """
    import sys

    # Strategy 1: psutil (most reliable, gets actual cwd)
    try:
        import psutil

        proc = psutil.Process()
        for _ in range(6):
            parent = proc.parent()
            if parent is None:
                break
            try:
                parent_cwd = parent.cwd()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc = parent
                continue
            if parent_cwd:
                p = Path(parent_cwd)
                if _is_valid_project_dir(p):
                    return p.resolve()
            proc = parent
    except ImportError:
        pass

    # Strategy 2: PowerShell fallback for Windows
    if sys.platform == "win32":
        result = _detect_via_powershell()
        if result is not None:
            return result

    return None


def _detect_via_powershell() -> Path | None:
    """Windows fallback: use PowerShell to walk process tree.

    Parses command lines of ancestor processes looking for project paths.
    Uses _is_valid_project_dir() to filter out system/tool directories.
    """
    import json as _json
    import re as _re
    import subprocess

    pid = os.getpid()

    for _ in range(5):
        ps_cmd = (
            f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" | Select-Object ParentProcessId | ConvertTo-Json'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # subprocess.run may return None for stdout when the process is killed
        # on timeout (esp. PowerShell); guard against AttributeError.
        if result.returncode != 0 or not (result.stdout or "").strip():
            break
        try:
            proc = _json.loads(result.stdout)
        except _json.JSONDecodeError:
            break
        parent_pid = proc.get("ParentProcessId")
        if not parent_pid or parent_pid == pid or parent_pid == 0:
            break
        # Get parent command line
        pp_cmd = (
            f'Get-CimInstance Win32_Process -Filter "ProcessId={parent_pid}" | '
            f"Select-Object CommandLine | ConvertTo-Json"
        )
        pp_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", pp_cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pp_result.returncode == 0 and (pp_result.stdout or "").strip():
            try:
                parent = _json.loads(pp_result.stdout)
            except _json.JSONDecodeError:
                pid = parent_pid
                continue
            cmdline = parent.get("CommandLine") or ""
            # Extract directory/file paths from command line
            for m in _re.finditer(r'([A-Za-z]:\\[^"\s]+)', cmdline):
                candidate = Path(m.group(1))
                if candidate.is_dir() and _is_valid_project_dir(candidate):
                    return candidate.resolve()
                if candidate.is_file() and _is_valid_project_dir(candidate.parent):
                    return candidate.parent.resolve()
        pid = parent_pid

    return None


def resolve_workspace(cli_workspace: str | None = None) -> Path:
    """
    按优先级返回 workspace：
    1. CLI --workspace 参数
    2. CRUX_WORKSPACE 环境变量
    3. 当前工作目录（如果非 CRUX 自身则直接使用）
    4. 当前工作目录即使为 CRUX 自身也尝试父进程检测

    结果会被缓存，避免重复调用时多次打印 WARNING。
    """
    global _cached_workspace

    # 如果已有缓存且此次调用未改变 CLI 参数，直接返回缓存
    if _cached_workspace is not None and cli_workspace is None:
        return _cached_workspace

    # 1. CLI 参数
    if cli_workspace:
        wp = Path(cli_workspace).resolve()
        if wp.exists():
            _cached_workspace = wp
            return wp
        print(f"\u26a0\ufe0f  --workspace 路径不存在: {wp}，回退")

    # 2. 环境变量
    env_ws = os.environ.get("CRUX_WORKSPACE")
    if env_ws:
        wp = Path(env_ws).resolve()
        if wp.exists():
            _cached_workspace = wp
            return wp
        print(f"\u26a0\ufe0f  CRUX_WORKSPACE 路径不存在: {wp}，回退")

    # 2.5. MCP roots (set by IDE during initialize handshake)
    import sys as _sys

    mcp_roots = os.environ.get("CRUX_MCP_ROOTS", "")
    if mcp_roots:
        for root_uri in mcp_roots.split("\n"):
            root_uri = root_uri.strip()
            if not root_uri:
                continue
            # Convert file:// URI to native path
            path_str = root_uri
            if root_uri.startswith("file://"):
                from urllib.parse import unquote, urlparse

                parsed = urlparse(root_uri)
                path_str = unquote(parsed.path)
                if _sys.platform == "win32" and path_str.startswith("/"):
                    path_str = path_str[1:]
            try:
                wp = Path(path_str).resolve()
                if wp.exists() and not is_crux_self(wp):
                    _cached_workspace = wp
                    return wp
            except Exception:
                continue

    # 3. 当前工作目录
    cwd = Path.cwd().resolve()

    # If cwd is NOT CRUX itself, use it directly.
    # If cwd IS CRUX (developing CRUX), still use it — the expensive
    # parent-process detection (psutil + PowerShell fallback ~2.4s) is
    # only needed in MCP-server mode, which is handled by --workspace
    # flag or CRUX_WORKSPACE / CRUX_MCP_ROOTS env vars above.
    _cached_workspace = cwd
    return cwd

    _cached_workspace = cwd
    return cwd


class WorkspaceGuard:
    """文件写入路径守卫 — 阻止写入 CRUX 自身目录"""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).resolve()

    def resolve(self, relative_path: str) -> Path:
        target = (self.workspace / relative_path).resolve()
        crux_root = get_crux_root()

        # 拒绝写入 CRUX 自身目录
        if str(target).startswith(str(crux_root)):
            raise RuntimeError(f"\u274c 拒绝写入 CRUX 自身目录: {target}\n   请使用 --workspace 指定目标项目路径")

        return target

    def write_text(self, relative_path: str, content: str) -> None:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
