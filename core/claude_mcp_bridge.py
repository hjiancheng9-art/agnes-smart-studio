"""Claude Code MCP Bridge — 让 CRUX 获得软件工程工具能力。

通过 stdio JSON-RPC 2.0 暴露 10 个工具给 CRUX 的 mcp_client：
  search_code / find_files / read_file / write_file / edit_file
  run_bash / web_search / web_fetch / git_diff_full / git_log_detailed

Architecture:
  CRUX (mcp_client.py) ──subprocess──→ ClaudeMcpBridge (本文件)
  CRUX 用 /mcp add claude -- python core/claude_mcp_bridge.py 注册后，
  在对话中通过 mcp_call_tool(server="claude", tool="search_code", ...) 调用。

Protocol: JSON-RPC 2.0 over stdio, newline-delimited, 对齐 core/mcp_server.py。
"""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = ["ClaudeMcpBridge", "main"]

# ── 协议常量 ─────────────────────────────────────────────────
MCP_PROTOCOL_VERSION = "2024-11-05"
ERR_PARSE_ERROR = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

ROOT = Path(__file__).resolve().parent.parent


def _server_info() -> dict:
    return {"name": "claude-code-bridge", "version": "1.0.0"}


# ═══════════════════════════════════════════════════════════════
# Tool Definitions
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "search_code",
        "description": (
            "Fast regex code search. Returns matching file paths or lines with "
            "optional context. Supports glob filtering, line offset, result limit, "
            "and multiline mode."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for (ripgrep syntax)",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: project root)",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files, e.g. '*.py' or '*.{ts,tsx}'",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output mode: content shows matching lines, files_with_matches shows paths only, count shows match counts",
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines before and after each match",
                },
                "head_limit": {
                    "type": "integer",
                    "description": "Max number of results to return (default: 50)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip first N results before applying head_limit",
                },
                "multiline": {
                    "type": "boolean",
                    "description": "Enable multiline mode where . matches newlines",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive search",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "find_files",
        "description": (
            "Fast file pattern matching using glob. Returns matching file paths sorted by modification time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern, e.g. '**/*.py' or 'src/**/*.ts'",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: project root)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read file contents. Supports offset and limit for large files. Reads images (PNG, JPG) as base64."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of lines to read",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file. Creates parent directories if needed. "
            "WARNING: overwrites existing files without confirmation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "File contents to write",
                },
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Exact string replacement in a file. Finds old_string in file and "
            "replaces it with new_string. Use replace_all=true to replace every "
            "occurrence. Fails if old_string is not unique (unless replace_all)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Execute a shell command. Uses Windows cmd.exe on Windows, bash on Unix. "
            "Commands are validated against dangerous patterns (rm -rf, fork bombs, "
            "disk formatting, etc.). Timeout: 120s default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60, max: 300)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "web_search",
        "description": ("Search the web and return structured results with titles and URLs."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of results (default: 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": ("Fetch a URL and return its content. Handles redirects. Returns text content up to 100KB."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Max response length in characters (default: 100000)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "git_diff_full",
        "description": (
            "Show complete git diff output. Supports file filtering, staged changes, and commit comparison."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Optional: limit diff to this file",
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes only (default: false)",
                },
                "commit": {
                    "type": "string",
                    "description": "Compare against this commit/branch (default: HEAD for unstaged, HEAD~1 for staged)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_log_detailed",
        "description": ("Show git commit history with flexible formatting and filtering."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (default: 10, max: 100)",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to show log for (default: current)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Only show commits affecting this file",
                },
                "format": {
                    "type": "string",
                    "description": "Pretty format string, e.g. '%h - %s (%an)'",
                },
                "oneline": {
                    "type": "boolean",
                    "description": "One line per commit (default: false)",
                },
            },
            "required": [],
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# Tool Implementations
# ═══════════════════════════════════════════════════════════════


def _resolve_path(raw: str) -> Path:
    """Resolve a file path relative to ROOT if not absolute."""
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p.resolve()


def _run_git(args: list[str], cwd: str = "") -> dict:
    """Run a git command, return {success, stdout, stderr, returncode}."""
    try:
        r = run_subprocess(["git", *args], cwd=cwd or str(ROOT), timeout=30)
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "git not found", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "git command timed out", "returncode": -1}


def _safe_command(command: str) -> tuple[bool, str]:
    """Validate a command against dangerous patterns. Returns (safe, reason)."""
    _ = command.lower()

    dangerous = [
        (r"rm\s+(-rf?|--recursive)\s+/", "recursive delete of root"),
        (r"rmdir\s+[/\\-]?s\s+/", "recursive delete of root"),
        (r">\s*/dev/sda", "raw disk write"),
        (r"mkfs\.", "filesystem format"),
        (r"dd\s+if=", "raw disk operation"),
        (r":\(\)\s*\{\s*:\|:&\s*\}\s*;:", "fork bomb"),
        (r"chmod\s+777\s+/", "world-writable root"),
        (r"format\s+[A-Za-z]:", "Windows disk format"),
        (r"diskpart", "Windows disk partition"),
        (r"cipher\s*/w", "Windows disk wipe"),
        (r"reg\s+delete.*/f", "registry delete force"),
        (r"powershell.*-enc\s+[A-Za-z0-9]", "encoded PowerShell"),
        (r"curl.*\|\s*(ba)?sh", "curl pipe shell"),
        (r"wget.*\|\s*(ba)?sh", "wget pipe shell"),
        (r"del\s+/[fsq]\s+[A-Za-z]:\\", "system delete"),
        (r"shutdown\s+", "system shutdown"),
        (r"reboot", "system reboot"),
    ]

    for pattern, reason in dangerous:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Dangerous command blocked: {reason}"

    return True, ""


# ── Tool handlers (return MCP CallToolResult dict) ────────────


def _handle_search_code(params: dict) -> dict:
    pattern = params.get("pattern", "")
    if not pattern:
        return _tool_error("Missing required parameter: pattern")

    search_path = str(_resolve_path(params.get("path", ".")) if params.get("path") else ROOT)
    glob_filter = params.get("glob", "")
    output_mode = params.get("output_mode", "content")
    context_lines = params.get("context", 0)
    head_limit = params.get("head_limit", 50)
    offset = params.get("offset", 0)
    multiline = params.get("multiline", False)
    case_insensitive = params.get("case_insensitive", False)

    cmd = ["rg", "--no-heading", "--color", "never", "--line-number"]
    if case_insensitive:
        cmd.append("--ignore-case")
    if multiline:
        cmd.extend(["--multiline", "--multiline-dotall"])
    if glob_filter:
        cmd.extend(["--glob", glob_filter])
    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])
    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")

    cmd.append(pattern)
    cmd.append(search_path)

    try:
        r = run_subprocess(cmd, timeout=30)
    except FileNotFoundError:
        # Fallback: use Python's re module for basic search
        return _search_fallback(
            pattern,
            search_path,
            glob_filter,
            output_mode,
            context_lines,
            head_limit,
            offset,
            multiline,
            case_insensitive,
        )
    except subprocess.TimeoutExpired:
        return _tool_error("Search timed out after 30s")

    if r.returncode not in (0, 1):  # 1 = no matches (normal)
        return _tool_error(f"Search failed: {r.stderr[:500]}")

    lines = r.stdout.splitlines()
    total = len(lines)

    if offset > 0:
        lines = lines[offset:]
    if head_limit > 0 and len(lines) > head_limit:
        lines = lines[:head_limit]

    text = "\n".join(lines) if lines else "(no matches found)"
    if len(lines) < total:
        text += f"\n\n[Showing {len(lines)} of {total} results]"

    return {"content": [{"type": "text", "text": text}], "isError": False}


