"""Tests for core/policy_gate.py — quality-driven auto-recovery decisions.

Functions tested:
  - decide_action(summary) -> str
  - should_retry(summary) -> bool
  - should_escalate(summary) -> bool
  - auto_recover(summary) -> dict
"""

from core.policy_gate import auto_recover, decide_action, should_escalate, should_retry


class TestDecideAction:
    """decide_action determines next action based on quality assessment."""

    def test_success_returns_pass(self):
        """完全成功时返回 pass."""
        assert decide_action({"quality_status": "success", "quality_flags": []}) == "pass"

    def test_partial_success_low_fail_returns_retry(self):
        """部分成功且失败率 <= 50% 返回 retry."""
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        assert decide_action(summary) == "retry"

    def test_partial_success_high_fail_returns_escalate(self):
        """部分成功但失败率 > 50% 返回 escalate."""
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 6,
            "tasks_total": 10,
        }
        assert decide_action(summary) == "escalate"

    def test_timeout_degraded_low_fail_returns_retry(self):
        """超时降级且失败率 <= 50% 返回 retry."""
        summary = {
            "quality_status": "timeout_degraded",
            "quality_flags": [],
            "tasks_failed": 1,
            "tasks_total": 5,
        }
        assert decide_action(summary) == "retry"

    def test_unknown_quality_returns_pass(self):
        """未知 quality_status 返回 pass."""
        assert decide_action({"quality_status": "unknown", "quality_flags": []}) == "pass"

    def test_excessive_fallback_triggers_circuit_break(self):
        """excessive_fallback 标志触发熔断."""
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["excessive_fallback_model_a"],
            "tasks_failed": 1,
            "tasks_total": 10,
        }
        assert decide_action(summary) == "circuit_break"

    def test_deadlock_detected_triggers_escalate(self):
        """死锁检测触发 escalate."""
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["deadlock_detected"],
            "tasks_failed": 1,
            "tasks_total": 10,
        }
        assert decide_action(summary) == "escalate"

    def test_needs_review_returns_escalate(self):
        """needs_review 状态返回 escalate."""
        summary = {
            "quality_status": "needs_review",
            "quality_flags": [],
            "tasks_failed": 0,
            "tasks_total": 5,
        }
        assert decide_action(summary) == "escalate"

    def test_zero_total_tasks_no_division_error(self):
        """tasks_total=0 时不会除以零."""
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 0,
            "tasks_total": 0,
        }
        # Should not raise ZeroDivisionError
        result = decide_action(summary)
        assert isinstance(result, str)

    def test_empty_summary_returns_pass(self):
        """空 summary 返回 pass."""
        assert decide_action({}) == "pass"


class TestShouldRetry:
    """should_retry delegates to decide_action."""

    def test_retry_action_returns_true(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        assert should_retry(summary) is True

    def test_pass_action_returns_false(self):
        summary = {"quality_status": "success", "quality_flags": []}
        assert should_retry(summary) is False

    def test_escalate_action_returns_false(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["deadlock_detected"],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        assert should_retry(summary) is False


class TestShouldEscalate:
    """should_escalate returns True for escalate or circuit_break."""

    def test_escalate_action_returns_true(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["deadlock_detected"],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        assert should_escalate(summary) is True

    def test_circuit_break_action_returns_true(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["excessive_fallback_model_a"],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        assert should_escalate(summary) is True

    def test_pass_action_returns_false(self):
        summary = {"quality_status": "success", "quality_flags": []}
        assert should_escalate(summary) is False

    def test_retry_action_returns_false(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 1,
            "tasks_total": 10,
        }
        assert should_escalate(summary) is False


class TestAutoRecover:
    """auto_recover returns detailed action + reason dict."""

    def test_returns_dict_with_expected_keys(self):
        result = auto_recover({"quality_status": "success", "quality_flags": []})
        assert "action" in result
        assert "auto_retry" in result
        assert "reason" in result
        assert isinstance(result, dict)

    def test_pass_action(self):
        result = auto_recover({"quality_status": "success", "quality_flags": []})
        assert result["action"] == "pass"
        assert result["auto_retry"] is False

    def test_retry_action(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 2,
            "tasks_total": 10,
        }
        result = auto_recover(summary)
        assert result["action"] == "retry"
        assert result["auto_retry"] is True
        assert "自动重试" in result["reason"]

    def test_escalate_action(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": [],
            "tasks_failed": 6,
            "tasks_total": 10,
        }
        result = auto_recover(summary)
        assert result["action"] == "escalate"
        assert result["auto_retry"] is False
        assert "人工介入" in result["reason"]

    def test_circuit_break_action(self):
        summary = {
            "quality_status": "partial_success",
            "quality_flags": ["excessive_fallback_model_a"],
            "tasks_failed": 1,
            "tasks_total": 10,
        }
        result = auto_recover(summary)
        assert result["action"] == "circuit_break"
        assert result["auto_retry"] is False
        assert "熔断" in result["reason"]
