"""Contract tests for core.mcp_server.MCPServer.

验证 MCP server 的 JSON-RPC 2.0 契约，与 core/mcp_client.py 对称：
- protocolVersion = "2024-11-05"
- newline-delimited UTF-8 文本分帧
- 工具 shape 是 MCP 原生（非 OpenAI wrapper）
- tools/call 走 ChatSession._dispatch_tool_impl，副作用正确转 MCP content
- 高风险工具 → isError；未知工具 → 结构化错误（不抛异常）
- notification 不回响应

所有测试用伪造的 session/registry，不打真实 API，不依赖 AgnesClient。
"""
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.mcp_server import (
    MCPServer,
    MCP_PROTOCOL_VERSION,
    ERR_METHOD_NOT_FOUND,
    ERR_INVALID_PARAMS,
    ERR_PARSE_ERROR,
    ERR_INVALID_REQUEST,
)


# ── Fixtures ────────────────────────────────────────────────

def make_registry(defs=None):
    """构造一个 mock registry，definitions 返回给定（或默认）OpenAI tool defs。"""
    reg = MagicMock()
    if defs is None:
        defs = [
            {  # BUILTIN 生成工具（无 executor，由 _dispatch_tool_impl 内联处理）
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "description": "生成图片",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "描述"},
                            "image_url": {"type": "string", "description": "参考图"},
                        },
                        "required": ["prompt"],
                    },
                },
            },
            {  # registry 工具（有 executor）
                "type": "function",
                "function": {
                    "name": "web_fetch",
                    "description": "抓取网页",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
        ]
    reg.definitions = defs
    return reg


def make_server(dispatch_impl=None, defs=None):
    """构造一个 MCPServer，session._dispatch_tool_impl 被 mock。

    注意：__init__ 会 reconfigure stdin/stdout，在重定向环境里可能抛，
    所以这里跳过 __init__ 直接设属性。
    """
    session = MagicMock()
    if dispatch_impl is not None:
        session._dispatch_tool_impl = dispatch_impl
    else:
        session._dispatch_tool_impl = MagicMock(return_value=("done", []))
    server = MCPServer.__new__(MCPServer)
    server._session = session
    server._registry = make_registry(defs)
    server._tools_cache = None
    return server


# ── initialize ──────────────────────────────────────────────

class TestInitialize:
    def test_returns_protocol_version(self):
        s = make_server()
        result = s._initialize({})
        assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert result["protocolVersion"] == "2024-11-05"

    def test_returns_server_info(self):
        s = make_server()
        result = s._initialize({})
        assert result["serverInfo"]["name"] == "agnes-smart-studio"
        assert "version" in result["serverInfo"]

    def test_declares_capabilities(self):
        s = make_server()
        result = s._initialize({})
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]

    def test_initialize_via_handle_full_envelope(self):
        """initialize 经 _handle 路由，返回合法 JSON-RPC 响应。"""
        s = make_server()
        resp = s._handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}},
        })
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION


# ── tools/list + schema 转换 ────────────────────────────────

class TestToolsList:
    def test_returns_mcp_shape(self):
        s = make_server()
        result = s._tools_list({})
        tools = result["tools"]
        assert len(tools) == 2
        for t in tools:
            assert set(t.keys()) == {"name", "description", "inputSchema"}
            assert t["inputSchema"]["type"] == "object"
            assert "properties" in t["inputSchema"]
            assert "required" in t["inputSchema"]

    def test_no_openai_wrapper(self):
        """MCP tool 不应带 {'type':'function','function':{...}} 外壳。"""
        s = make_server()
        tools = s._tools_list({})["tools"]
        for t in tools:
            assert "function" not in t
            assert "type" not in t or t.get("type") != "function"

    def test_openai_to_mcp_conversion_basic(self):
        defn = {
            "type": "function",
            "function": {
                "name": "foo", "description": "bar",
                "parameters": {"type": "object",
                               "properties": {"x": {"type": "integer"}},
                               "required": ["x"]},
            },
        }
        out = MCPServer._openai_to_mcp_tool(defn)
        assert out == {"name": "foo", "description": "bar",
                       "inputSchema": {"type": "object",
                                       "properties": {"x": {"type": "integer"}},
                                       "required": ["x"]}}

    def test_openai_to_mcp_missing_properties_defaults(self):
        """parameters 缺 properties/required 时补默认。"""
        defn = {"type": "function", "function": {
            "name": "x", "description": "y", "parameters": {"type": "object"}}}
        out = MCPServer._openai_to_mcp_tool(defn)
        assert out["inputSchema"]["properties"] == {}
        assert out["inputSchema"]["required"] == []

    def test_openai_to_mcp_non_object_params_normalized(self):
        """parameters 不是 object 时归一化。"""
        defn = {"type": "function", "function": {
            "name": "x", "description": "y", "parameters": {"type": "string"}}}
        out = MCPServer._openai_to_mcp_tool(defn)
        assert out["inputSchema"]["type"] == "object"

    def test_openai_to_mcp_invalid_returns_none(self):
        assert MCPServer._openai_to_mcp_tool({}) is None
        assert MCPServer._openai_to_mcp_tool({"function": {}}) is None
        assert MCPServer._openai_to_mcp_tool("not a dict") is None

    def test_tools_cached(self):
        """_all_tools 缓存，二次调用不重算 registry。"""
        s = make_server()
        first = s._all_tools()
        # 清空 registry.definitions，缓存应仍返回原结果
        s._registry.definitions = []
        second = s._all_tools()
        assert first is second  # 同一对象引用


