"""Targeted test runner — one-command edit→test→fix loop.

GPT gap fix #2 part B: "Add one-command edit-test-fix loop: modify files,
run targeted tests, summarize failure, patch again."

Builds on RepoMap to auto-discover matching tests.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.repo_map import get_repo_map

logger = logging.getLogger("crux.test_runner")

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TestResult:
    """Parsed pytest output for a single test run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration: float = 0.0
    failures: list[dict] = field(default_factory=list)  # [{file, line, test, message}]
    raw_output: str = ""
    exit_code: int = 0

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def summary(self) -> str:
        return f"{self.passed}P/{self.failed}F/{self.errors}E in {self.duration:.1f}s"


def run_tests(
    target: str = "",
    *,
    quick: bool = True,
    max_failures: int = 10,
    timeout: float = 120.0,
) -> TestResult:
    """Run tests targeting a specific file or module.

    Args:
        target: File path or module name. Auto-discovers tests if empty.
        quick: Use -x (stop on first failure) and -q (quiet) flags.
        max_failures: Max failures to show (--maxfail).
        timeout: Max runtime in seconds.

    Returns:
        TestResult with parsed counts and formatted failures.
    """
    # Discover test file
    test_path = _find_test_for(target) if target else ""

    cmd = [
        "C:/Users/huangjiancheng/AppData/Local/Programs/Python/Python311/python.exe",
        "-m",
        "pytest",
    ]
    if quick:
        cmd += ["-q", "--no-header", "-p", "no:xdist"]
    cmd.append(f"--maxfail={max_failures}")
    if test_path:
        cmd.append(test_path)
    else:
        cmd.append("tests/")

    result = TestResult()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        result.raw_output = proc.stdout + "\n" + proc.stderr
        result.exit_code = proc.returncode

        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")

        # Parse pytest summary — format: "X passed in Y.YYs" or "X passed, Y failed in Z.ZZs"
        # All-pass case: "5 passed in 0.12s"
        all_pass = re.search(r"(\d+)\s+passed\s+in\s+([\d.]+)s", combined)
        # With failures: "3 passed, 2 failed in 1.23s"
        with_fail = re.search(r"(\d+)\s+passed.*?(\d+)\s+failed.*?in\s+([\d.]+)s", combined)
        # With errors too: "3 passed, 1 failed, 1 error in 1.23s"
        with_errors = re.search(r"(\d+)\s+passed.*?(\d+)\s+failed.*?(\d+)\s+error.*?in\s+([\d.]+)s", combined)

        if with_errors:
            result.passed = int(with_errors.group(1))
            result.failed = int(with_errors.group(2))
            result.errors = int(with_errors.group(3))
            result.duration = float(with_errors.group(4))
        elif with_fail:
            result.passed = int(with_fail.group(1))
            result.failed = int(with_fail.group(2))
            result.duration = float(with_fail.group(3))
        elif all_pass:
            result.passed = int(all_pass.group(1))
            result.duration = float(all_pass.group(2))
        else:
            # Try to count dots (progress output)
            dots = combined.count(".")
            Fs = combined.count("F")
            Es = combined.count("E")
            if dots > 0 or Fs > 0 or Es > 0:
                result.passed = dots
                result.failed = Fs
                result.errors = Es

        result.total = result.passed + result.failed + result.errors

        # Parse individual FAILURES
        result.failures = _parse_failures(result.raw_output)

    except subprocess.TimeoutExpired:
        result.failures = [{"test": "(timeout)", "message": f"Test run exceeded {timeout}s"}]
        result.exit_code = -1
    except (OSError, FileNotFoundError) as e:
        result.failures = [{"test": "(runner)", "message": str(e)}]
        result.exit_code = -2

    return result


def run_test_loop(
    target: str,
    *,
    max_iterations: int = 3,
    on_failure: callable = None,
) -> bool:
    """Edit→test→fix loop: run test, report failures, retry up to N times.

    Args:
        target: Source file to test
        max_iterations: Max test-fix cycles
        on_failure: Callback receiving TestResult for each iteration

    Returns:
        True if tests pass, False if still failing after max_iterations.
    """
    for iteration in range(1, max_iterations + 1):
        result = run_tests(target, quick=True)
        if result.success:
            logger.info("Test loop: pass on iteration %d (%s)", iteration, result.summary)
            return True

        logger.warning("Test loop: iteration %d failed (%s)", iteration, result.summary)
        if on_failure:
            on_failure(result)

        if iteration < max_iterations:
            logger.info("Retrying... (%d/%d)", iteration + 1, max_iterations)

    logger.error("Test loop: exhausted after %d iterations", max_iterations)
    return False


def list_failing_tests(result: TestResult) -> list[str]:
    """Extract failing test names for quick re-run."""
    return [f["test"] for f in result.failures if f.get("test")]


# ── Internal ────────────────────────────────────────────────


def _find_test_for(target: str) -> str:
    """Find the matching test file for a source file."""
    repo = get_repo_map()

    # If target is already a test file, use it directly
    if "test" in target.lower():
        return target

    # Try RepoMap
    tests = repo.find_tests_for(target)
    if tests:
        return tests[0]

    # Fallback: guess naming convention
    stem = Path(target).stem
    candidates = [
        f"tests/test_{stem}.py",
        f"tests/{stem}/test_main.py",
    ]
    for c in candidates:
        if (ROOT / c).exists():
            return c

    return ""


def _parse_failures(output: str) -> list[dict]:
    """Extract structured failure info from pytest output."""
    failures = []
    # Pattern: FAILED test_file::test_name — message
    pattern = re.compile(r"FAILED\s+(\S+?::\S+?)\b")
    for match in pattern.finditer(output):
        test_name = match.group(1)
        # Try to extract the assertion message following this line
        failures.append({"test": test_name, "message": ""})

    # Find assertion messages
    assert_pattern = re.compile(r"E\s+(assert.*?|AssertionError.*?|TypeError.*?|ValueError.*?)$", re.MULTILINE)
    for match in assert_pattern.finditer(output):
        msg = match.group(1)[:200]
        # Attach to the most recent failure
        if failures:
            failures[-1]["message"] = msg

    return failures[:10]
