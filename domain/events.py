"""Runtime event types — the only output from RuntimeEngine to TUI/CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    request_id: str = ""
    sequence: int = 0


@dataclass(frozen=True, slots=True)
class RequestAccepted(RuntimeEvent):
    pass


@dataclass(frozen=True, slots=True)
class StageStarted(RuntimeEvent):
    stage: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class StageCompleted(RuntimeEvent):
    stage: str = ""


@dataclass(frozen=True, slots=True)
class PlanCreated(RuntimeEvent):
    mode: str = ""
    complexity: int = 0
    tool_count: int = 0


@dataclass(frozen=True, slots=True)
class ModelStarted(RuntimeEvent):
    provider: str = ""
    model: str = ""


@dataclass(frozen=True, slots=True)
class ModelToken(RuntimeEvent):
    text: str = ""


@dataclass(frozen=True, slots=True)
class ModelToolCall(RuntimeEvent):
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolStarted(RuntimeEvent):
    tool_name: str = ""


@dataclass(frozen=True, slots=True)
class ToolCompleted(RuntimeEvent):
    tool_name: str = ""
    ok: bool = True
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class FallbackStarted(RuntimeEvent):
    from_provider: str = ""
    to_provider: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class WarningRaised(RuntimeEvent):
    message: str = ""


@dataclass(frozen=True, slots=True)
class ResponseCompleted(RuntimeEvent):
    total_tokens: int = 0
    elapsed_ms: int = 0


@dataclass(frozen=True, slots=True)
class RequestFailed(RuntimeEvent):
    error_code: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class RequestCancelled(RuntimeEvent):
    pass
