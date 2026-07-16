"""Self-Audit Runner — orchestrates all audit suites, produces trace report.

Usage:
    python -m tests.self_audit.audit_runner              # full audit
    python -m tests.self_audit.audit_runner --quick       # skip CDP + slow tests
    python -m tests.self_audit.audit_runner --suite tool  # specific suite
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("output/self_audit")


def banner(text: str) -> str:
    width = 60
    return f"\n{'=' * width}\n  {text}\n{'=' * width}\n"


def run_pytest(args: list[str]) -> dict:
    """Run pytest and capture results."""
    cmd = [sys.executable, "-m", "pytest", *args]
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    duration = time.time() - start

    # Parse summary
    summary = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for line in result.stdout.split("\n"):
        if "passed" in line and "failed" in line:
            parts = line.strip().split(",")
            for p in parts:
                p = p.strip()
                if "passed" in p:
                    with contextlib.suppress(ValueError):
                        summary["passed"] = int(p.split()[0])
                elif "failed" in p:
                    with contextlib.suppress(ValueError):
                        summary["failed"] = int(p.split()[0])
                elif "skipped" in p:
                    with contextlib.suppress(ValueError):
                        summary["skipped"] = int(p.split()[0])
                elif "error" in p:
                    with contextlib.suppress(ValueError):
                        summary["errors"] = int(p.split()[0])

    return {
        "summary": summary,
        "duration_seconds": round(duration, 2),
        "exit_code": result.returncode,
        "stdout": result.stdout[-2000:] if result.stdout else "",
        "stderr": result.stderr[-2000:] if result.stderr else "",
    }


def generate_trace_report(suite_results: dict[str, dict]) -> dict:
    """Generate a unified trace report from all suite results."""
    trace_id = f"audit-{uuid.uuid4().hex[:12]}"
    total = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    suites = []

    for suite_name, result in suite_results.items():
        s = result["summary"]
        for k in total:
            total[k] += s.get(k, 0)
        suites.append(
            {
                "suite": suite_name,
                "status": "✅" if s.get("failed", 0) == 0 and s.get("errors", 0) == 0 else "❌",
                "passed": s.get("passed", 0),
                "failed": s.get("failed", 0),
                "skipped": s.get("skipped", 0),
                "errors": s.get("errors", 0),
                "duration_seconds": result.get("duration_seconds", 0),
            }
        )

    report = {
        "trace_id": trace_id,
        "version": "6.0.0",
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "overall": "✅ PASS" if total["failed"] == 0 and total["errors"] == 0 else "❌ FAIL",
        "suites": suites,
    }
    return report


def save_report(report: dict):
    """Save trace report to output directory."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{report['trace_id']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also write a human-readable summary
    summary_path = REPORT_DIR / "latest_summary.md"
    lines = [
        f"# CRUX Studio v{report['version']} Self-Audit Report",
        "",
        f"**Trace ID:** `{report['trace_id']}`",
        f"**Time:** {report['timestamp']}",
        f"**Overall:** {report['overall']}",
        "",
        "## Summary",
        "| Metric | Count |",
        "|--------|-------|",
        f"| ✅ Passed | {report['total']['passed']} |",
        f"| ❌ Failed | {report['total']['failed']} |",
        f"| ⏭️ Skipped | {report['total']['skipped']} |",
        f"| ⚠️ Errors | {report['total']['errors']} |",
        "",
        "## Suites",
    ]
    for suite in report["suites"]:
        lines.append(
            f"- {suite['status']} **{suite['suite']}**: "
            f"{suite['passed']} passed, {suite['failed']} failed, "
            f"{suite['skipped']} skipped ({suite['duration_seconds']}s)"
        )

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_report(report: dict):
    """Print report to console."""
    print(banner(f"Self-Audit Complete: {report['trace_id']}"))
    print(f"  Overall: {report['overall']}")
    print(
        f"  Total:   {report['total']['passed']} ✅ / {report['total']['failed']} ❌ "
        f"/ {report['total']['skipped']} ⏭️ / {report['total']['errors']} ⚠️"
    )
    print()
    for suite in report["suites"]:
        print(
            f"  {suite['status']} {suite['suite']:40s} "
            f"P:{suite['passed']} F:{suite['failed']} S:{suite['skipped']} "
            f"({suite['duration_seconds']}s)"
        )
    print()


SUITES = {
    "tool": ["tests/self_audit/test_tool_call_chain.py", "-v"],
    "routing": ["tests/self_audit/test_model_routing.py", "-v"],
    "injection": ["tests/self_audit/test_prompt_injection.py", "-v"],
    "cdp": ["tests/self_audit/test_cdp_stability.py", "-v"],
    "recovery": ["tests/self_audit/test_failure_recovery.py", "-v"],
    "all": ["tests/self_audit/", "-v"],
    "quick": [
        "tests/self_audit/test_tool_call_chain.py",
        "tests/self_audit/test_model_routing.py",
        "tests/self_audit/test_prompt_injection.py",
        "tests/self_audit/test_failure_recovery.py",
        "-v",
        "-k",
        "not cdp",
    ],
}


def main():
    parser = argparse.ArgumentParser(description="CRUX Studio Self-Audit Runner")
    parser.add_argument("--suite", choices=list(SUITES.keys()), default="all", help="Which suite to run")
    parser.add_argument("--quick", action="store_true", help="Quick mode: skip CDP + slow tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    suite_name = args.suite
    if args.quick:
        suite_name = "quick"

    print(banner(f"CRUX Studio v6.0.0 Self-Audit: {suite_name}"))
    print(f"Report dir: {REPORT_DIR}")
    print()

    if suite_name == "all":
        # Run each suite individually and collect results
        suite_results = {}
        for name in ["tool", "routing", "injection", "cdp", "recovery"]:
            print(f"\n  ▶ Running {name}...")
            result = run_pytest(SUITES[name] + (["-v"] if args.verbose else []))
            suite_results[name] = result
            status = "✅" if result["summary"]["failed"] == 0 else "❌"
            print(f"  {status} {name}: {result['summary']} ({result['duration_seconds']}s)")

        report = generate_trace_report(suite_results)
    else:
        result = run_pytest(SUITES[suite_name] + (["-v"] if args.verbose else []))
        suite_results = {suite_name: result}
        report = generate_trace_report(suite_results)

    save_report(report)
    print_report(report)

    # Exit with appropriate code
    sys.exit(0 if report["total"]["failed"] == 0 and report["total"]["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
