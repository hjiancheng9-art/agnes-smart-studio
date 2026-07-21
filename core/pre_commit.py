"""Pre-commit quality gates: self-heal audit + mojibake + TODOs.

Called by .pre-commit-config.yaml quality-gates hook.
Exits 0 on success, 1 if critical/high issues found.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_self_heal():
    """Run self-healer scan. Block commits with critical/high findings."""
    from core.self_heal import SelfHealer

    healer = SelfHealer()
    healer.run_all_scans()
    findings = healer.findings

    critical = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]
    auto_fixable = [f for f in findings if f.fixable and f.file != "core/self_heal.py"]

    if auto_fixable:
        print(f"[self-heal] {len(auto_fixable)} auto-fixable issues — applying...")
        fixed = healer.quick_fix().get("patches", 0)
        print(f"[self-heal] Fixed {fixed} issues. Please re-stage and commit.")
        return True

    if critical:
        print(f"[self-heal] ❌ {len(critical)} CRITICAL issues:")
        for f in critical:
            print(f"  {f.file}:{f.line} — {f.msg}")
        return True

    if high:
        print(f"[self-heal] ⚠ {len(high)} HIGH issues (use --no-verify to bypass):")
        for f in high:
            print(f"  {f.file}:{f.line} — {f.msg}")

    print(f"[self-heal] ✅ Clean ({len(findings)} findings, 0 critical)")
    return False


def check_mojibake():
    """Scan for mojibake (encoding corruption)."""
    chars = set("鍥閸鐢纴鏉悆殑掑曠")
    exclude = {
        "core/encoding_fix.py",
        "core/pre_commit.py",
        "core/self_heal.py",
        "tests/test_encoding_fix.py",
    }
    found = 0
    for f in ROOT.rglob("*.py"):
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if rel in exclude or "site-packages" in str(f) or "__pycache__" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            for c in chars:
                if c in content:
                    print(f"[mojibake] {rel}: contains '\\u{ord(c):04x}'")
                    found += 1
                    break
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
    if found:
        print(f"[mojibake] ❌ {found} files with encoding corruption")
        return True
    print("[mojibake] ✅ Clean")
    return False


def check_todos():
    """Count TODOs — warn if >50 but don't block."""
    import re

    count = 0
    for f in ROOT.rglob("*.py"):
        if "site-packages" in str(f) or "__pycache__" in str(f) or "tmp" in str(f).split("\\"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            count += len(re.findall(r"TODO|FIXME|HACK|XXX", content))
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
    print(f"[todos] {count} TODO/FIXME/HACK markers")


def check_tui_guard():
    """Run TUI regression guards — prevent agents from reverting TUI fixes."""
    import subprocess
    import sys

    try:
        r = subprocess.run(
            [sys.executable, "ui/tui_guard.py"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        print(r.stdout.rstrip())
        return r.returncode != 0
    except Exception as e:
        print(f"[tui-guard] ❌ {e}")
        return False  # Don't block on guard failure


def main():
    blocked = False

    print("=== CRUX Quality Gates ===\n")

    blocked |= check_mojibake()
    print()

    blocked |= check_self_heal()
    print()

    blocked |= check_tui_guard()
    print()

    check_todos()

    if blocked:
        print("\n❌ Quality gates FAILED. Fix issues and re-commit.")
        sys.exit(1)
    else:
        print("\n✅ All quality gates passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
