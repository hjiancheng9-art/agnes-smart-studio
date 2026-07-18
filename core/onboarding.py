"""First-run onboarding wizard — guided path to first productive action.

GPT gap fix #4: "Add first-run guided workflow: open project → scan repo →
suggest 3 tasks → run safe demo edit."

Detects first run, provides interactive task suggestions based on repo state.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("crux.onboarding")

ROOT = Path(__file__).resolve().parent.parent
CRUX_HOME = Path.home() / ".crux"
ONBOARDING_MARKER = CRUX_HOME / ".onboarding_complete"


def is_first_run() -> bool:
    """Check if this is the user's first run of CRUX."""
    return not ONBOARDING_MARKER.exists()


def mark_onboarded() -> None:
    """Mark onboarding as complete."""
    CRUX_HOME.mkdir(parents=True, exist_ok=True)
    ONBOARDING_MARKER.write_text("1", encoding="utf-8")


def get_suggestions() -> list[dict]:
    """Generate task suggestions based on current repo state.

    Returns list of {title, command, description} dicts.
    """
    suggestions = []

    # Check git state
    try:
        import subprocess

        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        dirty = len([line for line in (result.stdout or "").split("\n") if line.strip()])
        if dirty > 20:
            suggestions.append(
                {
                    "title": "Commit pending changes",
                    "command": "/commit",
                    "description": f"You have {dirty} uncommitted changes. Start by cleaning up git state.",
                }
            )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    # Check test state
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_smoke.py", "-q", "--no-header", "-p", "no:xdist"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        if result and "failed" in (result.stdout or "").lower():
            suggestions.append(
                {
                    "title": "Fix failing tests",
                    "command": "/test",
                    "description": "Some tests are failing. Run /test to see what needs fixing.",
                }
            )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    # Always available suggestions
    suggestions.append(
        {
            "title": "Ask CRUX to do something",
            "command": "/ask",
            "description": "Describe what you want: 'refactor the message pane' or 'add a new tool'.",
        }
    )
    suggestions.append(
        {
            "title": "Generate an image",
            "command": "/image a cyberpunk cat",
            "description": "Test the media generation pipeline with a quick image prompt.",
        }
    )
    suggestions.append(
        {
            "title": "Check system health",
            "command": "/health",
            "description": "Run a full system diagnostic to verify everything is configured.",
        }
    )

    return suggestions[:5]


def welcome_text(model_name: str = "CRUX") -> str:
    """Generate first-run welcome text."""
    suggestions = get_suggestions()

    lines = [
        "Welcome to CRUX Studio v6.1.0!",
        "",
        f"  Engine:  {model_name}  ·  1M context",
        "  Tools:   47 built-in  ·  Skills: 119 installed / 767 in market",
        "  Arch:    极简内核 · 百器待命 · 七兽按需 · Multi-Agent 已模块化",
        "",
        "  Quick start — try one of these:",
        "",
    ]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"  {i}. {s['title']}")
        lines.append(f"     {s['command']}")
        lines.append(f"     {s['description']}")
        lines.append("")

    lines.append("  Type /help anytime for the full command list.")
    return "\n".join(lines)


def run_onboarding() -> str | None:
    """Run the onboarding flow if first run. Returns welcome text or None."""
    if not is_first_run():
        return None

    try:
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        model_name = mgr.get_model("light") or "CRUX"
    except Exception:
        model_name = "CRUX"

    text = welcome_text(model_name)
    mark_onboarded()
    return text
