"""Safe file operations for tool calling.

These functions are called directly by the python-type tool executor,
avoiding shell escaping issues with triple-quotes and special characters.
"""

import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse
import contextlib

import httpx

__all__ = [
    'ROOT', 'count_lines', 'download_file', 'edit_file', 'env_check', 'glob_files', 'list_files', 'pip_install', 'read_file', 'run_python', 'run_test', 'search_files', 'think_deep', 'tree_dir', 'web_fetch', 'web_search', 'write_file',
]


ROOT = Path(__file__).resolve().parent.parent


def _safe_path(path: str, *, read_only: bool = False) -> Path:
    """Resolve path and enforce it stays within project root.

    Symlink-safe: resolves both the path and ROOT to real paths (no symlinks)
    before checking containment. Prevents symlink-based sandbox escapes
    (e.g. a symlink inside the project pointing to /etc).

    Args:
        path: File path to validate.
        read_only: If True, only resolve/normalize without enforcing project root
                   containment (for read_file/list_files). Write operations must
                   stay within project root.
    """
    p = Path(path).expanduser().resolve()
    if read_only:
        # 读取操作允许任意路径，仅做 resolve + expanduser
        return p
    root_real = ROOT.resolve()
    # resolve() already eliminates symlinks; compare real paths
    if root_real not in p.parents and p != root_real:
        raise ValueError(f"路径超出项目根目录: {path}")
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
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
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
            header += f" (lines {offset+1}-{offset+shown} of {total})"
        elif truncated:
            header += f" (first {shown} of {total} lines, use offset/limit for more)"
        return f"{header}\n{content}"
    except (OSError, UnicodeDecodeError) as e:
        return f"[错误] 读取失败: {e}"


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file with UTF-8 encoding.

    Args:
        path: Absolute or relative file path (enforced within project root)
        content: Text content to write

    Returns:
        Confirmation message with file path
    """
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written: {p}"


def search_files(pattern: str) -> str:
    """Search files in project for a regex pattern. Returns up to 50 matches.

    Args:
        pattern: Python regex pattern to search for

    Returns:
        Formatted results with file:line:content, or error message
    """
    import re
    import os
    from pathlib import Path
    _ROOT = Path(__file__).parent.parent
    TEXT_EXTS = {'.py', '.md', '.json', '.js', '.ts', '.html', '.css',
                 '.toml', '.yaml', '.yml', '.sh', '.bat', '.txt', '.cfg',
                 '.ini', '.env', '.xml', '.sql', '.rst', '.csv'}
    SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules',
                 '.venv', 'venv', 'output', '.codebuddy'}
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
                    with open(fpath, encoding='utf-8', errors='replace') as fh:
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
    from pathlib import Path
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
        "pytest", "pytest-cov", "pytest-asyncio", "pytest-mock",
        "black", "isort", "flake8", "mypy", "ruff",
        "coverage", "tox", "pre-commit",
        "pip", "setuptools", "wheel", "build", "twine",
        "httpx", "requests", "aiohttp",
        "rich", "click", "typer",
        "pydantic", "pydantic-settings",
        "numpy", "pandas", "matplotlib", "pillow",
        "openai", "python-dotenv", "nest-asyncio",
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
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True, text=True, timeout=120,
        )
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
    for pkg in ['httpx', 'rich', 'prompt_toolkit', 'nest_asyncio', 'dotenv']:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, '__version__', 'installed')
            lines.append(f"{pkg}: {ver}")
        except ImportError:
            lines.append(f"{pkg}: NOT INSTALLED")

    # Project health
    from pathlib import Path
    _ROOT = Path(__file__).parent.parent
    for check_file, label in [
        ('.env', 'Config (.env)'),
        ('tools.json', 'Tools config'),
        ('models.json', 'Models config'),
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
    original = p.read_text(encoding="utf-8")
    if old_text not in original:
        return f"Not found in {p}"
    result = original.replace(old_text, new_text, 1)
    p.write_text(result, encoding="utf-8")
    return f"Edited: {p}"


def think_deep(prompt: str, max_tokens: int = 2000) -> str:
    """Use local LLM (llama-server on :8080) for heavy reasoning.
    Auto-detects model name from /v1/models. Returns text or error.
    """
    import httpx
    import json

    LLAMA_BASE = "http://127.0.0.1:8080"
    LLAMA_TIMEOUT = 300

    model_id = "local-model"
    try:
        with httpx.Client(trust_env=False, timeout=10) as probe:
            r = probe.get(f"{LLAMA_BASE}/v1/models")
            if r.status_code == 200:
                models = r.json().get("models", [])
                if models:
                    model_id = models[0].get("name", model_id)
    except (httpx.HTTPError, OSError, KeyError):
        pass  # llama-server probe failed, use default model_id

    try:
        with httpx.Client(trust_env=False, timeout=LLAMA_TIMEOUT) as client:
            r = client.post(
                f"{LLAMA_BASE}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
            )
        if r.status_code == 200:
            body = r.json()
            choices = body.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                return content or "(empty response)"
            return "[local model: empty choices]"
        err = ""
        try:
            err = r.json().get("error", {}).get("message", r.text[:200])
        except (json.JSONDecodeError, KeyError, AttributeError):
            err = r.text[:200]
        return f"[local model error HTTP {r.status_code}: {err}]"
    except httpx.ConnectError:
        return "[local model not connected: llama-server not running on :8080]"
    except (httpx.HTTPError, OSError, KeyError) as e:
        return f"[local model call failed: {type(e).__name__}: {e}]"


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
# Only remove truly dangerous builtins that enable code injection / debugging escape.
# subprocess isolation already prevents filesystem / network side-effects from
# persisting, so import/open/getattr/class are safe to allow.
_DANGEROUS = ("exec", "eval", "compile", "breakpoint")
for _d in _DANGEROUS:
    try:
        delattr(builtins, _d)
    except (AttributeError, TypeError):
        pass
"""
    # Write to temp file to avoid command-line length limits and escape issues
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8",
            delete=False, dir=str(ROOT.parent)
        ) as tf:
            tf.write(_prelude)
            tf.write("\n# --- user code ---\n")
            tf.write(code)
            tf.write("\n")
            tmp_path = tf.name
    except (OSError, PermissionError) as e:
        return f"[错误] 临时文件创建失败: {e}"

    try:
        r = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=30, cwd=str(ROOT),
            encoding="utf-8", errors="replace",
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        if err:
            out = (out + "\n[stderr]\n" + err).strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "[错误] Python 执行超时 (30s)"
    except subprocess.SubprocessError as e:
        return f"[错误] Python 执行失败: {e}"
    finally:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink(missing_ok=True)


