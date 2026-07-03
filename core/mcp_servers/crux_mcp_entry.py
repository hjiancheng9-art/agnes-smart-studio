"""CRUX MCP Server entry point — launched by ZCode as a stdio MCP server.

Usage:
    python core/mcp_servers/crux_mcp_entry.py

ZCode spawns this as an MCP stdio server (JSON-RPC over stdin/stdout).
CRUX tools are exposed to ZCode via this server.
"""

import os
import sys

# Ensure the project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.mcp_server import run_mcp_server

if __name__ == "__main__":
    run_mcp_server()
