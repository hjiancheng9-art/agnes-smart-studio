"""MCP (Model Context Protocol) Server for crux-smart-studio.

让 CRUX 作为与 codex / claude / codebuddy 对等的"第四象"被调用：
三象执行 `claude mcp add crux -- crux mcp-serve` 后，即可在自己的会话里
直接调用 CRUX 的生成能力（生图/生视频/创意流水线）以及 ToolRegistry 里的全量工具。

Architecture:
    MCPServer        - stdio JSON-RPC 2.0 主循环，路由 MCP 方法到 CRUX 能力
    run_mcp_server   - 入口，构造无头 ChatSession + ToolRegistry 并启动 server

Protocol (与 core/mcp_client.py 对称):
    - JSON-RPC 2.0 over stdin/stdout (stdio transport)
    - newline-delimited UTF-8 文本（非 LSP 的 Content-Length framing）
    - protocolVersion = "2024-11-05"
    - 同步一问一答，不主动发 notification（client 不跳过 notification）
    - 工具调用统一走 ChatSession._dispatch_tool_impl，覆盖：
        · BUILTIN 生成工具 (generate_image / generate_video / multi_agent)
        · registry 注册的工具 (pipeline / comfyui / notebook / audio / tools.json)
        · 高风险工具确认（MCP 模式拒绝，无人工确认回路）

认证：复用 core.config.SETTINGS（环境变量优先，回退 ~/.crux/auth.json），
与 crux_studio.py 现有逻辑一致，零额外代码。
"""

import base64
import contextlib
import json
import mimetypes
import os
import signal
import sys
from pathlib import Path
from typing import Any

__all__ = ["MCPServer", "run_mcp_server"]


# ── 协议常量（对齐 core/mcp_client.py:178, :180）──────────────
MCP_PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC 标准错误码
ERR_PARSE_ERROR = -32700  # JSON 解析失败
ERR_INVALID_REQUEST = -32600  # 不是合法的 Request 对象
ERR_METHOD_NOT_FOUND = -32601  # 方法不存在
ERR_INVALID_PARAMS = -32602  # 参数无效
ERR_INTERNAL = -32603  # 内部错误


def _server_info() -> dict:
    """serverInfo 字段（延迟读 version，避免 import 环）。"""
    try:
        from core.version import __version__
    except ImportError:
        __version__ = "unknown"
    return {"name": "crux-smart-studio", "version": __version__}


