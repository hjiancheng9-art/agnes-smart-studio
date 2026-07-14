"""OpenAI-compatible protocol models — request & response schemas.

Implements the subset of OpenAI's Chat Completion API that matters:
- /v1/chat/completions (streaming + non-streaming)
- /v1/models (model listing)

Does NOT reimplement OpenAI's full API surface — just enough for clients
like Continue.dev, Aider, Cursor, and Copilot CLI to work.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Request models ──────────────────────────────────────


class ContentTextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ContentImagePart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: dict[str, str]  # {"url": "data:image/...;base64,..."}


ContentPart = ContentTextPart | ContentImagePart


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ToolFunction(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None


class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunction


class StreamOptions(BaseModel):
    include_usage: bool = False


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="agnes-2.0-pro", description="Model name")
    messages: list[Message]
    stream: bool = False
    max_tokens: int | None = Field(default=None, alias="max_tokens")
    max_completion_tokens: int | None = None
    temperature: float | None = 0.7
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[Tool] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream_options: StreamOptions | None = None
    # Extra fields that some clients send — accepted but ignored
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    seed: int | None = None
    user: str | None = None

    class Config:
        populate_by_name = True
        extra = "ignore"


# ── Response models (non-streaming) ─────────────────────


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class Choice(BaseModel):
    index: int
    message: ChoiceMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]
    usage: Usage | None = None


# ── Response models (streaming) ─────────────────────────


class DeltaContent(BaseModel):
    role: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class DeltaChoice(BaseModel):
    index: int
    delta: DeltaContent
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[DeltaChoice]
    usage: Usage | None = None


# ── Model list ──────────────────────────────────────────


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 1700000000
    owned_by: str = "crux"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
