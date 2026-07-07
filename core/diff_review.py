"""Diff review & approve loop — POST_TOOL_USE hook for safe code changes.

Captures file edits via post-edit diff snapshots, surfaces them
for user confirmation before applying the next write. Integrates
with the existing permission system (core/permission.py) and hook
pipeline (core/hooks.py).
"""

from __future__ import annotations

import contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DiffReviewer:
    """Collects diffs from write/edit tools, presents for approval.

    Usage in POST_TOOL_USE hook:
        reviewer = DiffReviewer.get()
        reviewer.capture(tool_name, file_path)
        # At end of agent turn, call reviewer.pending_diffs() to show summary.
    """

    _instance: DiffReviewer | None = None

    def __init__(self):
        self._changes: list[dict] = []
        self._snapshots: dict[str, str] = {}  # path -> pre-edit content

    @classmethod
    def get(cls) -> DiffReviewer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def snapshot(self, file_path: str) -> None:
        """Save pre-edit content for later diff."""
        p = Path(file_path)
        if p.exists():
            with contextlib.suppress(Exception):
                self._snapshots[file_path] = p.read_text(encoding="utf-8")

    def capture(self, tool_name: str, file_path: str, result_ok: bool = True) -> str | None:
        """Capture a post-edit diff. Returns diff string or None."""
        if not result_ok:
            return None
        p = Path(file_path)
        if not p.exists():
            return None
        try:
            current = p.read_text(encoding="utf-8")
        except Exception:
            return None
        old = self._snapshots.pop(file_path, None)
        if old is None:
            return None
        if old == current:
            return None
        diff = self._compute_diff(file_path, old, current)
        self._changes.append(
            {
                "tool": tool_name,
                "file": file_path,
                "diff": diff,
            }
        )
        return diff

    def pending_diffs(self) -> list[dict]:
        """Return all collected diffs and clear."""
        result = list(self._changes)
        self._changes.clear()
        return result

    def has_pending(self) -> bool:
        return len(self._changes) > 0

    @staticmethod
    def _compute_diff(file_path: str, old: str, new: str) -> str:
        """Compute a simple unified diff between old and new content."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        # Simple line-by-line diff
        result = [f"--- a/{file_path}", f"+++ b/{file_path}"]
        added = 0
        removed = 0
        i = j = 0
        while i < len(old_lines) or j < len(new_lines):
            if i < len(old_lines) and j < len(new_lines) and old_lines[i] == new_lines[j]:
                i += 1
                j += 1
            elif j < len(new_lines):
                result.append(f"+{new_lines[j].rstrip()}")
                added += 1
                j += 1
            elif i < len(old_lines):
                result.append(f"-{old_lines[i].rstrip()}")
                removed += 1
                i += 1
            else:
                break
        result.append(f"\n@@ -{removed} +{added} @@")
        return "\n".join(result)


# ── POST_TOOL_USE hook for integration ──────────────────────


def diff_review_hook(tool_name: str, args: dict, result: str) -> str | None:
    """POST_TOOL_USE hook: capture diffs after write/edit operations.

    Returns annotation string to append to tool result, or None.
    """
    if tool_name not in ("write_file", "edit_file", "patch_file"):
        return None

    reviewer = DiffReviewer.get()
    file_path = args.get("file_path", args.get("target", args.get("path", "")))
    if not file_path:
        return None

    ok = "[错误]" not in result and "error" not in result.lower()[:100]
    diff = reviewer.capture(tool_name, file_path, result_ok=ok)
    if diff:
        return f"\n\n[Diffs pending review — {reviewer._changes[-1]['file']} changed]"
    return None


def register_diff_review_hook():
    """Register the diff review hook into the global hook system."""
    try:
        from core.hooks import HookType, register_hook

        register_hook(HookType.POST_TOOL_USE, diff_review_hook, priority=50)
    except ImportError:
        pass
