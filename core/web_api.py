"""Web API server -- FastAPI-based REST interface for CRUX.

Endpoints:
    GET  /health          — health check
    GET  /capability      — capability snapshot
    POST /chat            — synchronous chat
    POST /chat/stream     — SSE streaming chat
    POST /tool/<name>     — execute a named tool
    GET  /self/audit      — run self-audit
    GET  /eval            — run evaluation benchmarks
    GET  /tools/score     — all tools health scorecard (static + runtime)
    GET  /tools/score/<name> — single tool score detail
    GET  /tools/score/runtime/live — runtime-only scores

Start: python -m core.web_api (or: uvicorn core.web_api:app)
"""

import json
import os
from pathlib import Path
from typing import Any

__all__ = ['ROOT', 'app', 'start_server']

ROOT = Path(__file__).resolve().parent.parent

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    HAS_FASTAPI = True
except ImportError:
    # FastAPI 缺失时设为 None，下游用 HAS_FASTAPI 守卫跳过路由注册
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment,misc]
    StreamingResponse = None  # type: ignore[assignment,misc]
    CORSMiddleware = None  # type: ignore[assignment,misc]
    HAS_FASTAPI = False

from core.version import __version__  # 单一版本真源

if HAS_FASTAPI:
    assert FastAPI is not None  # guarded by HAS_FASTAPI
    _app: Any = FastAPI(title="CRUX Studio API", version=__version__)
else:
    _app = None
app = _app

if HAS_FASTAPI and app is not None and CORSMiddleware is not None:
    # CORS: 生产环境应通过 CRUX_CORS_ORIGINS 环境变量限制来源
    # 默认仅开放本地开发，避免全通配符安全风险
    _cors_origins_raw = os.getenv("CRUX_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

def _get_session():
    """Lazy-import ChatSession to avoid heavy deps on health check."""
    from core.chat import ChatSession
    from core.client import CruxClient
    client = CruxClient()
    return ChatSession(client=client)

if HAS_FASTAPI and app is not None:

    @app.get("/health")
    async def health():
        from core.capability import capability_snapshot
        snap = capability_snapshot()
        return {"status": "ok", "version": __version__,
                "tests": snap.get("health", {}).get("tests", "unknown"),
                "provider": snap.get("health", {}).get("provider", "unknown")}

    @app.get("/capability")
    async def capability():
        from core.capability import capability_snapshot
        return capability_snapshot()

    if HTTPException is not None and Request is not None:
        # 局部绑定非 None 类型，避免函数体内报告 reportOptionalCall
        _HTTPException = HTTPException
        _Request: Any = Request  # Any 用于参数注解，避开 reportInvalidTypeForm

        @app.post("/chat")
        async def chat(req: _Request):  # type: ignore[valid-type]
            body = await req.json()
            message = body.get("message", "")
            if not message:
                raise _HTTPException(400, "message required")
            session = _get_session()
            responses = list(session.send_stream(message))
            result: list[str] = []
            for kind, payload in responses:
                if kind == "text":
                    result.append(payload)
            return {"response": "".join(result), "turn_count": len(responses)}

        @app.post("/chat/stream")
        async def chat_stream(req: _Request):  # type: ignore[valid-type]
            body = await req.json()
            message = body.get("message", "")
            if not message:
                raise _HTTPException(400, "message required")
            async def generate():
                session = _get_session()
                for kind, payload in session.send_stream(message):
                    if kind == "text":
                        yield f"data: {json.dumps({'type': 'text', 'content': payload})}\\n\\n"
                    elif kind in ("info", "image", "video"):
                        yield f"data: {json.dumps({'type': kind, 'content': str(payload)[:500]})}\\n\\n"
                yield f"data: {json.dumps({'type': 'done'})}\\n\\n"
            if StreamingResponse is not None:
                return StreamingResponse(generate(), media_type="text/event-stream")
            return {}

        @app.post("/tool/{tool_name}")
        async def run_tool(tool_name: str, req: _Request):  # type: ignore[valid-type]
            from core.tools import get_registry
            body: dict = {}
            try:
                body = await req.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # no body or invalid JSON → use empty dict
            reg = get_registry()
            if not reg.has(tool_name):
                raise _HTTPException(404, f"Tool not found: {tool_name}")
            result = reg.execute(tool_name, body)
            return {"tool": tool_name, "result": result[:5000]}

    @app.get("/self/audit")
    async def self_audit():
        from core.self_audit import audit
        return audit()

    @app.get("/eval")
    async def run_eval():
        from core.eval_harness import run_evals
        return run_evals()

    @app.get("/tools/score")
    async def tools_score():
        """全量工具健康度评分（静态 + 运行时）。

        返回聚合报告：分级分布、最差 TOP5、零测试清单、每工具 4 维度分。
        """
        from core import tool_call_log
        from core.tool_scorecard import save_report, score_all
        from core.tools import get_registry
        reg = get_registry()
        runtime_calls = tool_call_log.group_by_tool()
        report = score_all(reg, runtime_calls=runtime_calls)
        save_report(report)  # 持久化
        return report

    @app.get("/tools/score/{tool_name}")
    async def tools_score_one(tool_name: str):
        """单工具评分详情（含运行时数据，若有）。"""
        from core import tool_call_log
        from core.tool_scorecard import score_tool_runtime, score_tool_static
        from core.tools import get_registry
        if HTTPException is None:
            return {}
        reg = get_registry()
        if tool_name not in reg.tool_names:
            raise HTTPException(status_code=404, detail=f"tool not found: {tool_name}")
        result = score_tool_static(tool_name, reg)
        calls = tool_call_log.load_recent(limit=500, tool_name=tool_name)
        result["runtime"] = score_tool_runtime(tool_name, calls)
        return result

    @app.get("/tools/score/runtime/live")
    async def tools_score_runtime():
        """仅运行时评分（基于 tool_calls.jsonl 最近调用）。"""
        from core import tool_call_log
        from core.tool_scorecard import score_tool_runtime
        grouped = tool_call_log.group_by_tool()
        if not grouped:
            return {"status": "no_data", "message": "tool_calls.jsonl 为空，先执行一些工具调用"}
        results = []
        for name, calls in grouped.items():
            results.append(score_tool_runtime(name, calls))
        results.sort(key=lambda x: x.get("score") if x.get("score") is not None else -1)
        return {
            "total_tools_with_data": len(results),
            "total_calls": sum(c["call_count"] for c in results),
            "tools": results,
        }

    @app.get("/rag/search")
    async def rag_search(q: str = "", top_k: int = 10):
        from core.rag import semantic_search
        return semantic_search(q, top_k)

def start_server(host: str = "127.0.0.1", port: int = 8420):
    """Start the API server (requires uvicorn)."""
    if not HAS_FASTAPI:
        print("FastAPI not installed. Run: pip install fastapi uvicorn")
        return
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")  # type: ignore[arg-type]  # guarded by `if not HAS_FASTAPI: return`