def _search_fallback(
    pattern, search_path, glob_filter, output_mode, context_lines, head_limit, offset, multiline, case_insensitive
):
    """Fallback search using Python stdlib when ripgrep is not available."""
    import fnmatch

    sp = Path(search_path)
    if not sp.exists():
        return _tool_error(f"Path not found: {search_path}")

    flags = re.IGNORECASE if case_insensitive else 0
    if multiline:
        flags |= re.DOTALL

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return _tool_error(f"Invalid regex pattern: {e}")

    results = []
    files = list(sp.rglob("*")) if sp.is_dir() else [sp]

    if glob_filter:
        files = [f for f in files if fnmatch.fnmatch(f.name, glob_filter)]

    for fp in files:
        if not fp.is_file():
            continue
        if fp.suffix not in (
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".html",
            ".css",
            ".json",
            ".md",
            ".txt",
            ".toml",
            ".yaml",
            ".yml",
            ".cfg",
            ".ini",
            ".sh",
            ".bat",
            ".ps1",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".xml",
            ".svg",
        ):
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue

        if multiline:
            file_matches: list = list(regex.finditer(content))
        else:
            file_matches = []
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    file_matches.append((i, line))

        if file_matches:
            if output_mode == "files_with_matches":
                results.append(str(fp.relative_to(ROOT)))
            elif output_mode == "count":
                results.append(f"{fp.relative_to(ROOT)}: {len(file_matches)}")
            else:
                for match in file_matches[:10]:
                    if isinstance(match, tuple):
                        results.append(f"{fp.relative_to(ROOT)}:{match[0]}: {match[1][:200]}")
                    else:
                        results.append(f"{fp.relative_to(ROOT)}: {match.group(0)[:200]}")

    total = len(results)
    if offset > 0:
        results = results[offset:]
    if head_limit > 0 and len(results) > head_limit:
        results = results[:head_limit]

    text = "\n".join(results) if results else "(no matches found)"
    if total > len(results):
        text += f"\n\n[Showing {len(results)} of {total} results]"

    return {"content": [{"type": "text", "text": text}], "isError": False}


