"""
Tests for Intelligence Trace — 全链路可观测/可回放
"""
import time

from core.intelligence_trace import TraceRecord, TraceStep, TraceStore


class TestTraceRecord:
    def test_minimal_record(self):
        trace = TraceRecord(run_id="test-001", user_request="hello", mode="FAST")
        assert trace.run_id == "test-001"
        assert trace.status == "running"
        assert trace.started_at > 0

    def test_auto_run_id(self):
        trace = TraceRecord(user_request="hello", mode="FAST")
        assert len(trace.run_id) > 0  # should auto-generate

    def test_to_dict(self):
        trace = TraceRecord(
            run_id="t1", user_request="重构模块", mode="DEEP",
            status="pass", started_at=100, ended_at=200,
        )
        trace.steps.append(TraceStep(name="plan", status="success", duration=2.5))
        d = trace.to_dict()
        assert d["run_id"] == "t1"
        assert d["mode"] == "DEEP"
        assert d["status"] == "pass"
        assert d["step_count"] == 1
        assert d["total_duration"] == 100

    def test_failed_steps(self):
        trace = TraceRecord(run_id="t2", user_request="test", mode="DEEP")
        trace.steps.append(TraceStep(name="plan", status="success"))
        trace.steps.append(TraceStep(name="criticize", status="failed", error="bad"))
        assert len(trace.failed_steps) == 1
        assert trace.success_count == 1
        assert trace.failed_steps[0].error == "bad"


class TestTraceStore:
    def setup_method(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._tmp.close()
        self.store = TraceStore(db_path=self._tmp.name)

    def teardown_method(self):
        import os
        if hasattr(self, '_tmp') and os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_record_and_get(self):
        trace = TraceRecord(run_id="r1", user_request="测试", mode="DEEP", status="pass")
        trace.steps.append(TraceStep(name="plan", status="success", duration=1.0))
        trace.steps.append(TraceStep(name="verify", status="success"))
        trace.ended_at = time.time()

        run_id = self.store.record(trace)
        assert run_id == "r1"

        loaded = self.store.get("r1")
        assert loaded is not None
        assert loaded["mode"] == "DEEP"
        assert loaded["step_count"] == 2

    def test_get_nonexistent(self):
        loaded = self.store.get("nonexistent")
        assert loaded is None

    def test_query_by_status(self):
        t1 = TraceRecord(run_id="q1", user_request="a", mode="FAST", status="pass")
        t2 = TraceRecord(run_id="q2", user_request="b", mode="DEEP", status="fail")
        self.store.record(t1)
        self.store.record(t2)

        # Use a single connection for the whole store to work with :memory:
        passed = self.store.query(status="pass")
        assert len(passed) >= 1
        assert passed[0]["run_id"] == "q1"

        failed = self.store.query(status="fail")
        assert len(failed) >= 1

    def test_query_by_mode(self):
        t = TraceRecord(run_id="qm1", user_request="test", mode="DEEP", status="pass")
        self.store.record(t)
        deep_traces = self.store.query(mode="DEEP")
        assert len(deep_traces) >= 1

    def test_get_stats(self):
        t1 = TraceRecord(run_id="s1", user_request="a", mode="FAST", status="pass",
                          started_at=100, ended_at=110)
        t2 = TraceRecord(run_id="s2", user_request="b", mode="DEEP", status="fail",
                          started_at=200, ended_at=230)
        self.store.record(t1)
        self.store.record(t2)

        stats = self.store.get_stats()
        assert stats["total"] >= 2
        assert stats["passed"] >= 1
        assert stats["failed"] >= 1

    def test_clear(self):
        t = TraceRecord(run_id="c1", user_request="test", mode="FAST", status="pass")
        self.store.record(t)
        self.store.clear()
        stats = self.store.get_stats()
        assert stats["total"] == 0

    def test_export(self):
        t = TraceRecord(run_id="e1", user_request="export_test", mode="BALANCED", status="pass")
        self.store.record(t)
        exported = self.store.export(limit=10)
        assert len(exported) >= 1
        assert any(e["run_id"] == "e1" for e in exported)


class TestEvidenceGate:
    def setup_method(self):
        from core.evidence_gate import EvidenceGate
        self.gate = EvidenceGate()

    def test_no_evidence_fails(self):
        result = self.gate.check_text("我觉得这个问题修复了")
        assert result.passed is False
        assert result.evidence_quality == "none"

    def test_file_reference_passes(self):
        result = self.gate.check_text("已在 src/auth.py:42 添加判空处理，src/models.py:88 更新验证，测试通过")
        assert result.passed is True
        assert result.evidence_quality in ("strong", "medium")

    def test_code_block_evidence(self):
        result = self.gate.check_text("修改如下:\n```python\ndef validate(x):\n    if x is None:\n        raise ValueError()\n    return x > 0\n```")
        assert result.passed is True

    def test_multiple_evidence(self):
        text = """已在 src/auth.py:42 添加判空
                 在 src/auth.py:55 更新类型检查
                 测试在 tests/test_auth.py:12 通过"""
        result = self.gate.check_text(text)
        assert result.passed is True
        assert result.evidence_count >= 2

    def test_weak_evidence_fails(self):
        text = "如上所述，我认为问题可能已经修复了"
        result = self.gate.check_text(text)
        assert result.passed is False

    def test_gate_result_to_dict(self):
        from core.evidence_gate import GateResult
        r = GateResult(passed=False, reason="no evidence", evidence_count=0)
        d = r.to_dict()
        assert d["passed"] is False
        assert d["reason"] == "no evidence"
