"""Abstract Agent interface — all CRUX agents must implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from .errors import AgentError
    from .tool import ToolResult, ToolSpec


@dataclass
class AgentConfig:
    """Configuration for any CRUX agent."""

    name: str
    role: str
    max_steps: int = 20
    timeout_seconds: float = 300.0
    tools: list[ToolSpec] = field(default_factory=list)
    approval_required: bool = False


@dataclass
class AgentResult:
    """Unified result from agent execution."""

    success: bool
    output: Any = None
    steps_taken: int = 0
    elapsed_ms: float = 0.0
    error: AgentError | None = None
    tool_results: list[ToolResult] = field(default_factory=list)


class Agent(ABC):
    """Abstract agent that all CRUX agents (single, swarm, quest) must implement."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._step_count = 0

    @abstractmethod
    async def run(self, goal: str) -> AgentResult:
        """Execute the agent to achieve the given goal."""
        ...

    @abstractmethod
    async def run_stream(self, goal: str) -> AsyncIterator[AgentResult]:
        """Stream intermediate results during execution."""
        ...

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the running agent."""
        ...

    @property
    def step_count(self) -> int:
        return self._step_count
