#!/usr/bin/env python3
"""Smoke test runner — fast feedback, no I/O, no browser, no network.

Usage:
    python run_smoke_tests.py          # Run all unit tests
    python run_smoke_tests.py --fix    # Run + auto-fix lint issues
"""

import subprocess
import sys


def main():
    fix = "--fix" in sys.argv
    print("=" * 60)
    print("CRUX Smoke Tests")
    print("=" * 60)

    # Step 1: Compile check
    print("\n[1/4] Compile check (core + tests)...")
    r = subprocess.run(
        ["python", "-m", "compileall", "-q", "core", "tests"],
        capture_output=True, text=True, cwd=".",
    )
    if r.returncode != 0:
        print("⚠ Compile errors found:")
        print(r.stderr[:500])
    else:
        print("  ✅ All files compile")

    # Step 2: Unit tests (fast, no I/O)
    print("\n[2/4] Unit tests (fast, no I/O)...")
    r = subprocess.run(
        ["python", "-m", "pytest",
         "tests/test_interfaces.py", "tests/test_approval_gate.py",
         "tests/test_sandbox_executor.py", "tests/test_trm_routing.py",
         "tests/test_contracts.py", "tests/test_capability_registry.py",
         "tests/test_mcp_lsp_contracts.py",
         "-q", "--tb=line", "--maxfail=5"],
        capture_output=True, text=True, timeout=60, cwd=".",
    )
    for line in r.stdout.split("\n"):
        if any(kw in line for kw in ["passed", "failed", "error"]):
            print(f"  {line.strip()}")

    # Step 3: Lint check
    print("\n[3/4] Lint check...")
    r = subprocess.run(
        ["python", "-m", "ruff", "check", "core/interfaces/", "--quiet"],
        capture_output=True, text=True, cwd=".",
    )
    issues = [l for l in r.stdout.split("\n") if l.strip()]
    if issues:
        print(f"  ⚠ {len(issues)} lint issues")
        if fix:
            subprocess.run(["python", "-m", "ruff", "check", "core/interfaces/", "--fix"], cwd=".")
            print("  ✅ Auto-fixed")
    else:
        print("  ✅ No lint issues")

    # Step 4: Format check
    print("\n[4/4] Format check...")
    r = subprocess.run(
        ["python", "-m", "ruff", "format", "--check", "core/interfaces/"],
        capture_output=True, text=True, cwd=".",
    )
    if r.returncode != 0:
        print("  ⚠ Formatting needed")
        if fix:
            subprocess.run(["python", "-m", "ruff", "format", "core/interfaces/"], cwd=".")
            print("  ✅ Auto-formatted")
    else:
        print("  ✅ Formatting OK")

    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
