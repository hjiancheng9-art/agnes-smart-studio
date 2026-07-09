"""PR description generator — turns working-tree state into a pull request body.

GPT fix #3: "You already have git automation and diff context; this turns
completed work into shareable engineering output."

Uses diff_context + repo_map to collect evidence, then formats a structured
PR template ready for GitHub.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.diff_context import capture_diff_context
from core.repo_map import get_repo_map

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PRInfo:
    """Structured PR metadata extracted from repo state."""

    title: str = ""
    summary: str = ""  # bullet-point summary of changes
    changed_files: list[str] = None
    stat_summary: str = ""
    diff_summary: str = ""  # first 2000 chars of diff
    tests_run: str = ""
    risks: list[str] = None
    checklist: str = ""

    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []
        if self.risks is None:
            self.risks = []

    def format(self) -> str:
        """Format as a markdown PR body."""
        files_list = "\n".join(f"- `{f}`" for f in self.changed_files[:20])
        if len(self.changed_files) > 20:
            files_list += f"\n- ... and {len(self.changed_files) - 20} more files"

        risks_text = "\n".join(f"- {r}" for r in self.risks) if self.risks else "- None identified"

        return f"""## Summary

{self.summary}

## Changed Files

{files_list}

## Diff Summary

```
{self.stat_summary.strip() if self.stat_summary else "(no changes)"}
```

## Tests

{self.tests_run or "_(not run)_"}

## Risks

{risks_text}

## Checklist

- [ ] Tests pass locally
- [ ] No unrelated changes
- [ ] Breaking changes documented
- [ ] Rollback plan identified

---
🤖 Generated with [CRUX Studio](https://github.com/huangjiancheng/crux-studio)
"""


def generate_pr_description(
    *,
    title: str = "",
    summary: str = "",
    run_tests: bool = False,
) -> PRInfo:
    """Generate a PR description from the current git state.

    Args:
        title: Optional PR title. Auto-generated from branch/commits if empty.
        summary: Optional summary. Auto-generated from diff if empty.
        run_tests: If True, also run tests and include results.

    Returns:
        PRInfo ready for .format() or direct use.
    """
    ctx = capture_diff_context()
    repo = get_repo_map()

    info = PRInfo()

    # Title: from arg, or from recent commit, or from branch
    if title:
        info.title = title
    else:
        info.title = _guess_title()

    # Changed files
    info.changed_files = ctx.changed_files
    info.stat_summary = ctx.stat_summary

    # Diff summary (abbreviated)
    info.diff_summary = ctx.staged_diff[:2000] if ctx.staged_diff else ctx.unstaged_diff[:2000]

    # Summary
    if summary:
        info.summary = summary
    else:
        info.summary = _summarize_changes(ctx, repo)

    # Risks (simple heuristics)
    info.risks = _assess_risks(ctx)

    # Tests
    if run_tests:
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--no-header", "-p", "no:xdist"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            info.tests_run = (result.stdout or "")[:500] or (result.stderr or "")[:500]
        except (subprocess.TimeoutExpired, OSError):
            info.tests_run = "_(could not run — timeout or error)_"

    return info


# ── Internal helpers ──────────────────────────────────────────


def _guess_title() -> str:
    """Guess PR title from recent commits or branch."""
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        if r.stdout.strip():
            return r.stdout.strip().split(" ", 1)[-1] if " " in r.stdout.strip() else r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return "Update CRUX Studio"


def _summarize_changes(ctx, repo) -> str:
    """Auto-summarize based on what files changed."""
    points = []
    categories = set()

    for f in ctx.changed_files:
        if "test" in f.lower():
            categories.add("test")
        elif f.startswith("core/"):
            categories.add("core")
        elif f.startswith("ui/"):
            categories.add("ui")
        elif f.startswith("tools/"):
            categories.add("tools")
        else:
            categories.add("config/infra")

    if "ui" in categories:
        points.append("- UI/layout updates")
    if "core" in categories:
        points.append("- Core logic or engine changes")
    if "test" in categories:
        points.append("- Test suite updates")
    if "tools" in categories:
        points.append("- Tool definitions or tool behavior")
    if "config/infra" in categories:
        points.append("- Configuration, docs, or infrastructure")

    points.append(f"- {len(ctx.changed_files)} files changed")
    return "\n".join(points) if points else "_(auto-generated summary)_"


def _assess_risks(ctx) -> list[str]:
    """Simple risk heuristics based on what files changed."""
    risks = []
    for f in ctx.changed_files:
        if "config" in f.lower() or f.endswith(".env") or f.endswith("models.json"):
            risks.append("Configuration file changed — verify env-specific values")
        if "mcp" in f.lower() or "provider" in f.lower():
            risks.append("Provider/MCP changes — verify connectivity end-to-end")
        if f.startswith("core/") and not f.startswith("core/test"):
            risks.append("Core module changed — run full test suite")
        if len(f) > 3:
            break  # Just flag the first significant file
    if ctx.stat_summary and len(ctx.stat_summary.split("\n")) > 20:
        risks.append("Large diff (>20 files) — review for scope creep")
    if not risks:
        risks.append("Minimal risk — small, focused change")
    return risks[:3]
