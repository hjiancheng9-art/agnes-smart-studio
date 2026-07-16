"""Runner — bridge between OpenAI HTTP protocol and CRUX LLM backend.

Translates OpenAI ChatCompletionRequest → CruxClient calls → OpenAI responses.
Supports both streaming (SSE) and non-streaming modes.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from core.client import CruxClient
from core.gateway.protocol import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaChoice,
    DeltaContent,
    Message,
    ModelInfo,
    ModelList,
    Usage,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ── Known model aliases ─────────────────────────────────

MODEL_ALIASES: dict[str, str] = {
    # Agnes models (native)
    "agnes-2.0-flash": "agnes-2.0-flash",
    "agnes-2.0-pro": "agnes-2.0-pro",
    # DeepSeek models
    "deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v3": "deepseek-v4-flash",
    # OpenAI aliases → best CRUX match
    "gpt-4o": "agnes-2.0-pro",
    "gpt-4o-mini": "agnes-2.0-flash",
    "gpt-4-turbo": "agnes-2.0-pro",
    "gpt-4": "agnes-2.0-pro",
    "gpt-3.5-turbo": "agnes-2.0-flash",
    # Anthropic aliases
    "claude-3-5-sonnet": "agnes-2.0-pro",
    "claude-3-haiku": "agnes-2.0-flash",
}

AVAILABLE_MODELS = sorted(set(MODEL_ALIASES.values()))


def resolve_model(requested: str) -> str:
    """Resolve a client-requested model name to a CRUX model."""
    if requested in MODEL_ALIASES:
        return MODEL_ALIASES[requested]
    return "agnes-2.0-pro"


# ── Message conversion ──────────────────────────────────


def _extract_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            if part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        elif hasattr(part, "type") and part.type == "text":
            parts.append(part.text)
    return "\n".join(parts)


def convert_messages(msgs: list[Message]) -> list[dict]:
    """Convert OpenAI-format messages to CRUX-compatible dicts."""
    result: list[dict] = []
    for m in msgs:
        entry: dict = {"role": m.role}
        if isinstance(m.content, str):
            entry["content"] = m.content
        else:
            entry["content"] = _extract_text(m.content)
        if m.name:
            entry["name"] = m.name
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        result.append(entry)
    return result


def _tools_to_dicts(tools: list | None) -> list[dict] | None:
    if not tools:
        return None
    return [t.model_dump() if hasattr(t, "model_dump") else t for t in tools]


# ── Runner ──────────────────────────────────────────────


class GatewayRunner:
    """Bridges OpenAI protocol requests to the CRUX LLM backend."""

    def __init__(self, client: CruxClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> CruxClient:
        if self._client is None:
            self._client = CruxClient()
        return self._client

    def _make_chat_id(self) -> str:
        return f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # ── Non-streaming ────────────────────────────────

    def complete(self, req: ChatCompletionRequest) -> ChatCompletionResponse:
        model = resolve_model(req.model)
        messages = convert_messages(req.messages)
        tools = _tools_to_dicts(req.tools)

        raw: dict = self.client.chat(
            model=model,
            messages=messages,
            temperature=req.temperature or 0.7,
            top_p=req.top_p,
            max_tokens=req.max_tokens or req.max_completion_tokens,
            stop=req.stop,
            tools=tools,
            tool_choice=req.tool_choice,
            stream=False,
            thinking=False,  # gateway defaults to standard chat, not reasoning
        )

        choices_raw = raw.get("choices", [])
        usage_raw = raw.get("usage", {})

        choices = []
        for i, c in enumerate(choices_raw):
            msg = c.get("message", {})
            choices.append(
                Choice(
                    index=i,
                    message=ChoiceMessage(
                        role=msg.get("role", "assistant"),
                        content=msg.get("content"),
                        tool_calls=msg.get("tool_calls"),
                    ),
                    finish_reason=c.get("finish_reason"),
                )
            )

        usage = None
        if usage_raw:
            usage = Usage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
                total_tokens=usage_raw.get("total_tokens", 0),
            )

        return ChatCompletionResponse(
            id=raw.get("id", self._make_chat_id()),
            model=model,
            choices=choices,
            usage=usage,
        )

    # ── Streaming ────────────────────────────────────

    async def complete_stream(self, req: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        model = resolve_model(req.model)
        messages = convert_messages(req.messages)
        tools = _tools_to_dicts(req.tools)
        chat_id = self._make_chat_id()

        loop = asyncio.get_event_loop()

        # chat_stream() yields dicts in a blocking generator. Run in executor,
        # collect all chunks, then yield SSE from async context.
        def _collect() -> list[dict]:
            return list(
                self.client.chat_stream(
                    model=model,
                    messages=messages,
                    temperature=req.temperature or 0.7,
                    top_p=req.top_p,
                    max_tokens=req.max_tokens or req.max_completion_tokens,
                    stop=req.stop,
                    tools=tools,
                    tool_choice=req.tool_choice,
                    thinking=False,  # gateway defaults to standard chat
                )
            )

        chunks: list[dict] = await loop.run_in_executor(None, _collect)

        idx = 0
        finish_reason: str | None = None
        final_usage_raw: dict = {}

        for chunk in chunks:
            # Sentinel: {"_done": True, "choices": [...], "usage": {...}}
            if chunk.get("_done"):
                final_usage_raw = chunk.get("usage", {})
                if not finish_reason:
                    choices = chunk.get("choices", [])
                    if choices:
                        finish_reason = choices[0].get("finish_reason")
                continue

            choices_raw = chunk.get("choices", [])
            usage_raw = chunk.get("usage") or chunk.get("_usage")

            for c in choices_raw:
                delta = c.get("delta", {})
                fr = c.get("finish_reason")
                if fr:
                    finish_reason = fr

                dc = DeltaChoice(
                    index=idx,
                    delta=DeltaContent(
                        role=delta.get("role"),
                        content=delta.get("content"),
                        tool_calls=delta.get("tool_calls"),
                    ),
                    finish_reason=fr,
                )

                u = None
                if usage_raw:
                    u = Usage(
                        prompt_tokens=usage_raw.get("prompt_tokens", 0),
                        completion_tokens=usage_raw.get("completion_tokens", 0),
                        total_tokens=usage_raw.get("total_tokens", 0),
                    )

                yield f"data: {ChatCompletionChunk(id=chat_id, model=model, choices=[dc], usage=u).model_dump_json()}\n\n"
                idx += 1

        # Final chunk with usage
        final_usage = None
        if final_usage_raw:
            final_usage = Usage(
                prompt_tokens=final_usage_raw.get("prompt_tokens", 0),
                completion_tokens=final_usage_raw.get("completion_tokens", 0),
                total_tokens=final_usage_raw.get("total_tokens", 0),
            )

        final_chunk = ChatCompletionChunk(
            id=chat_id,
            model=model,
            choices=[
                DeltaChoice(
                    index=idx,
                    delta=DeltaContent(),
                    finish_reason=finish_reason or "stop",
                )
            ],
            usage=final_usage,
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"


def list_models() -> ModelList:
    """Return the list of available models."""
    return ModelList(data=[ModelInfo(id=m) for m in AVAILABLE_MODELS])
