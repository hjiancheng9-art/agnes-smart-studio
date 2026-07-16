"""Contract tests for MCP and LSP interfaces — protocol-level testing."""

import pytest

from core.interfaces.errors import MCPError
from core.interfaces.lsp import LSPClient, LSPCompletion, LSPDiagnostic
from core.interfaces.mcp import MCPClient, MCPResource, MCPResult, MCPToolDef

# ═══════════════════════════════════════════════════
#  Fake MCP Client
# ═══════════════════════════════════════════════════


class FakeMCPClient(MCPClient):
    """Fake MCP client for unit testing — no real server needed."""

    def __init__(self):
        self._connected = False
        self._tools: dict[str, MCPToolDef] = {}
        self._resources: dict[str, MCPResource] = {}

    def add_tool(self, name: str, description: str = "", input_schema: dict | None = None):
        self._tools[name] = MCPToolDef(
            name=name,
            description=description,
            input_schema=input_schema or {},
        )

    def add_resource(self, uri: str, name: str, description: str = ""):
        self._resources[uri] = MCPResource(uri=uri, name=name, description=description)

    async def connect(self):
        self._connected = True

    async def list_tools(self):
        return list(self._tools.values())

    async def call_tool(self, tool_name: str, arguments: dict | None = None):
        if tool_name not in self._tools:
            return MCPResult(success=False, error=MCPError("TOOL_NOT_FOUND", f"No tool: {tool_name}"))
        return MCPResult(success=True, data={"args": arguments or {}})

    async def read_resource(self, uri: str):
        if uri not in self._resources:
            return MCPResult(success=False, error=MCPError("RESOURCE_NOT_FOUND", f"No resource: {uri}"))
        return MCPResult(success=True, data={"uri": uri, "content": "mock content"})

    async def disconnect(self):
        self._connected = False

    def is_connected(self):
        return self._connected


class TestFakeMCPClient:
    """FakeMCPClient satisfies the MCPClient contract."""

    @pytest.fixture
    def client(self):
        c = FakeMCPClient()
        c.add_tool("search", "Search code", {"query": "string"})
        c.add_tool("execute", "Run code", {"code": "string"})
        c.add_resource("docs://guide", "Guide", "User guide")
        return c

    @pytest.mark.asyncio
    async def test_connect_and_list_tools(self, client):
        await client.connect()
        assert client.is_connected()
        tools = await client.list_tools()
        assert len(tools) == 2
        assert tools[0].name == "search"

    @pytest.mark.asyncio
    async def test_call_known_tool(self, client):
        result = await client.call_tool("search", {"query": "test"})
        assert result.success
        assert result.data["args"]["query"] == "test"

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, client):
        result = await client.call_tool("nonexistent")
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_read_resource(self, client):
        result = await client.read_resource("docs://guide")
        assert result.success

    @pytest.mark.asyncio
    async def test_read_missing_resource(self, client):
        result = await client.read_resource("docs://missing")
        assert not result.success

    @pytest.mark.asyncio
    async def test_disconnect(self, client):
        await client.connect()
        await client.disconnect()
        assert not client.is_connected()


# ═══════════════════════════════════════════════════
#  Fake LSP Client
# ═══════════════════════════════════════════════════


class FakeLSPClient(LSPClient):
    """Fake LSP client for unit testing — no real language server needed."""

    def __init__(self):
        self._alive = False
        self._diagnostics: dict[str, list[LSPDiagnostic]] = {}

    def set_diagnostics(self, file_path: str, diagnostics: list[LSPDiagnostic]):
        self._diagnostics[file_path] = diagnostics

    async def open(self, file_path: str):
        self._alive = True

    async def goto_definition(self, file_path: str, line: int, character: int):
        return []

    async def hover(self, file_path: str, line: int, character: int):
        return None

    async def references(self, file_path: str, line: int, character: int):
        return []

    async def diagnostics(self, file_path: str):
        return self._diagnostics.get(file_path, [])

    async def completion(self, file_path: str, line: int, character: int):
        return [LSPCompletion(label="test_func", detail="def test_func()", kind=2)]

    async def rename(self, file_path: str, line: int, character: int, new_name: str):
        return {"changes": {file_path: [{"range": {}, "newText": new_name}]}}

    async def shutdown(self):
        self._alive = False

    def is_alive(self):
        return self._alive


class TestFakeLSPClient:
    """FakeLSPClient satisfies the LSPClient contract."""

    @pytest.fixture
    def lsp(self):
        return FakeLSPClient()

    @pytest.mark.asyncio
    async def test_open_and_alive(self, lsp):
        assert not lsp.is_alive()
        await lsp.open("/tmp/test.py")
        assert lsp.is_alive()

    @pytest.mark.asyncio
    async def test_diagnostics_empty(self, lsp):
        await lsp.open("/tmp/test.py")
        diags = await lsp.diagnostics("/tmp/test.py")
        assert diags == []

    @pytest.mark.asyncio
    async def test_diagnostics_with_data(self, lsp):
        diag = LSPDiagnostic(
            range=None,
            message="unused import os",
            severity=2,
            code="F401",
        )
        lsp.set_diagnostics("/tmp/test.py", [diag])
        diags = await lsp.diagnostics("/tmp/test.py")
        assert len(diags) == 1
        assert diags[0].message == "unused import os"

    @pytest.mark.asyncio
    async def test_completion(self, lsp):
        await lsp.open("/tmp/test.py")
        items = await lsp.completion("/tmp/test.py", 0, 0)
        assert len(items) == 1
        assert items[0].label == "test_func"

    @pytest.mark.asyncio
    async def test_shutdown(self, lsp):
        await lsp.open("/tmp/test.py")
        await lsp.shutdown()
        assert not lsp.is_alive()

    @pytest.mark.asyncio
    async def test_goto_definition_returns_list(self, lsp):
        await lsp.open("/tmp/test.py")
        locs = await lsp.goto_definition("/tmp/test.py", 5, 10)
        assert isinstance(locs, list)