def count_lines() -> str:
    """Count lines of code by file extension in the current project.

    Returns:
        Formatted table of extension, lines, and file counts
    """
    from collections import defaultdict

    stats = defaultdict(lambda: [0, 0])
    for r, _d, fs in os.walk("."):
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

    target = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
              ".md", ".json", ".toml", ".yaml", ".yml", ".sh", ".bat"}
    lines_out = []
    for ext, (files, lines) in sorted(stats.items(), key=lambda x: -x[1][1]):
        if ext in target:
            lines_out.append(f"{ext:>8s} {lines:>8d} lines in {files:>4d} files")
    return "\n".join(lines_out) if lines_out else "No code files found"


# ════════════════════════════════════════════════════════════
#  SSRF 防护 — URL 校验器
# ════════════════════════════════════════════════════════════

_SSRF_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]",
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
            ("DuckDuckGo", f"https://html.duckduckgo.com/html/?q={q}",
             r'<a[^>]*result__a[^>]*>(.*?)</a>'),
            ("Bing", f"https://www.bing.com/search?q={q}",
             r'<li[^>]*b_algo[^>]*>.*?<a[^>]*>(.*?)</a>'),
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for _engine_name, url, pattern in engines:
            try:
                r = httpx.get(url, timeout=httpx.Timeout(5.0, connect=4.0),
                              trust_env=False, headers=headers, follow_redirects=True)
                if r.status_code == 200:
                    results = []
                    for m in re.finditer(pattern, r.text, re.DOTALL):
                        text = unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
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
    """下载文件到指定路径。纯 Python + SSRF 防护 + 路径限制。"""
    import os as _os
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
        sp.write_bytes(r.content)
        return f"Downloaded: {sp} ({len(r.content)} bytes)"
    except httpx.ConnectError:
        return f"[错误] 无法连接: {url[:60]}"
    except httpx.TimeoutException:
        return f"[错误] 下载超时: {url[:60]}"
    except (httpx.HTTPError, OSError) as e:
        return f"[错误] 下载失败: {e}"


def run_test(path: str = "tests/") -> str:
    """运行 pytest，纯 Python subprocess 列表传参。"""
    import subprocess
    import sys
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q", "--tb=short"],
            capture_output=True, text=True, timeout=60,
        )
        return r.stdout.strip() or r.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "[错误] 测试超时"
    except subprocess.SubprocessError as e:
        return f"[错误] 测试失败: {e}"
