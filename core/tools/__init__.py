"""Tool system (34 modules).

All tool modules live flat in core/; this package is a logical namespace
for discovery.  Import paths remain unchanged:

    from core.tool_router import get_tool_router
    from core.clipboard_tools import clipboard_copy

Category map:
"""

# ── Tool registry & routing ──────────────────────────────────────
__all__ = [
    # Registry, routing, and dispatch
    "tool_router",  # unified internal+MCP tool routing
    "tool_registry_mesh",  # TRM — multi-source tool index
    "tool_interceptor",  # pre/post call hooks and validation
    "tool_scorecard",  # tool quality scoring and ranking
    "tool_cache",  # tool result LRU caching
    "tool_call_parser",  # parse and validate tool call JSON
    "tool_call_validator",  # validate tool call before execution
    "tool_call_log",  # structured logging of all tool calls
    "tool_executor",  # async tool execution engine
    "tool_outcome",  # structured tool outcome records
    "tool_result",  # tool result normalization
    "tool_specs",  # tool parameter specs and schemas
    "tool_validation_integration",  # integration tests for validation
    "tools",  # main tool registry and dispatch
    "tools_defs",  # tool schema definitions (OpenAI format)
    # Built-in tools
    "browser_tools",  # browser automation (Playwright)
    "codex_tools",  # Codex agent bridge tools
    "context_tools",  # context window management
    "file_tools",  # file read/write/edit
    "format_tools",  # code formatting
    "git_tools",  # git operations (13 tools)
    "github_tools",  # GitHub API/PR/issues
    "image_tools",  # image generation and manipulation
    "audio_tools",  # speech-to-text and TTS
    "pw_tools",  # Playwright worker tools
    "pytest_runner",  # test execution
    # Infrastructure / integration tools (v6.1)
    "clipboard_tools",  # cross-platform clipboard read/write
    "notification_tools",  # desktop notifications
    "fs_watcher",  # polling-based directory monitoring
    "package_tools",  # pip/npm package management
    "redis_tools",  # Redis command execution
    "sql_tools",  # SQLite/MySQL/PostgreSQL query
    "ssh_tools",  # SSH remote execution and file transfer
    "webhook_server",  # local HTTP webhook listener
    "ws_server",  # WebSocket broadcast server
]
