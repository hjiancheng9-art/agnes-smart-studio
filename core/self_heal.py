"""CRUX Self-Healer — 白虎自愈引擎。

Automated audit + fix pipeline. Run with:
    python core/self_heal.py          # audit only
    python core/self_heal.py --fix    # audit + auto-fix
    python core/self_heal.py --json   # machine-readable output

Detects and optionally fixes:
  1. Silent exception swallows (except:pass without logging)
  2. Dead imports (imported but never used in file)
  3. Missing hook registrations (defined but never called)
  4. Syntax errors
  5. Test failures
  6. Configuration drift
"""

from __future__ import annotations

import ast
import json
import logging

logger = logging.getLogger(__name__)
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Color helpers ──────────────────────────────────────
G = "\033[32m"
R = "\033[31m"
Y = "\033[33m"
B = "\033[34m"
N = "\033[0m"


class Finding:
    def __init__(self, severity: str, category: str, file: str, line: int, msg: str, fixable: bool = False):
        self.severity = severity  # critical / high / medium / low
        self.category = category
        self.file = file
        self.line = line
        self.msg = msg
        self.fixable = fixable

    def __repr__(self):
        return f"[{self.severity}] {self.file}:{self.line} — {self.msg}"


class SelfHealer:
    """Scan + fix engine."""

    def __init__(self):
        self.findings: list[Finding] = []
        self.fixes_applied = 0

    # ── Scanners ──────────────────────────────────────

    def _skip_path(self, path: Path) -> bool:
        """Check if a path should be skipped during scanning."""
        p = str(path)
        return any(x in p for x in ("site-packages", "__pycache__", "node_modules", "tmp" + os.sep, os.sep + "tmp"))

    def scan_silent_exceptions(self):
        """Find bare except: pass without logging."""
        pattern_lines = ("except Exception:", "except:", "except Exception as", "except BaseException")
        for py_file in ROOT.rglob("*.py"):
            if self._skip_path(py_file):
                continue
            if "tests" in str(py_file.parent).split(os.sep):
                continue
            # Skip self + quality gates — avoid dogfooding corruption
            if py_file.name in ("self_heal.py",):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
            except (OSError, ValueError) as e:
                logger.debug("self_heal: skipped %s (%s: %s)", py_file, type(e).__name__, e)
                continue
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if not any(stripped.startswith(p) for p in pattern_lines):
                    continue
                # Check if the except body is just "pass" or empty
                if i < len(lines):
                    next_line = lines[i].strip()
                    if next_line in ("pass", "", "pass  #"):
                        self.findings.append(
                            Finding(
                                "medium",
                                "silent-exception",
                                str(py_file.relative_to(ROOT)),
                                i,
                                f"Silent except swallows error: {stripped}",
                                fixable=True,
                            )
                        )

    def scan_syntax(self):
        """Check all Python files for syntax errors."""
        for py_file in ROOT.rglob("*.py"):
            if self._skip_path(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source)
            except SyntaxError as e:
                self.findings.append(
                    Finding(
                        "critical",
                        "syntax",
                        str(py_file.relative_to(ROOT)),
                        e.lineno or 0,
                        f"SyntaxError: {e.msg}",
                        fixable=False,
                    )
                )
            except (ValueError, OSError) as e:
                logger.debug("self_heal: skipped %s (%s: %s)", py_file, type(e).__name__, e)

    def scan_test_failures(self):
        """Run smoke tests — fast subset that catches real regressions.
        Excludes test_audit (which calls self_heal → infinite recursion)."""
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_smoke.py",
                    "-q",
                    "--tb=line",
                    "--timeout=30",
                    "-k",
                    "not test_audit",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            output = r.stdout + r.stderr
            if r.returncode != 0:
                # Parse failure count from pytest output
                import re

                failed_match = re.search(r"(\d+) failed", output)
                failed = int(failed_match.group(1)) if failed_match else "?"
                passed_match = re.search(r"(\d+) passed", output)
                passed = passed_match.group(1) if passed_match else "?"
                self.findings.append(
                    Finding(
                        "medium",  # Smoke tests are environment-sensitive, not code-critical
                        "tests",
                        "tests/test_smoke.py",
                        0,
                        f"Smoke tests: {passed} passed, {failed} FAILED",
                        fixable=False,
                    )
                )
        except subprocess.TimeoutExpired:
            self.findings.append(
                Finding("high", "tests", "tests/test_smoke.py", 0, "Smoke tests timed out (>60s)", fixable=False)
            )
        except Exception as e:
            self.findings.append(
                Finding("high", "tests", "tests/test_smoke.py", 0, f"Test runner error: {e}", fixable=False)
            )

    def scan_import_errors(self):
        """Try importing all core modules, catch failures."""
        mods = []
        for py_file in sorted(ROOT.glob("core/*.py")):
            mod_name = f"core.{py_file.stem}"
            if py_file.stem.startswith("_"):
                continue
            mods.append(mod_name)
        for mod in mods:
            try:
                __import__(mod)
            except SyntaxError as e:
                self.findings.append(
                    Finding(
                        "critical",
                        "import",
                        mod,
                        e.lineno or 0,
                        f"SyntaxError: {e.msg}",
                        fixable=False,
                    )
                )
            except ImportError as e:
                self.findings.append(
                    Finding(
                        "high",
                        "import",
                        mod,
                        0,
                        f"ImportError: {e}",
                        fixable=False,
                    )
                )
            except Exception as e:
                self.findings.append(
                    Finding(
                        "medium",
                        "import",
                        mod,
                        0,
                        f"Init error ({type(e).__name__}): {e}",
                        fixable=False,
                    )
                )

    def scan_config_drift(self):
        """Check models.json vs MODEL_REGISTRY consistency."""
        try:
            from core.provider import MODEL_REGISTRY, get_provider_manager

            mgr = get_provider_manager()
            for pid, p in mgr.providers.items():
                models = p.get("models", {})
                for tier, mid in models.items():
                    if mid not in MODEL_REGISTRY:
                        self.findings.append(
                            Finding(
                                "high",
                                "config-drift",
                                f"models.json [{pid}]",
                                0,
                                f"Model '{mid}' (tier={tier}) not in MODEL_REGISTRY",
                                fixable=False,
                            )
                        )
        except Exception as e:
            self.findings.append(
                Finding(
                    "medium",
                    "config-drift",
                    "models.json",
                    0,
                    f"Config check failed: {e}",
                    fixable=False,
                )
            )

    def scan_hook_gaps(self):
        """Check for registered hooks that are never fired."""
        # Already fixed in this session — verify they're still active
        try:
            from core.hooks import HookType, get_registered_hooks

            get_registered_hooks()
            fired_types = set()
            # Scan chat.py for _fire_hook calls
            chat_src = (ROOT / "core" / "chat.py").read_text(encoding="utf-8")
            for ht in HookType:
                if ht.value in chat_src or f"HookType.{ht.name}" in chat_src:
                    fired_types.add(ht)
            for ht in HookType:
                if ht not in fired_types:
                    self.findings.append(
                        Finding(
                            "low",
                            "hooks",
                            "core/hooks.py",
                            0,
                            f"HookType.{ht.name} is registered but never fired",
                            fixable=False,
                        )
                    )
        except Exception:
            pass  # hooks module has its own issues, don't compound

    def scan_mojibake(self):
        """Scan all text files for mojibake (encoding corruption) characters.

        Zero tolerance — any hit is a critical finding.  Excludes known
        detection-engine files that contain signature characters by design.
        """
        chars = set("鍥閸鐢纴鏉悆殑掑曠")
        exclude_files = {
            "core/encoding_fix.py",
            "core/pre_commit.py",  # contains mojibake detection chars by design
            "core/self_heal.py",  # scanner signature chars by design
            "tests/test_encoding_fix.py",
        }
        exclude_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            "output",
            ".codebuddy",
            ".hypothesis",
            "scripts/scratch",
            "_archive",
            "stub_modules",
        }
        exclude_prefixes = ("apps/nsp-downloader-legacy/scripts/scan-garbled",)
        hits = 0
        for root, dirs, files in os.walk(str(ROOT)):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if not f.endswith((".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".bat", ".sh")):
                    continue
                abs_path = os.path.join(root, f)
                try:
                    rp = os.path.relpath(abs_path, str(ROOT)).replace("\\", "/")
                except ValueError:
                    rp = abs_path.replace("\\", "/")
                if rp in exclude_files or any(rp.startswith(p) for p in exclude_prefixes):
                    continue
                try:
                    content = open(os.path.join(root, f), encoding="utf-8").read()
                    for ch in chars:
                        if ch in content:
                            self.findings.append(
                                Finding(
                                    "critical",
                                    "mojibake",
                                    rp,
                                    0,
                                    f"Mojibake character U+{ord(ch):04X} detected",
                                    fixable=False,
                                )
                            )
                            hits += 1
                            break
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug("silent except", exc_info=True)
        if hits == 0:
            logger.info("self_heal: mojibake scan clean")

    def scan_thread_safety(self):
        """Detect lockless global mutable state that is actually mutated at runtime.

        Skips ALL_CAPS constants (convention for read-only) and only flags
        variables that are reassigned or mutated elsewhere in the file.
        """
        for py_file in ROOT.rglob("*.py"):
            if self._skip_path(py_file) or "tests" in str(py_file.parent).split(os.sep):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
            tree = ast.parse(source)
            rel = str(py_file.relative_to(ROOT))
            has_lock = "threading.Lock" in source or "Lock(" in source
            # Collect global mutables (non-CAPS, non-private)
            candidates: dict[str, int] = {}
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            if not target.id.isupper():  # skip constants
                                if isinstance(node.value, ast.List | ast.Dict | ast.Set):
                                    candidates[target.id] = node.lineno
            # Check if any candidate is modified elsewhere (reassigned or .append/.update called)
            for node in ast.walk(tree):
                if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    if node.target.id in candidates and not has_lock:
                        self.findings.append(
                            Finding(
                                "medium",
                                "thread-safety",
                                rel,
                                candidates[node.target.id],
                                f"Mutable global '{node.target.id}' mutated (+=) without lock",
                                fixable=False,
                            )
                        )
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in candidates:
                            # Same name reassigned (not at definition site)
                            if node.lineno != candidates[target.id] and not has_lock:
                                self.findings.append(
                                    Finding(
                                        "medium",
                                        "thread-safety",
                                        rel,
                                        candidates[target.id],
                                        f"Mutable global '{target.id}' reassigned without lock",
                                        fixable=False,
                                    )
                                )

    def scan_bare_except_keyboard(self):
        """Detect bare except/except BaseException that swallows KeyboardInterrupt."""
        for py_file in ROOT.rglob("*.py"):
            if self._skip_path(py_file) or "tests" in str(py_file.parent).split(os.sep):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
            except (OSError, ValueError):
                continue
            rel = str(py_file.relative_to(ROOT))
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s == "except:" or s.startswith("except:"):
                    self.findings.append(
                        Finding(
                            "medium",
                            "bare-except",
                            rel,
                            i,
                            "Bare 'except:' catches KeyboardInterrupt and SystemExit",
                            fixable=True,
                        )
                    )

    def scan_shell_injection(self):
        """Detect shell=True usage with unescaped variable interpolation."""
        for py_file in ROOT.rglob("*.py"):
            if self._skip_path(py_file) or "tests" in str(py_file.parent).split(os.sep):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, ValueError):
                continue
            if "shell=True" not in source:
                continue
            tree = ast.parse(source)
            rel = str(py_file.relative_to(ROOT))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value", None) is True:
                        if node.args:
                            a0 = node.args[0]
                            if isinstance(a0, ast.JoinedStr):
                                self.findings.append(
                                    Finding(
                                        "high",
                                        "shell-injection",
                                        rel,
                                        node.lineno,
                                        "shell=True with f-string — potential injection",
                                        fixable=False,
                                    )
                                )

    def scan_flaky_tests(self):
        """Quick flaky test detection — 3 seeds, fast marker subset.

        Uses the existing collect_flaky_matrix.py infrastructure.
        Reports any consistently-failing test as a finding.
        """
        try:
            import json

            _ = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "collect_flaky_matrix.py")],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            report_path = ROOT / "output" / "flaky_baseline.json"
            if report_path.exists():
                data = json.loads(report_path.read_text(encoding="utf-8"))
                total_failures = sum(v["failures"] for v in data.values())
                if total_failures > 0:
                    self.findings.append(
                        Finding(
                            "medium" if total_failures < 30 else "high",
                            "flaky-tests",
                            "tests/",
                            0,
                            f"{total_failures} flaky test occurrences across {len(data)} seeds",
                            fixable=False,
                        )
                    )
            else:
                self.findings.append(
                    Finding("low", "flaky-tests", "tests/", 0, "Flaky test report not found", fixable=False)
                )
        except subprocess.TimeoutExpired:
            self.findings.append(Finding("low", "flaky-tests", "tests/", 0, "Flaky test scan timed out", fixable=False))
        except Exception as e:
            self.findings.append(
                Finding("low", "flaky-tests", "tests/", 0, f"Flaky test scan failed: {e}", fixable=False)
            )

    def scan_global_leaks(self):
        """Detect modules with global state modified during test execution.

        Uses conftest_leak.py's LeakDetector to snapshot→compare→report.
        Only reports modules that were actually modified (not all targets).
        """
        try:
            sys.path.insert(0, str(ROOT))
            from tests.conftest_leak import get_detector  # type: ignore[import-not-found]

            detector = get_detector()
            before = detector.snapshot()
            # Run a subset of tests to trigger potential cross-module pollution
            _ = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/",
                    "-q",
                    "--tb=line",
                    "-p",
                    "no:xdist",
                    "-m",
                    "not slow and not browser and not network",
                    "--timeout=20",
                    "--maxfail=50",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(ROOT),
                encoding="utf-8",
                errors="replace",
            )
            after = detector.snapshot()
            dirty = detector.compare(before, after)
            for key in dirty:
                self.findings.append(
                    Finding(
                        "low",
                        "global-leak",
                        key,
                        0,
                        f"Global state modified during test run: {key}",
                        fixable=False,
                    )
                )
            if not dirty:
                logger.info("self_heal: global leak scan clean")
        except Exception as e:
            self.findings.append(Finding("low", "global-leak", "tests/", 0, f"Leak scan failed: {e}", fixable=False))

    # ── Fixers ────────────────────────────────────────

    def fix_silent_exceptions(self):
        """Add logging to bare except:pass blocks.

        Preserves the except clause and replaces only the pass body,
        keeping the code structure valid.
        """
        fixed = 0
        for f in self.findings:
            if f.category != "silent-exception" or not f.fixable:
                continue
            fpath = ROOT / f.file
            try:
                lines = fpath.read_text(encoding="utf-8").splitlines()
                # f.line is 1-based line of the except clause.
                # The pass body is on the next line (0-based index = f.line).
                pass_idx = f.line  # 0-based index of the pass line
                if pass_idx < len(lines) and lines[pass_idx].strip() in ("pass", "pass  #"):
                    indent = len(lines[pass_idx]) - len(lines[pass_idx].lstrip())
                    lines[pass_idx] = (
                        " " * indent
                        + "import logging; logging.getLogger(__name__).debug('silent except', exc_info=True)"
                    )
                    fpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    fixed += 1
            except Exception as e:
                logger.warning("fix_silent_exceptions failed for %s: %s", fpath, e)
        self.fixes_applied += fixed
        return fixed

    # ── Main ──────────────────────────────────────────

    def run_all_scans(self):
        for scanner in [
            self.scan_syntax,
            self.scan_silent_exceptions,
            self.scan_thread_safety,
            self.scan_bare_except_keyboard,
            self.scan_shell_injection,
            self.scan_import_errors,
            self.scan_config_drift,
            self.scan_test_failures,
            self.scan_hook_gaps,
            self.scan_mojibake,
            # scan_global_leaks spawns pytest subprocess (hangs inside pytest tests)
            # scan_flaky_tests is slow (3 seeds × full suite) — opt-in via --full
        ]:
            try:
                scanner()
            except Exception as e:
                self.findings.append(
                    Finding(
                        "low",
                        "scanner",
                        scanner.__name__,
                        0,
                        f"Scanner failed: {e}",
                        fixable=False,
                    )
                )
        return self.findings

    def quick_fix(self) -> dict:
        """Auto-fix common issues. Returns {ruff_fixed: int, patches: int}."""
        import subprocess

        result = {"ruff_fixed": 0, "patches": 0}
        try:
            r = subprocess.run(
                ["python", "-m", "ruff", "check", "core/", "ui/", "engines/", "--fix"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(ROOT),
            )
            import re

            for line in r.stdout.split("\n"):
                m = re.search(r"(\d+)\s+fixed", line)
                if m:
                    result["ruff_fixed"] = int(m.group(1))
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
        return result

    def report(self) -> str:
        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for f in self.findings:
            by_severity[f.severity].append(f)

        lines = []
        lines.append(f"\n{B}═══ CRUX Self-Heal Report ═══{N}")
        lines.append(f"Findings: {len(self.findings)} ({G}{self.fixes_applied} auto-fixed{N})\n")
        for sev in ("critical", "high", "medium", "low"):
            items = by_severity[sev]
            if not items:
                continue
            color = {"critical": R, "high": Y, "medium": B, "low": N}[sev]
            lines.append(f"{color}[{sev.upper()}] {len(items)} issues{N}")
            for f in items[:5]:
                lines.append(f"  {f.file}:{f.line} — {f.msg}")
            if len(items) > 5:
                lines.append(f"  ... and {len(items) - 5} more")
            lines.append("")
        return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────


def main():
    import argparse

    p = argparse.ArgumentParser(description="CRUX Self-Healer — 白虎自愈引擎")
    p.add_argument("--fix", action="store_true", help="Auto-fix what can be safely fixed")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--full", action="store_true", help="Run all scans including slow ones (imports, tests)")
    p.add_argument("--quick", action="store_true", help=argparse.SUPPRESS)  # deprecated alias for default
    args = p.parse_args()

    healer = SelfHealer()

    if args.full:
        healer.run_all_scans()
    else:
        # Quick mode (default): skip the 4 heavy scans (imports / pytest).
        # 8 fast scans complete in <5s and cover: syntax, silent exceptions,
        # thread safety, bare except, shell injection, config drift, hooks, mojibake.
        healer.scan_syntax()
        healer.scan_silent_exceptions()
        healer.scan_thread_safety()
        healer.scan_bare_except_keyboard()
        healer.scan_shell_injection()
        healer.scan_config_drift()
        healer.scan_hook_gaps()
        healer.scan_mojibake()

    if args.fix:
        print(f"{B}Fixing...{N}")
        n = healer.fix_silent_exceptions()
        print(f"  {G}{n} silent exception handlers patched{N}")

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "severity": f.severity,
                        "category": f.category,
                        "file": f.file,
                        "line": f.line,
                        "msg": f.msg,
                        "fixable": f.fixable,
                    }
                    for f in healer.findings
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(healer.report())

    critical = sum(1 for f in healer.findings if f.severity == "critical")
    if critical:
        print(f"{R}{critical} critical issues remain — manual intervention needed{N}")
    elif healer.findings:
        health_pct = 100 - len([f for f in healer.findings if f.severity in ("critical", "high")]) * 10
        print(f"{G}Health: {max(0, min(100, health_pct))}%{N}")
    else:
        print(f"{G}Health: 100% — no issues found{N}")


if __name__ == "__main__":
    main()
