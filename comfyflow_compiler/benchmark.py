"""ComfyFlow Compiler — 基准测试套件

用法:
  python -m comfyflow_compiler.benchmark                    # 全量
  python -m comfyflow_compiler.benchmark --quick            # 快速 (仅编译)
  python -m comfyflow_compiler.benchmark --report           # 输出 JSON 报告
"""

from __future__ import annotations

import json
import sys
import time
import os
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comfyflow_compiler.compiler import ComfyFlowCompiler
from comfyflow_compiler.intent_parser import parse_intent
from comfyflow_compiler.capability.snapshot import probe_comfyui

# 基准测试用例
BENCH_INTENTS = [
    "a cat astronaut in space",
    "cinematic portrait of a warrior, dramatic lighting",
    "cyberpunk city at night, neon lights, rain",
    "anime girl with blue hair, holding a sword",
    "a photorealistic tiger in the snow, detailed fur",
    "mountain landscape at sunset, photorealistic",
    "product shot of a perfume bottle on marble",
    "a dog running on the beach, video",
    "waves crashing on rocks, cinematic video",
    "turn this photo into anime style",
]

# 预期最小节点数（按任务类型）
MIN_NODES = {
    "txt2img": 3,
    "img2img": 3,
    "t2v": 3,
    "i2v": 3,
    "video": 3,   # intent parser returns "video" before compiler splits to t2v/i2v
}


@dataclass
class BenchmarkResult:
    """单次基准结果"""
    intent: str
    success: bool
    elapsed_ms: float
    blueprint_used: str = ""
    task_type: str = ""
    node_count: int = 0
    quality_score: float = 0.0
    error: str = ""


@dataclass
class BenchmarkReport:
    """完整基准报告"""
    version: str = "6.6.0"
    timestamp: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_compile_ms: float = 0.0
    avg_quality: float = 0.0
    min_nodes_ok: int = 0
    results: list[dict] = field(default_factory=list)
    by_task: dict = field(default_factory=dict)
    comfyui_online: bool = False
    comfyui_probe: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "avg_compile_ms": round(self.avg_compile_ms, 1),
            "avg_quality": round(self.avg_quality, 3),
            "min_nodes_ok": self.min_nodes_ok,
            "pass_rate": f"{self.passed}/{self.total}",
            "by_task": self.by_task,
            "comfyui_online": self.comfyui_online,
            "warnings": self.warnings,
        }


def run_benchmark(quick: bool = False) -> BenchmarkReport:
    """运行基准测试"""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    report = BenchmarkReport(timestamp=now)
    compiler = ComfyFlowCompiler()

    # ComfyUI 状态
    snap = probe_comfyui()
    report.comfyui_online = snap.comfyui_online
    report.comfyui_probe = snap.summary

    intents = BENCH_INTENTS[:5] if quick else BENCH_INTENTS
    total_start = time.time()

    for intent in intents:
        start = time.time()
        try:
            result = compiler.compile(intent)
            elapsed_ms = (time.time() - start) * 1000

            br = BenchmarkResult(
                intent=intent[:50],
                success=result.success,
                elapsed_ms=round(elapsed_ms, 1),
                blueprint_used=result.blueprint_used,
                error=result.error or "",
            )

            if result.success:
                report.passed += 1
                wf = result.workflow_json.get("prompt", result.workflow_json) if result.workflow_json else {}
                nodes = [v for v in wf.values() if isinstance(v, dict) and "class_type" in v]
                br.node_count = len(nodes)
                br.task_type = parse_intent(intent).task_type
                if result.quality_report:
                    br.quality_score = result.quality_report.overall_score

                # 检查节点数
                expected = MIN_NODES.get(br.task_type, 2)
                if br.node_count >= expected:
                    report.min_nodes_ok += 1
                else:
                    report.warnings.append(f"{intent[:30]}: {br.node_count} nodes < {expected}")

                # 按任务统计
                if br.task_type not in report.by_task:
                    report.by_task[br.task_type] = {"count": 0, "pass": 0}
                report.by_task[br.task_type]["count"] += 1
                report.by_task[br.task_type]["pass"] += 1
            else:
                report.failed += 1
                br.task_type = parse_intent(intent).task_type
                if br.task_type not in report.by_task:
                    report.by_task[br.task_type] = {"count": 0, "pass": 0}
                report.by_task[br.task_type]["count"] += 1

            report.results.append({
                "intent": br.intent,
                "success": br.success,
                "elapsed_ms": br.elapsed_ms,
                "blueprint": br.blueprint_used,
                "task_type": br.task_type,
                "nodes": br.node_count,
                "quality": br.quality_score,
                "error": br.error,
            })

        except Exception as e:
            report.failed += 1
            report.results.append({
                "intent": intent[:50],
                "success": False,
                "elapsed_ms": 0,
                "error": str(e),
            })

    report.total = report.passed + report.failed
    total_elapsed = time.time() - total_start

    if report.passed > 0:
        passed_results = [r for r in report.results if r["success"]]
        report.avg_compile_ms = sum(r["elapsed_ms"] for r in passed_results) / len(passed_results)
        report.avg_quality = sum(r["quality"] for r in passed_results if r["quality"]) / max(
            sum(1 for r in passed_results if r["quality"]), 1
        )

    return report


