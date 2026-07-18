"""Safe file operations for tool calling.

These functions are called directly by the python-type tool executor,
avoiding shell escaping issues with triple-quotes and special characters.
"""

import contextlib
import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "ROOT",
    "count_lines",
    "download_file",
    "edit_file",
    "env_check",
    "glob_files",
    "list_files",
    "pip_install",
    "read_file",
    "run_python",
    "run_test",
    "search_files",
    "think_deep",
    "tree_dir",
    "web_fetch",
    "web_search",
    "write_file",
]


def _resolve_workspace() -> Path:
    """Determine the workspace root: CRUX_WORKSPACE env → CWD → CRUX install dir."""
    import os as _os

    env = _os.environ.get("CRUX_WORKSPACE", "")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    _ = Path(__file__).resolve().parent.parent  # CRUX root; reserved for future use
    # If CWD is inside CRUX root, use CWD (user might be in a subdir)
    # If CWD is outside CRUX root, use CWD (user is in another project)
    return cwd


ROOT = _resolve_workspace()


# 敏感路径阻止列表 — read_file 拒绝读取这些（防止 LLM 窃取密钥/凭证）
_READ_BLOCKLIST = [
    ".env",
    "**/.env.*",
    "**/.git/config",
    "**/.ssh/*",
    "**/id_rsa*",
    "**/credentials*",
    "**/.aws/config",
    "**/.aws/credentials",
    "**/.claude/.env",
    "**/.npmrc",
    "**/settings.local.json",
]

# 危险系统路径阻止写入 — 防止 LLM 修改系统文件
_WRITE_BLOCKLIST = [
    # Windows system
    "C:\\Windows\\*",
    "C:\\Windows\\System32\\*",
    "C:\\Program Files\\*",
    "C:\\Program Files (x86)\\*",
    # Unix system
    "/etc/*",
    "/usr/*",
    "/boot/*",
    "/sys/*",
    "/proc/*",
    "/dev/*",
    "/bin/*",
    "/sbin/*",
    "/lib/*",
    # CRUX internal (protect core runtime)
    "**/__pycache__/*",
]


def _safe_path(path: str, *, read_only: bool = False) -> Path:
    """Resolve path and enforce safety boundaries.

    Symlink-safe: resolves the path to real paths (no symlinks) before
    checking. Prevents symlink-based escapes.

    Read operations: blocked from sensitive credential files.
    Write operations: blocked from system directories, allowed anywhere
    else (user home, other projects, Desktop, etc.).
    """
    from fnmatch import fnmatch

    p = Path(path).expanduser().resolve()
    p_str = str(p)

    # Sensitive credential files — never readable
    for blocked in _READ_BLOCKLIST:
        if fnmatch(p_str, blocked):
            raise ValueError(f"Access denied to sensitive path: {path}")

    if read_only:
        return p

    # Write operations: block system paths, allow everything else
    for blocked in _WRITE_BLOCKLIST:
        if fnmatch(p_str, blocked):
            raise ValueError(f"Write denied to system path: {path}\n  Matched block rule: {blocked}")
    return p


