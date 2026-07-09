"""Test P8: Intelligence Policy Router."""

import pytest

from core.intelligence.policy import RunMode
from core.intelligence.profiles import (
    balanced_policy,
    debug_policy,
    deep_policy,
    fast_policy,
    list_profiles,
    load_profile,
    safe_policy,
)
from core.intelligence.router import IntelligencePolicyRouter
from core.intelligence.signals import SignalExtractor, TaskSignals

# ── RunMode ─────────────────────────────────────────────────────────


class TestRunMode:
    def test_values(self):
        assert RunMode.FAST.value == "fast"
        assert RunMode.BALANCED.value == "balanced"
        assert RunMode.DEEP.value == "deep"
        assert RunMode.SAFE.value == "safe"
        assert RunMode.DEBUG.value == "debug"

    def test_all_modes_present(self):
        assert len(list(RunMode)) == 5


# ── ExecutionPolicy ─────────────────────────────────────────────────


class TestExecutionPolicy:
    def test_fast_defaults(self):
        p = fast_policy()
        assert p.mode == RunMode.FAST
        assert p.enable_reviewer is False
        assert p.enable_diff_guard is False
        assert p.enable_tool_validation is True
        assert p.eval_recording is False
        assert p.trace_level == "off"

    def test_balanced_defaults(self):
        p = balanced_policy()
        assert p.mode == RunMode.BALANCED
        assert p.enable_reviewer is False
        assert p.enable_result_verification is True

    def test_deep_defaults(self):
        p = deep_policy()
        assert p.mode == RunMode.DEEP
        assert p.enable_reviewer is True
        assert p.enable_task_decomposer is True
        assert p.max_self_correction_attempts == 3
        assert p.max_agent_rounds == 3

    def test_safe_defaults(self):
        p = safe_policy()
        assert p.mode == RunMode.SAFE
        assert p.enable_diff_guard is True
        assert p.enable_reviewer is True
        assert p.enable_result_verification is True

    def test_debug_defaults(self):
        p = debug_policy()
        assert p.mode == RunMode.DEBUG
        assert p.enable_debate is True
        assert p.trace_level == "verbose"

    def test_frozen_policy(self):
        p = balanced_policy()
        with pytest.raises(Exception):
            p.enable_reviewer = True  # frozen dataclass

    def test_to_dict(self):
        p = balanced_policy()
        d = p.to_dict()
        assert d["mode"] == "balanced"
        assert "enable_tool_validation" in d

    def test_summary(self):
        p = fast_policy()
        s = p.summary()
        assert "FAST" in s
        assert "✅" in s
        assert "❌" in s

    def test_load_profile_fast(self):
        p = load_profile("fast")
        assert p.mode == RunMode.FAST

    def test_load_profile_deep(self):
        p = load_profile("deep")
        assert p.mode == RunMode.DEEP

    def test_load_profile_unknown_falls_back(self):
        p = load_profile("nonexistent")
        assert p.mode == RunMode.BALANCED

    def test_list_profiles(self):
        profiles = list_profiles()
        assert "fast" in profiles
        assert "deep" in profiles
        assert len(profiles) == 5


# ── TaskSignals ─────────────────────────────────────────────────────


