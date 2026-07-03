"""Code formatting & linting tools.

Provides run_format (auto-detect and apply formatter) and run_lint
(static analysis with ruff/eslint) for Python and JS/TS projects.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_subprocess(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> dict:
    """Run a subprocess and return {ok, stdout, stderr, returncode}."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd or str(ROOT), shell=False,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"Command not found: {cmd[0]}", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timeout ({timeout}s): {' '.join(cmd)}", "returncode": -1}


def _detect_language(paths: list[str]) -> str:
    """Detect primary language from file extensions. Returns 'python' or 'javascript'."""
    py_exts = {".py"}
    js_exts = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    for p in paths:
        ext = Path(p).suffix.lower()
        if ext in py_exts:
            return "python"
        if ext in js_exts:
            return "javascript"
    return "python"  # default


def execute_run_format(paths: str = "", check: bool = False) -> str:
    """Format code files in-place.

    Python: ruff format + isort
    JavaScript/TypeScript: prettier (if available)

    Args:
        paths: Space-separated file/directory paths (default: all tracked Python files)
        check: If True, only check without modifying (dry-run)
    """
    targets = [p.strip() for p in paths.split() if p.strip()] if paths.strip() else []
    lang = _detect_language(targets) if targets else "python"

    results = []
    cwd = str(ROOT)

    if lang == "python":
        # ruff format
        ruff_args = ["ruff", "format"]
        if check:
            ruff_args.append("--check")
        ruff_args.extend(targets if targets else ["."])
        r = _run_subprocess(ruff_args, cwd=cwd)
        results.append({"tool": "ruff format", "check_only": check, **r})

        # isort
        isort_args = ["isort"]
        if check:
            isort_args.append("--check-only")
        isort_args.extend(targets if targets else ["."])
        r2 = _run_subprocess(isort_args, cwd=cwd)
        results.append({"tool": "isort", "check_only": check, **r2})
    else:
        # prettier
        prettier_args = ["npx", "prettier"]
        if check:
            prettier_args.append("--check")
        else:
            prettier_args.append("--write")
        prettier_args.extend(targets if targets else ["."])
        r = _run_subprocess(prettier_args, cwd=cwd, timeout=120)
        results.append({"tool": "prettier", "check_only": check, **r})

    any_fail = any(not r["ok"] for r in results)
    return json.dumps({
        "ok": not any_fail,
        "language": lang,
        "results": results,
    }, ensure_ascii=False, indent=2)


def execute_run_lint(paths: str = "", fix: bool = False) -> str:
    """Run static analysis / linting.

    Python: ruff check
    JavaScript/TypeScript: eslint

    Args:
        paths: Space-separated file/directory paths
        fix: If True, auto-fix issues where possible
    """
    targets = [p.strip() for p in paths.split() if p.strip()] if paths.strip() else []
    lang = _detect_language(targets) if targets else "python"

    cwd = str(ROOT)

    if lang == "python":
        cmd = ["ruff", "check"]
        if fix:
            cmd.append("--fix")
        cmd.extend(targets if targets else ["."])
        r = _run_subprocess(cmd, cwd=cwd)
    else:
        cmd = ["npx", "eslint"]
        if fix:
            cmd.append("--fix")
        cmd.extend(targets if targets else ["."])
        r = _run_subprocess(cmd, cwd=cwd, timeout=120)

    return json.dumps({
        "ok": r["ok"],
        "tool": "ruff check" if lang == "python" else "eslint",
        "fix_applied": fix,
        "stdout": r["stdout"][:4000],
        "stderr": r["stderr"][:2000],
        "returncode": r["returncode"],
    }, ensure_ascii=False, indent=2)


# ── Tool definitions ────────────────────────────────────────

FORMAT_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "run_format",
            "description": "Auto-format code files. Detects language and applies the correct formatter: ruff format + isort for Python, prettier for JS/TS/HTML/CSS. Use --check for dry-run without modifying files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "string",
                        "description": "Space-separated file/directory paths to format. Default: all tracked files in project.",
                    },
                    "check": {
                        "type": "boolean",
                        "description": "If true, only check formatting without modifying files (dry-run).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_lint",
            "description": "Run static analysis / linting. Detects language and uses ruff check (Python) or eslint (JS/TS). Use --fix to auto-fix issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "string",
                        "description": "Space-separated file/directory paths to lint. Default: all tracked files.",
                    },
                    "fix": {
                        "type": "boolean",
                        "description": "If true, auto-fix lint issues where possible.",
                    },
                },
                "required": [],
            },
        },
    },
]

FORMAT_EXECUTOR_MAP = {
    "run_format": lambda **kw: execute_run_format(
        paths=str(kw.get("paths", "")),
        check=bool(kw.get("check", False)),
    ),
    "run_lint": lambda **kw: execute_run_lint(
        paths=str(kw.get("paths", "")),
        fix=bool(kw.get("fix", False)),
    ),
}
