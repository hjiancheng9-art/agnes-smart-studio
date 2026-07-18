#!/usr/bin/env python3
"""Collect flaky test failure matrix across multiple random seeds."""

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

SEEDS = [1, 42, 99, 7, 13, 77, 100, 200, 300, 404]
ROOT = Path(__file__).resolve().parent.parent

results = {}
for seed in SEEDS:
    start = time.time()
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-q",
            "--tb=line",
            "-p",
            "no:xdist",
            f"--randomly-seed={seed}",
            "-m",
            "not slow and not browser and not network and not mcp and not lsp and not github and not e2e",
            "--timeout=30",
        ],
        capture_output=True,
        timeout=600,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - start
    failed = [l.strip() for l in r.stdout.splitlines() if "FAILED" in l]
    results[str(seed)] = {
        "failures": len(failed),
        "tests": failed,
        "elapsed": round(elapsed),
    }
    print(f"seed={seed}: {len(failed)} failures ({elapsed:.0f}s)", flush=True)

out_path = ROOT / "output" / "flaky_baseline.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

all_fails: Counter[str] = Counter()
for v in results.values():
    for t in v["tests"]:
        short = t.split("::", 1)[1] if "::" in t else t
        all_fails[short] += 1

print(f"\nSaved to {out_path}")
print("Consistently failing (>=8/10 seeds):")
for name, count in all_fails.most_common(30):
    if count >= 8:
        print(f"  {count}/10: {name}")
print("Sporadic (<8/10 seeds):")
for name, count in all_fails.most_common(30):
    if count < 8 and count > 0:
        print(f"  {count}/10: {name}")