# ── tools/call 路由 ──────────────────────────────────────────

class TestToolsCall:
    def test_routes_to_dispatch_with_serialized_args(self):
        """_dispatch_tool_impl 收到正确的 args_json 字符串。"""
        captured = {}

        def fake_dispatch(name, args_json):
            captured["name"] = name
            captured["args_json"] = args_json
            return ("ok", [])

        s = make_server(dispatch_impl=fake_dispatch)
        s._tools_call({"name": "generate_image", "arguments": {"prompt": "cat"}})
        assert captured["name"] == "generate_image"
        assert json.loads(captured["args_json"]) == {"prompt": "cat"}

    def test_text_result_becomes_text_content(self):
        s = make_server(dispatch_impl=lambda n, a: ("hello world", []))
        result = s._tools_call({"name": "generate_image", "arguments": {}})
        assert result["isError"] is False
        assert result["content"][0] == {"type": "text", "text": "hello world"}

    def test_image_side_effect_becomes_image_content(self):
        """('image', dict) 副作用 → MCP image content + 路径文本。"""
        # 用真实临时文件让 _image_payload_to_content 能读
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # 假 PNG header
            tmp_path = f.name

        try:
            payload = {"local_path": tmp_path, "url": "http://x/y.png",
                       "model": "agnes-image-2.1-flash", "prompt": "cat", "size": "1024x768"}
            s = make_server(dispatch_impl=lambda n, a: ("图片已生成", [("image", payload)]))
            result = s._tools_call({"name": "generate_image", "arguments": {}})
            types = [c["type"] for c in result["content"]]
            assert "image" in types
            assert "text" in types
            img = next(c for c in result["content"] if c["type"] == "image")
            assert img["mimeType"] == "image/png"
            assert len(img["data"]) > 0  # base64 非空
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_video_side_effect_becomes_text(self):
        """('video', dict) 副作用 → 文本（视频不内联 base64）。"""
        payload = {"local_path": "/x/vid.mp4", "url": "http://x/vid.mp4",
                   "task_id": "t1", "video_id": "v1", "model": "agnes-video-v2.0"}
        # registry 需含 generate_video，否则被未知工具拦截
        defs = [{"type": "function", "function": {
            "name": "generate_video", "description": "d",
            "parameters": {"type": "object", "properties": {}, "required": []}}}]
        s = make_server(dispatch_impl=lambda n, a: ("视频已生成", [("video", payload)]), defs=defs)
        result = s._tools_call({"name": "generate_video", "arguments": {}})
        # 没有视频 content，只有 text
        assert all(c["type"] == "text" for c in result["content"])
        merged = " ".join(c["text"] for c in result["content"])
        assert "v1" in merged  # video_id 出现在文本里

    def test_video_timeout_payload_marked(self):
        """视频超时状态在文本里标记 timeout + progress。"""
        payload = {"status": "timeout", "progress": 0.45, "video_id": "v9"}
        defs = [{"type": "function", "function": {
            "name": "generate_video", "description": "d",
            "parameters": {"type": "object", "properties": {}, "required": []}}}]
        s = make_server(dispatch_impl=lambda n, a: ("", [("video", payload)]), defs=defs)
        result = s._tools_call({"name": "generate_video", "arguments": {}})
        text = result["content"][-1]["text"]
        assert "timeout" in text.lower()
        assert "v9" in text

    def test_info_side_effect_appended_as_text(self):
        s = make_server(dispatch_impl=lambda n, a: ("done", [("info", "正在生成...")]))
        result = s._tools_call({"name": "generate_image", "arguments": {}})
        texts = [c["text"] for c in result["content"] if c["type"] == "text"]
        assert any("[info] 正在生成..." in t for t in texts)

    def test_high_risk_confirm_returns_error(self):
        """高风险工具返回 ('confirm', dict) → isError:true。"""
        defs = [{"type": "function", "function": {
            "name": "git_push", "description": "d",
            "parameters": {"type": "object", "properties": {}, "required": []}}}]
        s = make_server(dispatch_impl=lambda n, a: ("", [("confirm", {"tool": "git_push"})]),
                        defs=defs)
        result = s._tools_call({"name": "git_push", "arguments": {}})
        assert result["isError"] is True
        assert "high-risk" in result["content"][0]["text"].lower() or \
               "confirmation" in result["content"][0]["text"].lower()

    def test_unknown_tool_returns_structured_error(self):
        """未知工具 → isError:true 文本，不抛异常。"""
        s = make_server()
        result = s._tools_call({"name": "nonexistent_tool", "arguments": {}})
        assert result["isError"] is True
        assert "nonexistent_tool" in result["content"][0]["text"]

    def test_empty_output_gets_placeholder(self):
        """工具返回空文本 + 空副作用 → 占位文本。"""
        s = make_server(dispatch_impl=lambda n, a: ("", []))
        result = s._tools_call({"name": "generate_image", "arguments": {}})
        assert result["content"][0]["text"] == "(tool produced no output)"

    def test_missing_name_raises_jsonrpc_error(self):
        s = make_server()
        with pytest.raises(Exception) as exc:
            s._tools_call({})
        # _JSONRPCError 携带 ERR_INVALID_PARAMS code
        assert exc.value.code == ERR_INVALID_PARAMS

    def test_none_arguments_treated_as_empty(self):
        """arguments 缺省时当作 {}。"""
        captured = {}

        def fake_dispatch(n, a):
            captured["args_json"] = a
            return ("ok", [])

        s = make_server(dispatch_impl=fake_dispatch)
        s._tools_call({"name": "generate_image"})  # 无 arguments key
        assert json.loads(captured["args_json"]) == {}


