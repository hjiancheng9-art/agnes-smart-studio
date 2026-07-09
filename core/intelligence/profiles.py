# core/intelligence/profiles.py
"""Pre-defined ExecutionPolicy profiles for each RunMode."""

from __future__ import annotations

from core.intelligence.policy import ExecutionPolicy, RunMode


def fast_policy() -> ExecutionPolicy:
    """Simple Q&A, no tools, minimal overhead.

    - Keep basic tool validation
    - Turn off reviewer / debate / decomposer
    - Keep light prompt compiler
    - No diff guard, no context compression
    """
    return ExecutionPolicy(
        mode=RunMode.FAST,
        enable_tool_validation=True,
        enable_self_correction=True,
        max_self_correction_attempts=1,
        enable_result_verification=False,
        enable_diff_guard=False,
        enable_context_compiler=False,
        enable_context_compression=False,
        enable_reviewer=False,
        enable_debate=False,
        enable_task_decomposer=False,
        enable_skill_compiler=False,
        enable_prompt_compiler=True,
        trace_level="off",
        eval_recording=False,
        max_agent_rounds=1,
        reviewer_min_response_chars=9999,
    )


def balanced_policy() -> ExecutionPolicy:
    """Default chat mode — standard P1-P3, light P4-P5.

    - Tool validation + self-correction on
    - Result verification on
    - Context compiler on
    - Skill/prompt compiler on
    - Reviewer off (too expensive for default)
    - Debate off
    """
    return ExecutionPolicy(
        mode=RunMode.BALANCED,
        enable_tool_validation=True,
        enable_self_correction=True,
        max_self_correction_attempts=2,
        enable_result_verification=True,
        enable_diff_guard=False,
        enable_context_compiler=True,
        enable_context_compression=False,
        enable_reviewer=False,
        enable_debate=False,
        enable_task_decomposer=False,
        enable_skill_compiler=True,
        enable_prompt_compiler=True,
        trace_level="normal",
        eval_recording=True,
        max_agent_rounds=1,
        reviewer_min_response_chars=500,
    )


def deep_policy() -> ExecutionPolicy:
    """Complex engineering — full P1-P5, reviewer+decomposer on.

    - All P1-P3 enabled
    - Reviewer enabled
    - Task decomposer enabled
    - Context compression enabled (budget pressure)
    - Verbose tracing
    - Higher retry limit
    """
    return ExecutionPolicy(
        mode=RunMode.DEEP,
        enable_tool_validation=True,
        enable_self_correction=True,
        max_self_correction_attempts=3,
        enable_result_verification=True,
        enable_diff_guard=True,
        enable_context_compiler=True,
        enable_context_compression=True,
        enable_reviewer=True,
        enable_debate=False,
        enable_task_decomposer=True,
        enable_skill_compiler=True,
        enable_prompt_compiler=True,
        trace_level="verbose",
        eval_recording=True,
        max_agent_rounds=3,
        reviewer_min_response_chars=100,
    )


def safe_policy() -> ExecutionPolicy:
    """High-risk operations — maximum guards.

    - DiffGuard forced on
    - Reviewer forced on
    - Result verification forced on
    - Self-correction on
    - Debate off (too slow)
    """
    return ExecutionPolicy(
        mode=RunMode.SAFE,
        enable_tool_validation=True,
        enable_self_correction=True,
        max_self_correction_attempts=3,
        enable_result_verification=True,
        enable_diff_guard=True,
        enable_context_compiler=True,
        enable_context_compression=False,
        enable_reviewer=True,
        enable_debate=False,
        enable_task_decomposer=False,
        enable_skill_compiler=True,
        enable_prompt_compiler=True,
        trace_level="verbose",
        eval_recording=True,
        max_agent_rounds=2,
        reviewer_min_response_chars=50,
    )


def debug_policy() -> ExecutionPolicy:
    """Failure diagnosis — replay + regression + verbose trace.

    - All modules enabled for full introspection
    - Trace verbose
    - Eval recording on
    - Reviewer on
    """
    return ExecutionPolicy(
        mode=RunMode.DEBUG,
        enable_tool_validation=True,
        enable_self_correction=True,
        max_self_correction_attempts=3,
        enable_result_verification=True,
        enable_diff_guard=True,
        enable_context_compiler=True,
        enable_context_compression=True,
        enable_reviewer=True,
        enable_debate=True,
        enable_task_decomposer=True,
        enable_skill_compiler=True,
        enable_prompt_compiler=True,
        trace_level="verbose",
        eval_recording=True,
        max_agent_rounds=5,
        reviewer_min_response_chars=10,
    )


# Registry
_PROFILES = {
    "fast": fast_policy,
    "balanced": balanced_policy,
    "deep": deep_policy,
    "safe": safe_policy,
    "debug": debug_policy,
}


def load_profile(mode: str) -> ExecutionPolicy:
    """Load a policy by mode name. Falls back to balanced."""
    factory = _PROFILES.get(mode.lower())
    if factory is None:
        return balanced_policy()
    return factory()


def list_profiles() -> list[str]:
    return list(_PROFILES.keys())
