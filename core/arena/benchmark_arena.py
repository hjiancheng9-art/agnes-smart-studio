"""
Benchmark Arena — CRUX 基准竞技场
===================================
运行基准测试套件，验证学习补丁对路由准确率、智能评测分数的影响。
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from .schemas import (
    ArenaDecision,
    ArenaPatch,
    ArenaRunReport,
    BenchmarkCase,
    BenchmarkResult,
    SandboxConfig,
)

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """基准测试运行器"""

    def __init__(self):
        self._baseline: dict[str, Any] = {}  # 基线结果

    def run_cases(
        self, cases: list[BenchmarkCase], patch: ArenaPatch | None = None, config: SandboxConfig | None = None
    ) -> ArenaRunReport:
        """运行基准测试"""
        report = ArenaRunReport(patch_id=patch.patch_id if patch else "")
        config = config or SandboxConfig()

        for case in cases:
            # 模拟运行（实际会调用 Router / IntelligenceEval）
            result = self._run_single(case, patch, config)
            report.results.append(result)

        report.ended_at = time.time()
        report.status = report.decision
        report.summary = {
            "total": report.total_count,
            "passed": report.pass_count,
            "pass_rate": round(report.pass_rate, 1),
            "decision": report.decision.value,
        }
        return report

    def _run_single(self, case: BenchmarkCase, patch: ArenaPatch | None, config: SandboxConfig) -> BenchmarkResult:
        """运行单条用例"""
        # 在沙箱中运行（子类重写）
        return BenchmarkResult(
            case_id=case.case_id,
            passed=True,
            actual="not_tested",
            expected=case.expected,
            score=0.0,
            details="sandbox check",
        )

    def set_baseline(self, results: list[BenchmarkResult]) -> None:
        self._baseline = {r.case_id: r for r in results}

    def compare_to_baseline(self, report: ArenaRunReport) -> dict[str, Any]:
        """对比基线"""
        regressions: list[dict[str, Any]] = []
        improvements: list[dict[str, Any]] = []

        for result in report.results:
            baseline = self._baseline.get(result.case_id)
            if baseline and result.score < baseline.score:
                regressions.append(
                    {
                        "case_id": result.case_id,
                        "before": baseline.score,
                        "after": result.score,
                        "delta": result.score - baseline.score,
                    }
                )
            elif baseline and result.score > baseline.score:
                improvements.append(
                    {
                        "case_id": result.case_id,
                        "before": baseline.score,
                        "after": result.score,
                        "delta": result.score - baseline.score,
                    }
                )

        return {
            "has_regression": len(regressions) > 0,
            "regression_count": len(regressions),
            "improvement_count": len(improvements),
            "regressions": regressions[:5],
            "improvements": improvements[:3],
        }


class ArenaGate:
    """Arena 门禁 — 决定补丁是否可以发布"""

    MIN_PASS_RATE = 80.0
    MAX_REGRESSION_COUNT = 2

    def evaluate(self, report: ArenaRunReport, baseline_compare: dict[str, Any] | None = None) -> ArenaDecision:
        """评估测试结果"""
        if report.error:
            return ArenaDecision.FAIL

        # 1. 通过率检查
        if report.pass_rate < self.MIN_PASS_RATE:
            return ArenaDecision.FAIL

        # 2. 回归检查
        if baseline_compare and baseline_compare.get("has_regression"):
            if baseline_compare.get("regression_count", 0) > self.MAX_REGRESSION_COUNT:
                return ArenaDecision.FAIL
            return ArenaDecision.NEEDS_REVIEW

        return ArenaDecision.PASS

    def can_release(self, report: ArenaRunReport, baseline_compare: dict[str, Any] | None = None) -> bool:
        return self.evaluate(report, baseline_compare) == ArenaDecision.PASS


class ReportStore:
    """测试报告存储"""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "arena_reports.jsonl"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, report: ArenaRunReport) -> None:
        """保存报告"""
        data = report.to_dict()
        data["timestamp"] = time.time()
        with open(self.db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def load_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """加载最近报告"""
        if not self.db_path.exists():
            return []
        reports: list[dict[str, Any]] = []
        with open(self.db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    with contextlib.suppress(json.JSONDecodeError):
                        reports.append(json.loads(line))
        return reports[-limit:]

    def get_latest_for_patch(self, patch_id: str) -> dict[str, Any] | None:
        """获取补丁的最新报告"""
        reports = self.load_recent(100)
        for r in reports:
            if r.get("patch_id") == patch_id:
                return r
        return None

    def get_stats(self) -> dict[str, Any]:
        """获取统计"""
        reports = self.load_recent(100)
        if not reports:
            return {"total": 0}
        passes = sum(1 for r in reports if r.get("decision") == "pass")
        return {
            "total": len(reports),
            "pass_count": passes,
            "pass_rate": round(passes / len(reports) * 100, 1) if reports else 0,
        }


class ReleaseBridge:
    """发布桥接 — 连接 Arena 和 GradualRelease"""

    def __init__(self, arena_gate: ArenaGate | None = None, report_store: ReportStore | None = None):
        self.arena_gate = arena_gate or ArenaGate()
        self.report_store = report_store or ReportStore()

    def evaluate_for_release(
        self, report: ArenaRunReport, baseline_compare: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """评估补丁是否可以进入灰度发布"""
        decision = self.arena_gate.evaluate(report, baseline_compare)

        result = {
            "patch_id": report.patch_id,
            "decision": decision.value,
            "pass_rate": report.pass_rate,
            "can_release": decision == ArenaDecision.PASS,
            "needs_review": decision == ArenaDecision.NEEDS_REVIEW,
            "recommendation": "",
        }

        if decision == ArenaDecision.PASS:
            result["recommendation"] = "可以进入灰度发布"
        elif decision == ArenaDecision.NEEDS_REVIEW:
            result["recommendation"] = "需人工审查后决定"
        else:
            result["recommendation"] = "不通过，请检查回归项"

        return result