# ── 递归防护：MCP bridge tools 不可入向暴露 ───────────────────

class TestRecursionGuard:
    """验证 MCP bridge tools (mcp_*) 不被 Server 暴露，阻断 A→B→A 死循环。

    bridge tools 是 Agnes 作为 Client 调外部 server 的"出向"能力，
    若作为 Server 入向暴露回去，调用方可能反向调它们造成递归。
    """

    def test_bridge_tools_filtered_from_list(self):
        """tools/list 不返回任何 mcp_* 工具。"""
        defs = [
            {"type": "function", "function": {
                "name": "generate_image", "description": "d",
                "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {
                "name": "mcp_list_servers", "description": "d",
                "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {
                "name": "mcp_call_tool", "description": "d",
                "parameters": {"type": "object", "properties": {}, "required": []}}},
        ]
        s = make_server(defs=defs)
        tools = s._tools_list({})["tools"]
        names = {t["name"] for t in tools}
        assert "generate_image" in names
        assert "mcp_list_servers" not in names
        assert "mcp_call_tool" not in names

    def test_bridge_tool_call_refused_even_if_listed(self):
        """即使 listing 漏过，tools/call 也显式拒绝 mcp_* （第二道防线）。"""
        dispatched = []

        def fake_dispatch(n, a):
            dispatched.append(n)  # 不应被调用
            return ("should not reach", [])

        s = make_server(dispatch_impl=fake_dispatch)
        result = s._tools_call({"name": "mcp_call_tool", "arguments": {}})
        assert result["isError"] is True
        assert "bridge tool" in result["content"][0]["text"].lower()
        assert "recursion" in result["content"][0]["text"].lower()
        assert dispatched == []  # 根本没走到 _dispatch_tool_impl

    def test_is_bridge_tool_prefix_match(self):
        """_is_bridge_tool 按 mcp_ 前缀匹配，覆盖未来新增 bridge tools。"""
        assert MCPServer._is_bridge_tool("mcp_list_servers") is True
        assert MCPServer._is_bridge_tool("mcp_call_tool") is True
        assert MCPServer._is_bridge_tool("mcp_future_tool") is True  # 新增自动防护
        assert MCPServer._is_bridge_tool("generate_image") is False
        assert MCPServer._is_bridge_tool("web_fetch") is False
        assert MCPServer._is_bridge_tool("") is False
        assert MCPServer._is_bridge_tool("mcp") is False  # 必须有下划线后缀


