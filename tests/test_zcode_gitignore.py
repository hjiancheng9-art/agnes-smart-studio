"""Test .gitignore covers output/ runtime artifacts (Issue 5)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = ROOT / ".gitignore"


def _read_gitignore():
    return GITIGNORE.read_text(encoding="utf-8")


def test_output_in_gitignore():
    """Verify .gitignore contains output/ entry (or sub-entries)."""
    content = _read_gitignore()
    lines = [line.strip() for line in content.splitlines()]
    # Must have either a blanket output/ or the specific sub-entries
    assert "output/" in lines or "output/browser_sessions/" in lines, (
        ".gitignore must contain output/ or output/browser_sessions/"
    )


def test_history_in_gitignore():
    """Verify .gitignore contains output/history.json or *.json under output."""
    content = _read_gitignore()
    lines = [line.strip() for line in content.splitlines()]
    assert (
        "output/history.json" in lines
        or "output/*.json" in lines
    ), ".gitignore must contain output/history.json or output/*.json"


def test_runtime_artifacts_in_gitignore():
    """Verify .gitignore specifically covers known runtime output files."""
    content = _read_gitignore()
    lines = [line.strip() for line in content.splitlines()]

    required_entries = [
        "output/browser_sessions/",
        "output/images/",
        "output/history.json",
        "output/last_error.txt",
        "output/bypass_cache.json",
        "output/cost_log.jsonl",
        "output/cost_state.json",
        "output/tool_audit.jsonl",
    ]

    missing = [e for e in required_entries if e not in lines]
    # If output/ blanket is present, specific entries are optional
    if "output/" in lines:
        return  # blanket covers everything
    assert not missing, f"Missing .gitignore entries: {missing}"
