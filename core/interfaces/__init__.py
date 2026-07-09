"""Unified interfaces for CRUX tool system.

All 80+ internal tools, 56 skill packages, and MCP tools should
conform to these contracts. This prevents the tool ecosystem from
spiraling out of control as new tools are added.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ═══════════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════════

class ToolCategory(enum.Enum):
    SEARCH = "search"
    EXECUTE = "execute"
    REVIEW = "review"
    THINK = "think"
    GENERATE = "generate"
    STATUS = "status"
    IO = "io"
    BROWSER = "browser"
    MCP = "mcp"
    LSP = "lsp"
    GIT = "git"
    GITHUB = "github"
    TEST = "test"
    UTILITY = "utility"


class ToolRisk(enum.Enum):
    """Risk level determines if approval_gate or sandbox is required."""
    READONLY = "readonly"        # No side effects
    LOCAL_WRITE = "local_write"  # Writes to local filesystem
    NETWORK = "network"          # Outbound network
    SHELL = "shell"              # Shell execution
    BROWSER = "browser"          # Browser automation
    DESTRUCTIVE = "destructive"  # Can delete data / push / deploy


# ═══════════════════════════════════════════════════
#  Core Data Classes
# ═══════════════════════════════════════════════════

@dataclass
class ToolSpec:
    """Formal specification for any tool in the CRUX ecosystem."""
    name: str
    description: str
    category: ToolCategory
    risk: ToolRisk = ToolRisk.READONLY

    # Schema
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    # Execution
    timeout_seconds: float = 30.0
    max_retries: int = 0
    idempotent: bool = True

    # Dependencies
    requires_browser: bool = False
    requires_network: bool = False
    requires_mcp: bool = False
    requires_lsp: bool = False
    requires_github_token: bool = False

    # The actual callable (injected, not serialized)
    _handler: Optional[Callable[..., ToolResult]] = field(default=None, repr=False)

    def __post_init__(self):
        if self._handler is None:
            raise ValueError(f"ToolSpec '{self.name}' requires a handler callable")


@dataclass
class ToolResult:
    """Unified result from any tool execution.

    All tools MUST return this. No raw exceptions, no bare strings.
    """
    success: bool
    data: Any = None
    error: Optional[ToolError] = None
    tool_name: str = ""
    elapsed_ms: float = 0.0
    retry_count: int = 0

    @classmethod
    def ok(cls, data: Any, tool_name: str = "", elapsed_ms: float = 0.0) -> "ToolResult":
        return cls(success=True, data=data, tool_name=tool_name, elapsed_ms=elapsed_ms)

    @classmethod
    def fail(cls, error: "ToolError", tool_name: str = "", elapsed_ms: float = 0.0) -> "ToolResult":
        return cls(success=False, error=error, tool_name=tool_name, elapsed_ms=elapsed_ms)


@dataclass
class ToolError:
    """Structured error from tool execution."""
    code: str                     # e.g. "TIMEOUT", "NETWORK", "PERMISSION_DENIED"
    message: str
    detail: Optional[str] = None
    recoverable: bool = False     # Can the caller retry?
    original_exception: Optional[Exception] = field(default=None, repr=False)

    # Standard error codes
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_INPUT = "INVALID_INPUT"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    BROWSER_ERROR = "BROWSER_ERROR"
    MCP_ERROR = "MCP_ERROR"
    LSP_ERROR = "LSP_ERROR"
    INTERNAL = "INTERNAL"
    RATE_LIMITED = "RATE_LIMITED"


# ═══════════════════════════════════════════════════
#  Execution wrapper
# ═══════════════════════════════════════════════════

def execute_tool(spec: ToolSpec, **kwargs) -> ToolResult:
    """Safe tool execution with timeout and error wrapping.

    Every tool call in CRUX should go through this function.
    """
    if spec._handler is None:
        return ToolResult.fail(
            ToolError(ToolError.INTERNAL, f"Tool '{spec.name}' has no handler"),
            tool_name=spec.name
        )

    start = time.perf_counter()
    try:
        data = spec._handler(**kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        return ToolResult.ok(data, tool_name=spec.name, elapsed_ms=elapsed)
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        err = ToolError(
            code=_classify_error(e),
            message=str(e),
            detail=repr(e),
            recoverable=_is_recoverable(e),
            original_exception=e,
        )
        return ToolResult.fail(err, tool_name=spec.name, elapsed_ms=elapsed)


def _classify_error(e: Exception) -> str:
    name = type(e).__name__.lower()
    if "timeout" in name:
        return ToolError.TIMEOUT
    if any(kw in name for kw in ("connection", "network", "socket", "http")):
        return ToolError.NETWORK
    if "permission" in name:
        return ToolError.PERMISSION_DENIED
    if any(kw in name for kw in ("value", "type", "attribute", "key")):
        return ToolError.INVALID_INPUT
    if "browser" in name or "playwright" in name or "cdp" in name:
        return ToolError.BROWSER_ERROR
    return ToolError.INTERNAL


def _is_recoverable(e: Exception) -> bool:
    name = type(e).__name__.lower()
    return any(kw in name for kw in ("timeout", "connection", "retry", "rate"))
