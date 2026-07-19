"""Test P11: Failure Learning Loop / Trace-to-Regression System."""

import os
import time

import pytest

from core.failure_learning import (
    FailureCategory,
    FailureLearningLoop,
    FailureSample,
    FixVerifier,
    LearningStats,
    RegressionExporter,
    RootCauseAnalyzer,
    TraceExtractor,
)


@pytest.fixture
def sample():
    return FailureSample(
        id="test-001",
        category="tool_validation_blocked",
        severity="high",
        timestamp=time.time(),
        user_message="read_file('nonexistent.txt')",
        assistant_response="Here's the file content...",
        tool_calls=[{"name": "read_file", "arguments": {"path": ""}}],
        actual_outcome="Tool blocked: missing required parameter 'path'",
        expected_outcome="Tool should execute read_file with valid path",
    )


@pytest.fixture
def loop():
    return FailureLearningLoop(export_dir="/tmp/_p11_test_regression")


class TestFailureSample:
    def test_creation(self, sample):
        assert sample.id == "test-001"
        assert sample.category == "tool_validation_blocked"
        assert "read_file" in sample.tool_calls[0]["name"]

    def test_to_dict(self, sample):
        d = sample.to_dict()
        assert d["category"] == "tool_validation_blocked"
        assert d["severity"] == "high"
        assert len(d["user_message"]) > 0

    def test_defaults(self):
        s = FailureSample()
        assert s.id == ""
        assert s.tool_calls == []


class TestFailureCategory:
    def test_values(self):
        cats = [c.value for c in FailureCategory]
        assert "tool_validation_blocked" in cats
        assert "consistency_issue" in cats
        assert "hallucination" in cats
        assert "empty_response" in cats


class TestTraceExtractor:
    def test_extract_minimal(self):
        extractor = TraceExtractor()
        decisions = [
            {"category": "policy", "decision": "DEEP", "reason": "complex", "outcome": "selected"},
            {"category": "tool_validation", "decision": "read_file", "reason": "missing path", "outcome": "block"},
            {"category": "reviewer", "decision": "review", "reason": "empty", "outcome": "issues_found"},
        ]
        trace = extractor.extract_minimal(decisions)
        assert "block" in trace

    def test_extract_minimal_empty(self):
        extractor = TraceExtractor()
        assert extractor.extract_minimal([]) == ""

    def test_extract_from_failure(self, sample):
        extractor = TraceExtractor()
        ctx = extractor.extract_from_failure(sample)
        assert "nonexistent" in ctx


class TestRootCauseAnalyzer:
    def test_analysis(self, sample):
        analyzer = RootCauseAnalyzer()
        result = analyzer.analyze(sample)
        assert len(result.root_cause) > 0
        assert len(result.fix_suggestion) > 0

    def test_different_categories(self):
        analyzer = RootCauseAnalyzer()
        for cat in ["hallucination", "consistency_issue", "unclosed_fence"]:
            s = FailureSample(category=cat, user_message="test")
            result = analyzer.analyze(s)
            assert len(result.fix_suggestion) > 0


class TestFixVerifier:
    def test_verify_identical(self):
        v = FixVerifier()
        s = FailureSample(actual_outcome="error: X")
        assert not v.verify(s, "same output", "same output")

    def test_verify_fixed(self):
        v = FixVerifier()
        s = FailureSample(actual_outcome="error: runtime exception")
        assert v.verify(s, "error: runtime exception", "success: completed")

    def test_verify_empty_after(self):
        v = FixVerifier()
        s = FailureSample()
        assert not v.verify(s, "before", "")

    def test_diff(self):
        v = FixVerifier()
        diff = v.diff("line1\nline2\n", "line1\nline2\nline3\n")
        assert "line3" in diff


class TestRegressionExporter:
    def test_export(self, sample, tmp_path):
        exporter = RegressionExporter(export_dir=str(tmp_path / "regression"))
        path = exporter.export(sample)
        assert os.path.exists(path)
        assert sample.exported

    def test_list_cases(self, sample, tmp_path):
        exporter = RegressionExporter(export_dir=str(tmp_path / "regression2"))
        exporter.export(sample)
        cases = exporter.list_cases()
        assert len(cases) >= 1
        assert cases[0]["category"] == "tool_validation_blocked"

    def test_list_empty(self):
        exporter = RegressionExporter(export_dir="/tmp/_nonexistent_dir_12345")
        cases = exporter.list_cases()
        assert cases == []


class TestFailureLearningLoop:
    def test_capture(self, loop):
        s = loop.capture("tool_execution_failed", user_message="run bash", actual_outcome="command not found")
        assert s.category == "tool_execution_failed"
        assert len(loop.samples) == 1

    def test_capture_and_analyze(self, loop):
        s = loop.capture("tool_validation_blocked", user_message="read file")
        result = loop.analyze(s)
        assert len(result.root_cause) > 0

    def test_capture_from_trace(self, loop):
        decisions = [
            {"category": "tool_validation", "decision": "write_file", "outcome": "block"},
        ]
        s = loop.capture_from_trace(decisions, user_message="write file")
        assert len(s.trace_snippet) > 0

    def test_full_pipeline(self, loop):
        s = loop.run_full_pipeline(
            category="hallucination",
            user_message="show config",
            assistant_response="Config: ...",
            actual_outcome="Referenced file not read",
            expected_outcome="Should only reference read files",
            severity="high",
            before_output="file not found: config.py",
            after_output="success: config read",
        )
        assert s.fix_verified
        assert s.exported
        assert len(s.root_cause) > 0

    def test_export(self, loop):
        s = loop.capture("test", user_message="test")
        path = loop.export(s)
        assert os.path.exists(path)
        os.unlink(path)

    def test_stats(self, loop):
        loop.capture("a", user_message="1")
        loop.capture("b", user_message="2")
        stats = loop.stats()
        assert stats.total_failures >= 2

    def test_report(self, loop):
        loop.capture("test", user_message="x")
        report = loop.report()
        assert "Failure Learning Loop" in report


class TestIntegration:
    def test_validation_layer_import(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        assert hasattr(vl, "learning_loop")

    def test_capture_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        s = vl.capture_failure("tool_execution_failed", user_message="test", actual_outcome="error")
        assert s.category == "tool_execution_failed"

    def test_analyze_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        s = vl.capture_failure("tool_validation_blocked", user_message="test")
        result = vl.analyze_failure(s)
        assert len(result.root_cause) > 0

    def test_export_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        s = vl.capture_failure("test", user_message="export test")
        path = vl.export_failure(s)
        assert len(path) > 0
        if os.path.exists(path):
            os.unlink(path)

    def test_full_pipeline_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        s = vl.run_failure_pipeline(
            category="consistency_issue",
            user_message="show data",
            actual_outcome="Answer contradicts tool result",
            expected_outcome="Answer should match tool result",
        )
        assert s.exported

    @pytest.mark.flaky(reason="Cross-module ValidationLayer init pollution. See docs/flaky-tests.md.")
    def test_stats_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        stats = vl.learning_stats
        assert isinstance(stats, LearningStats)

    def test_report_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        report = vl.failure_report
        assert len(report) > 0

    def test_chat_p11_flag(self):
        import py_compile

        py_compile.compile("core/chat.py", doraise=True)
