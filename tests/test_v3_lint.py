"""Verify v3 app has no lint issues (F821 undefined names)."""

import subprocess
import sys
from pathlib import Path


def test_no_undefined_names_in_app() -> None:
    """queue.Empty must not trigger F821."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F821", "ui/v3/app.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    f821_lines = [l for l in result.stdout.splitlines() if "F821" in l]
    assert not f821_lines, "Found F821 undefined name errors in ui/v3/app.py:\n" + "\n".join(f821_lines)
