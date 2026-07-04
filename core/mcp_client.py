"""MCP (Model Context Protocol) Client for crux-smart-studio

Connects to external MCP servers via stdio transport, discovers their tools
and resources, and provides an executor map for the ToolRegistry system.

四象融合架构：
    - ToolRegistry.load(mcp=True) 自动注入 MCP_TOOL_DEFS + MCP_EXECUTOR_MAP
    - core/chat.py 所有 reload 路径均传 mcp=True（agent_mode / _reload_tools / skill）
    - /mcp 斜杠命令 (ui/mixins/diag.py:_chat_mcp) 提供 REPL 管理界面
    - crux mcp-serve 启动时同样 load(mcp=True)，双向可达

Architecture:
    MCPServerConfig  - Dataclass for server configuration
    MCPClient        - Manages server lifecycle, JSON-RPC 2.0 communication
    MCP_TOOL_DEFS    - OpenAI function-format tool definitions
    MCP_EXECUTOR_MAP - Executor functions returning JSON strings

Communication:
    Uses JSON-RPC 2.0 over stdin/stdout (stdio transport).
    Each request is a JSON object followed by a newline.
    Responses are read line-by-line from server stdout.
"""

import contextlib
import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field

from core.config import OUTPUT_DIR

__all__ = [
    "MCPClient",
    "MCPServerConfig",
    "MCP_EXECUTOR_MAP",
    "MCP_TOOL_DEFS",
    "get_mcp_client",
]


# ── Server Configuration ──────────────────────────────────


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


# ── MCP Client ────────────────────────────────────────────


