"""Edit proposal pipeline — diff preview → confirm → apply → rollback.

GPT competitive analysis fix #1: "Until CRUX can safely change files with diff
preview, it feels like a smart chat TUI, not a coding tool."

Self-contained pipeline with backup → apply → rollback, independent of PatchEngine.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.edit_pipeline")

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class EditProposal:
    """A single proposed file edit."""

    path: str  # relative to repo root
    original: str  # current file content
    proposed: str  # new content
    description: str = ""  # what this edit does

    @property
    def diff(self) -> str:
        """Unified diff for preview."""
        return "\n".join(
            difflib.unified_diff(
                self.original.splitlines(keepends=True),
                self.proposed.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
                lineterm="",
            )
        )

    @property
    def has_changes(self) -> bool:
        return self.original != self.proposed

    @property
    def change_size(self) -> int:
        """Approximate change size in lines."""
        return abs(len(self.proposed.splitlines()) - len(self.original.splitlines()))


@dataclass
class EditPlan:
    """Collection of proposed edits for one operation."""

    proposals: list[EditProposal] = field(default_factory=list)
    summary: str = ""  # human-readable summary

    @property
    def total_changes(self) -> int:
        return sum(1 for p in self.proposals if p.has_changes)

    @property
    def affected_files(self) -> list[str]:
        return [p.path for p in self.proposals if p.has_changes]

    def format_preview(self, max_lines: int = 200) -> str:
        """Format a concise diff preview for the user."""
        lines = [f"Edit Plan: {self.summary}", f"{self.total_changes} file(s) affected:\n"]
        for p in self.proposals:
            if not p.has_changes:
                continue
            lines.append(f"  {p.path} ({p.change_size:+d} lines)")
            if p.description:
                lines.append(f"    {p.description}")
            diff_lines = p.diff.split("\n")
            if len(diff_lines) > max_lines:
                diff_lines = [*diff_lines[:max_lines], f"... ({len(diff_lines) - max_lines} more lines)"]
            for dl in diff_lines:
                lines.append(f"    {dl}")
        return "\n".join(lines)


class EditPipeline:
    """Safe edit pipeline with preview, confirm, apply, and rollback.

    Usage:
        pipeline = EditPipeline(confirm_fn=my_confirm_callback)
        plan = pipeline.prepare("core/foo.py", new_content, "Add bar()")
        success = pipeline.apply(plan)
        if not success:
            pipeline.rollback(plan)
    """

    def __init__(self, confirm_fn: Callable[[EditPlan], bool] | None = None) -> None:
        self.confirm = confirm_fn or (lambda _: True)  # default: auto-confirm
        self.history: list[EditPlan] = []  # for undo stack
        self._backup_map: dict[str, str] = {}  # path → original content

    def prepare(
        self,
        path: str,
        new_content: str,
        description: str = "",
    ) -> EditPlan:
        """Prepare a single-file edit proposal with diff preview.

        Args:
            path: File path relative to repo root
            new_content: The complete new file content
            description: What this edit achieves
        """
        full_path = ROOT / path
        original = full_path.read_text(encoding="utf-8") if full_path.exists() else ""

        proposal = EditProposal(
            path=path,
            original=original,
            proposed=new_content,
            description=description,
        )
        return EditPlan(proposals=[proposal], summary=description)

    def prepare_multi(
        self,
        edits: list[tuple[str, str, str]],  # [(path, new_content, description), ...]
        summary: str = "",
    ) -> EditPlan:
        """Prepare a multi-file edit plan."""
        proposals = []
        for path, new_content, desc in edits:
            full_path = ROOT / path
            original = full_path.read_text(encoding="utf-8") if full_path.exists() else ""
            proposals.append(EditProposal(path=path, original=original, proposed=new_content, description=desc))
        return EditPlan(proposals=proposals, summary=summary)

    def preview(self, plan: EditPlan) -> str:
        """Return a formatted diff preview string."""
        return plan.format_preview()

    def apply(self, plan: EditPlan) -> bool:
        """Apply the edit plan. Returns True if successful, False on failure."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Backup
        for proposal in plan.proposals:
            full_path = ROOT / proposal.path
            if full_path.exists():
                self._backup_map[proposal.path] = full_path.read_text(encoding="utf-8")

        # Apply
        for proposal in plan.proposals:
            if not proposal.has_changes:
                continue
            full_path = ROOT / proposal.path
            try:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(proposal.proposed, encoding="utf-8")
                logger.info("Applied: %s (%d lines)", proposal.path, proposal.change_size)
            except OSError as e:
                logger.error("Failed to write %s: %s", proposal.path, e)
                self.rollback(plan)
                return False

        self.history.append(plan)
        logger.info("Edit plan applied: %s (%d files) at %s", plan.summary, plan.total_changes, timestamp)
        return True

    def rollback(self, plan: EditPlan) -> bool:
        """Rollback an applied edit plan. Returns True if successful."""
        for proposal in plan.proposals:
            full_path = ROOT / proposal.path
            if proposal.path in self._backup_map:
                try:
                    full_path.write_text(self._backup_map[proposal.path], encoding="utf-8")
                    logger.info("Rolled back: %s", proposal.path)
                except OSError as e:
                    logger.error("Failed to rollback %s: %s", proposal.path, e)
                    return False
            elif not full_path.exists() or proposal.original == "":
                # File was created by this plan — delete it
                try:
                    full_path.unlink(missing_ok=True)
                    logger.info("Removed new file: %s", proposal.path)
                except OSError as e:
                    logger.error("Failed to remove %s: %s", proposal.path, e)
                    return False
        logger.info("Rollback complete: %s", plan.summary)
        return True

    def undo_last(self) -> bool:
        """Undo the most recently applied plan."""
        if not self.history:
            logger.warning("No edit history to undo")
            return False
        plan = self.history.pop()
        return self.rollback(plan)

    def diff_for(self, path: str) -> str:
        """Show current working-tree diff for a file."""
        full_path = ROOT / path
        if not full_path.exists():
            return f"(file not found: {path})"
        try:
            import subprocess

            result = subprocess.run(
                ["git", "diff", "--", path],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            return (result.stdout or "(no changes)") if result else "(git unavailable)"
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return "(git unavailable)"


# Singleton for TUI integration
_pipeline: EditPipeline | None = None


def get_pipeline() -> EditPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = EditPipeline()
    return _pipeline
