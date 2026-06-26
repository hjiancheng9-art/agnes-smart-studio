"""Tests for #8 /eval CLI command (table + json output).

验证 /eval 命令注册、dispatch 路由、eval_harness 执行、表格/JSON 输出。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestEvalCommandRegistration:
    """/eval 命令应注册到 COMMANDS 并正确路由。"""

    def test_eval_in_commands(self):
        from core.commands import get_all

        keys = [c.key for c in get_all()]
        assert "eval" in keys

    def test_eval_command_def(self):
        from core.commands import get_all

        cmd = next(c for c in get_all() if c.key == "eval")
        assert cmd.name == "/eval"
        assert cmd.handler == "_chat_eval"
        assert cmd.category == "诊断配置"

    def test_eval_in_dispatch_table(self):
        from core.commands import build_dispatch_table

        table = build_dispatch_table()
        assert "eval" in table
        handler, cmd_def = table["eval"]
        assert handler == "_chat_eval"

    def test_eval_total_command_count(self):
        from core.commands import get_all

        assert len(get_all()) >= 31


class TestEvalHarnessExecution:
    """EvalEngine 应能执行基准测试并返回正确结构。"""

    def test_eval_engine_run_all_structure(self):
        from core.eval_harness import BENCHMARKS, EvalEngine

        engine = EvalEngine()

        # 用一个简单的 mock executor 让 run_all 完成
        def mock_executor(name, args):
            return "OK passed no errors Python encoding"

        report = engine.run_all(tool_executor=mock_executor)
        assert "suite" in report
        assert "total" in report
        assert "passed" in report
        assert "failed" in report
        assert "score" in report
        assert "results" in report
        assert report["total"] == len(BENCHMARKS)
        assert len(report["results"]) == len(BENCHMARKS)

    def test_eval_engine_all_pass(self):
        """所有关键词命中时全部通过。"""
        from core.eval_harness import BENCHMARKS, EvalEngine

        all_keywords = []
        for b in BENCHMARKS:
            all_keywords.extend(b["expected_keywords"])
        all_keywords_str = " ".join(all_keywords)

        def mock_executor(name, args):
            return all_keywords_str

        engine = EvalEngine()
        report = engine.run_all(tool_executor=mock_executor)
        assert report["passed"] == report["total"]
        assert report["score"] > 90

    def test_eval_engine_all_fail(self):
        """输出不含任何关键词时全部失败。"""
        from core.eval_harness import EvalEngine

        def mock_executor(name, args):
            return "xyzzy nothing relevant"

        engine = EvalEngine()
        report = engine.run_all(tool_executor=mock_executor)
        assert report["passed"] == 0
        assert report["score"] == 0

    def test_eval_engine_results_have_required_fields(self):
        from core.eval_harness import EvalEngine

        def mock_executor(name, args):
            return "OK"

        engine = EvalEngine()
        report = engine.run_all(tool_executor=mock_executor)
        for r in report["results"]:
            assert "id" in r
            assert "name" in r
            assert "category" in r
            assert "status" in r
            assert "score" in r
            assert "elapsed" in r


class TestEvalHarnessDefaults:
    """run_evals() 无参调用时应使用 get_registry()。"""

    def test_run_evals_returns_report(self):
        from core.eval_harness import run_evals

        # run_evals 使用 get_registry，如果没有 tools.json 也能跑
        report = run_evals()
        assert "total" in report
        assert isinstance(report["results"], list)

    def test_benchmark_definitions_valid(self):
        from core.eval_harness import BENCHMARKS

        assert len(BENCHMARKS) >= 5
        for b in BENCHMARKS:
            assert "id" in b
            assert "name" in b
            assert "goal" in b
            assert "category" in b
            assert "expected_keywords" in b
            assert "weight" in b
            assert isinstance(b["expected_keywords"], list)
            assert b["weight"] > 0


class TestEvalHandlerExists:
    """DiagCommandsMixin 应有 _chat_eval 方法。"""

    def test_eval_handler_in_mixin(self):
        from ui.mixins.diag import DiagCommandsMixin

        assert hasattr(DiagCommandsMixin, "_chat_eval")
        assert callable(DiagCommandsMixin._chat_eval)
