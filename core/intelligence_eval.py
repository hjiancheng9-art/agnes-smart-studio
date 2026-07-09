"""
Intelligence Eval — CRUX 端到端智能评测
=======================================
不再只测"路由选对了没"，而是测"复杂任务真的解决好了没"。

评测维度:
1. OutcomeMatch: 最终结果是否符合预期
2. EvidenceQuality: 答案是否有证据支撑
3. StepCompleteness: 步骤是否完整（所有步骤都走了）
4. Recovery: 失败步骤是否被正确处理

使用方式:
    python -m core.intelligence_eval
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evidence_gate import EvidenceGate
from .intelligence_trace import TraceStore

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """端到端评测样本"""
    id: str
    request: str
    expected_outcome: str
    tags: list[str] | None = None
    difficulty: str = "medium"
    expected_steps: list[str] | None = None  # 预期的步骤

    @classmethod
    def from_dict(cls, d: dict) -> EvalCase:
        return cls(
            id=d["id"],
            request=d["request"],
            expected_outcome=d.get("expected_outcome", ""),
            tags=d.get("tags"),
            difficulty=d.get("difficulty", "medium"),
            expected_steps=d.get("expected_steps"),
        )


@dataclass
class EvalResult:
    """单条评测结果"""
    case_id: str
    request: str
    outcome_match: bool = False        # 结果是否符合预期
    evidence_quality: str = "none"     # none / weak / medium / strong
    step_completeness: float = 0.0     # 0.0 - 1.0
    has_recovery: bool = False         # 失败步骤是否回退/修复
    total_duration: float = 0.0
    score: float = 0.0                 # 综合评分 0-100
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "request": self.request[:80],
            "outcome_match": self.outcome_match,
            "evidence_quality": self.evidence_quality,
            "step_completeness": round(self.step_completeness, 2),
            "has_recovery": self.has_recovery,
            "total_duration": round(self.total_duration, 2),
            "score": round(self.score, 1),
        }


@dataclass
class EvalReport:
    """评测报告"""
    total: int = 0
    results: list[EvalResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.score for r in self.results) / len(self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.score >= 70)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total * 100 if self.total else 0.0

    @property
    def evidence_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        for r in self.results:
            q = r.evidence_quality
            stats[q] = stats.get(q, 0) + 1
        return stats

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pass_count": self.pass_count,
            "pass_rate": round(self.pass_rate, 1),
            "avg_score": round(self.avg_score, 1),
            "evidence_stats": self.evidence_stats,
            "duration_seconds": round(self.end_time - self.start_time, 2),
            "results": [r.to_dict() for r in self.results],
        }


class IntelligenceEval:
    """端到端智能评测引擎"""

    def __init__(self, trace_store: TraceStore | None = None,
                 evidence_gate: EvidenceGate | None = None):
        self.trace_store = trace_store or TraceStore()
        self.evidence_gate = evidence_gate or EvidenceGate()

    def load_cases(self, jsonl_path: str | Path) -> list[EvalCase]:
        """加载评测样本"""
        cases: list[EvalCase] = []
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning(f"评测集文件不存在: {path}")
            return cases
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cases.append(EvalCase.from_dict(data))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"第 {line_num} 行解析失败: {e}")
        return cases

    def evaluate_trace(self, trace: dict[str, Any], case: EvalCase) -> EvalResult:
        """用轨迹评估单条样本"""
        result = EvalResult(case_id=case.id, request=case.request)

        if not trace:
            result.score = 0
            result.details = {"error": "no_trace"}
            return result

        # 1. 结果匹配度
        status = trace.get("status", "")
        result.outcome_match = status in ("pass", "partial")

        # 2. 证据质量
        critique = trace.get("critique_summary", "")
        steps = trace.get("steps", [])
        all_outputs = " ".join(s.get("output_summary", "") for s in steps)
        combined_text = critique + " " + all_outputs + " " + case.request

        gate_result = self.evidence_gate.check_text(combined_text, question=case.request)
        result.evidence_quality = gate_result.evidence_quality

        # 3. 步骤完整性
        expected = case.expected_steps or ["plan", "criticize"]
        if steps:
            step_names = [s.get("name", "") for s in steps]
            matched = sum(1 for e in expected if e in step_names)
            result.step_completeness = matched / len(expected) if expected else 1.0
        else:
            result.step_completeness = 0.0

        # 4. 失败恢复
        failed = [s for s in steps if s.get("status") == "failed"]
        has_repair = any("repair" in s.get("name", "") for s in steps)
        result.has_recovery = bool(failed) and has_repair

        # 5. 耗时
        result.total_duration = trace.get("total_duration", 0)

        # 6. 综合评分
        score = 0.0
        if result.outcome_match:
            score += 30
        quality_scores = {"none": 0, "weak": 10, "medium": 20, "strong": 30}
        score += quality_scores.get(result.evidence_quality, 0)
        score += result.step_completeness * 20
        if result.has_recovery:
            score += 10
        # 耗时惩罚（超过 120s 扣分）
        if result.total_duration > 120:
            score -= min(20, (result.total_duration - 120) / 10)
        result.score = max(0, min(100, score))

        result.details = {
            "status": status,
            "step_count": len(steps),
            "failed_step_count": len(failed),
        }
        return result

    def evaluate_all(self, cases: list[EvalCase]) -> EvalReport:
        """评测所有样本"""
        report = EvalReport(start_time=time.time())

        for case in cases:
            report.total += 1
            # 找轨迹 — 简单匹配 request 前缀
            traces = self.trace_store.query(limit=100)
            matched_trace = None
            for t in traces:
                if t.get("user_request", "").startswith(case.request[:30]):
                    matched_trace = t
                    break

            if matched_trace:
                result = self.evaluate_trace(matched_trace, case)
            else:
                # 无轨迹 — 只能评分 0
                result = EvalResult(case_id=case.id, request=case.request,
                                    score=20, details={"error": "no_trace_found"})

            report.results.append(result)

        report.end_time = time.time()
        return report

    def print_report(self, report: EvalReport) -> str:
        """打印评测报告"""
        d = report.to_dict()
        lines = []
        lines.append("=" * 60)
        lines.append("📊 端到端智能评测报告")
        lines.append("=" * 60)
        lines.append(f"总样本:  {d['total']}")
        lines.append(f"通过:    {d['pass_count']} ({d['pass_rate']:.1f}%)")
        lines.append(f"平均分:  {d['avg_score']:.1f}/100")
        lines.append(f"证据质量: {d['evidence_stats']}")
        lines.append(f"耗时:    {d['duration_seconds']:.2f}s")
        lines.append("")
        lines.append("─" * 40)
        lines.append("各样本评分:")
        for r in d['results']:
            icon = "✅" if r['score'] >= 70 else "❌"
            lines.append(f"  {icon} [{r['case_id']}] {r['score']:5.1f}分 | "
                         f"结果={r['outcome_match']} 证据={r['evidence_quality']} "
                         f"步骤={r['step_completeness']:.0%}")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


def main(jsonl_path: str | None = None, verbose: bool = False):
    """CLI 入口"""
    if jsonl_path is None:
        jsonl_path = str(Path(__file__).parent.parent / "data" / "intelligence_eval_cases.jsonl")

    eval_engine = IntelligenceEval()
    cases = eval_engine.load_cases(jsonl_path)

    if not cases:
        print(f"❌ 未加载到评测样本 (从 {jsonl_path})")
        return

    report = eval_engine.evaluate_all(cases)
    output = eval_engine.print_report(report)
    print(output)

    if report.avg_score < 60:
        print("\n⚠️ 平均分 < 60，需要优化")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Intelligence Eval — 端到端评测")
    parser.add_argument("--jsonl", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    main(jsonl_path=args.jsonl, verbose=args.verbose)
