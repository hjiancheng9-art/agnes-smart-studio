"""Diff-aware context injection — agents know what changed before acting.

GPT capability fix #2: "Agents must know what just changed before testing,
reviewing, or continuing. Inject diff context into task_executor/multi_agent."

Claude Code pattern: every prompt includes a snapshot of recent changes so the
model doesn't operate on stale assumptions about file state.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Safety: never include these files in diff context (secrets, large binaries)
EXCLUDE_PATTERNS = [
    ".env",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "output/",
    "__pycache__/",
    ".mypy_cache/",
    ".pytest_cache/",
    "*.pyc",
    "*.pyo",
    "node_modules/",
    ".git/",
]

MAX_DIFF_BYTES = 24000  # ~6K tokens at 4 chars/token
MAX_FILE_LIST = 50


@dataclass
class DiffContext:
    """Snapshot of current working-tree changes for agent context injection."""

    branch: str = ""
    changed_files: list[str] = None  # type: ignore
    stat_summary: str = ""  # git diff --stat
    staged_diff: str = ""  # git diff --cached (unified, truncated if large)
    unstaged_diff: str = ""  # git diff (working tree, truncated)
    recent_commits: str = ""  # last 5 commits (one-line)

    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []

    def inject(self, max_bytes: int = MAX_DIFF_BYTES) -> str:
        """Format as an LLM-injectable context block.

        Injects into the system prompt or prepends to the first user message.
        Callsites use this to give agents awareness of current repo state.
        """
        if not self.changed_files and not self.stat_summary:
            return "(clean working tree — no uncommitted changes)"

        lines = [
            "## Working Tree State",
            f"Branch: {self.branch or 'unknown'}",
        ]

        if self.stat_summary.strip():
            lines.append(f"\n### Changes (git diff --stat)\n```\n{self.stat_summary.strip()}\n```")

        if self.staged_diff.strip():
            staged = self.staged_diff
            if len(staged) > max_bytes:
                staged = staged[:max_bytes] + "\n... (truncated)"
            lines.append(f"\n### Staged Diff\n```diff\n{staged.strip()}\n```")

        if self.unstaged_diff.strip() and len(self.unstaged_diff.strip()) + len(self.staged_diff.strip()) < max_bytes:
            unstaged = self.unstaged_diff
            remaining = max_bytes - len(self.staged_diff or "")
            if len(unstaged) > remaining:
                unstaged = unstaged[:remaining] + "\n... (truncated)"
            lines.append(f"\n### Unstaged Diff\n```diff\n{unstaged.strip()}\n```")

        if self.recent_commits.strip():
            lines.append(f"\n### Recent Commits\n```\n{self.recent_commits.strip()}\n```")

        result = "\n".join(lines)
        return result[:max_bytes]


def capture_diff_context() -> DiffContext:
    """Capture the current git working-tree state.

    Returns a DiffContext ready for injection into agent prompts.
    Safe: never reads file contents — only git metadata.
    Fast: all subprocess calls have 10s timeout.
    """
    ctx = DiffContext()

    def _run(args: list[str]) -> str:
        try:
            r = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            return (r.stdout or "") if r else ""
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return ""

    # Branch
    branch = _run(["git", "branch", "--show-current"]).strip()
    ctx.branch = branch or "main"

    # Changed files list
    changed = _run(["git", "diff", "--name-only", "HEAD"]).strip().split("\n")
    ctx.changed_files = [f for f in changed if f][:MAX_FILE_LIST]

    # Stat summary
    ctx.stat_summary = _run(["git", "diff", "--stat", "HEAD"])

    # Staged diff (what's about to be committed)
    ctx.staged_diff = _run(["git", "diff", "--cached", "--unified=3"])

    # Unstaged diff (working tree changes)
    ctx.unstaged_diff = _run(["git", "diff", "--unified=3"])

    # Recent commits
    ctx.recent_commits = _run(["git", "log", "--oneline", "-5"])

    return ctx


def inject_diff_context(prompt: str) -> str:
    """Prepend diff context to an agent prompt. Convenience wrapper.

    Usage:
        enriched = inject_diff_context(original_prompt)
        result = agent.execute(enriched)
    """
    ctx = capture_diff_context()
    context_block = ctx.inject()
    return f"{context_block}\n\n---\n\n{prompt}"