class MCPClient:
    """Manages MCP server connections, tool/resource discovery, and invocation.

    Uses JSON-RPC 2.0 protocol over stdin/stdout to communicate with server
    processes started via subprocess.Popen.
    """

    CONFIG_PATH = OUTPUT_DIR / "mcp_servers.json"
    REQUEST_TIMEOUT = 30  # seconds

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._next_id_lock = threading.Lock()
        self._next_id = 1
        self._load_config()
        import atexit

        atexit.register(self._cleanup_all)

    def _cleanup_all(self):
        """Terminate all child processes on exit/crash."""
        for name in list(self._processes.keys()):
            with contextlib.suppress(subprocess.SubprocessError, OSError):
                self._terminate_process(name, self._processes[name])

    # ── Server Registry ───────────────────────────────────

    def add_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> dict:
        """Register a new MCP server configuration.

        Args:
            name: Unique server identifier.
            command: Command to start the server (e.g. "python", "node", "npx").
            args: Command arguments.
            env: Extra environment variables for the server process.

        Returns:
            Dict with the added server config and status.
        """
        with self._lock:
            if name in self._servers:
                return {"error": f"Server '{name}' already exists"}

            cfg = MCPServerConfig(
                name=name,
                command=command,
                args=args or [],
                env=env or {},
            )
            self._servers[name] = cfg
            self._save_config()
            return {"status": "ok", "server": asdict(cfg)}

    def list_servers(self) -> list[dict]:
        """Return all registered server configurations with connection status.

        Returns:
            List of server info dicts with name, command, enabled, and connected status.
        """
        with self._lock:
            return [
                {
                    "name": cfg.name,
                    "command": cfg.command,
                    "args": cfg.args,
                    "enabled": cfg.enabled,
                    "connected": cfg.name in self._processes,
                }
                for cfg in self._servers.values()
            ]

    def remove_server(self, name: str) -> bool:
        """Remove a server configuration. Disconnects if running.

        Returns:
            True if the server was found and removed.
        """
        with self._lock:
            if name not in self._servers:
                return False
            # Disconnect if currently connected
            if name in self._processes:
                self.disconnect(name)
            del self._servers[name]
            self._save_config()
            return True

    def health_check(self, name: str) -> dict:
        """Check if an MCP connection is alive. Reconnect if dead."""
        proc = self._processes.get(name)
        if proc is None:
            result = self.connect(name)
            return {"name": name, "status": result.get("status", "reconnected"), "action": "connected"}
        
        poll = proc.poll()
        if poll is not None:
            # Process died, reconnect
            self._processes.pop(name, None)
            result = self.connect(name)
            return {"name": name, "status": result.get("status", "reconnected"), "action": "reconnected"}
        
        return {"name": name, "status": "alive", "action": "none"}
    
    def health_check_all(self) -> list[dict]:
        """Health check all registered servers."""
        results = []
        for name in list(self._servers.keys()):
            results.append(self.health_check(name))
        return results

    # ── Connection Lifecycle ───────────────────────────────

    def connect(self, name: str) -> dict:
        """Start an MCP server process and send the initialize request.

        Args:
            name: Server identifier from the registry.

        Returns:
            Dict with server capabilities on success, or error dict on failure.
        """
        with self._lock:
            if name not in self._servers:
                return {"error": f"Server '{name}' not configured"}
            cfg = self._servers[name]
            if not cfg.enabled:
                return {"error": f"Server '{name}' is disabled"}

        if name in self._processes:
            return {"error": f"Server '{name}' already connected"}

        # Build environment: current env + server-specific overrides
        proc_env = {**os.environ, **cfg.env}

        try:
            proc = subprocess.Popen(
                [cfg.command, *cfg.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=proc_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
        except (subprocess.SubprocessError, OSError) as e:
            return {"error": f"Failed to start server '{name}': {e}"}

        # Check if process started successfully
        if proc.returncode is not None:
            stderr_output = proc.stderr.read() if proc.stderr else ""
            return {"error": f"Server '{name}' exited immediately: {stderr_output}"}

        with self._lock:
            self._processes[name] = proc

        # Send MCP initialize request
        init_result = self._send_request(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "crux-smart-studio", "version": "1.0.0"},
            },
        )

        if "error" in init_result:
            # Clean up on init failure
            self._terminate_process(name, proc)
            return {"error": f"Initialize failed for '{name}': {init_result['error']}"}

        # Send initialized notification (no response expected)
        self._send_notification(proc, "notifications/initialized")

        return {"status": "connected", "name": name, "capabilities": init_result.get("result", {})}

    def disconnect(self, name: str) -> dict:
        """Stop a connected MCP server process.

        Returns:
            Dict with disconnect status.
        """
        with self._lock:
            proc = self._processes.pop(name, None)

        if proc is None:
            return {"error": f"Server '{name}' not connected"}

        self._terminate_process(name, proc)
        return {"status": "disconnected", "name": name}

    # ── Tool Discovery & Invocation ───────────────────────

    def list_tools(self, name: str) -> list[dict]:
        """Call tools/list on a connected server. Auto-connect if needed."""
        proc = self._processes.get(name)
        if proc is None:
            result = self.connect(name)
            if "error" in result:
                return [{"error": result["error"]}]
            proc = self._processes.get(name)
            if proc is None:
                return [{"error": f"Server '{name}' not connected"}]

        result = self._send_request(proc, "tools/list")
        if "error" in result:
            return [{"error": str(result["error"])}]
        return result.get("result", {}).get("tools", [])

    def call_tool(self, name: str, tool_name: str, arguments: dict | None = None) -> dict:
        """Call tools/call on a connected server.

        Args:
            name: Server identifier.
            tool_name: Name of the tool to invoke.
            arguments: Tool input arguments as a dict.

        Returns:
            Dict with tool result or error.
        """
        proc = self._processes.get(name)
        if proc is None:
            result = self.connect(name)
            if "error" in result:
                return {"error": result["error"]}
            proc = self._processes.get(name)
            if proc is None:
                return {"error": f"Server '{name}' not connected"}

        params: dict[str, str | dict] = {"name": tool_name}
        if arguments is not None:
            params["arguments"] = arguments

        result = self._send_request(proc, "tools/call", params)
        if "error" in result:
            return {"error": str(result["error"])}
        return result.get("result", {})

    # ── Resource Discovery & Reading ───────────────────────

    def list_resources(self, name: str) -> list[dict]:
        """Call resources/list on a connected server.

        Returns:
            List of resource dicts, or error list on failure.
        """
        proc = self._processes.get(name)
        if proc is None:
            return [{"error": f"Server '{name}' not connected"}]

        result = self._send_request(proc, "resources/list")
        if "error" in result:
            return [{"error": str(result["error"])}]
        return result.get("result", {}).get("resources", [])

    def read_resource(self, name: str, uri: str) -> dict:
        """Call resources/read on a connected server.

        Args:
            name: Server identifier.
            uri: Resource URI to read.

        Returns:
            Dict with resource contents or error.
        """
        proc = self._processes.get(name)
        if proc is None:
            return {"error": f"Server '{name}' not connected"}

        result = self._send_request(proc, "resources/read", {"uri": uri})
        if "error" in result:
            return {"error": str(result["error"])}
        return result.get("result", {})

    # ── JSON-RPC 2.0 Communication ─────────────────────────

    def _send_request(
        self,
        proc: subprocess.Popen,
        method: str,
        params: dict | None = None,
    ) -> dict:
        """Send a JSON-RPC 2.0 request to a server process and wait for response.

        Writes a JSON message + newline to the process stdin, then reads a
        line from stdout and parses it as the JSON-RPC response.

        Args:
            proc: The running server process.
            method: RPC method name.
            params: Optional params dict.

        Returns:
            Parsed JSON-RPC response dict.
        """
        with self._next_id_lock:
            request_id = self._next_id
            self._next_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        request_line = json.dumps(request, ensure_ascii=False) + "\n"

        try:
            # Check if process is still alive
            if proc.returncode is not None:
                return {
                    "error": {
                        "code": -32000,
                        "message": f"Server process exited with code {proc.returncode}",
                    }
                }

            stdin = proc.stdin
            if stdin is None:
                return {"error": {"code": -32000, "message": "Write failed: stdin is closed"}}
            stdin.write(request_line)
            stdin.flush()
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            return {"error": {"code": -32000, "message": f"Write failed: {e}"}}

        # Read response with timeout
        try:
            # Use a thread to read with timeout
            stdout = proc.stdout
            if stdout is None:
                return {"error": {"code": -32000, "message": "Read failed: stdout is closed"}}
            response_line = None

            def _read():
                try:
                    response_line_holder[0] = stdout.readline()
                except Exception as e:
                    read_error_holder[0] = e

            response_line_holder: list[str | None] = [None]
            read_error_holder: list[Exception | None] = [None]

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout=self.REQUEST_TIMEOUT)

            if reader.is_alive():
                # Timeout — process may be stuck
                return {
                    "error": {
                        "code": -32001,
                        "message": f"Request timed out after {self.REQUEST_TIMEOUT}s",
                    }
                }

            if read_error_holder[0] is not None:
                return {
                    "error": {
                        "code": -32000,
                        "message": f"Read failed: {read_error_holder[0]}",
                    }
                }

            response_line = response_line_holder[0]
            if response_line is None or response_line == "":
                # Process may have exited
                if proc.returncode is not None:
                    stderr_output = ""
                    with contextlib.suppress(OSError, UnicodeDecodeError):
                        stderr = proc.stderr
                        stderr_output = stderr.read() if stderr is not None else ""
                    return {
                        "error": {
                            "code": -32000,
                            "message": f"Server exited (code {proc.returncode}): {stderr_output[:500]}",
                        }
                    }
                return {
                    "error": {
                        "code": -32000,
                        "message": "Empty response from server",
                    }
                }

            response = json.loads(response_line)

            # Validate JSON-RPC structure
            if response.get("jsonrpc") != "2.0":
                return {
                    "error": {
                        "code": -32600,
                        "message": "Invalid JSON-RPC response: missing or wrong jsonrpc version",
                    }
                }

            # Check if response ID matches request ID
            # Some MCP servers (e.g. Codex) return id: null — accept as valid
            if response.get("id") is not None and response.get("id") != request_id:
                return {
                    "error": {
                        "code": -32600,
                        "message": f"Response ID mismatch: expected {request_id}, got {response.get('id')}",
                    }
                }

            return response

        except json.JSONDecodeError as e:
            return {"error": {"code": -32700, "message": f"JSON parse error: {e}"}}
        except (TypeError, KeyError) as e:
            return {"error": {"code": -32000, "message": f"Unexpected error: {e}"}}

    def _send_notification(self, proc: subprocess.Popen, method: str) -> None:
        """Send a JSON-RPC 2.0 notification (no ID, no response expected)."""
        notification = {"jsonrpc": "2.0", "method": method}
        stdin = proc.stdin
        if stdin is None:
            return
        try:
            stdin.write(json.dumps(notification, ensure_ascii=False) + "\n")
            stdin.flush()
        except (subprocess.SubprocessError, OSError):
            pass  # Notifications are fire-and-forget

    # ── Process Management ─────────────────────────────────

    def _terminate_process(self, name: str, proc: subprocess.Popen) -> None:
        """Gracefully terminate a server process."""
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except (subprocess.SubprocessError, OSError):
                pass
        except (subprocess.SubprocessError, OSError):
            pass

    # ── Config Persistence ─────────────────────────────────

    def _save_config(self) -> None:
        """Persist server configs to JSON file."""
        data = {"servers": [asdict(cfg) for cfg in self._servers.values()]}
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_config(self) -> None:
        """Load server configs from JSON file."""
        if not self.CONFIG_PATH.exists():
            return
        try:
            with open(self.CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError):
            return

        for srv in data.get("servers", []):
            name = srv.get("name", "")
            if not name:
                continue
            self._servers[name] = MCPServerConfig(
                name=name,
                command=srv.get("command", ""),
                args=srv.get("args", []),
                env=srv.get("env", {}),
                enabled=srv.get("enabled", True),
            )


