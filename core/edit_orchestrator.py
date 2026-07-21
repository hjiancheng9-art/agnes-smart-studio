"""Git-aware editing — auto-commit + repo map for multi-file code changes.

Inspired by Aider's core value: every edit is a git commit, and the LLM
can see the project structure.  Zero external dependencies.

Usage:
    from core.edit_orchestrator import auto_commit, repo_context

    # After any file write/edit:
    auto_commit(filepath, "fix: correct typo in config loader")

    # Inject into system prompt:
    system_prompt += repo_context()
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def auto_commit(filepath: str, message: str) -> str:
    """Stage + commit a file change. Returns commit message or empty string.

    Only commits if CRUX_AUTO_COMMIT=true env var is set.
    """
    if os.environ.get("CRUX_AUTO_COMMIT", "").strip().lower() != "true":
        return ""
    try:
        p = Path(filepath)
        rel = str(p.resolve().relative_to(ROOT.resolve())) if p.is_absolute() else filepath
        r = subprocess.run(
            ["git", "add", rel],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            return ""
        r = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT),
        )
        if r.returncode == 0:
            return message
        return ""
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return ""


def repo_context(max_items: int = 12) -> str:
    """Generate a compact repo map for the LLM system prompt.

    Shows project structure, key symbols, and recently changed files.
    Returns empty string if repo map is unavailable.
    """
    try:
        from core.repo_map import get_repo_map

        rm = get_repo_map()
        rm.scan()
        summary = rm.context_summary(max_items=max_items)
        if summary:
            return f"\n\n[Project structure — {max_items} key files]\n{summary}"
    except (ImportError, OSError):
        pass
    return ""
