"""Unified tool execution result model — Phase 1 of tool chain refactoring.

Replaces bare exception strings with structured ToolOutcome that carries:
- Status (succeeded/failed/timed_out/cancelled/unknown)
- Failure details with recovery instructions
- Timing and attempt metadata

This lets the chat loop make informed decisions instead of treating all failures identically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"  # side-effect may have happened


class RecoveryAction(str, Enum):
    NONE = "none"
    FIX_ARGUMENTS = "fix_arguments"
    RETRY_AFTER_DELAY = "retry_after_delay"
    USE_ALTERNATIVE_TOOL = "use_alternative_tool"
    RECONCILE_SIDE_EFFECT = "reconcile_side_effect"


@dataclass
class ToolFailure:
    """Structured error info. Carries enough context for the chat loop to decide next action."""
    code: str
    message: str
    recovery: RecoveryAction = RecoveryAction.NONE
    retry_after_ms: int | None = None
    side_effect_certain: bool = True  # False = operation may have completed despite error


@dataclass
class ToolOutcome:
    """Unified result of a single tool execution attempt."""
    status: ToolStatus
    value: str = ""  # tool result text (for model consumption)
    failure: ToolFailure | None = None
    tool_name: str = ""
    attempt: int = 1
    duration_ms: int = 0
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    def mark_done(self) -> None:
        self.duration_ms = int((time.monotonic() - self._start_time) * 1000)

    @classmethod
    def success(cls, value: str, tool_name: str = "") -> ToolOutcome:
        o = cls(status=ToolStatus.SUCCEEDED, value=value, tool_name=tool_name)
        o.mark_done()
        return o

    @classmethod
    def failure_of(cls, code: str, message: str, tool_name: str = "",
                   recovery: RecoveryAction = RecoveryAction.NONE,
                   side_effect_certain: bool = True) -> ToolOutcome:
        o = cls(
            status=ToolStatus.FAILED,
            tool_name=tool_name,
            failure=ToolFailure(
                code=code, message=message, recovery=recovery,
                side_effect_certain=side_effect_certain,
            ),
        )
        o.mark_done()
        return o

    @classmethod
    def timeout(cls, tool_name: str = "", message: str = "") -> ToolOutcome:
        o = cls(
            status=ToolStatus.TIMED_OUT,
            tool_name=tool_name,
            failure=ToolFailure(
                code="tool.timeout", message=message or "Tool timed out",
                recovery=RecoveryAction.RETRY_AFTER_DELAY,
            ),
        )
        o.mark_done()
        return o

    @classmethod
    def cancelled(cls, tool_name: str = "") -> ToolOutcome:
        o = cls(status=ToolStatus.CANCELLED, tool_name=tool_name)
        o.mark_done()
        return o

    @classmethod
    def unknown_side_effect(cls, tool_name: str = "", message: str = "") -> ToolOutcome:
        """Side-effect may have happened despite error (e.g. timeout after submit)."""
        o = cls(
            status=ToolStatus.UNKNOWN,
            tool_name=tool_name,
            failure=ToolFailure(
                code="tool.unknown_outcome", message=message,
                recovery=RecoveryAction.RECONCILE_SIDE_EFFECT,
                side_effect_certain=False,
            ),
        )
        o.mark_done()
        return o