class MCPServer:
    """stdio JSON-RPC 2.0 MCP server，把 CRUX 能力暴露给三象。

    单实例处理一个 client 的请求流。主循环 readline → 解析 → 路由 → 单行响应。
    """

    def __init__(self, session: Any, registry: Any) -> None:
        # session: ChatSession（提供 _dispatch_tool_impl）
        # registry: ToolRegistry（提供 definitions / has / execute）
        self._session = session
        self._registry = registry
        # Windows 上 stdout 默认可能翻译换行，显式锁定为 \n + utf-8
        try:
            sys.stdout.reconfigure(newline="\n", encoding="utf-8", write_through=True)  # type: ignore[attr-defined]
            sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            # 某些 stdin/stdout 不是 TextIOWrapper（如重定向），静默降级
            pass
        self._tools_cache: list[dict] | None = None  # 懒构造，initialize 后稳定

    # ── 主循环 ────────────────────────────────────────────────

    def run(self) -> None:
        """stdio 主循环：逐行读请求 → 路由 → 写单行响应。EOF 即退出。"""
        self._log("crux mcp-serve ready (stdin=JSON-RPC, stdout=responses, stderr=log)")
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                # 解析失败必须回错误（id 无法得知，用 null）
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": ERR_PARSE_ERROR, "message": "Parse error"},
                    }
                )
                continue
            response = self._handle(msg)
            if response is not None:  # notification 返回 None，不回响应
                self._write(response)
        self._log("stdin EOF, exiting")

    def _handle(self, msg: Any) -> dict | None:
        """路由单条消息。Request → 返回响应 dict；Notification → 返回 None。"""
        if not isinstance(msg, dict):
            return self._error(None, ERR_INVALID_REQUEST, "Request must be a JSON object")

        if msg.get("jsonrpc") != "2.0":
            return self._error(msg.get("id"), ERR_INVALID_REQUEST, "Missing or invalid 'jsonrpc' field")

        method = msg.get("method")
        if not isinstance(method, str):
            return self._error(msg.get("id"), ERR_INVALID_REQUEST, "Missing 'method' field")

        # 通知（无 id）→ 不回响应
        is_notification = "id" not in msg
        req_id = msg.get("id")
        params = msg.get("params") or {}

        try:
            handler = self._METHODS.get(method)
            if handler is None:
                if is_notification:
                    return None  # 未知通知静默忽略
                return self._error(req_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")
            result = handler(self, params)
            if is_notification:
                return None
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except _JSONRPCError as e:
            if is_notification:
                return None
            return self._error(req_id, e.code, e.message)
        except (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError, AttributeError) as e:
            import traceback

            tb = traceback.format_exc()
            self._log(f"internal error handling {method}: {e!r}\n{tb}")
            if is_notification:
                return None
            return self._error(req_id, ERR_INTERNAL, f"Internal error: {type(e).__name__}: {e}")

    # ── MCP 方法 ──────────────────────────────────────────────

    def _initialize(self, params: dict) -> dict:
        """initialize — 回 protocolVersion + capabilities + serverInfo。

        client (core/mcp_client.py:174-182) 发 capabilities:{}，不消费 server
        capabilities，故这里声明什么都安全。
        """
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {},  # 第一版只读 output/ 产物
            },
            "serverInfo": _server_info(),
        }

    def _tools_list(self, params: dict) -> dict:
        """tools/list — 返回 CRUX 全量工具（BUILTIN + registry），转 MCP shape。"""
        return {"tools": self._all_tools()}

    def _tools_call(self, params: dict) -> dict:
        """tools/call — 统一走 ChatSession._dispatch_tool_impl。

        覆盖三类工具：
        - BUILTIN 生成工具（generate_image/video/multi_agent，含 LLM prompt 增强）
        - registry 工具（pipeline/comfyui/notebook/audio/tools.json）
        - 高风险工具（返回 confirm 副作用 → MCP 模式拒绝）
        """
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _JSONRPCError(ERR_INVALID_PARAMS, "Missing or invalid 'name'")

        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise _JSONRPCError(ERR_INVALID_PARAMS, "'arguments' must be an object")

        # 递归防护（第二道防线）：MCP bridge tools 是 CRUX 作为 Client 的
        # "出向"能力，禁止作为 Server 入向被调用，否则 A→B→A 死循环。
        # _all_tools() 已过滤不让调用方看到，这里显式拒绝兜底。
        if self._is_bridge_tool(name):
            return self._tool_error(
                f"Tool '{name}' is an MCP bridge tool (outbound only). "
                f"It cannot be invoked through the MCP server interface to "
                f"prevent recursion (A→B→A). Use it from within a CRUX "
                f"chat session instead.",
                is_error=True,
            )

        # 未知工具 → 结构化错误（让 LLM 知道工具不存在，而非崩溃）
        known = {t["name"] for t in self._all_tools()}
        if name not in known:
            return self._tool_error(f"Unknown tool: {name}. Use 'tools/list' to see available tools.")

        # 统一调度入口（core/chat.py:662）
        args_json = json.dumps(args, ensure_ascii=False)
        text, sides = self._session._dispatch_tool_impl(name, args_json)
        return self._format_tool_result(name, text, sides)

    def _resources_list(self, params: dict) -> dict:
        """resources/list — 暴露 output/ 下的产物（图片/视频/manifest）。"""
        try:
            from core.config import OUTPUT_DIR
        except ImportError:
            return {"resources": []}
        resources: list[dict] = []
        for sub in ("images", "videos", "keyframes"):
            d = OUTPUT_DIR / sub
            if not d.exists():
                continue
            for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm"):
                    continue
                resources.append(
                    {
                        "uri": p.as_uri(),
                        "name": p.name,
                        "mimeType": (mimetypes.guess_type(str(p))[0] or "application/octet-stream"),
                        "description": f"CRUX generated asset: {p.name}",
                    }
                )
                if len(resources) >= 100:  # 上限保护，避免目录爆炸
                    break
        return {"resources": resources}

    def _resources_read(self, params: dict) -> dict:
        """resources/read — 按 file:// URI 读产物（图片转 base64，视频给路径文本）。"""
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise _JSONRPCError(ERR_INVALID_PARAMS, "Missing 'uri'")

        path = Path(uri.replace("file://", ""))
        # 安全校验：只允许读 OUTPUT_DIR 内的文件（防路径穿越）
        try:
            from core.config import OUTPUT_DIR

            path = path.resolve()
            # 正确方向: 确保 path 在 OUTPUT_DIR 内
            path.relative_to(OUTPUT_DIR.resolve())  # 抛 ValueError 即越界
        except (ImportError, ValueError) as err:
            raise _JSONRPCError(ERR_INVALID_PARAMS, "URI must point inside CRUX output/ dir") from err
        if not path.is_file():
            raise _JSONRPCError(ERR_INVALID_PARAMS, f"File not found: {uri}")

        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        # 视频太大不内联 base64，返回路径文本（三象可读路径自行处理）
        video_exts = {".mp4", ".webm", ".mov"}
        if path.suffix.lower() in video_exts or path.stat().st_size > 5 * 1024 * 1024:
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": mime,
                        "text": json.dumps(
                            {"local_path": str(path), "size_bytes": path.stat().st_size}, ensure_ascii=False
                        ),
                    }
                ]
            }
        # 图片/小文件 → base64 blob
        data = path.read_bytes()
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": mime,
                    "blob": base64.b64encode(data).decode("ascii"),
                }
            ]
        }

    # 方法分发表（class-level，_handle 查这里）
    _METHODS = {
        "initialize": _initialize,
        "tools/list": _tools_list,
        "tools/call": _tools_call,
        "resources/list": _resources_list,
        "resources/read": _resources_read,
        # notifications/initialized / notifications/cancelled → 无 handler 即静默忽略
    }

    # ── 工具合并与格式转换 ────────────────────────────────────

    def _all_tools(self) -> list[dict]:
        """合并 BUILTIN_TOOLS + registry.definitions，去重，转 MCP shape。

        缓存：initialize 后工具集稳定，避免每次 tools/list 都重算。

        递归防护（第一道防线）：过滤 MCP bridge tools (mcp_*)。
        这些是 CRUX 作为 Client 调外部 server 的"出向"能力，若作为 Server
        暴露回去，调用方（如 claude）可能反向调它们 → A 调 B 时 B 又调 A，
        死循环 + 子进程指数膨胀。第二道防线在 _tools_call() 显式拒绝。
        """
        if self._tools_cache is not None:
            return self._tools_cache

        merged: list[dict] = []
        seen: set[str] = set()

        # registry 先（tools.json 里用户定义的工具优先级最高）
        for defn in self._registry.definitions:
            tool = self._openai_to_mcp_tool(defn)
            if tool is None:
                continue
            # 过滤 MCP bridge tools — 阻断出向能力被入向回灌
            if self._is_bridge_tool(tool["name"]):
                continue
            if tool["name"] not in seen:
                merged.append(tool)
                seen.add(tool["name"])

        self._tools_cache = merged
        return merged

    @staticmethod
    def _is_bridge_tool(name: str) -> bool:
        """识别 MCP bridge tools（出向 Client 工具，不可入向暴露）。

        对齐 core/mcp_client.py:MCP_TOOL_DEFS 的 4 个工具名前缀。
        用 startswith("mcp_") 而非硬编码列表，未来新增 bridge tools
        自动纳入防护。
        """
        return isinstance(name, str) and name.startswith("mcp_")

    @staticmethod
    def _openai_to_mcp_tool(defn: dict) -> dict | None:
        """OpenAI function 格式 → MCP tool 格式。

        OpenAI: {"type":"function","function":{"name","description","parameters":{...}}}
        MCP:    {"name","description","inputSchema":{...}}
        """
        func = defn.get("function") if isinstance(defn, dict) else None
        if not isinstance(func, dict) or "name" not in func:
            return None
        params = func.get("parameters") or {}
        # 确保 inputSchema 是合法 JSON Schema object
        if not isinstance(params, dict) or params.get("type") != "object":
            params = {"type": "object", "properties": {}}
        # 防御：缺 properties/required 时补默认（client 只消费朴素子集）
        params.setdefault("properties", {})
        params.setdefault("required", [])
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "inputSchema": params,
        }

    # ── tools/call 结果格式化 ─────────────────────────────────

    def _format_tool_result(self, name: str, text: str, sides: list[tuple[str, Any]]) -> dict:
        """把 _dispatch_tool_impl 的 (text, sides) 转 MCP CallToolResult。

        sides 元素形态（core/chat.py:665）:
            ("info", str)      → 追加文本提示
            ("image", dict)    → 追加 image content + 路径文本
            ("video", dict)    → 追加 video 路径文本（视频不内联 base64）
            ("confirm", dict)  → 高风险工具，MCP 拒绝
        """
        # 高风险工具确认 → MCP 是程序化调用，无人工确认回路
        for kind, payload in sides:
            if kind == "confirm":
                return self._tool_error(
                    f"Tool '{name}' requires interactive confirmation (high-risk). "
                    f"MCP mode refuses high-risk tools. Payload: "
                    f"{json.dumps(payload, ensure_ascii=False)}",
                    is_error=True,
                )

        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})

        for kind, payload in sides:
            if kind == "info" and isinstance(payload, str):
                content.append({"type": "text", "text": f"[info] {payload}"})
            elif kind == "image" and isinstance(payload, dict):
                content.extend(self._image_payload_to_content(payload))
            elif kind == "video" and isinstance(payload, dict):
                content.append({"type": "text", "text": self._video_payload_to_text(payload)})

        if not content:
            content.append({"type": "text", "text": "(tool produced no output)"})

        return {"content": content, "isError": False}

    def _image_payload_to_content(self, payload: dict) -> list[dict]:
        """把生成图片的 dict 转 MCP content。

        引擎返回的 dict（engines/text_to_image.py:64）:
            {"url", "local_path", "model", "prompt", "size", "seed"}
        MCP 策略：能读本地文件就给 base64 blob（三象可直接看图），
        否则给路径+URL 文本。
        """
        contents: list[dict] = []
        local = payload.get("local_path")
        if local and os.path.isfile(local):
            try:
                data = Path(local).read_bytes()
                mime = mimetypes.guess_type(local)[0] or "image/png"
                contents.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(data).decode("ascii"),
                        "mimeType": mime,
                    }
                )
            except OSError:
                pass  # 读失败降级到文本
        # 同时给路径+URL 文本（让三象两种消费方式都能用）
        meta = {k: payload[k] for k in ("local_path", "url", "model", "size", "seed") if payload.get(k)}
        if meta:
            contents.append({"type": "text", "text": json.dumps(meta, ensure_ascii=False)})
        return contents

    def _video_payload_to_text(self, payload: dict) -> str:
        """视频 dict → 文本（视频太大不内联 base64）。

        引擎返回（engines/video.py:288）:
            {"url", "local_path", "task_id", "video_id", "model", "prompt", "num_frames",
             "status"?("timeout"), "progress"?}
        """
        meta = {
            k: payload[k]
            for k in ("local_path", "url", "task_id", "video_id", "model", "num_frames", "status", "progress")
            if payload.get(k)
        }
        if payload.get("status") == "timeout":
            return (
                f"[video timeout] progress={payload.get('progress', 0):.0%}, "
                f"video_id={payload.get('video_id', '')} — "
                f"poll later with this video_id. {json.dumps(meta, ensure_ascii=False)}"
            )
        return json.dumps(meta, ensure_ascii=False)

    # ── 响应构造 helpers ──────────────────────────────────────

    def _tool_error(self, message: str, is_error: bool = True) -> dict:
        """构造 MCP CallToolResult 的错误形态（isError=true + 文本）。"""
        return {"content": [{"type": "text", "text": message}], "isError": is_error}

    def _error(self, req_id: Any, code: int, message: str) -> dict:
        """构造 JSON-RPC error 响应。"""
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def _write(self, obj: dict) -> None:
        """写单行 JSON-RPC 响应（newline-delimited，对齐 client 的 readline）。"""
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _log(self, msg: str) -> None:
        """日志写 stderr（不污染 stdout 的 JSON-RPC 流）。"""
        sys.stderr.write(f"[crux-mcp] {msg}\n")
        sys.stderr.flush()


