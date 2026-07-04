"""Executor data models — extracted from core/executor.py to reduce module size.

Contains pure dataclasses shared by TaskExecutor, SmartPlanner, and SelfReflection.
No I/O or tool-calling logic here. Verbatim copies from the original executor.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Step:
    id: str
    description: str
    tool: str
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verify: str | None = None  # "syntax" | "test" | None
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""
    error: str = ""


@dataclass
class Task:
    id: str
    goal: str
    steps: list[Step] = field(default_factory=list)
    status: str = "pending"
    errors_allowed: int = 0
    reflection_enabled: bool = False  # enable self-reflection on step failure
    max_retries_per_step: int = 2  # max reflection/retry attempts per step


@dataclass
class Goal:
    """A goal-mode task with clear finish line, boundaries, and budget."""

    id: str
    intent: str
    finish_line: str = ""
    boundaries: str = ""
    status: str = "active"  # active | paused | completed | cancelled
    max_steps: int = 20
    max_tool_calls: int = 100
    max_duration_seconds: int = 0  # 0 = unlimited
    steps_executed: int = 0
    tool_calls_made: int = 0
    created_at: str = ""
    updated_at: str = ""
    evidence: str = ""

    def is_budget_exhausted(self) -> bool:
        return self.steps_executed >= self.max_steps or self.tool_calls_made >= self.max_tool_calls

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Goal:
        return cls(**data)


@dataclass
class AdjustResult:
    """Self-reflection 的输出：决定下一步行动。"""

    action: str  # "retry" | "replan" | "skip"
    tool: str = ""
    args: dict = field(default_factory=dict)
    reason: str = ""
