"""
Tests for Adaptive Learner — Phase 5 自适应学习
"""

from core.adaptive_learner import AdaptiveLearner, FailureAnalyzer, PolicyAdapter
from core.learning_store import LearningRecord, LearningStore


class TestLearningRecord:
    def test_minimal(self):
        r = LearningRecord(failure_type="route_mismatch")
        assert r.episode_id
        assert r.failure_type == "route_mismatch"
        assert r.severity == "medium"

    def test_auto_fields(self):
        r = LearningRecord(failure_type="plan_incomplete", severity="high")
        assert r.episode_id
        assert len(r.episode_id) == 12

    def test_to_dict(self):
        r = LearningRecord(
            episode_id="e1",
            failure_type="route_mismatch",
            request="重构认证模块",
            routed_mode="BALANCED",
            expected_mode="DEEP",
            diagnosis="路由误判",
            severity="high",
            root_cause="信号权重不足",
            policy_patch={"type": "signal_adjust"},
        )
        d = r.to_dict()
        assert d["episode_id"] == "e1"
        assert d["failure_type"] == "route_mismatch"
        assert d["policy_patch"]["type"] == "signal_adjust"


class TestLearningStore:
    def setup_method(self):
        import tempfile

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.store = LearningStore(db_path=self._tmp.name)

    def teardown_method(self):
        import os

        if hasattr(self, "_tmp") and os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_record_and_get(self):
        r = LearningRecord(
            episode_id="e1",
            failure_type="route_mismatch",
            request="test",
            routed_mode="FAST",
            expected_mode="DEEP",
        )
        pid = self.store.record(r)
        assert pid == "e1"

        loaded = self.store.get("e1")
        assert loaded is not None
        assert loaded.failure_type == "route_mismatch"

    def test_query(self):
        self.store.record(LearningRecord(episode_id="q1", failure_type="route_mismatch", request="a"))
        self.store.record(LearningRecord(episode_id="q2", failure_type="repair_failed", request="b"))
        self.store.record(LearningRecord(episode_id="q3", failure_type="route_mismatch", request="c"))

        route_fails = self.store.query(failure_type="route_mismatch")
        assert len(route_fails) >= 2

        repair_fails = self.store.query(failure_type="repair_failed")
        assert len(repair_fails) >= 1

    def test_mark_applied(self):
        r = LearningRecord(episode_id="a1", failure_type="plan_incomplete", request="test")
        self.store.record(r)

        assert self.store.mark_applied("a1", effectiveness=0.8) is True
        loaded = self.store.get("a1")
        assert loaded.applied is True
        assert loaded.effectiveness == 0.8

    def test_get_summary(self):
        self.store.record(LearningRecord(episode_id="s1", failure_type="route_mismatch", request="a", severity="high"))
        self.store.record(LearningRecord(episode_id="s2", failure_type="repair_failed", request="b", severity="medium"))
        self.store.record(LearningRecord(episode_id="s3", failure_type="route_mismatch", request="c", severity="high"))

        summary = self.store.get_summary()
        assert summary.total_episodes >= 3
        assert "route_mismatch" in summary.failure_type_dist

    def test_clear(self):
        self.store.record(LearningRecord(episode_id="c1", failure_type="route_mismatch", request="test"))
        self.store.clear()
        assert self.store.get_summary().total_episodes == 0