def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a text file, optionally with offset and limit for large files.

    Args:
        path: File path (absolute, relative, or outside project — reads allowed anywhere)
        offset: Line number to start from (0 = beginning)
        limit: Max lines to read (0 = all lines)

    Returns:
        File content with line numbers, or error message
    """
    try:
        p = _safe_path(path, read_only=True)
    except ValueError as e:
        return f"[安全拒绝] {e}"
    if not p.is_file():
        return f"[错误] 文件不存在: {path}"
    try:
        # Fast path: UTF-8 with replace
        raw = p.read_bytes()
        content = raw.decode("utf-8", errors="replace")

        # Check for encoding issues (replacement chars or mojibake)
        if "�" in content:
            try:
                from core.encoding_fix import fix_garbled_bytes, is_likely_garbled

                recovered, enc, _ = fix_garbled_bytes(raw)
                # Use recovered text if UTF-8 decoding was wrong
                if enc != "utf-8" or is_likely_garbled(content):
                    content = recovered
            except ImportError:
                pass

        lines = content.split("\n")
        total = len(lines)
        if offset > 0:
            lines = lines[offset:]
        effective_limit = limit if limit > 0 else 500
        if len(lines) > effective_limit:
            lines = lines[:effective_limit]
            truncated = True
        else:
            truncated = False
        content = "\n".join(lines)
        header = f"--- {path} ---"
        shown = len(lines)
        if offset or limit:
            header += f" (lines {offset + 1}-{offset + shown} of {total})"
        elif truncated:
            header += f" (first {shown} of {total} lines, use offset/limit for more)"
        return f"{header}\n{content}"
    except (OSError, UnicodeDecodeError) as e:
        return f"[错误] 读取失败: {e}"


def _snapshot_if_core(p: Path) -> None:
    """Auto-snapshot core/*.py files before modification (anti-self-damage)."""
    try:
        core_root = Path(__file__).resolve().parent
        if p.resolve().is_relative_to(core_root) and p.suffix == ".py":
            snap_dir = core_root.parent / "output" / "snapshots"
            snap_dir.mkdir(parents=True, exist_ok=True)
            import time

            ts = time.strftime("%Y%m%d_%H%M%S")
            snap_path = snap_dir / f"{p.stem}_{ts}.py.bak"
            snap_path.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    except (OSError, ValueError):
        pass  # snapshot failure must not block the write


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with UTF-8 encoding.

    Args:
        path: Absolute or relative file path (enforced within project root)
        content: Text content to write

    Returns:
        Confirmation message with file path
    """
    p = _safe_path(path)
    _snapshot_if_core(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: temp file + os.replace to avoid partial writes on crash
    import tempfile as _tf

    fd, tmp_name = _tf.mkstemp(suffix=".tmp", prefix=".crux_write_", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(p))
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
    return f"Written: {p}"


def safe_rewrite_file(path: str, old_lines: str, new_lines: str) -> str:
    """Replace old_lines with new_lines in a file — context is code-computed, not LLM-generated.

    Unlike apply_patch/edit_file where the model must guess the exact context,
    this tool reads the actual file, finds old_lines precisely, and replaces.
    Multi-line blocks are supported. Returns the number of replacements made.

    This is CRUX's most reliable self-repair tool — zero context-match failures.
    """
    p = _safe_path(path)
    if not p.is_file():
        return f"[错误] 文件不存在: {path}"
    _snapshot_if_core(p)
    original = p.read_text(encoding="utf-8")
    count = original.count(old_lines)
    if count == 0:
        return f"[错误] 未找到匹配文本（{len(old_lines)} 字符），文件可能已被修改。请重新 read_file 获取最新内容。"
    if count > 1:
        return f"[警告] 找到 {count} 处匹配，为安全起见不执行。请提供更精确的上下文（包含前后各 1-2 行唯一特征）。"
    result = original.replace(old_lines, new_lines, 1)
    p.write_text(result, encoding="utf-8")
    return f"Replaced 1 occurrence in {p}"


def search_files(pattern: str) -> str:
    """Search files in project for a regex pattern. Returns up to 50 matches.

    Args:
        pattern: Python regex pattern to search for

    Returns:
        Formatted results with file:line:content, or error message
    """
    import os
    import re
    from pathlib import Path

    _ROOT = Path(__file__).parent.parent
    TEXT_EXTS = {
        ".py",
        ".md",
        ".json",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".toml",
        ".yaml",
        ".yml",
        ".sh",
        ".bat",
        ".txt",
        ".cfg",
        ".ini",
        ".env",
        ".xml",
        ".sql",
        ".rst",
        ".csv",
    }
    from core.constraints import PROJECT_SKIP_DIRS

    SKIP_DIRS = PROJECT_SKIP_DIRS
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"[错误] 无效的正则表达式: {e}"
    matches = []
    try:
        for dirpath, dirnames, filenames in os.walk(str(_ROOT)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in filenames:
                if Path(f).suffix.lower() not in TEXT_EXTS:
                    continue
                fpath = os.path.join(dirpath, f)
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, 1):
                            if regex.search(line):
                                rel = os.path.relpath(fpath, str(_ROOT))
                                matches.append(f"{rel}:{i}:{line.rstrip()}")
                                if len(matches) >= 50:
                                    return "\n".join(matches)
                except (OSError, PermissionError):
                    pass
    except (OSError, RuntimeError) as e:
        return f"[错误] 搜索失败: {e}"
    return "\n".join(matches) if matches else f"(no matches for pattern: {pattern})"


def list_files(path: str = ".") -> str:
    """List files and directories in a given path with sizes.

    Args:
        path: Directory path to list (absolute, relative, or outside project — reads allowed anywhere)

    Returns:
        Formatted listing with file sizes
    """
    try:
        p = _safe_path(path, read_only=True)
    except ValueError as e:
        return f"[安全拒绝] {e}"
    if not p.is_dir():
        return f"[错误] 目录不存在: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items[:50]:
            if item.is_dir():
                lines.append(f"{'':>10}  {item.name}/")
            else:
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                lines.append(f"{size:>10}  {item.name}")
        return "\n".join(lines)
    except (OSError, PermissionError) as e:
        return f"[错误] 列出目录失败: {e}"


def pip_install(package: str) -> str:
    """Install a Python package — whitelist only for safety.

    Only allows packages from a curated safe list. Returns a clear error
    for anything outside the whitelist, preventing arbitrary code execution.
    """
    _SAFE_PACKAGES = {
        "pytest",
        "pytest-cov",
        "pytest-asyncio",
        "pytest-mock",
        "black",
        "isort",
        "flake8",
        "mypy",
        "ruff",
        "coverage",
        "tox",
        "pre-commit",
        "pip",
        "setuptools",
        "wheel",
        "build",
        "twine",
        "httpx",
        "requests",
        "aiohttp",
        "rich",
        "click",
        "typer",
        "pydantic",
        "pydantic-settings",
        "numpy",
        "pandas",
        "matplotlib",
        "pillow",
        "openai",
        "python-dotenv",
        "nest-asyncio",
    }
    import subprocess
    import sys

    packages = [p.strip() for p in package.split() if p.strip()]
    if not packages:
        return "[错误] 请指定要安装的包名"
    rejected = [p for p in packages if p not in _SAFE_PACKAGES]
    if rejected:
        return (
            f"[安全拒绝] 以下包不在白名单中: {', '.join(rejected)}\n"
            f"白名单: {', '.join(sorted(_SAFE_PACKAGES))}\n"
            "如需安装其他包，请手动在终端执行。"
        )
    try:
        result = run_subprocess([sys.executable, "-m", "pip", "install", *packages], timeout=120)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "[错误] pip install 超时"
    except subprocess.SubprocessError as e:
        return f"[错误] pip install 失败: {e}"


def env_check(name: str = "") -> str:
    """Check environment: Python version, key packages, project health.

    Returns:
        Environment report
    """
    import sys

    lines = []
    lines.append(f"Python: {sys.version}")
    lines.append(f"Platform: {sys.platform}")
    lines.append(f"Encoding: {sys.getdefaultencoding()}")
    lines.append(f"Filesystem encoding: {sys.getfilesystemencoding()}")

    # Key packages
    for pkg in ["httpx", "rich", "prompt_toolkit", "nest_asyncio", "dotenv"]:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "installed")
            lines.append(f"{pkg}: {ver}")
        except ImportError:
            lines.append(f"{pkg}: NOT INSTALLED")

    # Project health
    from pathlib import Path

    _ROOT = Path(__file__).parent.parent
    for check_file, label in [
        (".env", "Config (.env)"),
        ("tools.json", "Tools config"),
        ("models.json", "Models config"),
    ]:
        exists = (_ROOT / check_file).exists()
        lines.append(f"{label}: {'OK' if exists else 'MISSING'}")

    return "\n".join(lines)


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace the first occurrence of old_text with new_text in a file.

    Args:
        path: File path (must be within project root)
        old_text: Exact text to find (first match only)
        new_text: Replacement text

    Returns:
        Confirmation message
    """
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"[安全拒绝] {e}"
    if not p.is_file():
        return f"[错误] 文件不存在: {path}"
    _snapshot_if_core(p)
    original = p.read_text(encoding="utf-8")
    if old_text not in original:
        return f"Not found in {p}"
    result = original.replace(old_text, new_text, 1)
    p.write_text(result, encoding="utf-8")
    return f"Edited: {p}"


def think_deep(prompt: str, max_tokens: int = 2000) -> str:
    """[已弃用] llama.cpp 已停止维护，本地重型推理不再可用。
    请直接在当前对话中提出深度推理需求，无需通过此工具。"""
    return "[已弃用] llama.cpp 不再维护，think_deep 不可用。请直接在当前对话中提出深度推理需求。"


def run_python(code: str) -> str:
    """Execute Python code in an isolated subprocess, return captured output.

    Runs in a fresh subprocess with minimal builtin restrictions.
    Only truly dangerous builtins are removed (exec/eval/compile/breakpoint);
    import/open/class definitions are allowed since subprocess isolation
    already provides a strong security boundary.

    For long-running or complex code, write to .py first via write_file,
    then execute with run_bash.
    """
    import subprocess
    import sys
    import tempfile

    _prelude = """
import builtins
from core.mcp_servers._mcp_utils import run_subprocess
# Only remove breakpoint to prevent debugger escape from subprocess.
# exec/eval/compile are KEPT because Python's import machinery (exec_module)
# requires them — deleting them breaks all imports in the sandbox.
# The subprocess boundary is the real security layer here.
_DANGEROUS = ("breakpoint",)
for _d in _DANGEROUS:
    try:
        delattr(builtins, _d)
    except (AttributeError, TypeError):
        pass
"""
    # Write to temp file to avoid command-line length limits and escape issues
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False, dir=str(ROOT.parent)
        ) as tf:
            tf.write(_prelude)
            tf.write("\n# --- user code ---\n")
            tf.write(code)
            tf.write("\n")
            tmp_path = tf.name
    except (OSError, PermissionError) as e:
        return f"[错误] 临时文件创建失败: {e}"

    try:
        r = run_subprocess([sys.executable, tmp_path], timeout=30, cwd=str(ROOT))
        out = r.stdout.strip()
        err = r.stderr.strip()
        if err:
            out = (out + "\n[stderr]\n" + err).strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "[错误] Python 执行超时 (30s)。可拆分任务，或写入 .py 文件后用 run_bash 分段执行。"
    except subprocess.SubprocessError as e:
        return f"[错误] Python 执行失败: {e}"
    finally:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink(missing_ok=True)


def count_lines(path: str = "") -> str:
    """Count lines of code by file extension.

    Args:
        path: Optional directory or file to count. Empty = project root (.).

    Returns:
        Formatted table of extension, lines, and file counts
    """
    from collections import defaultdict

    target_dir = path if path else "."
    stats = defaultdict(lambda: [0, 0])

    if os.path.isfile(target_dir):
        ext = os.path.splitext(target_dir)[1]
        try:
            with open(target_dir, encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh)
            if ext:
                stats[ext][0] += 1
                stats[ext][1] += n
        except (OSError, PermissionError):
            pass
    else:
        for r, _d, fs in os.walk(target_dir):
            if ".git" in r or "__pycache__" in r or ".codebuddy" in r:
                continue
            for f in fs:
                ext = os.path.splitext(f)[1]
                if not ext:
                    continue
                try:
                    with open(os.path.join(r, f), encoding="utf-8", errors="replace") as fh:
                        n = sum(1 for _ in fh)
                    stats[ext][0] += 1
                    stats[ext][1] += n
                except (OSError, PermissionError):
                    pass

    target = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".html",
        ".css",
        ".md",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".sh",
        ".bat",
    }
    lines_out = []
    for ext, (files, lines) in sorted(stats.items(), key=lambda x: -x[1][1]):
        if ext in target:
            lines_out.append(f"{ext:>8s} {lines:>8d} lines in {files:>4d} files")
    return "\n".join(lines_out) if lines_out else "No code files found"


# ════════════════════════════════════════════════════════════
#  SSRF 防护 — URL 校验器
# ════════════════════════════════════════════════════════════

_SSRF_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "169.254.169.254",  # AWS/cloud metadata
    "metadata.google.internal",  # GCP metadata
}
_SSRF_BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]


def _validate_url(url: str) -> str | None:
    """Validate URL for SSRF safety. Returns error string or None if safe."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return f"无效 URL: {url[:100]}"
    if parsed.scheme not in ("http", "https"):
        return f"不支持的协议: {parsed.scheme}"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return f"无法解析主机名: {url[:100]}"
    if hostname in _SSRF_BLOCKED_HOSTS:
        return f"禁止访问内部地址: {hostname}"
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _SSRF_BLOCKED_NETS:
            if addr in net:
                return f"禁止访问内部网络: {hostname}"
    except ValueError:
        # Not an IP — resolve hostname and check
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in resolved:
                ip = sockaddr[0]
                addr = ipaddress.ip_address(ip)
                for net in _SSRF_BLOCKED_NETS:
                    if addr in net:
                        return f"禁止访问内部网络: {hostname} → {ip}"
        except (socket.gaierror, OSError):
            pass  # DNS resolution failed — let httpx handle it
    return None


# ════════════════════════════════════════════════════════════
#  以下为 tools.json shell→python 迁移的新实现
# ════════════════════════════════════════════════════════════


def glob_files(pattern: str) -> str:
    """Glob 搜索文件，返回匹配路径列表。纯 Python 实现，无 shell 风险。"""
    from pathlib import Path

    try:
        results = sorted(Path(".").glob(pattern))[:100]
        return "\n".join(str(p) for p in results) or "(no matches)"
    except (OSError, ValueError) as e:
        return f"[错误] glob 失败: {e}"


def web_fetch(url: str) -> str:
    """获取网页文本内容（最多5000字符）。纯 Python httpx + SSRF 防护。"""
    err = _validate_url(url)
    if err:
        return f"[安全拒绝] {err}"
    try:
        r = httpx.get(url, timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True, trust_env=False)
        r.raise_for_status()
        return r.text[:5000]
    except httpx.ConnectError:
        return f"[错误] 无法连接: {url[:60]}"
    except httpx.TimeoutException:
        return f"[错误] 连接超时: {url[:60]}"
    except (httpx.HTTPError, OSError) as e:
        return f"[错误] 获取失败: {e}"


def web_search(query: str) -> str:
    """搜索互联网，多引擎自动回退，5秒内返回或放弃。"""
    try:
        from html import unescape
        from urllib.parse import quote

        q = quote(query)
        engines = [
            ("DuckDuckGo", f"https://html.duckduckgo.com/html/?q={q}", r"<a[^>]*result__a[^>]*>(.*?)</a>"),
            ("Bing", f"https://www.bing.com/search?q={q}", r"<li[^>]*b_algo[^>]*>.*?<a[^>]*>(.*?)</a>"),
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for _engine_name, url, pattern in engines:
            try:
                r = httpx.get(
                    url,
                    timeout=httpx.Timeout(5.0, connect=4.0),
                    trust_env=False,
                    headers=headers,
                    follow_redirects=True,
                )
                if r.status_code == 200:
                    results = []
                    for m in re.finditer(pattern, r.text, re.DOTALL):
                        text = unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
                        if text and len(text) > 3:
                            results.append(text)
                            if len(results) >= 5:
                                break
                    if results:
                        return "\n".join(results)
            except (httpx.HTTPError, OSError, re.error):
                continue
        return "(搜索服务不可用，请检查网络)"
    except (httpx.HTTPError, OSError, re.error) as e:
        return f"[错误] 搜索失败: {e}"


def tree_dir(depth: int = 3) -> str:
    """树形展示目录布局。纯 Python，无 shell 风险。"""
    import os

    lines = []
    root = os.path.abspath(".")
    for dp, dirs, files in os.walk(root):
        rel = os.path.relpath(dp, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        if level > depth:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if level == 0:
            lines.append(root)
        else:
            prefix = "  " * level
            lines.append(f"{prefix}{os.path.basename(dp)}/")
        for f in sorted(files):
            if not f.startswith("."):
                lines.append(f"{'  ' * (level + 1)}{f}")
    return "\n".join(lines[:500])


def download_file(url: str, save_path: str) -> str:
    """下载文件到指定路径。纯 Python + SSRF 防护 + 路径限制 + 磁盘空间检查。"""
    import os as _os
    import shutil as _shutil

    err = _validate_url(url)
    if err:
        return f"[安全拒绝] {err}"
    try:
        sp = _safe_path(save_path)
    except ValueError as e:
        return f"[安全拒绝] {e}"
    try:
        _os.makedirs(_os.path.dirname(str(sp)) or ".", exist_ok=True)
        r = httpx.get(url, follow_redirects=True, timeout=httpx.Timeout(60.0, connect=8.0), trust_env=False)
        r.raise_for_status()
        content_len = len(r.content)
        # 磁盘空间检查（写前预检，避免半写损坏）
        if content_len > 0:
            disk_free = _shutil.disk_usage(_os.path.dirname(str(sp)) or ".").free
            if content_len > disk_free:
                return f"[错误] 磁盘空间不足: 需要 {content_len} bytes，可用 {disk_free} bytes"
        sp.write_bytes(r.content)
        return f"Downloaded: {sp} ({content_len} bytes)"
    except httpx.ConnectError:
        return f"[错误] 无法连接: {url[:60]}"
    except httpx.TimeoutException:
        return f"[错误] 下载超时: {url[:60]}"
    except (httpx.HTTPError, OSError) as e:
        # 清理可能的部分写入
        if sp.exists():
            with contextlib.suppress(OSError):
                sp.unlink()
        return f"[错误] 下载失败: {e}"


def run_test(path: str = "tests/", timeout: float = 1800) -> str:
    """运行 pytest，纯 Python subprocess 列表传参。默认 30 分钟总超时，
    单测 120s 硬超时（pytest-timeout），防止个别测试卡死拖垮全量。
    子目录/单文件可适当缩小 timeout。"""
    import subprocess
    import sys

    try:
        r = run_subprocess(
            [sys.executable, "-m", "pytest", path, "-q", "--tb=short", "--timeout=120"],
            timeout=timeout,
        )
        return r.stdout.strip() or r.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[错误] 测试超时 ({timeout}s)"
    except subprocess.SubprocessError as e:
        return f"[错误] 测试失败: {e}"