def _handle_find_files(params: dict) -> dict:
    pattern = params.get("pattern", "")
    if not pattern:
        return _tool_error("Missing required parameter: pattern")

    base = _resolve_path(params.get("path", ".")) if params.get("path") else ROOT
    if not base.exists():
        return _tool_error(f"Path not found: {base}")

    matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    paths = [str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in matches[:200]]

    text = "\n".join(paths) if paths else "(no files found)"
    if len(matches) > 200:
        text += f"\n\n[Showing 200 of {len(matches)} files]"

    return {"content": [{"type": "text", "text": text}], "isError": False}


def _handle_read_file(params: dict) -> dict:
    file_path = _resolve_path(params.get("file_path", ""))
    if not file_path.exists():
        return _tool_error(f"File not found: {file_path}")
    if file_path.is_dir():
        return _tool_error(f"Path is a directory: {file_path}")

    offset_val = params.get("offset", 0)
    limit_val = params.get("limit", 2000)

    # Image files → read as base64
    if file_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        import base64
        import mimetypes

        mime = mimetypes.guess_type(str(file_path))[0] or "image/png"
        data = file_path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return {
            "content": [
                {"type": "image", "data": b64, "mimeType": mime},
                {"type": "text", "text": f"[Image: {file_path.name}, {len(data)} bytes]"},
            ],
            "isError": False,
        }

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        return _tool_error(f"Failed to read file: {e}")

    lines = content.splitlines()
    total = len(lines)

    if offset_val > 0:
        lines = lines[offset_val:]
    if limit_val > 0 and len(lines) > limit_val:
        lines = lines[:limit_val]

    # Format with line numbers
    start = offset_val + 1 if offset_val > 0 else 1
    result = "\n".join(f"{start + i}\t{line}" for i, line in enumerate(lines))

    if total > len(lines):
        result += f"\n\n[Showing lines {start}-{start + len(lines) - 1} of {total}]"

    return {"content": [{"type": "text", "text": result}], "isError": False}


