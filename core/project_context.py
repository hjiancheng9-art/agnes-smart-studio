"""Project Context — inject live project state before every turn.

Gives the model awareness of what's changed since last session,
so it doesn't have to discover the project state from scratch.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def get_project_snapshot() -> str:
    """Fast project context summary for pre-turn injection.

    Returns abbreviated state that fits in <500 tokens:
      - current branch + dirty/clean
      - recent commits (last 3)
      - changed files (max 10)
      - last self-heal result (if available)
    """
    parts = ["[项目状态]"]

    dirty = 0
    r2 = None

    # ── Git branch + status ──
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        branch = r.stdout.strip()
        r2 = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        dirty = len([l for l in r2.stdout.split("\n") if l.strip()])
        parts.append(f"分支 {branch}" + (f"，{dirty} 个文件改动" if dirty else "（干净）"))
    except Exception:
        parts.append("(git 不可用)")

    # ── Recent commits ──
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", "-3", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        commits = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
        if commits:
            parts.append(f"最近提交: {'; '.join(commits[:3])}")
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)

    # ── Changed files ──
    if dirty and r2 is not None:
        try:
            changed = [l[3:] for l in r2.stdout.split("\n")[:10] if len(l) > 3]
            if changed:
                parts.append(f"改动文件: {', '.join(changed[:10])}")
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    # ── Self-heal quick check ──
    try:
        from core.self_heal import SelfHealer

        h = SelfHealer()
        h.scan_syntax()
        if not h.findings:
            parts.append("自检: 语法 OK")
        else:
            parts.append(f"自检: {len(h.findings)} 语法问题待修复")
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)

    return "\n".join(parts)