# ── JSON-RPC envelope / framing / notifications ─────────────

class TestJsonRpcEnvelope:
    def test_unknown_method_returns_32601(self):
        s = make_server()
        resp = s._handle({"jsonrpc": "2.0", "id": 5, "method": "foobar"})
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND
        assert resp["id"] == 5

    def test_invalid_jsonrpc_field(self):
        s = make_server()
        resp = s._handle({"jsonrpc": "1.0", "id": 1, "method": "initialize"})
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    def test_missing_method(self):
        s = make_server()
        resp = s._handle({"jsonrpc": "2.0", "id": 1})
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    def test_non_object_message(self):
        s = make_server()
        resp = s._handle("not an object")
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    def test_notification_returns_none(self):
        """通知（无 id）不回响应。"""
        s = make_server()
        resp = s._handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp is None

    def test_unknown_notification_returns_none(self):
        """未知通知静默忽略（不报 method not found）。"""
        s = make_server()
        resp = s._handle({"jsonrpc": "2.0", "method": "notifications/foobar"})
        assert resp is None

    def test_write_produces_single_line_ending_newline(self, capsys):
        s = make_server()
        s._write({"jsonrpc": "2.0", "id": 1, "result": {}})
        out = capsys.readouterr().out
        assert out.endswith("\n")
        assert out.count("\n") == 1
        # 内容是合法 JSON
        assert json.loads(out.strip())["jsonrpc"] == "2.0"

    def test_write_utf8_not_ascii_escaped(self, capsys):
        """中文等非 ASCII 字符不转义（ensure_ascii=False）。"""
        s = make_server()
        s._write({"jsonrpc": "2.0", "id": 1, "result": {"msg": "你好"}})
        out = capsys.readouterr().out
        assert "你好" in out

    def test_handler_exception_becomes_internal_error(self):
        """handler 抛异常 → ERR_INTERNAL，不崩 server。"""
        s = make_server()
        # 让 _tools_call 抛非 _JSONRPCError 的异常
        s._session._dispatch_tool_impl = MagicMock(side_effect=RuntimeError("boom"))
        resp = s._handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                          "params": {"name": "generate_image", "arguments": {}}})
        # RuntimeError 在 _tools_call 之外被 _handle 的 try/except 兜住
        assert resp["error"]["code"] == -32603


# ── run() 主循环 smoke ─────────────────────────────────────

class TestRunLoop:
    def test_run_processes_pipe_and_exits_on_eof(self, monkeypatch):
        """run() 读 stdin 多行 → 逐行响应 → EOF 退出。"""
        s = make_server()
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            "",  # 空行跳过
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),  # 通知不回
        ]
        monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines)))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", out_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())  # 吞日志

        s.run()

        responses = [json.loads(l) for l in out_buf.getvalue().splitlines() if l.strip()]
        # 2 个响应（initialize + tools/list），通知不回，空行跳过
        assert len(responses) == 2
        assert responses[0]["id"] == 1
        assert responses[0]["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
        assert responses[1]["id"] == 2
        assert "tools" in responses[1]["result"]

    def test_run_recovers_from_parse_error(self, monkeypatch):
        """坏 JSON → 回 parse error，继续处理后续行。"""
        s = make_server()
        lines = [
            "this is not json",
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        ]
        monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines)))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", out_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())

        s.run()

        responses = [json.loads(l) for l in out_buf.getvalue().splitlines() if l.strip()]
        assert len(responses) == 2
        assert responses[0]["error"]["code"] == ERR_PARSE_ERROR
        assert responses[1]["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION


# ── resources（轻量，只验契约形态）──────────────────────────

class TestResources:
    def test_resources_list_returns_dict_with_resources_key(self):
        s = make_server()
        result = s._resources_list({})
        assert isinstance(result, dict)
        assert "resources" in result
        assert isinstance(result["resources"], list)

    def test_resources_read_missing_uri_raises(self):
        s = make_server()
        with pytest.raises(Exception) as exc:
            s._resources_read({})
        assert exc.value.code == ERR_INVALID_PARAMS
