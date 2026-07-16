"""Unified result types — ToolOutcome and Result for all subsystems."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from domain.errors import Failure

T = TypeVar("T")


class ToolStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    status: ToolStatus = ToolStatus.SUCCESS
    content: str = ""
    error: Failure | None = None
    tool_name: str = ""

    @classmethod
    def success(cls, content: str, tool_name: str = "") -> ToolOutcome:
        return cls(status=ToolStatus.SUCCESS, content=content, tool_name=tool_name)

    @classmethod
    def failure(cls, code: str, message: str, tool_name: str = "", retryable: bool = False) -> ToolOutcome:
        return cls(
            status=ToolStatus.FAILURE,
            tool_name=tool_name,
            error=Failure(code=code, kind="internal", message=message, retryable=retryable),
        )

    @classmethod
    def cancelled(cls, tool_name: str = "") -> ToolOutcome:
        return cls(status=ToolStatus.CANCELLED, tool_name=tool_name)


@dataclass(frozen=True, slots=True)
class Success(Generic[T]):
    value: T


@dataclass(frozen=True, slots=True)
class Failed:
    error: Failure


Result = Success[T] | Failed
