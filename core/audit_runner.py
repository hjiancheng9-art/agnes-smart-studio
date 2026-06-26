"""Audit runner — unified diagnostic functions used by UI commands.

Extracted from ui/mixins/diag.py and ui/self_commands.py to eliminate
code duplication. Both /self check, /self files, /self health, /self fix,
and /self audit now delegate here.
"""

import ast
import os
import sys
from pathlib import Path

__all__ = [
    "ROOT",
    "audit_syntax",
    "audit_deps",
    "collect_source_snippets",
    "project_tree_data",
    "health_checks",
    "health_summary",
]


ROOT = Path(__file__).resolve().parent.parent

from core.constraints import PROJECT_SKIP_DIRS as _SKIP_DIRS

# ── Syntax scan ──────────────────────────────────────────────────────────


def audit_syntax(root: Path | str | None = None) -> list[str]:
    """Scan all .py files under *root* for syntax errors.

    Returns a list of error strings (one per broken file).
    """
    root = Path(root) if root else ROOT
    errors: list[str] = []
    for dp, _dirs, files in os.walk(root):
        # Match skip dirs by path segment, not substring (avoids false
        # positives like "output" matching ".../test_skips_output_dir0/")
        parts = Path(dp).parts
        if any(part in _SKIP_DIRS for part in parts):
            continue
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            fp = os.path.join(dp, f)
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    ast.parse(fh.read(), filename=str(fp))
            except SyntaxError:
                errors.append(str(Path(fp).relative_to(root)))
    return errors


# ── Dependency / health checks ─────────────────────────────────────────────


def audit_deps() -> tuple[bool, str]:
    """Check that all required packages are importable.

    Returns (ok, message).
    """
    try:
        import httpx  # noqa: F401
        import rich  # noqa: F401
        from dotenv import load_dotenv  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        return False, f"Missing dependency: {exc.name}"
    return True, "All dependencies installed"


def health_checks() -> list[dict]:
    """Return a list of health check results.

    Each entry: {"category": str, "ok": bool, "message": str}.
    """
    results = []

    # API key
    try:
        from core.config import SETTINGS

        key_ok = bool(SETTINGS.api_key) and "sk-your" not in SETTINGS.api_key
        results.append({"category": "API Key", "ok": key_ok, "message": "configured" if key_ok else "not configured"})
    except (ImportError, AttributeError):
        results.append({"category": "API Key", "ok": False, "message": "cannot check"})

    # Python version
    results.append(
        {
            "category": "Python",
            "ok": sys.version_info >= (3, 10),
            "message": sys.version.split()[0],
        }
    )

    # Dependencies
    ok, msg = audit_deps()
    results.append({"category": "Dependencies", "ok": ok, "message": msg})

    return results


def health_summary() -> str:
    """Return a single-line health summary string."""
    checks = health_checks()
    ok_count = sum(1 for c in checks if c["ok"])
    fail_count = len(checks) - ok_count
    return f"{ok_count} OK, {fail_count} failed"


# ── Source snippet collection ──────────────────────────────────────────────


def collect_source_snippets(
    root: Path | str | None = None,
    dirs: list[str] | None = None,
    max_chars: int = 50_000,
    max_per_file: int = 3_000,
    max_files_per_dir: int = 4,
) -> str:
    """Collect Python source snippets for AI analysis.

    Returns a Markdown-formatted string suitable as LLM context.
    """
    root = Path(root) if root else ROOT
    dirs = dirs or ["core", "engines"]
    total = 0
    parts: list[str] = []

    for sub in dirs:
        sub_path = root / sub
        if not sub_path.is_dir():
            continue
        for dp, _dirs_in_dir, files in os.walk(sub_path):
            selected = [f for f in files if f.endswith(".py")][:max_files_per_dir]
            for f in selected:
                if total >= max_chars:
                    break
                fp = os.path.join(dp, f)
                rel = os.path.relpath(fp, root)
                try:
                    with open(fp, encoding="utf-8") as fh:
                        content = fh.read()[:max_per_file]
                    parts.append(f"### {rel}\n```python\n{content}\n```\n\n")
                    total += len(content)
                except (OSError, UnicodeDecodeError):
                    pass
            if total >= max_chars:
                break

    return "".join(parts)


# ── Project tree ───────────────────────────────────────────────────────────


def project_tree_data(root: Path | str | None = None, depth: int = 2) -> list[dict]:
    """Return the project directory tree as structured data.

    Each entry: {"name": str, "is_dir": bool, "children": list[dict]}.
    Suitable for rendering with Rich Tree or JSON output.
    """
    root = Path(root) if root else ROOT
    items: list[dict] = []
    for item in sorted(root.iterdir()):
        if item.name.startswith(".") or item.name == "__pycache__":
            continue
        if item.is_dir():
            children = [
                {"name": sub.name, "is_dir": sub.is_dir(), "children": []}
                for sub in sorted(item.iterdir())[:depth]
                if not sub.name.startswith(".")
            ]
            items.append({"name": item.name + "/", "is_dir": True, "children": children})
        else:
            items.append({"name": item.name, "is_dir": False, "children": []})
    return items
