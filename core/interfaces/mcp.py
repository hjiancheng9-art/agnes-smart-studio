"""Abstract MCP (Model Context Protocol) interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .errors import MCPError


@dataclass
class MCPToolDef:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResource:
    """An MCP resource."""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"


@dataclass
class MCPResult:
    """Unified result from MCP operations."""

    success: bool
    data: Any = None
    error: MCPError | None = None
    elapsed_ms: float = 0.0


class MCPClient(ABC):
    """Abstract MCP client — all MCP server connections implement this."""

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the MCP server."""
        ...

    @abstractmethod
    async def list_tools(self) -> list[MCPToolDef]:
        """List available tools on the server."""
        ...

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPResult:
        """Call a tool on the server."""
        ...

    @abstractmethod
    async def read_resource(self, uri: str) -> MCPResult:
        """Read a resource from the server."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        ...
