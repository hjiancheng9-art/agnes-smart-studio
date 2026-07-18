#!/usr/bin/env python3
"""Incremental pyright check — fails only when NEW errors are introduced.

Compares current pyright output against the locked baseline in
pyright_baseline.json.  Errors present in the baseline are ignored
(they are pre-existing and triaged).  Errors not in the baseline
cause a non-zero exit.

Usage:
    python scripts/check_pyright_incremental.py          # fail on new errors
    python scripts/check_pyright_incremental.py --accept # update baseline
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "pyright_baseline.json"


def _run_pyright() -> list[dict]:
    """Run pyright and return list of diagnostic dicts."""
    r = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    data = json.loads(r.stdout) if r.stdout else {}
    return data.get("generalDiagnostics", [])


def _diagnostic_key(d: dict) -> str:
    """Stable key for a diagnostic: file + line + message (ignoring range details)."""
    file = d.get("file", "")
    line = d.get("range", {}).get("start", {}).get("line", 0)
    msg = d.get("message", "")[:120]
    return f"{file}:{line}:{msg}"


def main():
    accept = "--accept" in sys.argv

    current = _run_pyright()
    current_keys = {_diagnostic_key(d) for d in current}

    if BASELINE_PATH.exists():
        baseline_data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        baseline = baseline_data.get("generalDiagnostics", [])
        baseline_keys = {_diagnostic_key(d) for d in baseline}
    else:
        baseline_keys = set()

    new_errors = current_keys - baseline_keys
    fixed_errors = baseline_keys - current_keys

    print(f"Total errors: {len(current)} (baseline: {len(baseline_keys)})")
    if fixed_errors:
        print(f"Fixed since baseline: {len(fixed_errors)}")
    if new_errors:
        print(f"NEW errors (not in baseline): {len(new_errors)}")
        for key in sorted(new_errors):
            print(f"  {key}")
    else:
        print("No new errors introduced.")

    if accept:
        new_baseline = {
            "version": "1.1.410",
            "time": str(int(Path(__file__).stat().st_mtime)),
            "generalDiagnostics": current,
        }
        BASELINE_PATH.write_text(json.dumps(new_baseline, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Baseline updated: {BASELINE_PATH} ({len(current)} errors locked)")
        return 0

    if new_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
