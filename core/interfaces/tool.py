"""Tool interfaces — re-exports from the core interfaces module."""

from core.interfaces import (
    ToolCategory,
    ToolError,
    ToolResult,
    ToolRisk,
    ToolSpec,
    execute_tool,
)

__all__ = [
    "ToolCategory",
    "ToolError",
    "ToolResult",
    "ToolRisk",
    "ToolSpec",
    "execute_tool",
]