def _handle_write_file(params: dict) -> dict:
    file_path = params.get("file_path", "")
    content = params.get("content", "")
    if not file_path:
        return _tool_error("Missing required parameter: file_path")

    fp = _resolve_path(file_path)
    fp.parent.mkdir(parents=True, exist_ok=True)

    try:
        fp.write_text(content, encoding="utf-8")
    except (OSError, UnicodeEncodeError) as e:
        return _tool_error(f"Failed to write file: {e}")

    size = fp.stat().st_size
    return {
        "content": [{"type": "text", "text": f"File written: {fp} ({size} bytes, {content.count(chr(10))} lines)"}],
        "isError": False,
    }


def _handle_edit_file(params: dict) -> dict:
    file_path = params.get("file_path", "")
    old_string = params.get("old_string", "")
    new_string = params.get("new_string", "")
    replace_all = params.get("replace_all", False)

    if not file_path:
        return _tool_error("Missing required parameter: file_path")
    if not old_string:
        return _tool_error("Missing required parameter: old_string")

    fp = _resolve_path(file_path)
    if not fp.exists():
        return _tool_error(f"File not found: {file_path}")

    try:
        content = fp.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return _tool_error(f"Failed to read file: {e}")

    if old_string not in content:
        return _tool_error("old_string not found in file")

    count = content.count(old_string)
    if count > 1 and not replace_all:
        return _tool_error(
            f"old_string found {count} times in file. "
            f"Set replace_all=true to replace all, or make old_string more specific."
        )

    if replace_all:
        new_content = content.replace(old_string, new_string)
        replacements = count
    else:
        new_content = content.replace(old_string, new_string, 1)
        replacements = 1

    # Backup before writing
    backup = fp.with_suffix(fp.suffix + ".bak")
    import contextlib

    with contextlib.suppress(OSError):
        backup.write_text(content, encoding="utf-8")

    try:
        fp.write_text(new_content, encoding="utf-8")
    except (OSError, UnicodeEncodeError) as e:
        return _tool_error(f"Failed to write file: {e}")

    return {
        "content": [
            {
                "type": "text",
                "text": f"File edited: {file_path} ({replacements} replacement(s)). Backup at {backup.name}",
            }
        ],
        "isError": False,
    }


def _handle_run_bash(params: dict) -> dict:
    command = params.get("command", "")
    if not command:
        return _tool_error("Missing required parameter: command")

    safe, reason = _safe_command(command)
    if not safe:
        return _tool_error(reason)

    timeout_val = min(params.get("timeout", 120), 120)
    cwd = params.get("cwd", str(ROOT))

    is_windows = sys.platform == "win32"
    try:
        if is_windows:
            r = run_subprocess(["cmd.exe", "/c", command], cwd=cwd, timeout=timeout_val)
        else:
            r = run_subprocess(command, shell=True, cwd=cwd, timeout=timeout_val)
    except subprocess.TimeoutExpired:
        return _tool_error(f"Command timed out after {timeout_val}s")
    except (subprocess.SubprocessError, OSError) as e:
        return _tool_error(f"Command failed: {e}")

    output = r.stdout
    if r.stderr:
        output += f"\n[stderr]\n{r.stderr}"

    if not output.strip():
        output = f"(exit code: {r.returncode})"

    return {"content": [{"type": "text", "text": output[:50000]}], "isError": False}


