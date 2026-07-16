"""Abstract Execution interface — sandbox, code executor, pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .errors import ExecutionError


@dataclass
class ExecutionConfig:
    """Configuration for any code executor."""

    timeout_seconds: float = 30.0
    max_memory_mb: int = 512
    allow_network: bool = False
    allow_filesystem: bool = True
    allowed_modules: list[str] = field(default_factory=list)
    denied_modules: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Unified result from code execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    elapsed_ms: float = 0.0
    error: ExecutionError | None = None
    exit_code: int = 0


class CodeExecutor(ABC):
    """Abstract code executor — sandbox, pipeline, TDD all implement this."""

    @abstractmethod
    def execute(self, code: str, config: ExecutionConfig | None = None) -> ExecutionResult:
        """Execute code with the given configuration."""
        ...

    @abstractmethod
    def execute_file(self, path: str, config: ExecutionConfig | None = None) -> ExecutionResult:
        """Execute a file."""
        ...

    @abstractmethod
    def is_safe(self, code: str) -> bool:
        """Check if code is safe to execute (no sandbox violations)."""
        ...
