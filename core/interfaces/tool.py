"""Tool interfaces — re-exports from the core interfaces module."""

from core.interfaces import (
    ToolCategory,
    ToolRisk,
    ToolSpec,
    ToolResult,
    ToolError,
    execute_tool,
)

__all__ = [
    "ToolCategory",
    "ToolRisk",
    "ToolSpec",
    "ToolResult",
    "ToolError",
    "execute_tool",
]
