"""Test: "五兽" must only appear in core/lore/ files (narrative flavor).
All other code files must use "七兽".
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_wubeast_only_in_lore():
    """Walk all .py files; "五兽" is allowed only in core/lore/, violations elsewhere."""
    violations = []
    excluded_dirs = {"__pycache__", "node_modules", ".git", ".claude"}

    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # Prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            filepath = Path(dirpath) / filename
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()

            # Skip the test file itself
            if rel == "tests/test_zcode_wubeast.py":
                continue

            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception:
                continue

            if "五兽" not in content:
                continue

            # Allowed only under core/lore/
            if rel.startswith("core/lore/"):
                continue
            if rel.startswith("core/lore_archive/"):
                continue
            violations.append(rel)

    assert violations == [], (
        f"Found '五兽' in {len(violations)} non-lore file(s):\n  "
        + "\n  ".join(violations)
        + "\n\nThese files must use '七兽' instead."
    )
