#!/usr/bin/env python3
"""Post-tool temp file cleanup Hook — CRUX Studio.
Auto-deletes tmp*.py files from home directory and generated .txt files from project root.
Hook must never block — all errors silently caught.
"""

import logging
import os
import sys
import time


def clean_tmp_py(home: str) -> int:
    """Delete tmp*.py files in user home dir (age > 30s to avoid race)."""
    now = time.time()
    count = 0
    try:
        for f in os.listdir(home):
            if f.startswith("tmp") and f.endswith(".py"):
                fp = os.path.join(home, f)
                try:
                    st = os.stat(fp)
                    if now - st.st_mtime > 30:  # older than 30s = safe
                        os.remove(fp)
                        count += 1
                except (OSError, PermissionError):
                    pass
    except Exception:
        import logging
        logging.getLogger('crux').debug('silent except', exc_info=True)
    return count


def clean_generated_txt(root: str) -> int:
    """Delete auto-generated .txt snippet files from project root.
    Keep: requirements.txt, anything user-created manually.
    Auto-generated patterns: crux_b_*, crux_banner*, splash_*, tui_*, ptk_*, debug_*
    """
    auto_prefixes = ("crux_b_", "crux_banner", "splash_", "tui_", "ptk_", "debug_", "system_prompt_", "entity_")
    keep = {"requirements.txt"}
    count = 0
    try:
        for f in os.listdir(root):
            if f.endswith(".txt") and f not in keep and any(f.startswith(p) for p in auto_prefixes):
                fp = os.path.join(root, f)
                try:
                    os.remove(fp)
                    count += 1
                except (OSError, PermissionError):
                    pass
    except Exception:
        import logging
        logging.getLogger('crux').debug('silent except', exc_info=True)
    return count


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # .claude/hooks/ -> project root
    home = os.path.expanduser("~")

    deleted_py = clean_tmp_py(home)
    deleted_txt = clean_generated_txt(root)

    if deleted_py or deleted_txt:
        parts = []
        if deleted_py:
            parts.append(f"{deleted_py} tmp*.py")
        if deleted_txt:
            parts.append(f"{deleted_txt} .txt snippets")
        print(f"\n  [cleanup] 已清理: {', '.join(parts)}", file=sys.stderr)


if __name__ == "__main__":
    main()
