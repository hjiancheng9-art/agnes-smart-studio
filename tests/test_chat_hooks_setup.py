"""Guardrail tests for ChatSession hook wiring (refactor P1).

These pin the contract of core.chat_hooks_setup.wire_session_hooks: it must set
every Phase flag / hook attribute on the session and never raise, even when the
optional hook modules are unavailable. wire_session_hooks is called from
ChatSession.__init__; testing it directly avoids constructing a full session.
"""

from types import SimpleNamespace

from core.chat_hooks_setup import wire_session_hooks


def _fake_session():
    """Minimal object exposing the attributes/methods wire_session_hooks reads."""
    return SimpleNamespace(
        code_mode=False,
        agent_mode=False,
        messages=[{"role": "system", "content": "sys"}],
        _build_session_context=lambda: "",
        _get_schema_for_tool=lambda name: None,
    )


class TestWireSessionHooks:
    def test_does_not_raise(self):
        session = _fake_session()
        wire_session_hooks(session)  # must never raise

    def test_all_phase_flags_set(self):
        session = _fake_session()
        wire_session_hooks(session)
        for flag in (
            "_p6_telemetry_hooked",
            "_p8_policy_hooked",
            "_p9_project_hooked",
            "_p10_trace_hooked",
            "_p11_failure_learning_hooked",
            "_p12_benchmark_hooked",
            "_p13_field_arena_hooked",
        ):
            assert getattr(session, flag) is True, f"{flag} not set"

    def test_core_session_attributes_set(self):
        session = _fake_session()
        wire_session_hooks(session)
        # These must always be present after wiring, even if optional deps fail.
        assert hasattr(session, "vision_ctx")
        assert hasattr(session, "tvl")  # None on failure, object on success
        assert hasattr(session, "_intelligence_hook")
        assert session._intel_mode == "BALANCED"
        assert session._intel_analysis == {}
        assert session._intel_config == {}
        assert session._pipeline_result is None
        assert hasattr(session, "_adaptive_learner")

    def test_session_context_injected_in_code_mode(self):
        session = _fake_session()
        session.code_mode = True
        session._build_session_context = lambda: "\n[ctx]"
        wire_session_hooks(session)
        assert session.messages[0]["content"].endswith("[ctx]")

    def test_no_context_injection_in_chat_mode(self):
        session = _fake_session()
        session._build_session_context = lambda: "\n[ctx]"
        wire_session_hooks(session)
        # chat mode (code_mode/agent_mode both False) → no injection
        assert session.messages[0]["content"] == "sys"