def _handle_web_search(params: dict) -> dict:
    query = params.get("query", "")
    limit = min(params.get("limit", 10), 20)

    if not query:
        return _tool_error("Missing required parameter: query")

    try:
        # Use DuckDuckGo Lite (no API key needed)
        url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={"User-Agent": "CRUX-Claude-Bridge/1.0"})

        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract result links
        results = []
        for match in re.finditer(
            r'<a[^>]*class="result-link"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>',
            html,
        ):
            url_val = match.group(1)
            title = match.group(2).strip()
            if url_val and title and not url_val.startswith("//duckduckgo.com"):
                results.append(f"{title}\n  {url_val}")
                if len(results) >= limit:
                    break

        if not results:
            # Fallback: extract any link-like patterns
            for match in re.finditer(r'<a[^>]*href="(https?://[^"]*)"[^>]*>([^<]+)</a>', html):
                url_val = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if url_val and title and len(title) > 5:
                    results.append(f"{title}\n  {url_val}")
                    if len(results) >= limit:
                        break

        text = "\n\n".join(results) if results else f"No results found for: {query}"
        return {"content": [{"type": "text", "text": text}], "isError": False}

    except (OSError, ValueError, RuntimeError) as e:
        return _tool_error(f"Web search failed: {e}")


def _handle_web_fetch(params: dict) -> dict:
    url = params.get("url", "")
    max_length = min(params.get("max_length", 100000), 500000)

    if not url:
        return _tool_error("Missing required parameter: url")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CRUX-Claude-Bridge/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Follow redirects (urllib does this by default)
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

            # Try to decode as text
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()

            # Decode with encoding auto-detection for robustness.
            # Chinese websites often declare UTF-8 but serve GBK content.
            try:
                from core.encoding_fix import fix_garbled_bytes

                text, _used_enc, _recovered = fix_garbled_bytes(raw)
            except ImportError:
                # encoding_fix not available, fall back to declared encoding
                try:
                    text = raw.decode(encoding, errors="replace")
                except (UnicodeDecodeError, LookupError):
                    text = raw.decode("utf-8", errors="replace")

            # Strip HTML tags for readability
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) > max_length:
                text = text[:max_length] + f"\n\n[Truncated at {max_length} chars, original: {len(text)} chars]"

            return {"content": [{"type": "text", "text": text}], "isError": False}

    except urllib.error.HTTPError as e:
        return _tool_error(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return _tool_error(f"URL error: {e.reason}")
    except (OSError, ValueError, RuntimeError) as e:
        return _tool_error(f"Web fetch failed: {e}")


def _handle_git_diff_full(params: dict) -> dict:
    file_path = params.get("file_path", "")
    staged = params.get("staged", False)
    commit = params.get("commit", "")

    args = ["diff"]
    if staged:
        args.append("--staged")
    if commit:
        args.append(commit)
    if file_path:
        args.extend(["--", file_path])

    result = _run_git(args)
    if not result["success"] and result["stderr"]:
        return _tool_error(f"git diff failed: {result['stderr']}")

    text = result["stdout"] if result["stdout"] else "(no changes)"
    return {"content": [{"type": "text", "text": text[:50000]}], "isError": False}


def _handle_git_log_detailed(params: dict) -> dict:
    count = min(params.get("count", 10), 100)
    branch = params.get("branch", "")
    file_path = params.get("file_path", "")
    format_str = params.get("format", "")
    oneline = params.get("oneline", False)

    args = ["log", f"-n{count}"]
    if oneline:
        args.append("--oneline")
    if format_str:
        args.extend(["--pretty=format:" + format_str])
    if branch:
        args.append(branch)
    if file_path:
        args.extend(["--", file_path])

    result = _run_git(args)
    if not result["success"] and result["stderr"]:
        return _tool_error(f"git log failed: {result['stderr']}")

    text = result["stdout"] if result["stdout"] else "(no commits)"
    return {"content": [{"type": "text", "text": text[:50000]}], "isError": False}


# ── Tool dispatch table ───────────────────────────────────────

_TOOL_HANDLERS = {
    "search_code": _handle_search_code,
    "find_files": _handle_find_files,
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "edit_file": _handle_edit_file,
    "run_bash": _handle_run_bash,
    "web_search": _handle_web_search,
    "web_fetch": _handle_web_fetch,
    "git_diff_full": _handle_git_diff_full,
    "git_log_detailed": _handle_git_log_detailed,
}


def _tool_error(message: str) -> dict:
    """Construct MCP CallToolResult error form."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


# ═══════════════════════════════════════════════════════════════
# JSON-RPC Server
# ═══════════════════════════════════════════════════════════════


class _JsonRpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ClaudeMcpBridge:
    """stdio JSON-RPC 2.0 MCP server exposing software engineering tools."""

    def __init__(self) -> None:
        try:
            sys.stdout.reconfigure(newline="\n", encoding="utf-8", write_through=True)
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    def run(self) -> None:
        self._log("claude-code-bridge ready (stdin=JSON-RPC, stdout=responses, stderr=log)")
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": ERR_PARSE_ERROR, "message": "Parse error"},
                    }
                )
                continue
            response = self._handle(msg)
            if response is not None:
                self._write(response)
        self._log("stdin EOF, exiting")

    def _handle(self, msg: Any) -> dict | None:
        if not isinstance(msg, dict):
            return self._error(None, ERR_INVALID_REQUEST, "Request must be a JSON object")

        if msg.get("jsonrpc") != "2.0":
            return self._error(msg.get("id"), ERR_INVALID_REQUEST, "Missing or invalid 'jsonrpc' field")

        method = msg.get("method")
        if not isinstance(method, str):
            return self._error(msg.get("id"), ERR_INVALID_REQUEST, "Missing 'method' field")

        is_notification = "id" not in msg
        req_id = msg.get("id")
        params = msg.get("params") or {}

        try:
            handler = self._METHODS.get(method)
            if handler is None:
                if is_notification:
                    return None
                return self._error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
            result = handler(self, params)
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except _JsonRpcError as e:
            if is_notification:
                return None
            return self._error(req_id, e.code, e.message)
        except (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError, AttributeError) as e:
            import traceback

            tb = traceback.format_exc()
            self._log(f"internal error handling {method}: {e!r}\n{tb}")
            if is_notification:
                return None
            return self._error(req_id, ERR_INTERNAL, f"Internal error: {type(e).__name__}: {e}")

    # ── MCP methods ──────────────────────────────────────────

    def _initialize(self, _params: dict) -> dict:
        # Capture workspace roots from the MCP client (IDE)
        roots = _params.get("roots", [])
        if roots:
            import os as _os

            _mcp_roots = []
            for r in roots:
                uri = r.get("uri", "") if isinstance(r, dict) else str(r)
                if uri:
                    _mcp_roots.append(uri)
            if _mcp_roots:
                _os.environ["CRUX_MCP_ROOTS"] = "\n".join(_mcp_roots)
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": _server_info(),
        }

    def _tools_list(self, _params: dict) -> dict:
        return {"tools": TOOLS}

    def _tools_call(self, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _JsonRpcError(ERR_INVALID_PARAMS, "Missing or invalid 'name'")

        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            raise _JsonRpcError(ERR_INVALID_PARAMS, "'arguments' must be an object")

        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return _tool_error(f"Unknown tool: {name}. Use 'tools/list' to see available tools.")

        return handler(args)

    _METHODS = {
        "initialize": _initialize,
        "tools/list": _tools_list,
        "tools/call": _tools_call,
    }

    # ── Helpers ──────────────────────────────────────────────

    def _error(self, req_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def _write(self, obj: dict) -> None:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _log(self, msg: str) -> None:
        sys.stderr.write(f"[claude-bridge] {msg}\n")
        sys.stderr.flush()


# ── Entry Point ───────────────────────────────────────────────


def main() -> None:
    """Entry point: python core/claude_mcp_bridge.py"""
    server = ClaudeMcpBridge()
    try:
        server.run()
    except KeyboardInterrupt:
        server._log("interrupted, exiting")


if __name__ == "__main__":
    main()