class TestTaskSignals:
    def test_simple_query(self):
        extractor = SignalExtractor()
        signals = extractor.extract("What is the capital of France?")
        assert signals.requires_tools is False
        assert signals.estimated_task_complexity < 0.25
        assert signals.estimated_risk <= 0.02

    def test_code_task(self):
        extractor = SignalExtractor()
        signals = extractor.extract("read_file('auth.py') and show me the content")
        # read_file keyword should trigger tools flag
        assert signals.requires_tools is True

    def test_danger_keywords(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Delete the entire database file")
        assert signals.has_danger_keywords is True
        assert signals.estimated_risk > 0.3

    def test_shell_command(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Run bash command to check disk space")
        assert signals.requires_shell is True
        assert signals.estimated_risk > 0.2

    def test_architecture_task(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Design the architecture for a microservice system")
        assert signals.requires_architecture_reasoning is True
        assert signals.estimated_task_complexity > 0.3

    def test_multi_step(self):
        extractor = SignalExtractor()
        signals = extractor.extract("First read the file, then edit it, then run tests")
        assert signals.requires_multi_step is True

    def test_failure_indicator(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Still not working, same error as before")
        assert signals.has_failure_indicator is True

    def test_token_pressure(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Hello", current_tokens=50000, max_tokens=64000)
        assert signals.token_pressure > 0.7

    def test_prior_failure_score(self):
        extractor = SignalExtractor()
        signals = extractor.extract("Fix it", prior_failures=5, prior_total_turns=6)
        assert signals.prior_failure_score > 0.5

    def test_long_message_complexity(self):
        extractor = SignalExtractor()
        signals = extractor.extract("x" * 2000)
        assert signals.estimated_task_complexity >= 0.5

    def test_to_dict(self):
        s = TaskSignals(estimated_task_complexity=0.5, estimated_risk=0.3)
        d = s.to_dict()
        assert d["estimated_task_complexity"] == 0.5
        assert d["estimated_risk"] == 0.3


# ── IntelligencePolicyRouter ────────────────────────────────────────


class TestRouter:
    def test_simple_question_gets_fast(self):
        router = IntelligencePolicyRouter()
        policy = router.route("What is 2+2?")
        assert policy.mode == RunMode.FAST

    def test_code_task_gets_balanced_or_deep(self):
        router = IntelligencePolicyRouter()
        # Contains edit_file keyword → requires_tools=True → complexity > 0.25
        policy = router.route("edit_file('auth.py') to fix the login bug")
        assert policy.mode in (RunMode.BALANCED, RunMode.DEEP)

    def test_danger_gets_safe(self):
        router = IntelligencePolicyRouter()
        policy = router.route("Delete the entire config directory")
        assert policy.mode == RunMode.SAFE

    def test_failure_indicator_gets_debug(self):
        router = IntelligencePolicyRouter()
        policy = router.route("Still broken, same error", prior_failures=3, prior_total_turns=5)
        assert policy.mode == RunMode.DEBUG

    def test_architecture_gets_deep(self):
        router = IntelligencePolicyRouter()
        policy = router.route("Design the architecture for a new CRUX phase")
        assert policy.mode == RunMode.DEEP

    def test_multi_step_gets_deep(self):
        router = IntelligencePolicyRouter()
        policy = router.route("First read config, then edit it, then restart")
        assert policy.mode == RunMode.DEEP

    def test_force_mode_bypass(self):
        router = IntelligencePolicyRouter()
        # Even simple question should become deep if forced
        policy = router.route("Hello", force_mode="deep")
        assert policy.mode == RunMode.DEEP

    def test_force_mode_fast(self):
        router = IntelligencePolicyRouter()
        policy = router.route("Delete everything", force_mode="fast")
        assert policy.mode == RunMode.FAST

    def test_explain_last(self):
        router = IntelligencePolicyRouter()
        router.route("Hello")
        explanation = router.explain_last()
        assert "FAST" in explanation or "BALANCED" in explanation

    def test_no_decision_yet(self):
        router = IntelligencePolicyRouter()
        assert "No routing decision" in router.explain_last()

    def test_high_prior_failure_gets_debug(self):
        router = IntelligencePolicyRouter()
        policy = router.route("Write a simple test", prior_failures=5, prior_total_turns=6)
        assert policy.mode == RunMode.DEBUG

    def test_empty_message_defaults_balanced(self):
        router = IntelligencePolicyRouter()
        policy = router.route("")
        assert policy.mode in (RunMode.FAST, RunMode.BALANCED)


# ── Integration with ValidationLayer ────────────────────────────────


class TestIntegration:
    def test_router_in_validation_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert hasattr(vl, "policy_router")
        assert hasattr(vl, "_current_policy")

    def test_route_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        policy = vl.route_policy("What is Python?")
        assert policy is not None
        assert policy.mode in (RunMode.FAST, RunMode.BALANCED)

    def test_force_mode_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        policy = vl.force_mode("deep")
        assert policy.mode == RunMode.DEEP
        assert vl.current_policy.mode == RunMode.DEEP

    def test_explain_through_layer(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        vl.route_policy("Hello")
        explanation = vl.explain_policy()
        assert explanation is not None

    def test_chat_p8_flag(self):
        import py_compile
        py_compile.compile("core/chat.py", doraise=True)
