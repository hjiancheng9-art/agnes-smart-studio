"""Unified error types for CRUX — all modules should use these."""

from __future__ import annotations


class CRUXError(Exception):
    """Base exception for all CRUX errors."""
    code: str = "UNKNOWN"
    recoverable: bool = False

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════
#  Browser / CDP errors
# ═══════════════════════════════════════════════════

class BrowserError(CRUXError):
    code = "BROWSER_ERROR"


class CDPDisconnected(BrowserError):
    code = "CDP_DISCONNECTED"
    recoverable = True


class CDPTimeout(BrowserError):
    code = "CDP_TIMEOUT"
    recoverable = True


class SelectorNotFound(BrowserError):
    code = "SELECTOR_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  MCP errors
# ═══════════════════════════════════════════════════

class MCPError(CRUXError):
    code = "MCP_ERROR"


class MCPDisconnected(MCPError):
    code = "MCP_DISCONNECTED"
    recoverable = True


class MCPToolNotFound(MCPError):
    code = "MCP_TOOL_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  LSP errors
# ═══════════════════════════════════════════════════

class LSPError(CRUXError):
    code = "LSP_ERROR"


class LSPDisconnected(LSPError):
    code = "LSP_DISCONNECTED"
    recoverable = True


class LSPSymbolNotFound(LSPError):
    code = "LSP_SYMBOL_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  Execution / sandbox errors
# ═══════════════════════════════════════════════════

class ExecutionError(CRUXError):
    code = "EXECUTION_ERROR"


class SandboxViolation(ExecutionError):
    code = "SANDBOX_VIOLATION"


class TimeoutError(ExecutionError):
    code = "EXECUTION_TIMEOUT"
    recoverable = True


# ═══════════════════════════════════════════════════
#  Permission / governance errors
# ═══════════════════════════════════════════════════

class PermissionDenied(CRUXError):
    code = "PERMISSION_DENIED"


class ApprovalRequired(PermissionDenied):
    code = "APPROVAL_REQUIRED"


# ═══════════════════════════════════════════════════
#  Tool / registry errors
# ═══════════════════════════════════════════════════

class ToolError(CRUXError):
    code = "TOOL_ERROR"


class ToolNotFound(ToolError):
    code = "TOOL_NOT_FOUND"


class ToolContractViolation(ToolError):
    code = "TOOL_CONTRACT_VIOLATION"


class RateLimited(ToolError):
    code = "RATE_LIMITED"
    recoverable = True


# ═══════════════════════════════════════════════════
#  Agent errors
# ═══════════════════════════════════════════════════

class AgentError(CRUXError):
    code = "AGENT_ERROR"


class AgentTimeout(AgentError):
    code = "AGENT_TIMEOUT"
    recoverable = True


class AgentLoopDetected(AgentError):
    code = "AGENT_LOOP_DETECTED"
