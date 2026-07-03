"""Self-audit engine — comprehensive codebase scanning and issue classification."""

import json
import re
from pathlib import Path

from rich.rule import Rule

from core.constraints import PROJECT_SKIP_DIRS
from core.pytest_runner import parse_test_summary, run_pytest_safe

__all__ = ["AuditEngine", "ROOT", "audit"]
ROOT = Path(__file__).resolve().parent.parent


class AuditEngine:
    _SKIP_DIRS = PROJECT_SKIP_DIRS

    def __init__(self, root=None) -> None:
        self.root = root or ROOT
        self.findings = []

    def scan(self):
        self.findings = []
        self._check_imports()
        self._check_exceptions()
        self._check_files()
        self._check_config()
        self._check_skills()
        self._check_tests()
        self._check_encoding()
        self._check_git()
        return self._build_report()

    def _add(self, **kw):
        self.findings.append(kw)

    def _check_imports(self):
        for pyfile in sorted(self.root.rglob("*.py")):
            if "__pycache__" in pyfile.parts:
                continue
            try:
                content = pyfile.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(content.splitlines(), 1):
                s = line.strip()
                if re.match(r"\bfrom\b.*\bimport\s+\*", s) and not s.startswith("#"):
                    self._add(
                        category="imports",
                        severity="medium",
                        title="Wildcard import in " + pyfile.name,
                        detail="L" + str(i) + ": " + line.strip(),
                        file=str(pyfile.relative_to(self.root)),
                        line=i,
                    )

    def _check_exceptions(self):
        for pyfile in sorted(self.root.rglob("*.py")):
            if "__pycache__" in pyfile.parts:
                continue
            try:
                lines = pyfile.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines):
                s = line.strip()
                if s == "except:":
                    self._add(
                        category="exceptions",
                        severity="high",
                        title="Bare except: in " + pyfile.name,
                        detail="L" + str(i + 1) + ": " + s,
                        file=str(pyfile.relative_to(self.root)),
                        line=i + 1,
                    )

    def _check_files(self):
        for f in sorted(self.root.rglob("*")):
            if any(skip in f.parts for skip in self._SKIP_DIRS) or not f.is_file():
                continue
            try:
                sz = f.stat().st_size
            except OSError:
                continue
            rel = str(f.relative_to(self.root))
            if sz == 0:
                self._add(category="files", severity="medium", title="Empty: " + rel, file=rel)
            elif sz > 10_000_000 and f.suffix in (".json", ".jsonl"):
                self._add(
                    category="files",
                    severity="high",
                    title="Oversized: " + rel,
                    detail=str(round(sz / 1048576, 1)) + "MB",
                    file=rel,
                )

    def _check_config(self):
        mp = self.root / "models.json"
        if mp.exists():
            try:
                d = json.loads(mp.read_text(encoding="utf-8"))
                active = d.get("active", "")
                if active not in d.get("providers", {}):
                    self._add(
                        category="config",
                        severity="critical",
                        title="Active provider not in providers list",
                        file="models.json",
                    )
            except json.JSONDecodeError:
                self._add(category="config", severity="critical", title="models.json invalid JSON", file="models.json")
        tp = self.root / "tools.json"
        if tp.exists():
            try:
                d = json.loads(tp.read_text(encoding="utf-8"))
                for t in d.get("tools", []):
                    if t.get("type") == "shell" and "pip install" in t.get("command", ""):
                        self._add(
                            category="config",
                            severity="critical",
                            title="Dangerous tool: " + t["name"],
                            file="tools.json",
                        )
            except json.JSONDecodeError:
                self._add(category="config", severity="critical", title="tools.json invalid JSON", file="tools.json")

    def _check_skills(self):
        sd = self.root / "skills"
        if not sd.exists():
            return
        for sf in sorted(sd.glob("*.skill.json")):
            try:
                sz = sf.stat().st_size
                if sz == 0:
                    self._add(
                        category="skills",
                        severity="medium",
                        title="Empty: " + sf.name,
                        file=str(sf.relative_to(self.root)),
                    )
                    continue
                data = json.loads(sf.read_text(encoding="utf-8"))
                missing = [k for k in ("name", "description", "prompt") if k not in data or not data[k]]
                if missing:
                    self._add(
                        category="skills",
                        severity="medium",
                        title="Invalid: " + sf.name,
                        detail="Missing: " + str(missing),
                        file=str(sf.relative_to(self.root)),
                    )
            except json.JSONDecodeError:
                self._add(
                    category="skills",
                    severity="high",
                    title="Bad JSON: " + sf.name,
                    file=str(sf.relative_to(self.root)),
                )

    def _check_tests(self):
        # 经 run_pytest_safe 统一封装：在 pytest 内运行时自动短路，
        # 避免自检时 spawn 子 pytest 跑完整 tests/ 造成无限递归 fork。
        try:
            r = run_pytest_safe(test_target="tests/", timeout=30, cwd=self.root)
            out = (r.stdout or "") + (r.stderr or "")
            passed, failed = parse_test_summary(out)
            if "skipped (running inside pytest)" in out:
                # 守卫触发：当前就在 pytest 进程里，无法也不应递归自检。
                return
            if failed > 0:
                self._add(
                    category="tests",
                    severity="critical",
                    title=str(failed) + "/" + str(passed + failed) + " tests failing",
                )
            elif passed == 0:
                self._add(category="tests", severity="high", title="No tests found")
        except (OSError, ValueError) as e:
            self._add(category="tests", severity="medium", title="Cannot run tests", detail=str(e))

    def _check_encoding(self):
        for pyfile in sorted(self.root.rglob("*.py")):
            if "__pycache__" in pyfile.parts:
                continue
            try:
                if "chcp 65001" in pyfile.read_text(encoding="utf-8", errors="replace") and pyfile.name != "self_audit.py":
                    self._add(
                        category="encoding",
                        severity="low",
                        title="chcp hack: " + pyfile.name,
                        file=str(pyfile.relative_to(self.root)),
                    )
            except OSError:
                pass

    def _check_git(self):
        gd = self.root / ".git"
        if not gd.exists():
            return
        for name in ("COMMIT_EDITMSG", "FETCH_HEAD", "ORIG_HEAD"):
            p = gd / name
            if p.is_file():
                self._add(category="git", severity="low", title="Leftover: .git/" + name, file=".git/" + name)

    def _build_report(self):
        sev = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in self.findings:
            s = f.get("severity", "info")
            sev[s] = sev.get(s, 0) + 1
        return {
            "total_findings": len(self.findings),
            "by_severity": sev,
            "findings": self.findings,
            "auto_fixable": sum(1 for f in self.findings if f.get("auto_fix")),
        }

    def print_report(self, report=None):
        if report is None:
            report = self._build_report()
        from rich.console import Console as _RC
        console = _RC()
        COLORS = {
            "success": "green", "error": "red", "warning": "yellow",
            "primary": "blue", "muted": "dim white", "info": "cyan",
        }

        SEVERITY_COLORS = {
            "critical": COLORS["error"],
            "high": COLORS["warning"],
            "medium": COLORS["primary"],
            "low": COLORS["muted"],
            "info": "",
        }
        console.print()
        console.print(Rule("CRUX Self-Audit — " + str(report["total_findings"]) + " findings", style=COLORS["primary"]))
        for s in ("critical", "high", "medium", "low"):
            n = report["by_severity"].get(s, 0)
            if n:
                console.print("  [" + SEVERITY_COLORS[s] + "]" + s.upper() + ": " + str(n) + "[/]")
        for f in report["findings"]:
            sev = f.get("severity", "info")
            color = SEVERITY_COLORS.get(sev, "")
            fi = " (" + f.get("file", "") + ")" if f.get("file") else ""
            if color:
                console.print("  [" + color + "][" + sev.upper() + "][/] " + f["title"] + fi)
            else:
                console.print("  [" + sev.upper() + "] " + f["title"] + fi)
            if f.get("detail"):
                console.print("         " + f["detail"])


def audit():
    return AuditEngine().scan()
