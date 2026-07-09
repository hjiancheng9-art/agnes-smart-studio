"""Benchmark 测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from comfyflow_compiler.benchmark import (
    BenchmarkResult, BenchmarkReport, run_benchmark, print_report,
    BENCH_INTENTS, MIN_NODES,
)


def test_bench_intents_have_min_nodes():
    """所有基准意图都有对应最小节点定义"""
    for intent in BENCH_INTENTS:
        from comfyflow_compiler.intent_parser import parse_intent
        task = parse_intent(intent)
        assert task.task_type in MIN_NODES, f"{intent[:30]} → {task.task_type} 无 MIN_NODES 定义"


def test_run_benchmark_quick():
    """快速基准不应崩溃"""
    report = run_benchmark(quick=True)
    assert report.total > 0
    assert report.total <= 5  # quick mode
    assert report.passed + report.failed == report.total
    assert report.timestamp, "应有时间戳"


def test_run_benchmark_full():
    """全量基准不应崩溃"""
    report = run_benchmark(quick=False)
    assert report.total == len(BENCH_INTENTS)
    assert report.passed + report.failed == report.total
    assert report.comfyui_online in (True, False)


def test_benchmark_report_serialization():
    """to_dict 输出应有必要字段"""
    report = run_benchmark(quick=True)
    d = report.to_dict()
    required = ["version", "timestamp", "total", "passed", "failed",
                 "avg_compile_ms", "pass_rate", "by_task", "comfyui_online"]
    for k in required:
        assert k in d, f"缺少字段: {k}"
    assert d["pass_rate"] == f"{report.passed}/{report.total}"


def test_benchmark_result_fields():
    """BenchmarkResult 字段正确"""
    br = BenchmarkResult(
        intent="test",
        success=True,
        elapsed_ms=100.0,
        blueprint_used="test_bp",
        task_type="txt2img",
        node_count=8,
        quality_score=0.85,
    )
    assert br.success
    assert br.elapsed_ms == 100.0
    assert br.task_type == "txt2img"


def test_print_report_no_crash():
    """print_report 不崩溃"""
    import io
    report = run_benchmark(quick=True)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        print_report(report)
    finally:
        sys.stdout = old
    output = buf.getvalue()
    assert "ComfyFlow Compiler" in output
    assert "Benchmark Report" in output
    assert "Passed" in output or "passed" in output


def test_benchmark_label():
    """测试标签"""
    from comfyflow_compiler import __version__ as V
    assert V == "6.6.0"
