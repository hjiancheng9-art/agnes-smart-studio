"""Tests for core/fixability_estimator.py — L0 seed filter + L1 probes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fixability_estimator import (
    CUDAMemoryProbe,
    FixabilityEstimator,
    FixabilityResult,
    LLMAnalyzer,
    ModuleImportProbe,
    StaticSeedFilter,
    SyntaxErrorProbe,
)


class TestStaticSeedFilter:
    def test_cuda_oom_is_quarantined(self):
        f = StaticSeedFilter()
        r = f.evaluate("run_bash", "CUDA out of memory", {})
        assert r is not None
        assert r.score == 0.0 or r.action_hint in ("abort", "diagnose")

    def test_module_not_found_is_actionable(self):
        f = StaticSeedFilter()
        r = f.evaluate("pip_install", "ModuleNotFoundError: No module named 'foo'", {})
        if r is not None:
            assert r.action_hint in ("retry", "diagnose", "escalate")

    def test_none_for_unknown(self):
        f = StaticSeedFilter()
        r = f.evaluate("unknown_tool", "completely new error type", {})
        # May return a generic result or None
        assert r is None or isinstance(r, FixabilityResult)


class TestCUDAMemoryProbe:
    def test_can_handle_oom(self):
        p = CUDAMemoryProbe()
        assert p.can_handle("CUDA out of memory", {})

    def test_cannot_handle_import_error(self):
        p = CUDAMemoryProbe()
        assert not p.can_handle("ModuleNotFoundError", {})

    def test_estimate_returns_result(self):
        p = CUDAMemoryProbe()
        r = p.estimate("CUDA out of memory", {"batch_size": 4})
        assert isinstance(r, FixabilityResult)
        # torch may or may not be installed — just verify it returns a valid result
        assert 0 <= r.score <= 1.0


class TestModuleImportProbe:
    def test_can_handle_import(self):
        p = ModuleImportProbe()
        assert p.can_handle("ModuleNotFoundError: No module named 'torch'", {})

    def test_cannot_handle_cuda(self):
        p = ModuleImportProbe()
        assert not p.can_handle("CUDA out of memory", {})


class TestHTTPProbe:
    def test_can_handle_syntax(self):
        p = SyntaxErrorProbe()
        assert p.can_handle("SyntaxError: invalid syntax", {})

    def test_cannot_handle_timeout(self):
        p = SyntaxErrorProbe()
        assert not p.can_handle("timeout", {})


class TestLLMAnalyzer:
    def test_heuristic_syntax_is_high_score(self):
        a = LLMAnalyzer()
        r = a.evaluate("run_python", "SyntaxError: invalid syntax", {})
        assert r.score > 0.5
        assert r.action_hint == "retry"
        assert r.repair_class_hint == "code"

    def test_heuristic_memory_is_low_score(self):
        a = LLMAnalyzer()
        r = a.evaluate("run_bash", "CUDA out of memory", {})
        assert r.score <= 0.3

    def test_heuristic_unknown(self):
        a = LLMAnalyzer()
        r = a.evaluate("unknown_tool", "random error", {})
        assert r.score == 0.3


class TestFixabilityEstimator:
    def test_estimate_returns_result(self):
        est = FixabilityEstimator()
        r = est.estimate("run_test", "AssertionError: assert False", {})
        assert isinstance(r, FixabilityResult)
        assert 0 <= r.score <= 1.0

    def test_estimate_unknown(self):
        est = FixabilityEstimator()
        r = est.estimate("unknown_tool", "weird error", {})
        assert isinstance(r, FixabilityResult)
