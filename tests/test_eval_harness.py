"""Tests for core/eval_harness.py"""

from core.eval_harness import EvalEngine


class TestEvalHarness:
    def test_create(self):
        engine = EvalEngine()
        assert engine is not None

    def test_run_all(self):
        engine = EvalEngine()
        result = engine.run_all()
        assert result is not None
