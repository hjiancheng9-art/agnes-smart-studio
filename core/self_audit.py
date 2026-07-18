"""Self-audit engine — now delegates to self_heal (single source of truth).

Kept for backward compatibility.  Previously had ~260 lines of standalone
scan logic that overlapped heavily with self_heal.py.  Now a thin wrapper.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ROOT", "AuditEngine", "audit"]

import core.self_heal as _sh


class AuditEngine:
    """Backward-compatible wrapper — delegates to self_heal.SelfHealer."""
    def __init__(self, root=None):
        self._h = _sh.SelfHealer()

    def scan(self):
        self._h.run_all_scans()
        return self._build_report()

    def print_report(self):
        print(self._h.report())

    def _build_report(self):
        by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        findings = []
        auto_fixable = 0
        for f in self._h.findings:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
            findings.append({"severity": f.severity, "category": f.category, "file": f.file, "line": f.line, "msg": f.msg})
            if f.fixable:
                auto_fixable += 1
        return {
            "total_findings": len(self._h.findings),
            "by_severity": by_sev,
            "findings": findings,
            "auto_fixable": auto_fixable,
        }


def audit() -> dict[str, Any]:
    """Run full audit via self_heal, return self_audit-compatible dict."""
    h = _sh.SelfHealer()
    h.run_all_scans()
    by_sev: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    findings: list[dict] = []
    auto_fixable = 0
    for f in h.findings:
        sev = f.severity
        by_sev[sev] = by_sev.get(sev, 0) + 1
        findings.append({"severity": sev, "category": f.category, "file": f.file, "line": f.line, "msg": f.msg})
        if f.fixable:
            auto_fixable += 1
    return {
        "total_findings": len(h.findings),
        "by_severity": by_sev,
        "findings": findings,
        "auto_fixable": auto_fixable,
    }


# Legacy export
ROOT = _sh.ROOT
