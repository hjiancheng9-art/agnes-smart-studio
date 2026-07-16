"""Unified task classification and execution plan — single source of truth.

Replaces dual enums (TaskGrade A-D / TaskComplexity TRIVIAL-CRITICAL)
and scattered decision logic across execution_policy, router, and chat_prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class TaskComplexity(IntEnum):
    SIMPLE = 1
    STANDARD = 2
    COMPLEX = 3
    CRITICAL = 4


class ExecutionMode:
    DIRECT = "direct"
    SKILL = "skill"
    ORCHESTRATE = "orchestrate"
    SWARM = "swarm"


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Immutable per-turn execution plan. Built once at turn start, consumed by all subsystems."""
    complexity: TaskComplexity = TaskComplexity.STANDARD
    mode: str = ExecutionMode.DIRECT
    model_alias: str = "pro"  # "light" | "pro" | "reasoner"
    prompt_profile: str = "default"  # "debug" | "architecture" | "research" | "default"
    tool_names: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()
    use_orchestrator: bool = False
    use_swarm: bool = False


def plan_from_policy(user_text: str) -> ExecutionPlan:
    """Fast rule-based classification. Uses existing ExecutionPolicy keywords."""
    from core.execution_policy import choose_policy, ExecutionMode as EM

    policy = choose_policy(user_text)
    t = user_text.lower()

    # Complexity
    if policy.mode == EM.SWARM:
        complexity = TaskComplexity.CRITICAL
    elif policy.mode == EM.ORCHESTRATE:
        complexity = TaskComplexity.COMPLEX
    elif len(user_text) < 50:
        complexity = TaskComplexity.SIMPLE
    else:
        complexity = TaskComplexity.STANDARD

    # Model
    model = "pro" if complexity >= TaskComplexity.COMPLEX else "light"

    # Tools — minimal set per mode
    base_tools = ("read_file", "search_files", "glob_files")
    if policy.mode == EM.ORCHESTRATE:
        tools = base_tools + ("orchestrate", "write_file", "edit_file", "run_bash", "run_test")
    elif policy.mode == EM.SWARM:
        tools = ("agent_swarm", "orchestrate", "read_file", "search_files", "glob_files")
    elif policy.mode == EM.SKILL:
        tools = base_tools + ("skill_load", "skill_search")
    else:
        tools = base_tools + ("run_bash", "write_file", "edit_file", "run_test", "web_search")

    return ExecutionPlan(
        complexity=complexity,
        mode=policy.mode,
        model_alias=model,
        tool_names=tools,
        use_orchestrator=policy.mode == EM.ORCHESTRATE,
        use_swarm=policy.mode == EM.SWARM,
    )
