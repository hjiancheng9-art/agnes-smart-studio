"""
Tests for Benchmark Arena — Phase 7
"""

import os
import tempfile

from core.arena.benchmark_arena import ArenaGate, BenchmarkRunner, ReleaseBridge, ReportStore
from core.arena.patch_runner import PatchRunner
from core.arena.schemas import (
    ArenaDecision,
    ArenaPatch,
    ArenaRunReport,
    BenchmarkCase,
    BenchmarkResult,
    PatchRisk,
    SandboxConfig,
)


class TestSchemas:
    def test_arena_patch_defaults(self):
        p = ArenaPatch(description="test")
        assert p.patch_id
        assert p.risk == PatchRisk.MEDIUM
        assert p.created_at > 0

    def test_arena_run_report_defaults(self):
        r = ArenaRunReport(patch_id="p1")
        assert r.run_id
        assert r.status == ArenaDecision.FAIL
        assert r.pass_count == 0
        assert r.pass_rate == 0.0

    def test_arena_run_report_decision(self):
        r = ArenaRunReport(patch_id="p1")
        r.results = [BenchmarkResult(case_id="c1", passed=True, score=1.0)] * 10
        assert r.pass_rate == 100.0
        assert r.decision == ArenaDecision.PASS

    def test_arena_run_report_partial_decision(self):
        r = ArenaRunReport(patch_id="p1")
        r.results = [BenchmarkResult(case_id=f"c{i}", passed=i < 8, score=1.0) for i in range(10)]
        assert r.pass_rate == 80.0
        assert r.decision in (ArenaDecision.PASS, ArenaDecision.NEEDS_REVIEW)

    def test_arena_run_report_fail_decision(self):
        r = ArenaRunReport(patch_id="p1")
        r.results = [BenchmarkResult(case_id=f"c{i}", passed=False, score=0.0) for i in range(10)]
        assert r.pass_rate == 0.0
        assert r.decision == ArenaDecision.FAIL

    def test_benchmark_case(self):
        c = BenchmarkCase(case_id="c1", type="router", input="你好", expected="FAST")
        assert c.case_id == "c1"
        assert c.weight == 1.0

    def test_sandbox_config_defaults(self):
        c = SandboxConfig()
        assert c.isolation_level == "high"
        assert c.allow_file_write is False


class TestBenchmarkRunner:
    def test_run_empty_cases(self):
        runner = BenchmarkRunner()
        report = runner.run_cases([])
        assert report.total_count == 0
        assert report.pass_rate == 0.0

    def test_run_with_cases(self):
        runner = BenchmarkRunner()
        cases = [
            BenchmarkCase(case_id="c1", type="router", input="你好", expected="FAST"),
            BenchmarkCase(case_id="c2", type="router", input="重构", expected="DEEP"),
        ]
        report = runner.run_cases(cases)
        assert report.total_count == 2

    def test_compare_to_baseline(self):
        runner = BenchmarkRunner()
        baseline = [BenchmarkResult(case_id="c1", passed=True, score=0.9)]
        runner.set_baseline(baseline)
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id="c1", passed=True, score=0.5)]
        comparison = runner.compare_to_baseline(report)
        assert comparison["has_regression"] is True


class TestArenaGate:
    def test_empty_report_fails(self):
        gate = ArenaGate()
        report = ArenaRunReport(patch_id="p1")
        assert gate.evaluate(report) == ArenaDecision.FAIL

    def test_high_pass_rate_passes(self):
        gate = ArenaGate()
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id=f"c{i}", passed=True, score=1.0) for i in range(10)]
        assert gate.evaluate(report) == ArenaDecision.PASS

    def test_low_pass_rate_fails(self):
        gate = ArenaGate()
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id=f"c{i}", passed=i < 4, score=1.0) for i in range(10)]
        assert gate.evaluate(report) == ArenaDecision.FAIL

    def test_can_release(self):
        gate = ArenaGate()
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id=f"c{i}", passed=True, score=1.0) for i in range(10)]
        assert gate.can_release(report) is True


class TestReportStore:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        self.tmp.close()
        self.store = ReportStore(db_path=self.tmp.name)

    def teardown_method(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_save_and_load(self):
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id="c1", passed=True, score=1.0)]
        self.store.save(report)
        loaded = self.store.load_recent(10)
        assert len(loaded) >= 1
        assert loaded[-1]["patch_id"] == "p1"

    def test_get_latest_for_patch(self):
        r1 = ArenaRunReport(patch_id="p1")
        r1.results = [BenchmarkResult(case_id="c1", passed=True)]
        r2 = ArenaRunReport(patch_id="p1")
        r2.results = [BenchmarkResult(case_id="c1", passed=False)]
        self.store.save(r1)
        self.store.save(r2)
        latest = self.store.get_latest_for_patch("p1")
        assert latest is not None

    def test_get_stats_empty(self):
        stats = self.store.get_stats()
        assert stats["total"] == 0


class TestPatchRunner:
    def setup_method(self):
        self.runner = PatchRunner()

    def test_apply_signal_adjustment(self):
        patch = ArenaPatch(
            patch={
                "type": "signal_weight_adjust",
                "target_signals": [{"signal": "has_code", "action": "increase", "delta": 1.0}],
            },
            description="调整 has_code 权重",
        )
        result = self.runner.apply_patch(patch)
        assert result is True
        assert self.runner.is_sandbox_active() is True

    def test_rollback(self):
        patch = ArenaPatch(
            patch={
                "type": "signal_weight_adjust",
                "target_signals": [{"signal": "has_code", "action": "increase", "delta": 2.0}],
            },
            description="测试回滚",
        )
        self.runner.apply_patch(patch)
        count = self.runner.rollback()
        assert count >= 1

    def test_empty_patch(self):
        patch = ArenaPatch(patch={}, description="空补丁")
        result = self.runner.apply_patch(patch)
        assert result is False

    def test_direct_weight(self):
        patch = ArenaPatch(
            patch={"type": "signal_weight_direct", "signal_name": "has_code", "new_weight": 5.0},
            description="直接设置",
        )
        result = self.runner.apply_patch(patch)
        assert result is True
        self.runner.rollback()


class TestReleaseBridge:
    def test_evaluate_pass(self):
        bridge = ReleaseBridge()
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id=f"c{i}", passed=True) for i in range(10)]
        result = bridge.evaluate_for_release(report)
        assert result["can_release"] is True

    def test_evaluate_fail(self):
        bridge = ReleaseBridge()
        report = ArenaRunReport(patch_id="p1")
        report.results = [BenchmarkResult(case_id=f"c{i}", passed=False) for i in range(10)]
        result = bridge.evaluate_for_release(report)
        assert result["can_release"] is False
