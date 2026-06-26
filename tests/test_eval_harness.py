"""Tests for core.eval_harness — 基准评测套件与打分引擎。

EvalEngine 对预定义的 benchmark 任务执行 tool_executor 回调，
基于关键词命中打分（score >= 0.5 → pass）。
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.eval_harness import BENCHMARKS, ROOT, EvalEngine, run_evals

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

    def test_categories_are_known(self):
        """category 只允许 code_search / code_quality / understand 三种。"""
        valid = {"code_search", "code_quality", "understand"}
        for b in BENCHMARKS:
            assert b["category"] in valid, f"{b['id']} 的 category={b['category']} 不在 {valid} 中"

    def test_benchmark_ids_have_prefix(self):
        """所有 benchmark id 应以 bench_ 开头，方便过滤。"""
        for b in BENCHMARKS:
            assert b["id"].startswith("bench_"), f"{b['id']} 缺少 bench_ 前缀"

    def test_total_weight_is_positive(self):
        """BENCHMARKS 权重之和须 > 0，保证 run_all 除法安全。"""
        total = sum(b["weight"] for b in BENCHMARKS)
        assert total > 0

    def test_no_extra_keys(self):
        """BENCHMARK 字段白名单检查：不应包含非预期字段。"""
        allowed = {"id", "name", "goal", "category", "expected_keywords", "weight"}
        for b in BENCHMARKS:
            extra = set(b.keys()) - allowed
            assert not extra, f"{b['id']} 包含多余字段: {extra}"


# ── run_benchmark 打分（传 mock tool_executor）─────────────────


class TestRunBenchmark:
    """单基准执行：分类分发、打分逻辑、异常处理。"""

    def test_all_keywords_hit_full_score(self):
        bench = {
            "id": "t1",
            "name": "Test",
            "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo"],
            "weight": 1.0,
        }

        # 返回含全部关键词的输出
        def executor(name, args):
            return "alpha and bravo found here"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 1.0
        assert result["status"] == "pass"

    def test_no_keywords_zero_score(self):
        bench = {
            "id": "t2",
            "name": "Test",
            "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "nothing relevant here"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 0.0
        assert result["status"] == "fail"

    def test_partial_keyword_boundary(self):
        bench = {
            "id": "t3",
            "name": "Test",
            "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo", "charlie"],
            "weight": 1.0,
        }

        # 命中 2/3 → 0.67 → pass (>=0.5)
        def executor(name, args):
            return "alpha bravo here"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == round(2 / 3 * 1.0, 2)
        assert result["status"] == "pass"

    def test_partial_below_threshold(self):
        bench = {
            "id": "t4",
            "name": "Test",
            "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["alpha", "bravo", "charlie"],
            "weight": 0.6,
        }

        # 命中 1/3 → 0.2 → fail (< 0.5)
        def executor(name, args):
            return "only alpha"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == round(1 / 3 * 0.6, 2)
        assert result["status"] == "fail"

    def test_keyword_matching_case_insensitive(self):
        bench = {
            "id": "t5",
            "name": "Test",
            "category": "understand",
            "goal": "test goal",
            "expected_keywords": ["Alpha", "BRAVO"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "ALPHA and bravo in output"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 1.0

    def test_code_search_dispatches_search_files(self):
        bench = {
            "id": "t6",
            "name": "Test",
            "category": "code_search",
            "goal": "Find where the base URL is",
            "expected_keywords": ["found"],
            "weight": 1.0,
        }
        calls = []

        def executor(name, args):
            calls.append((name, args))
            return "found"

        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "search_files"
        # pattern 取 goal.split()[0]
        assert calls[0][1]["pattern"] == "Find"

    def test_code_quality_dispatches_env_check(self):
        bench = {
            "id": "t7",
            "name": "Test",
            "category": "code_quality",
            "goal": "Check syntax",
            "expected_keywords": ["OK"],
            "weight": 1.0,
        }
        calls = []

        def executor(name, args):
            calls.append((name, args))
            return "OK"

        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "env_check"

    def test_understand_dispatches_read_file(self):
        bench = {
            "id": "t8",
            "name": "Test",
            "category": "understand",
            "goal": "Read the docs",
            "expected_keywords": ["content"],
            "weight": 1.0,
        }
        calls = []

        def executor(name, args):
            calls.append((name, args))
            return "content"

        EvalEngine().run_benchmark(bench, executor)
        assert calls[0][0] == "read_file"
        assert calls[0][1]["path"] == "README.md"

    def test_output_truncated_to_500(self):
        bench = {
            "id": "t9",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "a" * 1000

        result = EvalEngine().run_benchmark(bench, executor)
        assert len(result["output"]) <= 500

    def test_elapsed_is_non_negative(self):
        bench = {
            "id": "t10",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "x"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["elapsed"] >= 0

    def test_result_has_required_fields(self):
        bench = {
            "id": "t11",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "x"

        result = EvalEngine().run_benchmark(bench, executor)
        for key in ("id", "name", "category", "status", "score", "output", "elapsed"):
            assert key in result

    def test_exact_pass_threshold(self):
        """score 恰好 0.5 应判为 pass。"""
        bench = {
            "id": "t12",
            "name": "Threshold",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["key1", "key2"],
            "weight": 1.0,
        }
        # 1/2 * 1.0 = 0.5 → pass
        def executor(name, args):
            return "key1 only"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 0.5
        assert result["status"] == "pass"

    def test_empty_expected_keywords_no_crash(self):
        """expected_keywords 为空时，max(..., 1) 保护除零。"""
        bench = {
            "id": "t13",
            "name": "Empty KW",
            "category": "understand",
            "goal": "test",
            "expected_keywords": [],
            "weight": 1.0,
        }

        def executor(name, args):
            return "anything"

        result = EvalEngine().run_benchmark(bench, executor)
        # 0 / max(0,1) * 1.0 = 0.0
        assert result["score"] == 0.0
        assert result["status"] == "fail"

    def test_weight_zero(self):
        """weight=0 时 score 应为 0.0，status 为 fail。"""
        bench = {
            "id": "t14",
            "name": "Zero Weight",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["alpha"],
            "weight": 0.0,
        }

        def executor(name, args):
            return "alpha"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 0.0
        assert result["status"] == "fail"

    def test_executor_returns_none_raises_type_error(self):
        """tool_executor 返回 None → output[:500] 触发 TypeError 逃逸。"""
        bench = {
            "id": "t15",
            "name": "None Output",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            return None

        with pytest.raises(TypeError):
            EvalEngine().run_benchmark(bench, executor)

    def test_keyword_substring_match(self):
        """关键词是子串匹配，非全词匹配。"""
        bench = {
            "id": "t16",
            "name": "Substring",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["base_url"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "the base_url is here"

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 1.0

    def test_started_is_recent(self):
        """started 应是接近当前时间的 Unix 时间戳。"""
        bench = {
            "id": "t17",
            "name": "Timestamp",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }
        before = time.time()

        def executor(name, args):
            return "x"

        result = EvalEngine().run_benchmark(bench, executor)
        after = time.time()
        assert before <= result["started"] <= after

    def test_run_benchmark_does_not_accumulate_results(self):
        """run_benchmark 不修改 self.results，仅返回结果（累积由 run_all 负责）。"""
        bench = {
            "id": "t18",
            "name": "Standalone",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            return "x"

        engine = EvalEngine()
        result = engine.run_benchmark(bench, executor)
        assert isinstance(result, dict)
        assert engine.results == []


# ── 异常处理 ──────────────────────────────────────────────────


class TestRunBenchmarkExceptions:
    """只 catch OSError/ValueError/RuntimeError，其余逃逸。"""

    def test_os_error_caught(self):
        bench = {
            "id": "te1",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise OSError("disk full")

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["status"] == "error"
        assert "disk full" in result["output"]

    def test_runtime_error_caught(self):
        bench = {
            "id": "te2",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise RuntimeError("crash")

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["status"] == "error"
        assert "crash" in result["output"]

    def test_error_output_truncated_to_200(self):
        bench = {
            "id": "te3",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }
        long_msg = "x" * 300

        def executor(name, args):
            raise ValueError(long_msg)

        result = EvalEngine().run_benchmark(bench, executor)
        assert len(result["output"]) <= 200

    def test_key_error_not_caught(self):
        # KeyError 不在 catch 范围，会逃逸
        bench = {
            "id": "te4",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise KeyError("not caught")

        with pytest.raises(KeyError):
            EvalEngine().run_benchmark(bench, executor)

    def test_value_error_caught(self):
        """ValueError 在 catch 列表中，应被捕获为 error。"""
        bench = {
            "id": "te5",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise ValueError("bad value")

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["status"] == "error"
        assert "bad value" in result["output"]

    def test_error_elapsed_still_recorded(self):
        """异常路径也应记录 elapsed。"""
        bench = {
            "id": "te6",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise RuntimeError("boom")

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["elapsed"] >= 0

    def test_error_score_remains_zero(self):
        """异常路径不应修改初始 score=0.0。"""
        bench = {
            "id": "te7",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise OSError("fail")

        result = EvalEngine().run_benchmark(bench, executor)
        assert result["score"] == 0.0

    def test_type_error_not_caught(self):
        """TypeError 不在 catch 列表中，应逃逸。"""
        bench = {
            "id": "te8",
            "name": "Test",
            "category": "understand",
            "goal": "test",
            "expected_keywords": ["x"],
            "weight": 1.0,
        }

        def executor(name, args):
            raise TypeError("type error")

        with pytest.raises(TypeError):
            EvalEngine().run_benchmark(bench, executor)


# ── run_all 汇总 ────────────────────────────────────────────────


class TestRunAll:
    """run_all 汇总报告结构。"""

    def test_all_pass(self):
        # 构造一个全 pass 的 executor
        all_kw = set()
        for b in BENCHMARKS:
            all_kw.update(b["expected_keywords"])

        def executor(name, args):
            return " ".join(all_kw)

        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        assert report["suite"] == "CRUX Core Benchmarks"
        assert report["total"] == len(BENCHMARKS)
        assert report["passed"] == len(BENCHMARKS)
        assert report["failed"] == 0
        assert report["score"] == 100.0
        assert len(report["results"]) == len(BENCHMARKS)

    def test_all_fail(self):
        def executor(name, args):
            return "no keywords at all"

        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        assert report["passed"] == 0
        assert report["failed"] == len(BENCHMARKS)
        assert report["score"] == 0.0

    def test_report_structure(self):
        def executor(name, args):
            return "x"

        report = EvalEngine().run_all(tool_executor=executor)
        for key in ("suite", "total", "passed", "failed", "score", "results"):
            assert key in report
        assert isinstance(report["results"], list)
        assert len(report["results"]) == len(BENCHMARKS)

    def test_mixed_pass_fail_score(self):
        """部分 pass / fail 时 score 按权重加权。"""
        all_kw = set()
        for b in BENCHMARKS[:2]:
            all_kw.update(b["expected_keywords"])

        def executor(name, args):
            return " ".join(all_kw)

        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        # 前 2 个 pass（weight 各 1.0），剩余 fail
        assert 0 < report["score"] < 100.0
        assert report["passed"] >= 1
        assert report["failed"] >= 1
        assert report["passed"] + report["failed"] == report["total"]

    def test_non_uniform_weights(self):
        """BENCHMARKS 含 weight=0.5 的 bench_tool_list，总分不等于简单平均。"""
        # 全命中 executor
        all_kw = set()
        for b in BENCHMARKS:
            all_kw.update(b["expected_keywords"])

        def executor(name, args):
            return " ".join(all_kw)

        engine = EvalEngine()
        report = engine.run_all(tool_executor=executor)
        # total_weight = 1.0*4 + 0.5 = 4.5
        total_weight = sum(b["weight"] for b in BENCHMARKS)
        assert total_weight == 4.5
        # all pass → score = 100.0
        assert report["score"] == 100.0

    def test_results_populated_on_engine(self):
        """run_all 后 engine.results 应被填充。"""
        def executor(name, args):
            return "x"

        engine = EvalEngine()
        engine.run_all(tool_executor=executor)
        assert len(engine.results) == len(BENCHMARKS)

    def test_results_reset_on_subsequent_run_all(self):
        """连续两次 run_all，第二次应重置 results。"""
        def executor(name, args):
            return "x"

        engine = EvalEngine()
        engine.run_all(tool_executor=executor)
        assert len(engine.results) == len(BENCHMARKS)
        engine.run_all(tool_executor=executor)
        # 不应变成 2x BENCHMARKS
        assert len(engine.results) == len(BENCHMARKS)

    def test_total_plus_failed_equals_total(self):
        """passed + failed == total。"""
        def executor(name, args):
            return "partial keyword"

        report = EvalEngine().run_all(tool_executor=executor)
        assert report["passed"] + report["failed"] == report["total"]

    def test_suite_name_constant(self):
        """suite 字段应为固定字符串。"""
        def executor(name, args):
            return "x"

        report = EvalEngine().run_all(tool_executor=executor)
        assert report["suite"] == "CRUX Core Benchmarks"


# ── EvalEngine.__init__ ──────────────────────────────────────


class TestEvalEngineInit:
    """EvalEngine 构造函数行为。"""

    def test_default_root_is_module_root(self):
        engine = EvalEngine()
        assert engine.root == ROOT

    def test_custom_root(self):
        custom = Path("/tmp/custom_root")
        engine = EvalEngine(root=custom)
        assert engine.root == custom

    def test_initial_results_empty(self):
        engine = EvalEngine()
        assert engine.results == []


# ── run_evals 模块函数 ──────────────────────────────────────


class TestRunEvals:
    """run_evals() 便捷函数：用 mock 隔离 get_registry。"""

    def test_returns_report_dict(self):
        all_kw = set()
        for b in BENCHMARKS:
            all_kw.update(b["expected_keywords"])

        with patch("core.tools.get_registry") as mock_reg:
            mock_reg.return_value.execute = lambda name, args: " ".join(all_kw)

            report = run_evals()

        assert report["suite"] == "CRUX Core Benchmarks"
        assert isinstance(report, dict)
        assert "score" in report

    def test_uses_registry_when_no_executor(self):
        """run_evals() 不传 tool_executor，应调用 get_registry。"""
        with patch("core.tools.get_registry") as mock_reg:
            mock_reg.return_value.execute = lambda name, args: "no keywords"

            run_evals()

        mock_reg.assert_called_once()
