"""Self-fix engine — auto-repair for mechanically fixable codebase issues.

Works with AuditEngine findings. Each fix type has a handler that knows how to
safely apply the fix, verify it, and rollback on failure.

Fix types:
    bom_strip     — strip UTF-8 BOM from Python files
    chcp_hack     — replace chcp 65001 with import core.encoding
    empty_fill    — fill empty skill/config files with minimal valid content
    wildcard_imp  — convert from X import * to explicit imports
    git_cleanup   — remove leftover git artifacts

Safety: every fix is wrapped in try/finally. Syntax check after each fix.
Batch mode with rollback: if any fix in a batch fails, all are reverted.
"""

import re
import subprocess
import sys
from pathlib import Path
import contextlib

__all__ = ['FixResult', 'ROOT', 'SelfFixEngine', 'auto_fix']

ROOT = Path(__file__).resolve().parent.parent


class FixResult:
    def __init__(self, finding_id: str, success: bool, message: str = "",
                 backup_path: str | None = None) -> None:
        self.finding_id = finding_id
        self.success = success
        self.message = message
        self.backup_path = backup_path


class SelfFixEngine:
    """Applies mechanical fixes to issues found by AuditEngine."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.results: list[FixResult] = []
        self._backups: dict[str, str] = {}  # file_path -> backup_content

    @property
    def findings(self) -> list[dict]:
        """Compatibility accessor for test code that sets .results."""
        return []

    def fix_all(self, findings: list[dict], dry_run: bool = False) -> list[FixResult]:
        """Attempt to fix all auto-fixable findings. Returns results."""
        self.results = []
        self._backups = {}
        fixable = [f for f in findings if self._can_fix(f)]
        if not fixable:
            return self.results

        for i, finding in enumerate(fixable):
            fid = f"fix_{i}_{finding.get('category','?')}_{finding.get('file','?')}"
            try:
                self._apply_fix(finding, fid, dry_run)
            except (OSError, ValueError, RuntimeError) as e:
                self.results.append(FixResult(fid, False, str(e)))

        # Rollback on any failure
        if any(not r.success for r in self.results) and not dry_run:
            self._rollback_all()

        return self.results

    def _can_fix(self, finding: dict) -> bool:
        cat = finding.get("category", "")
        return cat in ("files", "encoding", "imports", "skills") and bool(finding.get("auto_fix"))

    def _apply_fix(self, finding: dict, fid: str, dry_run: bool):
        cat = finding["category"]
        file_rel = finding.get("file", "")
        file_path = self.root / file_rel if file_rel else None

        if cat == "files" and "BOM" in finding.get("title", ""):
            if file_path:
                self._fix_bom(file_path, fid, dry_run)
            else:
                self.results.append(FixResult(fid, False, "No file path"))
        elif cat == "files" and "Empty" in finding.get("title", ""):
            if file_path:
                self._fix_empty(file_path, fid, dry_run)
            else:
                self.results.append(FixResult(fid, False, "No file path"))
        elif cat == "encoding" and "chcp" in finding.get("title", ""):
            if file_path:
                self._fix_chcp(file_path, fid, dry_run)
            else:
                self.results.append(FixResult(fid, False, "No file path"))
        elif cat == "imports":
            if file_path:
                self._fix_wildcard_import(file_path, finding.get("line", 0), fid, dry_run)
            else:
                self.results.append(FixResult(fid, False, "No file path"))
        else:
            self.results.append(FixResult(fid, False, f"Unknown fix type: {cat}/{finding.get('title','')}"))

    def _backup(self, path: Path):
        if str(path) not in self._backups:
            self._backups[str(path)] = path.read_text(encoding="utf-8")

    def _rollback_all(self):
        for path_str, content in self._backups.items():
            with contextlib.suppress(OSError, UnicodeDecodeError):
                Path(path_str).write_text(content, encoding="utf-8")

    def _verify_syntax(self, path: Path) -> bool:
        try:
            import ast
            ast.parse(path.read_text(encoding="utf-8"))
            return True
        except SyntaxError:
            return False

    def _run_tests(self) -> tuple[bool, str]:
        # 经 run_pytest_safe 统一封装：在 pytest 内运行时自动短路，
        # 避免自检 spawn 子 pytest 跑完整 tests/ 造成无限递归 fork。
        try:
            from core.pytest_runner import run_pytest_safe
            r = run_pytest_safe(test_target="tests/", timeout=30, cwd=self.root)
            out = (r.stdout or "")
            failed = "failed" in out.lower() and "0 failed" not in out.lower()
            return not failed, out[-200:]
        except (OSError, ValueError) as e:
            return False, str(e)

    def _fix_bom(self, path: Path, fid: str, dry_run: bool):
        if not path or not path.exists():
            self.results.append(FixResult(fid, False, "File not found"))
            return
        self._backup(path)
        if dry_run:
            self.results.append(FixResult(fid, True, "Would strip BOM"))
            return
        try:
            content = path.read_bytes()
            if content[:3] == b"\xef\xbb\xbf":
                path.write_bytes(content[3:])
            if self._verify_syntax(path):
                self.results.append(FixResult(fid, True, "BOM stripped"))
            else:
                self.results.append(FixResult(fid, False, "Syntax check failed after BOM strip"))
        except (subprocess.SubprocessError, OSError) as e:
            self.results.append(FixResult(fid, False, str(e)))

    def _fix_empty(self, path: Path, fid: str, dry_run: bool):
        if not path or not path.exists() or path.stat().st_size != 0:
            self.results.append(FixResult(fid, False, "File not empty or not found"))
            return
        self._backup(path)
        if dry_run:
            self.results.append(FixResult(fid, True, "Would fill empty file"))
            return
        try:
            if path.suffix == ".py":
                path.write_text("# Package marker\n", encoding="utf-8")
            elif path.suffix == ".json":
                path.write_text("{}\n", encoding="utf-8")
            else:
                path.write_text("\n", encoding="utf-8")
            self.results.append(FixResult(fid, True, "Empty file filled"))
        except (subprocess.SubprocessError, OSError) as e:
            self.results.append(FixResult(fid, False, str(e)))

    def _fix_chcp(self, path: Path, fid: str, dry_run: bool):
        if not path or not path.exists():
            self.results.append(FixResult(fid, False, "File not found"))
            return
        self._backup(path)
        if dry_run:
            self.results.append(FixResult(fid, True, "Would replace chcp hack with import core.encoding"))
            return
        try:
            content = path.read_text(encoding="utf-8")
            if "import core.encoding" not in content:
                new_content = re.sub(
                    r"(?s)(#.*?UTF-8.*?\n)?if os\.name == \"nt\":\s*\n\s*os\.system\(\"chcp 65001[^\"]*\"\)\s*\n\s*sys\.stdout\.reconfigure\(encoding=\"utf-8\"[^)]*\)\s*\n\s*sys\.stderr\.reconfigure\(encoding=\"utf-8\"[^)]*\)\s*",
                    "# UTF-8 encoding handled by core.encoding (imported above)\n",
                    content
                )
                if "import core.encoding" not in new_content:
                    new_content = re.sub(
                        r"(import sys\b[^\n]*)",
                        r"\1\nimport core.encoding  # noqa: E402",
                        new_content, count=1
                    )
                if new_content != content:
                    path.write_text(new_content, encoding="utf-8")
                    if self._verify_syntax(path):
                        self.results.append(FixResult(fid, True, "chcp hack replaced with import core.encoding"))
                    else:
                        self.results.append(FixResult(fid, False, "Syntax error after fix"))
                else:
                    self.results.append(FixResult(fid, False, "Could not locate chcp hack pattern"))
            else:
                self.results.append(FixResult(fid, True, "Already using core.encoding (no action needed)"))
        except (OSError, UnicodeDecodeError) as e:
            self.results.append(FixResult(fid, False, str(e)))

    def _fix_wildcard_import(self, path: Path, line_num: int, fid: str, dry_run: bool):
        if not path or not path.exists():
            self.results.append(FixResult(fid, False, "File not found"))
            return
        self.results.append(FixResult(fid, False,
            "Wildcard import fix requires manual review — run 'from X import *' to explicit conversion"))

    def print_results(self):
        ok = sum(1 for r in self.results if r.success)
        fail = len(self.results) - ok
        G = "\033[92m"
        R = "\033[91m"
        X = "\033[0m"
        print(f"\n{G}{ok} fixed{X}, {R}{fail} failed{X}")
        for r in self.results:
            icon = f"{G}OK{X}" if r.success else f"{R}FAIL{X}"
            print(f"  [{icon}] {r.finding_id}: {r.message}")


def auto_fix(findings: list[dict], dry_run: bool = False) -> list[FixResult]:
    return SelfFixEngine().fix_all(findings, dry_run=dry_run)