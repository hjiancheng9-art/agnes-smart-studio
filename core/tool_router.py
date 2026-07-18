"""Unified tool router — internal tools + MCP tools as one namespace.

GPT capability fix #3: "Normalize internal + MCP tools so agent loop can call
either transparently. Closes the biggest Claude Code gap."

Pattern: Claude Code's tool registry — internal and MCP tools are first-class.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("crux.tool_router")

# Internal tool registry — populated at startup
_internal_tools: dict[str, callable] = {}

# MCP tool metadata cache: {tool_full_name: {name, description, server, parameters}}
_mcp_tools: dict[str, dict] = {}

_initialized = False


def register_internal(name: str, handler: callable) -> None:
    """Register an internal CRUX tool."""
    _internal_tools[name] = handler


def register_mcp_tools(server_name: str, tools: list[dict]) -> int:
    """Index MCP tools from a server. Returns count registered."""
    count = 0
    for tool in tools:
        full_name = f"mcp.{server_name}.{tool['name']}"
        _mcp_tools[full_name] = {
            "name": full_name,
            "description": tool.get("description", ""),
            "server": server_name,
            "parameters": tool.get("inputSchema", tool.get("parameters", {})),
        }
        count += 1
    return count


def reset_tool_router() -> None:
    """Test isolation: clear all registered tools (internal + MCP)."""
    _internal_tools.clear()
    _mcp_tools.clear()
    global _initialized
    _initialized = False


def list_all_tools() -> list[dict]:
    """List all available tools (internal + MCP) with metadata.

    Returns list of {name, description, source: 'internal'|'mcp', parameters}.
    """
    tools = []

    # Internal tools — loaded from tools.json
    try:
        tools_json = json.loads((__import__("pathlib").Path(__file__).parent.parent / "tools.json").read_text("utf-8"))
        for t in tools_json.get("tools", []):
            tools.append(
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "source": "internal",
                    "category": t.get("category", "utility"),
                    "parameters": t.get("parameters", {}),
                }
            )
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    # MCP tools
    for full_name, meta in _mcp_tools.items():
        tools.append(
            {
                "name": full_name,
                "description": meta["description"],
                "source": "mcp",
                "server": meta["server"],
                "parameters": meta.get("parameters", {}),
            }
        )

    return tools


def get_tool_schema(name: str) -> dict | None:
    """Get the JSON Schema (parameters) for a tool by name.

    Used by ToolValidator._has_tool() and _get_schema() as a schema_provider
    callback. Checks tools.json first, then falls back to programmatically
    registered tools (e.g. task_launch from background.py).
    Returns the tool's parameters dict, or None if not found.
    """
    tool = find_tool(name)
    if tool:
        return tool.get("parameters", {})
    # Fallback: programmatically registered tools not in tools.json
    # NOTE: registry.has() checks _executors (may miss tools only in _definitions),
    #       so directly use registry.schema() which checks _definitions.
    try:
        from core.tools import get_registry

        schema = get_registry().schema(name)
        if schema:
            return schema.get("parameters", {})
    except Exception:
        logger.debug("Exception in tool_router", exc_info=True)
    return None


def find_tool(name: str) -> dict | None:
    """Find a tool by name (internal or mcp.*). Returns metadata or None."""
    all_tools = list_all_tools()
    for t in all_tools:
        if t["name"] == name:
            return t
    # Fuzzy: try without mcp. prefix
    for t in all_tools:
        if t["name"].endswith(f".{name}") or t["name"] == name:
            return t
    return None


async def call_tool(name: str, arguments: dict | None = None) -> dict:
    """Call a tool by name — internal or MCP.

    Args:
        name: Tool name. Use "mcp.<server>.<tool>" for MCP tools,
              or plain name for internal tools.
        arguments: Tool arguments dict.

    Returns:
        {success: bool, result: any, error: str|None}
    """
    args = arguments or {}

    # MCP tools: name starts with "mcp."
    if name.startswith("mcp."):
        return await _call_mcp_tool(name, args)

    # Internal tools
    return await _call_internal_tool(name, args)


async def _call_internal_tool(name: str, args: dict) -> dict:
    """Call an internal CRUX tool."""
    handler = _internal_tools.get(name)
    if not handler:
        # Try to import and call dynamically
        return await _dispatch_internal_dynamic(name, args)

    try:
        result = handler(**args) if callable(handler) else handler
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        logger.exception("Internal tool '%s' failed", name)
        return {"success": False, "result": None, "error": str(e)}


async def _call_mcp_tool(full_name: str, args: dict) -> dict:
    """Call an MCP tool via the bridge client.

    Tool name format: mcp.<server_name>.<tool_name>
    e.g. mcp.codex.codex_ask or mcp.crux.generate_image
    """
    meta = _mcp_tools.get(full_name)
    if not meta:
        # Try auto-register from connected servers
        _refresh_mcp_tools()
        meta = _mcp_tools.get(full_name)
        if not meta:
            return {"success": False, "result": None, "error": f"Unknown MCP tool: {full_name}"}

    try:
        from core.mcp_client import get_mcp_client

        client = get_mcp_client()
        if client is None:
            # Attempt lazy init — MCP servers configured in ~/.crux/mcp_servers.json
            try:
                from core.mcp_client import MCPClient

                client = MCPClient()
                client.load_config()
                for name in client.list_servers():
                    try:
                        client.connect(name)
                        tools = client.list_tools(name)
                        register_mcp_tools(name, tools)
                    except Exception:
                        logger.debug("Cannot auto-connect MCP server: %s", name, exc_info=True)
            except Exception as e:
                return {"success": False, "result": None, "error": f"MCP client unavailable: {e}"}

        if client is None:
            return {
                "success": False,
                "result": None,
                "error": "MCP client not initialized. Run crux init to configure.",
            }

        result = client.call_tool(meta["server"], meta["name"].split(".")[-1], args)
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        logger.exception("MCP tool '%s' failed", full_name)
        return {"success": False, "result": None, "error": str(e)}


def _refresh_mcp_tools() -> None:
    """Re-index MCP tools from all connected servers."""
    try:
        from core.mcp_client import get_mcp_client

        client = get_mcp_client()
        if client:
            for name in client.list_servers():
                try:
                    tools = client.list_tools(name)
                    register_mcp_tools(name, tools)
                except Exception as e:
                    logger.debug("Non-critical: %s", e, exc_info=True)
    except Exception as e:
        logger.debug("Non-critical: %s", e, exc_info=True)


async def _dispatch_internal_dynamic(name: str, args: dict) -> dict:
    """Fallback: try to find and call a tool by matching tools.json entries."""
    try:
        # Read tools.json for the tool definition
        tools_path = __import__("pathlib").Path(__file__).parent.parent / "tools.json"
        tools_data = json.loads(tools_path.read_text("utf-8"))
        for t in tools_data.get("tools", []):
            if t["name"] != name:
                continue
            command = t.get("command", "")
            if not command:
                return {"success": False, "result": None, "error": f"No handler for: {name}"}

            # Execute as shell command (tools.json pattern)
            import subprocess

            # Substitute {param} placeholders
            for key, val in args.items():
                command = command.replace(f"{{{key}}}", str(val))

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": result.returncode == 0,
                "result": result.stdout or result.stderr,
                "error": None if result.returncode == 0 else result.stderr,
            }

        return {"success": False, "result": None, "error": f"Tool not found: {name}"}
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


# Compatibility alias for external callers
def get_tool_router():
    """Get the tool router singleton (compatibility wrapper)."""
    return {
        "list": list_all_tools,
        "find": find_tool,
        "call": call_tool,
        "register": register_internal,
        "index_mcp": register_mcp_tools,
    }