def print_report(report: BenchmarkReport):
    """打印基准报告"""
    print(f"\n{'='*55}")
    print(f"  ComfyFlow Compiler — Benchmark Report")
    print(f"{'='*55}")
    print(f"  Version:     {report.version}")
    print(f"  Timestamp:   {report.timestamp}")
    print(f"  ComfyUI:     {'✅ online' if report.comfyui_online else '❌ offline'}")

    if report.comfyui_probe:
        s = report.comfyui_probe
        print(f"  Environment: {s.get('version','')} | {s.get('nodes','')} | {s.get('models','')}")

    print(f"\n  {'─'*55}")
    print(f"  {'Result':^8} {'Elapsed':>8} {'Quality':>8} {'Nodes':>5}  {'Intent':<30}")
    print(f"  {'─'*55}")

    for r in report.results:
        flag = "✅" if r["success"] else "❌"
        q = f"{r['quality']:.2f}" if r["quality"] else "-"
        n = str(r["nodes"]) if r["nodes"] else "-"
        e = f"{r['elapsed_ms']:6.0f}ms" if r["elapsed_ms"] else "  N/A"
        print(f"  {flag:^8} {e:>8} {q:>8} {n:>5}  {r['intent'][:30]}")

    print(f"  {'─'*55}")
    print(f"\n  Summary:")
    print(f"    Total:     {report.total}")
    print(f"    Passed:    {report.passed} ✅")
    print(f"    Failed:    {report.failed} {'❌' if report.failed else '✅'}")
    print(f"    Pass rate: {report.passed}/{report.total} ({report.passed/max(report.total,1)*100:.0f}%)")
    print(f"    Avg compile: {report.avg_compile_ms:.0f}ms")
    print(f"    Avg quality: {report.avg_quality:.3f}")
    print(f"    Min nodes ok: {report.min_nodes_ok}/{report.passed}")

    if report.by_task:
        print(f"\n  By Task:")
        for task, stats in sorted(report.by_task.items()):
            print(f"    {task:12s}: {stats['pass']}/{stats['count']} passed")

    if report.warnings:
        print(f"\n  ⚠️  Warnings:")
        for w in report.warnings:
            print(f"    {w}")

    print(f"{'='*55}")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    output_json = "--report" in sys.argv

    report = run_benchmark(quick=quick)
    print_report(report)

    if output_json:
        path = "output/benchmark_report.json"
        os.makedirs("output", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"\n  Report saved: {path}")
