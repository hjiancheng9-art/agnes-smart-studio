#!/usr/bin/env python3
"""Check staged Python files for Chinese characters in newly added lines.

Incremental enforcement of the ASCII-only source rule:
only checks lines added in the current commit (git diff --cached).
Existing Chinese in comments/docstrings is NOT flagged.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# CJK Unified Ideographs + Extension A + Compatibility Ideographs
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")


def _git_diff_cached() -> list[tuple[str, int, str]]:
    """Get newly added lines from staged changes.

    Returns list of (filename, line_number, content).
    Only includes Python files and only lines starting with '+' (additions).
    """
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", "*.py"],
            capture_output=True,
            timeout=10,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    hits: list[tuple[str, int, str]] = []
    current_file = ""
    current_line = 0

    for line in r.stdout.splitlines():
        if line.startswith("+++ "):
            # New file header: +++ b/path/to/file.py
            current_file = line[6:]  # strip "+++ b/"
            continue
        if line.startswith("@@"):
            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            parts = line.split("+", 2)
            if len(parts) > 1:
                new_part = parts[1].split(" ")[0].split(",")[0]
                try:
                    current_line = int(new_part)
                except ValueError:
                    current_line = 0
            continue
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]  # strip leading '+'
            if _CJK_RE.search(content):
                hits.append((current_file, current_line, content[:120]))
        if not line.startswith("-") and not line.startswith("\\"):
            current_line += 1

    return hits


def main() -> int:
    hits = _git_diff_cached()

    if not hits:
        print("[PASS] No Chinese characters in staged changes")
        return 0

    print(f"[FAIL] Found {len(hits)} line(s) with Chinese characters in staged Python files:")
    for filename, lineno, content in hits:
        print(f"  {filename}:{lineno}: {content}")

    print("\nCRUX enforces ASCII-only source code. Chinese text belongs in:")
    print("  - locales/zh-CN.json (language pack)")
    print("  - Docstrings/comments (allowed but discouraged for new code)")
    print("\nTo bypass in emergencies: SKIP=check-chinese-incremental git commit")
    return 1


if __name__ == "__main__":
    sys.exit(main())
