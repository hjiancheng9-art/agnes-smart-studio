"""Unified error types for CRUX — all modules should use these."""

from __future__ import annotations


class CRUXError(Exception):
    """Base exception for all CRUX errors."""

    code: str = "UNKNOWN"
    recoverable: bool = False

    def __init__(self, message: str, detail: str | None = None):
        """初始化 CRUX 错误 — 设置错误码、消息和详情。"""
        super().__init__(message)
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════
#  Browser / CDP errors
# ═══════════════════════════════════════════════════


class BrowserError(CRUXError):
    """浏览器相关错误基类。"""

    code = "BROWSER_ERROR"


class CDPDisconnected(BrowserError):
    """CDP (Chrome DevTools Protocol) 连接断开。"""

    code = "CDP_DISCONNECTED"
    recoverable = True


class CDPTimeout(BrowserError):
    """CDP 操作超时。"""

    code = "CDP_TIMEOUT"
    recoverable = True


class SelectorNotFound(BrowserError):
    """CSS/XPath 选择器未找到目标元素。"""

    code = "SELECTOR_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  MCP errors
# ═══════════════════════════════════════════════════


class MCPError(CRUXError):
    """MCP (Model Context Protocol) 相关错误基类。"""

    code = "MCP_ERROR"


class MCPDisconnected(MCPError):
    """MCP 服务器连接断开。"""

    code = "MCP_DISCONNECTED"
    recoverable = True


class MCPToolNotFound(MCPError):
    """MCP 工具未找到。"""

    code = "MCP_TOOL_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  LSP errors
# ═══════════════════════════════════════════════════


class LSPError(CRUXError):
    """LSP (Language Server Protocol) 相关错误基类。"""

    code = "LSP_ERROR"


class LSPDisconnected(LSPError):
    """LSP 服务器连接断开。"""

    code = "LSP_DISCONNECTED"
    recoverable = True


class LSPSymbolNotFound(LSPError):
    """LSP 符号查找未找到。"""

    code = "LSP_SYMBOL_NOT_FOUND"


# ═══════════════════════════════════════════════════
#  Execution / sandbox errors
# ═══════════════════════════════════════════════════


class ExecutionError(CRUXError):
    """代码执行相关错误基类。"""

    code = "EXECUTION_ERROR"


class SandboxViolation(ExecutionError):
    """沙箱安全策略违规。"""

    code = "SANDBOX_VIOLATION"


class TimeoutError(ExecutionError):
    """执行超时。"""

    code = "EXECUTION_TIMEOUT"
    recoverable = True


# ═══════════════════════════════════════════════════
#  Permission / governance errors
# ═══════════════════════════════════════════════════


class PermissionDenied(CRUXError):
    """操作权限不足。"""

    code = "PERMISSION_DENIED"


class ApprovalRequired(PermissionDenied):
    """操作需要用户审批。"""

    code = "APPROVAL_REQUIRED"


# ═══════════════════════════════════════════════════
#  Tool / registry errors
# ═══════════════════════════════════════════════════


class ToolError(CRUXError):
    """工具调用相关错误基类。"""

    code = "TOOL_ERROR"


class ToolNotFound(ToolError):
    """工具未在注册表中找到。"""

    code = "TOOL_NOT_FOUND"


class ToolContractViolation(ToolError):
    """工具调用违反参数契约。"""

    code = "TOOL_CONTRACT_VIOLATION"


class RateLimited(ToolError):
    """工具调用被限流。"""

    code = "RATE_LIMITED"
    recoverable = True


# ═══════════════════════════════════════════════════
#  Agent errors
# ═══════════════════════════════════════════════════


class AgentError(CRUXError):
    """Agent 执行相关错误基类。"""

    code = "AGENT_ERROR"


class AgentTimeout(AgentError):
    """Agent 执行超时。"""

    code = "AGENT_TIMEOUT"
    recoverable = True


class AgentLoopDetected(AgentError):
    """检测到 Agent 循环调用。"""

    code = "AGENT_LOOP_DETECTED"
