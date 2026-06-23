"""Tests for core.eval_harness — 基准评测套件与打分引擎。

EvalEngine 对预定义的 benchmark 任务执行 tool_executor 回调，
基于关键词命中打分（score >= 0.5 → pass）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.eval_harness import BENCHMARKS, EvalEngine


# ── BENCHMARKS 数据健全性（零 mock）────────────────────────────


class TestBenchmarksData:
    """预定义基准数据应结构完整、ID 唯一。"""

    def test_all_have_required_keys(self):
        required = {"id", "name", "goal", "category", "expected_keywords", "weight"}
        for b in BENCHMARKS:
            assert required.issubset(b.keys()), f"{b.get('id', '?')} 缺少字段 {required - b.keys()}"

    def test_ids_are_unique(self):
        ids = [b["id"] for b in BENCHMARKS]
        assert len(ids) == len(set(ids)), f"重复 ID: {[x for x in ids if ids.count(x) > 1]}"

    def test_expected_keywords_non_empty(self):
        for b in BENCHMARKS:
            assert len(b["expected_keywords"]) > 0, f"{b['id']} 的 expected_keywords 为空"

    def test_weight_positive(self):
        for b in BENCHMARKS:
            assert b["weight"] > 0, f"{b['id']} 的 weight <= 0"

    def test_at_least_one_benchmark(self):
        assert len(BENCHMARKS) >= 1


# ── run_benchmark 打分（传 mock tool_executor）─────────────────


class TestRunBenchmark:
    """单基准执行：分类分发、打分逻辑、异常处理。"""

    def test_all_keywords_hit_full_score(self):
        bench = {
            "id": "t1", "name": "Test", "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo"],
            "weight": 1.0,
        }
        # 返回含全部关键词的输出
        executor = lambda name, args: "alpha and bravo found here"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 1.0
        assert result["status"] == "pass"

    def test_no_keywords_zero_score(self):
        bench = {
            "id": "t2", "name": "Test", "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo"],
            "weight": 1.0,
        }
        executor = lambda name, args: "nothing relevant here"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 0.0
        assert result["status"] == "fail"

    def test_partial_keyword_boundary(self):
        bench = {
            "id": "t3", "name": "Test", "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo", "charlie"],
            "weight": 1.0,
        }
        # 命中 2/3 → 0.67 → pass (>=0.5)
        executor = lambda name, args: "alpha bravo here"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == round(2 / 3 * 1.0, 2)
        assert result["status"] == "pass"

    def test_partial_below_threshold(self):
        bench = {
            "id": "t4", "name": "Test", "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo", "charlie"],
            "weight": 0.6,
        }
        # 命中 1/3 → 0.2 → fail (< 0.5)
        executor = lambda name, args: "only alpha"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == round(1 / 3 * 0.6, 2)
        assert result["status"] == "fail"

    def test_keyword_matching_case_insensitive(self):
        bench = {
            "id": "t5", "name": "Test", "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["Alpha", "BRAVO"],
            "weight": 1.0,
        }
        executor = lambda name, args: "ALPHA and bravo in output"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 1.0

    def test_code_search_dispatches_search_files(self):
        bench = {
            "id": "t6", "name": "Test", "category": "code_search",
            "goal": "Find where the base URL is",
            "expected_keywords": ["found"],
            "weight": 1.0,
        }
        calls = []
        executor = lambda name, args: (calls.append((name, args)), "found")[1]
        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "search_files"
        # pattern 取 goal.split()[0]
        assert calls[0][1]["pattern"] == "Find"

    def test_code_quality_dispatches_env_check(self):
        bench = {
            "id": "t7", "name": "Test", "category": "code_quality",
            "goal": "Check syntax",
            "expected_keywords": ["OK"],
            "weight": 1.0,
        }
        calls = []
        executor = lambda name, args: (calls.append((name, args)), "OK")[1]
        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "env_check"

    def test_understand_dispatches_read_file(self):
        bench = {
            "id": "t8", "name": "Test", "category": "understand",
            "goal": "Read the docs",
            "expected_keywords": ["content"],
            "weight": 1.0,
        }
        calls = []
        executor = lambda name, args: (calls.append((name, args)), "content")[1]
        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "read_file"
        assert calls[0][1]["path"] == "README.md"

    def test_output_truncated_to_500(self):
        bench = {
            "id": "t9", "name": "Test", "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }
        executor = lambda name, args: "a" * 1000
        result = EvalEngine().run_benchmark(bench, executor)
        assert len(result["output"]) <= 500

    def test_elapsed_is_non_negative(self):
        bench = {
            "id": "t10", "name": "Test", "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }
        executor = lambda name, args: "x"
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["elapsed"] >= 0

    def test_result_has_required_fields(self):
        bench = {
            "id": "t11", "name": "Test", "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }
        executor = lambda name, args: "x"
        result = EvalEngine().run_benchmark(bench, executor)
        for key in ("id", "name", "category", "status", "score", "output", "elapsed"):
            assert key in result


# ── 异常处理 ──────────────────────────────────────────────────


class TestRunBenchmarkExceptions:
    """只 catch OSError/ValueError/RuntimeError，其余逃逸。"""

    def test_os_error_caught(self):
        bench = {
            "id": "te1", "name": "Test", "category": "understand",
            "goal": "test", "expected_keywords": ["x"], "weight": 1.0,
        }
        executor = lambda name, args: (_ for _ in ()).throw(OSError("disk full"))
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["status"] == "error"
        assert "disk full" in result["output"]

    def test_runtime_error_caught(self):
        bench = {
            "id": "te2", "name": "Test", "category": "understand",
            "goal": "test", "expected_keywords": ["x"], "weight": 1.0,
        }
        executor = lambda name, args: (_ for _ in ()).throw(RuntimeError("crash"))
        result = EvalEngine().run_benchmark(bench, executor)
        assert result["status"] == "error"
        assert "crash" in result["output"]

    def test_error_output_truncated_to_200(self):
        bench = {
            "id": "te3", "name": "Test", "category": "understand",
            "goal": "test", "expected_keywords": ["x"], "weight": 1.0,
        }
        long_msg = "x" * 300
        executor = lambda name, args: (_ for _ in ()).throw(ValueError(long_msg))
        result = EvalEngine().run_benchmark(bench, executor)
        assert len(result["output"]) <= 200

    def test_key_error_not_caught(self):
        # KeyError 不在 catch 范围，会逃逸
        bench = {
            "id": "te4", "name": "Test", "category": "understand",
            "goal": "test", "expected_keywords": ["x"], "weight": 1.0,
        }
        executor = lambda name, args: (_ for _ in ()).throw(KeyError("not caught"))
        with pytest.raises(KeyError):
            EvalEngine().run_benchmark(bench, executor)


# ── run_all 汇总 ────────────────────────────────────────────────


class TestRunAll:
    """run_all 汇总报告结构。"""

    def test_all_pass(self):
        # 构造一个全 pass 的 executor
        all_kw = set()
        for b in BENCHMARKS:
            all_kw.update(b["expected_keywords"])
        executor = lambda name, args: " ".join(all_kw)

        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        assert report["suite"] == "CRUX Core Benchmarks"
        assert report["total"] == len(BENCHMARKS)
        assert report["passed"] == len(BENCHMARKS)
        assert report["failed"] == 0
        assert report["score"] == 100.0
        assert len(report["results"]) == len(BENCHMARKS)

    def test_all_fail(self):
        executor = lambda name, args: "no keywords at all"
        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        assert report["passed"] == 0
        assert report["failed"] == len(BENCHMARKS)
        assert report["score"] == 0.0

    def test_report_structure(self):
        executor = lambda name, args: "x"
        report = EvalEngine().run_all(tool_executor=executor)
        for key in ("suite", "total", "passed", "failed", "score", "results"):
            assert key in report
        assert isinstance(report["results"], list)
        assert len(report["results"]) == len(BENCHMARKS)