class _JSONRPCError(Exception):
    """携带 JSON-RPC 错误码的内部异常，用于在 handler 里短路返回标准错误。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── 入口 ────────────────────────────────────────────────────


def run_mcp_server(argv: list[str] | None = None) -> None:
    """crux mcp-serve 入口。

    构造无头 ChatSession + ToolRegistry，启动 MCPServer.run()。
    认证由 core.config.SETTINGS 自动处理（环境变量优先 → auth.json 回退）。
    """
    argv = argv or []

    # config import 触发 _load_auth_file()（core/config.py:27-46），
    # 自动把 ~/.crux/auth.json 补进环境变量。SETTINGS.api_key 即可用。
    from core.config import SETTINGS

    if not SETTINGS.api_key:
        sys.stderr.write("[crux-mcp] ERROR: CRUX_API_KEY not set. Run `crux init` or export CRUX_API_KEY.\n")
        sys.exit(1)

    # 构造无头 ChatSession（core/chat.py:145-152）
    # brain / t2i / vid 全从 client 派生，_dispatch_tool_impl 可直接调
    from core.chat import ChatSession
    from core.client import CruxClient

    client = CruxClient(api_key=SETTINGS.api_key, base_url=SETTINGS.base_url)
    session = ChatSession(client)
    # 载入全量工具 + MCP 桥接（四象融合：双向可达）
    # mcp=True 注入 mcp_list_servers / mcp_call_tool 等，让三象调 CRUX 时
    # CRUX 也能反向调其他 MCP server 的工具
    session.tools.load(mcp=True)

    # 干净退出：SIGTERM / 键盘中断
    server = MCPServer(session, session.tools)

    def _on_sigterm(signum, frame):
        server._log(f"received signal {signum}, shutting down")
        sys.exit(0)

    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, _on_sigterm)  # Windows 对某些信号受限，静默降级

    try:
        server.run()
    except KeyboardInterrupt:
        server._log("interrupted, exiting")
