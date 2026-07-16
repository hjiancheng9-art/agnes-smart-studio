"""
Router Replay — CRUX 路由评测回放引擎
=====================================
加载 router_golden_cases.jsonl → 对每条跑当前 IntelligencePolicyRouter →
计算精确匹配率、overroute/underroute 率、混淆矩阵。

使用方式:
    python -m core.router_replay
    python -m core.router_replay --jsonl data/router_golden_cases.jsonl --verbose
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .intelligence_policy import IntelligencePolicyRouter

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════
# ── 数据结构 ──
# ════════════════════════════════════════════════


@dataclass
class RouteEvalCase:
    """单条路由评测样本"""

    id: str
    text: str
    expected_mode: str
    acceptable_modes: list[str] | None = None
    expected_flags: dict[str, bool] | None = None
    tags: list[str] | None = None
    priority: str = "P0"

    @classmethod
    def from_dict(cls, d: dict) -> RouteEvalCase:
        return cls(
            id=d.get("id", "UNKN"),
            text=d.get("text", d.get("request", "")),
            expected_mode=d.get("expected_mode", "BALANCED"),
            acceptable_modes=d.get("acceptable_modes") or [d.get("expected_mode", "BALANCED")],
            expected_flags=d.get("expected_flags") or {},
            tags=d.get("tags") or [],
            priority=d.get("priority", "P0"),
        )

    def mode_acceptable(self, actual: str) -> bool:
        """检查实际路由模式是否可接受"""
        return actual in (self.acceptable_modes or [self.expected_mode])

    @property
    def ok(self) -> bool:
        return True  # 由外层评估


@dataclass
class SingleResult:
    """单条测试结果"""

    case_id: str
    text: str
    expected: str
    actual: str
    passed: bool
    acceptable: bool
    signal_scores: dict[str, float]
    latency: float = 0.0
    flags_match: bool = True
    failure_reason: str = ""


@dataclass
class EvalReport:
    """评测报告"""

    total: int = 0
    passed: int = 0
    acceptable: int = 0
    failures: list[SingleResult] = field(default_factory=list)
    results: list[SingleResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    # 混淆矩阵: {expected: {actual: count}}
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    # 标签分组
    by_tag: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        """精确匹配率"""
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def acceptable_rate(self) -> float:
        """可接受匹配率"""
        if self.total == 0:
            return 0.0
        return self.acceptable / self.total

    @property
    def overroute_rate(self) -> float:
        """过度路由率（应简单却给了复杂）"""
        cnt = sum(1 for r in self.results if r.expected in ("FAST", "BALANCED") and r.actual in ("DEEP", "SAFE"))
        return cnt / self.total if self.total else 0.0

    @property
    def underroute_rate(self) -> float:
        """不足路由率（应复杂却给了简单）"""
        cnt = sum(
            1 for r in self.results if r.expected in ("DEEP", "SAFE", "RESEARCH") and r.actual in ("FAST", "BALANCED")
        )
        return cnt / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "acceptable": self.acceptable,
            "accuracy": round(self.accuracy, 4),
            "acceptable_rate": round(self.acceptable_rate, 4),
            "overroute_rate": round(self.overroute_rate, 4),
            "underroute_rate": round(self.underroute_rate, 4),
            "duration_seconds": round(self.end_time - self.start_time, 2),
            "confusion": self.confusion,
            "by_tag": self.by_tag,
            "failures": [
                {
                    "id": f.case_id,
                    "expected": f.expected,
                    "actual": f.actual,
                    "reason": f.failure_reason,
                    "text": f.text[:80],
                }
                for f in self.failures[:20]
            ],
            "failure_count": len(self.failures),
        }


# ════════════════════════════════════════════════
# ── 回放引擎 ──
# ════════════════════════════════════════════════


class RouterReplay:
    """路由回放引擎"""

    def __init__(self, router: IntelligencePolicyRouter | None = None):
        self.router = router or IntelligencePolicyRouter()

    def load_cases(self, jsonl_path: str | Path) -> list[RouteEvalCase]:
        """从 JSONL 加载样本"""
        cases: list[RouteEvalCase] = []
        path = Path(jsonl_path)

        if not path.exists():
            logger.warning(f"黄金集文件不存在: {path}")
            return cases

        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cases.append(RouteEvalCase.from_dict(data))
                except json.JSONDecodeError as e:
                    logger.warning(f"第 {line_num} 行 JSON 解析失败: {e}")

        logger.info(f"加载 {len(cases)} 条黄金样本")
        return cases

    def run_single(self, case: RouteEvalCase) -> SingleResult:
        """对单条样本执行路由"""
        start = time.time()

        # 路由
        mode = self.router.route(case.text)
        actual = mode.value

        # 信号分数
        try:
            summary = self.router.summary(case.text)
            scores = summary.get("signal_scores", {})
        except Exception:
            scores = {}

        latency = time.time() - start

        passed = actual == case.expected_mode
        acceptable = case.mode_acceptable(actual)

        # 标记检查
        flags_match = True
        failure_reason = ""

        if not passed:
            failure_reason = f"期望 {case.expected_mode}，实际 {actual}"
        elif not acceptable:
            failure_reason = f"模式 {actual} 不在可接受列表 {case.acceptable_modes} 中"

        return SingleResult(
            case_id=case.id,
            text=case.text,
            expected=case.expected_mode,
            actual=actual,
            passed=passed,
            acceptable=acceptable,
            signal_scores=scores,
            latency=latency,
            flags_match=flags_match,
            failure_reason=failure_reason,
        )

    def run_all(self, cases: list[RouteEvalCase]) -> EvalReport:
        """对所有样本执行路由评测"""
        report = EvalReport(start_time=time.time())

        for case in cases:
            result = self.run_single(case)
            report.results.append(result)
            report.total += 1

            if result.passed:
                report.passed += 1
            if result.acceptable:
                report.acceptable += 1
            if not result.acceptable:
                report.failures.append(result)

            # 混淆矩阵
            exp = case.expected_mode
            act = result.actual
            if exp not in report.confusion:
                report.confusion[exp] = {}
            report.confusion[exp][act] = report.confusion[exp].get(act, 0) + 1

            # 标签分组
            if case.tags:
                for tag in case.tags:
                    if tag not in report.by_tag:
                        report.by_tag[tag] = {"total": 0, "passed": 0}
                    report.by_tag[tag]["total"] += 1
                    if result.passed:
                        report.by_tag[tag]["passed"] += 1

        report.end_time = time.time()
        return report

    def print_report(self, report: EvalReport, verbose: bool = False) -> str:
        """打印评测报告"""
        lines: list[str] = []
        d = report.to_dict()

        lines.append("=" * 60)
        lines.append("📊 Router Replay 评测报告")
        lines.append("=" * 60)
        lines.append(f"总样本:     {d['total']}")
        lines.append(f"精确匹配:   {d['passed']} ({d['accuracy'] * 100:.1f}%)")
        lines.append(f"可接受匹配: {d['acceptable']} ({d['acceptable_rate'] * 100:.1f}%)")
        lines.append(f"过度路由率: {d['overroute_rate'] * 100:.1f}%")
        lines.append(f"不足路由率: {d['underroute_rate'] * 100:.1f}%")
        lines.append(f"耗时:       {d['duration_seconds']:.2f}s")
        lines.append("")

        # 混淆矩阵
        lines.append("─" * 40)
        lines.append("混淆矩阵 (期望\\实际):")
        all_modes = sorted(set(list(d["confusion"].keys()) + [v for cm in d["confusion"].values() for v in cm]))
        header = "{:<12}".format("期望\\实际") + "".join(f"{m:<8}" for m in all_modes)
        lines.append(header)
        for exp in all_modes:
            row = f"{exp:<12}"
            for act in all_modes:
                cnt = d["confusion"].get(exp, {}).get(act, 0)
                row += f"{cnt:<8}"
            lines.append(row)

        # 标签分组
        if d["by_tag"]:
            lines.append("")
            lines.append("─" * 40)
            lines.append("按标签分组:")
            for tag, info in sorted(d["by_tag"].items()):
                acc = info["passed"] / info["total"] * 100 if info["total"] else 0
                lines.append(f"  {tag:<15} {info['passed']}/{info['total']} ({acc:.0f}%)")

        # 失败详情
        if d["failures"] and verbose:
            lines.append("")
            lines.append("─" * 40)
            lines.append(f"失败详情 (前 {len(d['failures'])} 条):")
            for f in d["failures"]:
                lines.append(f'  [{f["id"]}] {f["reason"]}: "{f["text"]}"')

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# ════════════════════════════════════════════════
# ── CLI 入口 ──
# ════════════════════════════════════════════════


def main(jsonl_path: str | None = None, verbose: bool = False):
    """CLI 入口"""
    if jsonl_path is None:
        jsonl_path = str(Path(__file__).parent.parent / "data" / "router_golden_cases.jsonl")

    replay = RouterReplay()
    cases = replay.load_cases(jsonl_path)

    if not cases:
        print(f"❌ 未加载到黄金样本 (从 {jsonl_path})")
        return

    report = replay.run_all(cases)
    output = replay.print_report(report, verbose=verbose)
    print(output)

    # 返回便于程序调用
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Router Replay — 路由评测回放")
    parser.add_argument("--jsonl", default=None, help="黄金集 JSONL 路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示失败详情")
    args = parser.parse_args()

    report = main(jsonl_path=args.jsonl, verbose=args.verbose)
    if report and report.accuracy < 0.8:
        print(f"\n⚠️ 准确率 {report.accuracy * 100:.1f}% < 80%，建议优化路由")