# ── Global Singleton ──────────────────────────────────────

_mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Return the global MCPClient singleton."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


def reset_mcp_client() -> None:
    """Terminate all MCP server processes and drop the global singleton.

    Used for test isolation and hot reload. A subsequent get_mcp_client()
    call will spin up a fresh MCPClient.
    """
    global _mcp_client
    if _mcp_client is not None:
        with contextlib.suppress(Exception):
            _mcp_client._cleanup_all()
        _mcp_client = None


# ── Tool Definitions for ToolRegistry ─────────────────────

MCP_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "mcp_list_servers",
            "description": "List all configured MCP servers and their status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_list_tools",
            "description": "List tools available on a connected MCP server. Connect to the server first if not already connected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {
                        "type": "string",
                        "description": "Name of the MCP server to query",
                    },
                },
                "required": ["server_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_call_tool",
            "description": "Invoke a tool on a connected MCP server. The arguments parameter should be a JSON object string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {
                        "type": "string",
                        "description": "Name of the MCP server",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Name of the tool to invoke",
                    },
                    "arguments": {
                        "type": "string",
                        "description": "JSON object string with tool input arguments",
                    },
                },
                "required": ["server_name", "tool_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_read_resource",
            "description": "Read a resource from a connected MCP server by URI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {
                        "type": "string",
                        "description": "Name of the MCP server",
                    },
                    "uri": {
                        "type": "string",
                        "description": "URI of the resource to read",
                    },
                },
                "required": ["server_name", "uri"],
            },
        },
    },
]


