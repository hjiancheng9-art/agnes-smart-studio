"""Execution plan and routing types — one immutable plan per turn."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal


class TaskComplexity(IntEnum):
    SIMPLE = 1
    STANDARD = 2
    COMPLEX = 3
    CRITICAL = 4


ExecutionMode = Literal["direct", "skill", "orchestrate", "swarm"]


@dataclass(frozen=True, slots=True)
class ModelRoute:
    provider: str
    model: str
    context_limit: int = 128000


@dataclass(frozen=True, slots=True)
class PromptPlan:
    task_profile: str = "default"
    tool_names: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    request_id: str = ""
    complexity: TaskComplexity = TaskComplexity.STANDARD
    mode: ExecutionMode = "direct"
    model_route: ModelRoute = field(default_factory=lambda: ModelRoute(provider="deepseek", model="deepseek-v4-flash"))
    prompt_plan: PromptPlan = field(default_factory=PromptPlan)
    max_turns: int = 10
    max_tool_calls: int = 30
    max_elapsed_s: float = 600.0
