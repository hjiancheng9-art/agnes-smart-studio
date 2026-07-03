#!/usr/bin/env python3
"""Post-test resource check Hook — CRUX Studio.
Checks for lingering high-memory Python processes after Bash commands.
Warns if worker processes from previous test/build runs are still alive.
"""
import subprocess
import sys

# Only check after commands that look like tests/builds
# (Hook can't inspect the actual command, so we check every Bash call
#  but only warn when residue is found)
try:
    result = subprocess.run(
        ["tasklist", "/fi", "imagename eq python.exe", "/fo", "csv", "/nh"],
        capture_output=True, text=True, timeout=5,
    )
    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]

    high_mem = []
    for line in lines:
        parts = line.replace('"', "").split(",")
        if len(parts) >= 5:
            try:
                mem_kb = int(parts[4].strip())
                pid = parts[1].strip()
                # > 100MB = suspicious test worker
                if mem_kb > 100000:
                    high_mem.append((pid, mem_kb // 1024))
            except (ValueError, IndexError):
                continue

    if high_mem:
        print("\n  [Hook: resource-check] High-memory Python processes detected:", file=sys.stderr)
        for pid, mem_mb in high_mem:
            print(f"    PID {pid}: {mem_mb}MB", file=sys.stderr)
        print("  Consider: taskkill //F //FI \"MEMUSAGE gt 40000\" //IM \"python.exe\"", file=sys.stderr)
        print("", file=sys.stderr)

except Exception:
    pass  # Hook must never block