# ── Executor Functions ────────────────────────────────────


def _exec_mcp_list_servers(**kwargs) -> str:
    """Executor: list all configured MCP servers."""
    client = get_mcp_client()
    return json.dumps(client.list_servers(), ensure_ascii=False)


def _exec_mcp_list_tools(**kwargs) -> str:
    """Executor: list tools on an MCP server."""
    client = get_mcp_client()
    name = kwargs.get("server_name", "")
    # Auto-connect if not already connected
    if name not in client._processes:
        connect_result = client.connect(name)
        if "error" in connect_result:
            return json.dumps(connect_result, ensure_ascii=False)
    tools = client.list_tools(name)
    return json.dumps(tools, ensure_ascii=False)


def _exec_mcp_call_tool(**kwargs) -> str:
    """Executor: invoke a tool on an MCP server."""
    client = get_mcp_client()
    name = kwargs.get("server_name", "")
    tool_name = kwargs.get("tool_name", "")
    arguments_str = kwargs.get("arguments", "")
    arguments = None
    if arguments_str:
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON in arguments parameter"}, ensure_ascii=False)
    # Auto-connect if not already connected
    if name not in client._processes:
        connect_result = client.connect(name)
        if "error" in connect_result:
            return json.dumps(connect_result, ensure_ascii=False)
    result = client.call_tool(name, tool_name, arguments)
    return json.dumps(result, ensure_ascii=False)


def _exec_mcp_read_resource(**kwargs) -> str:
    """Executor: read a resource from an MCP server."""
    client = get_mcp_client()
    name = kwargs.get("server_name", "")
    uri = kwargs.get("uri", "")
    # Auto-connect if not already connected
    if name not in client._processes:
        connect_result = client.connect(name)
        if "error" in connect_result:
            return json.dumps(connect_result, ensure_ascii=False)
    result = client.read_resource(name, uri)
    return json.dumps(result, ensure_ascii=False)


MCP_EXECUTOR_MAP = {
    "mcp_list_servers": _exec_mcp_list_servers,
    "mcp_list_tools": _exec_mcp_list_tools,
    "mcp_call_tool": _exec_mcp_call_tool,
    "mcp_read_resource": _exec_mcp_read_resource,
}