class TestFailureAnalyzer:
    def setup_method(self):
        self.analyzer = FailureAnalyzer()

    def test_route_mismatch_diagnosis(self):
        trace = {
            "run_id": "t1",
            "mode": "BALANCED",
            "status": "fail",
            "user_request": "排查一下这个间歇性崩溃的根因",
            "steps": [
                {"name": "plan", "status": "success", "duration": 1.0},
                {"name": "verify", "status": "failed"},
            ],
        }
        diagnosis = self.analyzer.diagnose_from_trace(trace, expected_mode="DEEP")
        assert diagnosis is not None
        assert diagnosis.failure_type == "route_mismatch"
        assert "DEEP" in diagnosis.root_cause or "BALANCED" in diagnosis.root_cause

    def test_plan_failure_diagnosis(self):
        trace = {
            "run_id": "t2",
            "mode": "DEEP",
            "status": "fail",
            "user_request": "重构认证模块",
            "steps": [
                {"name": "plan", "status": "failed"},
                {"name": "verify", "status": "skipped"},
            ],
        }
        diagnosis = self.analyzer.diagnose_from_trace(trace)
        assert diagnosis is not None
        assert diagnosis.failure_type == "plan_incomplete"

    def test_critic_failure_diagnosis(self):
        trace = {
            "run_id": "t3",
            "mode": "DEEP",
            "status": "fail",
            "user_request": "测试",
            "steps": [
                {"name": "plan", "status": "success"},
                {"name": "criticize", "status": "failed", "output_summary": "critical: 2 issues"},
                {"name": "verify", "status": "skipped"},
            ],
        }
        diagnosis = self.analyzer.diagnose_from_trace(trace)
        assert diagnosis is not None
        assert diagnosis.failure_type == "critic_missed"

    def test_repair_failure_diagnosis(self):
        trace = {
            "run_id": "t4",
            "mode": "DEEP",
            "status": "fail",
            "user_request": "测试",
            "steps": [
                {"name": "plan", "status": "success"},
                {"name": "criticize", "status": "success"},
                {"name": "repair", "status": "failed"},
                {"name": "verify", "status": "skipped"},
            ],
        }
        diagnosis = self.analyzer.diagnose_from_trace(trace)
        assert diagnosis is not None
        assert diagnosis.failure_type == "repair_failed"

    def test_no_diagnosis_for_success(self):
        trace = {
            "run_id": "t5",
            "mode": "FAST",
            "status": "pass",
            "user_request": "你好",
            "steps": [{"name": "direct_response", "status": "success"}],
        }
        diagnosis = self.analyzer.diagnose_from_trace(trace, expected_mode="FAST")
        assert diagnosis is None

    def test_none_trace(self):
        diagnosis = self.analyzer.diagnose_from_trace(None)
        assert diagnosis is None


class TestPolicyAdapter:
    def setup_method(self):
        self.adapter = PolicyAdapter()

    def test_signal_adjust(self):
        patch = {
            "type": "signal_weight_adjust",
            "target_signals": [
                {"signal": "has_multi_step", "action": "increase", "delta": 0.5},
            ],
        }
        result = self.adapter.apply_patch(patch)
        assert result is True

    def test_invalid_patch(self):
        result = self.adapter.apply_patch(None)
        assert result is False

    def test_pending_patches(self):
        self.adapter.apply_patch({"type": "plan_config_tune", "suggestion": "增加max_rounds"})
        patches = self.adapter.get_pending_patches()
        assert len(patches) == 1
        assert patches[0]["type"] == "plan_config_tune"

        # Second call should be empty
        assert len(self.adapter.get_pending_patches()) == 0


class TestAdaptiveLearner:
    def setup_method(self):
        import tempfile

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.learner = AdaptiveLearner(
            learning_store=LearningStore(db_path=self._tmp.name),
        )

    def teardown_method(self):
        import os

        if hasattr(self, "_tmp") and os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_learn_from_trace_with_mismatch(self):
        trace = {
            "run_id": "l1",
            "mode": "BALANCED",
            "status": "fail",
            "user_request": "排查间歇崩溃根因，包含多步骤分析",
            "steps": [{"name": "plan", "status": "success"}],
        }
        record = self.learner.learn_from_trace(trace, expected_mode="DEEP")
        assert record is not None
        assert record.failure_type == "route_mismatch"

    def test_learning_disabled(self):
        self.learner.disable_learning()
        trace = {"run_id": "l2", "mode": "FAST", "status": "fail", "user_request": "test", "steps": []}
        record = self.learner.learn_from_trace(trace, expected_mode="DEEP")
        assert record is None

    def test_learning_enable_disable(self):
        assert self.learner.learning_enabled is True
        self.learner.disable_learning()
        assert self.learner.learning_enabled is False
        self.learner.enable_learning()
        assert self.learner.learning_enabled is True

    def test_get_summary(self):
        trace = {
            "run_id": "l3",
            "mode": "BALANCED",
            "status": "fail",
            "user_request": "test",
            "steps": [{"name": "plan", "status": "failed"}],
        }
        self.learner.learn_from_trace(trace, expected_mode="DEEP")
        summary = self.learner.get_summary()
        assert summary.total_episodes >= 1

    def test_clear(self):
        trace = {
            "run_id": "l4",
            "mode": "FAST",
            "status": "fail",
            "user_request": "test",
            "steps": [{"name": "plan", "status": "failed"}],
        }
        self.learner.learn_from_trace(trace, expected_mode="DEEP")
        self.learner.clear()
        assert self.learner.get_summary().total_episodes == 0
