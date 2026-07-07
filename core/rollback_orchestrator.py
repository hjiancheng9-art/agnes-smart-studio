"""Auto-rollback orchestrator — chains all undo mechanisms.

Wires together: patch.rollback_last(), git stash pop, defense.py snapshots,
and git_workflow.snapshot/restore into a unified rollback system.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("crux.rollback")

# In-memory undo log (survives within session)
_undo_log: list[dict] = []


def auto_snapshot(label: str = "") -> str:
    """Take a pre-operation snapshot. Returns snapshot label."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    snap_label = label or f"auto-{ts}"
    try:
        from core.git_workflow import git_snapshot

        git_snapshot(snap_label)
        _undo_log.append({"label": snap_label, "ts": time.time(), "method": "git_stash"})
        logger.debug("snapshot created: %s", snap_label)
        return snap_label
    except Exception as e:
        logger.debug("snapshot failed: %s", e)
        return ""


def rollback_last_op() -> dict:
    """Undo the last operation using chain fallback.
    Returns {"success": bool, "method": str, "detail": str}.
    """
    # 1. Try patch.rollback_last (most recent file edits)
    try:
        from core.patch import rollback_last

        result = rollback_last()
        if result.get("success"):
            return {"success": True, "method": "patch_undo", "detail": "rolled back last patch"}
    except Exception as e:
        logger.debug("patch undo failed: %s", e)

    # 2. Try git stash pop (most recent git snapshot)
    try:
        from core.git_workflow import GitWorkflow

        gw = GitWorkflow()
        stashes = gw._list_stashes()
        if stashes:
            gw.restore_snapshot()
            return {"success": True, "method": "git_stash_pop", "detail": "restored git stash"}
    except Exception as e:
        logger.debug("git stash pop failed: %s", e)

    return {"success": False, "method": "none", "detail": "no undo mechanism available"}


def rollback_to_snapshot(label: str) -> dict:
    """Rollback to a specific named snapshot."""
    try:
        from core.git_workflow import GitWorkflow

        gw = GitWorkflow()
        gw.restore_snapshot(label)
        return {"success": True, "method": "git_stash_pop", "detail": f"restored snapshot: {label}"}
    except Exception as e:
        return {"success": False, "method": "none", "detail": str(e)}


def list_snapshots() -> list[str]:
    """List available rollback snapshots."""
    try:
        from core.git_workflow import GitWorkflow

        gw = GitWorkflow()
        return gw._list_stashes()
    except Exception:
        return []
