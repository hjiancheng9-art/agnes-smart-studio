"""FastAPI server — OpenAI-compatible HTTP endpoint.

Usage:
    crux serve --port 8000
    crux serve --host 0.0.0.0 --port 8080

Then point any OpenAI client at http://localhost:8000/v1
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from core.gateway.runner import AVAILABLE_MODELS, GatewayRunner, list_models

if TYPE_CHECKING:
    from core.gateway.protocol import (
        ChatCompletionRequest,
        ChatCompletionResponse,
    )

logger = logging.getLogger(__name__)


# ── App factory ─────────────────────────────────────────


def create_app(runner: GatewayRunner | None = None) -> FastAPI:
    """Create the FastAPI application with all routes registered."""
    if runner is None:
        runner = GatewayRunner()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("CRUX Gateway started — models: %s", AVAILABLE_MODELS)
        yield
        logger.info("CRUX Gateway shutting down")

    app = FastAPI(
        title="CRUX Gateway",
        description="OpenAI-compatible API powered by CRUX Studio",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins for local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────

    @app.get("/")
    async def root():
        from core.version import __version__ as _gw_ver

        return {
            "service": "CRUX Studio OpenAI 兼容 API 网关",
            "version": _gw_ver,
            "endpoints": {
                "GET /health": "健康检查",
                "GET /v1/models": "列出可用模型",
                "POST /v1/chat/completions": "聊天补全（OpenAI 兼容）",
            },
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "models": AVAILABLE_MODELS}

    @app.get("/v1/models")
    async def get_models():
        return list_models()

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        if not req.messages:
            raise HTTPException(status_code=400, detail="messages is required")

        if req.stream:
            return StreamingResponse(
                runner.complete_stream(req),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            try:
                resp: ChatCompletionResponse = runner.complete(req)
                return resp
            except Exception as e:
                logger.exception("Chat completion failed")
                raise HTTPException(status_code=500, detail=str(e)) from e

    return app


# ── Server entry point ──────────────────────────────────


def run_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the gateway server (blocking). Called from CLI."""
    app = create_app()
    logger.info("Starting CRUX Gateway on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="info")
