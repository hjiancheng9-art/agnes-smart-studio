"""Abstract LSP (Language Server Protocol) interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .errors import LSPError


@dataclass
class LSPPosition:
    """Position in a source file."""
    line: int       # 0-based
    character: int  # 0-based


@dataclass
class LSPRange:
    """Range in a source file."""
    start: LSPPosition
    end: LSPPosition


@dataclass
class LSPLocation:
    """Location in a source file."""
    uri: str
    range: LSPRange


@dataclass
class LSPDiagnostic:
    """A diagnostic (error, warning, hint) from LSP."""
    range: LSPRange
    message: str
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    code: str = ""


@dataclass
class LSPHover:
    """Hover information."""
    contents: str
    range: LSPRange | None = None


@dataclass
class LSPCompletion:
    """Completion item."""
    label: str
    detail: str = ""
    documentation: str = ""
    kind: int = 0


@dataclass
class LSPResult:
    """Unified result from LSP operations."""
    success: bool
    data: Any = None
    error: LSPError | None = None
    elapsed_ms: float = 0.0


class LSPClient(ABC):
    """Abstract LSP client — all language server connections implement this."""

    @abstractmethod
    async def open(self, file_path: str) -> None:
        """Open a file in the LSP server."""
        ...

    @abstractmethod
    async def goto_definition(self, file_path: str, line: int, character: int) -> list[LSPLocation]:
        """Go to definition of a symbol."""
        ...

    @abstractmethod
    async def hover(self, file_path: str, line: int, character: int) -> LSPHover | None:
        """Get hover information."""
        ...

    @abstractmethod
    async def references(self, file_path: str, line: int, character: int) -> list[LSPLocation]:
        """Find all references to a symbol."""
        ...

    @abstractmethod
    async def diagnostics(self, file_path: str) -> list[LSPDiagnostic]:
        """Get diagnostics for a file."""
        ...

    @abstractmethod
    async def completion(self, file_path: str, line: int, character: int) -> list[LSPCompletion]:
        """Get completion suggestions."""
        ...

    @abstractmethod
    async def rename(self, file_path: str, line: int, character: int, new_name: str) -> dict[str, Any]:
        """Rename a symbol across the project."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the LSP server."""
        ...

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if the LSP server is alive."""
        ...
