"""Pre-commit quality gates — automated checks before git commit.

Mirrors Claude Code's smart-commit skill: runs TODO scan, mojibake check,
syntax validation, and test smoke before allowing commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mojiabke scan — dangerous characters that signal encoding corruption
_MOJIBAKE_CHARS = set("鍥閸鐢纴鏉悆殑掑曠")
# Known files that intentionally contain mojibake signature characters.
_MOJIBAKE_EXCLUDE: set[str] = {
    "core/pre_commit.py",
    "core/self_heal.py",
    "core/encoding_fix.py",
    ".github/workflows/ci.yml",
}


def run_quality_gates(files: list[str] | None = None) -> tuple[bool, str]:
    """Run all quality gates. Returns (passed, report)."""
    results: list[str] = []
    all_pass = True

    # Gate 1: Detect TODO/FIXME in staged changes
    if files is None:
        files = _staged_files()
    for f in files:
        if not f.endswith(".py"):
            continue
        p = ROOT / f
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") and ("TODO" in stripped or "FIXME" in stripped):
                results.append(f"  {f}:{i}: {stripped[:120]}")
    if results:
        all_pass = False
        results.insert(0, f"[FAIL] Found {len(results)} TODO/FIXME markers:")

    # Gate 2: Mojiabke scan
    mojibake_hits = 0
    for f in files or []:
        if not f.endswith((".py", ".bat", ".sh", ".json", ".md")):
            continue
        if f in _MOJIBAKE_EXCLUDE:
            continue
        p = ROOT / f
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for ch in _MOJIBAKE_CHARS:
            if ch in content:
                mojibake_hits += 1
                results.append(f"  {f}: mojibake char U+{ord(ch):04X}")
                break
    if mojibake_hits:
        all_pass = False
        results.insert(-len(results) if results else 0, f"[FAIL] Mojiabke detected in {mojibake_hits} files:")

    # Gate 3: Syntax check
    syntax_errors = 0
    for f in files or []:
        if not f.endswith(".py"):
            continue
        p = ROOT / f
        if not p.exists():
            continue
        try:
            import ast

            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            syntax_errors += 1
            results.append(f"  {f}:{e.lineno}: {e.msg}")
    if syntax_errors:
        all_pass = False
        results.insert(-syntax_errors, f"[FAIL] {syntax_errors} syntax errors:")

    # Gate 4: Quick smoke test (optional, may be slow)
    # Skipped by default; use --smoke flag to enable

    if all_pass:
        results.append("[PASS] All quality gates passed")
    return all_pass, "\n".join(results)


def _staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(ROOT),
        )
        return [f.strip() for f in r.stdout.splitlines() if f.strip()]
    except Exception:
        return []


# ── CLI ───────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="CRUX pre-commit quality gates")
    p.add_argument("files", nargs="*", help="Files to check (default: staged)")
    p.add_argument("--smoke", action="store_true", help="Also run quick smoke test")
    args = p.parse_args()

    files = args.files if args.files else _staged_files()
    if not files:
        print("[SKIP] No files to check")
        sys.exit(0)

    ok, report = run_quality_gates(files)
    print(report)
    if args.smoke and ok:
        print("\nRunning smoke test...")
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_smoke.py", "--quick", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        print(r.stdout[-500:] if r.stdout else r.stderr[-500:])
        if r.returncode != 0:
            print("[FAIL] Smoke test failed")
            sys.exit(1)
    sys.exit(0 if ok else 1)
