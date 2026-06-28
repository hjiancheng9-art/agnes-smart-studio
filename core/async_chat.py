"""CRUX API 异步客户端 — 真异步 httpx.AsyncClient 实现。

与 core/client.py (同步 CruxClient) API 对齐但全部 async/await。
用于需要非阻塞调用的场景（后台任务 / 并发请求 / IDE 集成）。
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from .config import SETTINGS

__all__ = ["AsyncCruxClient"]

logger = logging.getLogger("crux.async_client")


def _sanitize_json(data):
    """Recursively remove surrogate characters from JSON data (shared with sync client)."""
    if isinstance(data, str):
        if not any(0xD800 <= ord(c) <= 0xDFFF for c in data):
            return data
        return "".join(c for c in data if not (0xD800 <= ord(c) <= 0xDFFF))
    if isinstance(data, dict):
        return {k: _sanitize_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_json(v) for v in data]
    return data


class AsyncCruxClient:
    """CRUX AI API 异步客户端 — 真 async/await，基于 httpx.AsyncClient。

    用法:
        async with AsyncCruxClient() as client:
            result = await client.chat(model="...", messages=[...])
            async for delta in client.chat_stream(model="...", messages=[...]):
                ...
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or SETTINGS.api_key
        self.base_url = (base_url or SETTINGS.base_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = SETTINGS.max_retries
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的异步 HTTP 请求。"""
        retries = kwargs.pop("retries", self.max_retries)
        last_exc = None
        for attempt in range(retries):
            try:
                if method == "POST":
                    resp = await self._http.post(url, **kwargs)
                else:
                    resp = await self._http.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.WriteError,
                httpx.PoolTimeout,
                httpx.TimeoutException,
            ) as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403, 402):
                    raise
                if attempt < retries - 1 and (
                    e.response.status_code == 429 or e.response.status_code >= 500
                ):
                    wait = (2**attempt) if e.response.status_code == 429 else (0.5 * (attempt + 1))
                    await asyncio.sleep(wait)
                    last_exc = e
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    # ── 文本 ──────────────────────────────────────────────
    async def chat(
        self,
        model: str = "agnes-2.0-flash",
        messages: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        enable_thinking: bool = False,
        frequency_penalty: float = 0.3,
        presence_penalty: float = 0.3,
        **kwargs,
    ) -> dict:
        """调用文本对话接口（异步）。"""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages or [],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
            body["parallel_tool_calls"] = True
        if enable_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": True}
        body.update(kwargs)

        resp = await self._request_with_retry("POST", "/chat/completions", json=body)
        return _sanitize_json(resp.json())

    async def chat_multimodal(
        self,
        text: str,
        image_url: str,
        model: str = "",
        **kwargs,
    ) -> dict:
        """多模态理解（异步）。"""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        return await self.chat(model=model, messages=messages, **kwargs)

    async def chat_stream(
        self,
        model: str = "agnes-2.0-flash",
        messages: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        timeout: float = 120.0,
        frequency_penalty: float = 0.3,
        presence_penalty: float = 0.3,
        **kwargs,
    ):
        """流式调用（异步生成器）。yield delta 字典同同步版。"""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages or [],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        body.update(kwargs)

        _stream_retries = 2
        for _attempt in range(_stream_retries + 1):
            try:
                async with self._http.stream(
                    "POST",
                    "/chat/completions",
                    json=body,
                    timeout=httpx.Timeout(timeout, connect=30.0),
                ) as resp:
                    if resp.status_code >= 400:
                        status = resp.status_code
                        err_detail = ""
                        try:
                            await resp.aread()
                            body_text = resp.text[:500]
                            if body_text:
                                err_detail = f" - {body_text}"
                        except (OSError, ValueError, httpx.HTTPError):
                            pass
                        if _attempt < _stream_retries and (status == 429 or status >= 500):
                            wait = (2**_attempt) if status == 429 else (0.5 * (_attempt + 1))
                            await asyncio.sleep(wait)
                            continue
                        yield {"content": f"\n[HTTP {status}{err_detail}]", "_finish": "error"}
                        return

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = _sanitize_json(json.loads(data))
                        except json.JSONDecodeError:
                            logger.debug("async chat_stream JSON decode error: %s", data[:200])
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta", {}) or {}
                        out = {k: v for k, v in delta.items() if v}
                        finish = choice.get("finish_reason")
                        if finish:
                            out["_finish"] = finish
                        usage = chunk.get("usage")
                        if usage:
                            out["_usage"] = usage
                        if out:
                            yield out
                    return
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.PoolTimeout,
                httpx.TimeoutException,
            ) as e:
                if _attempt < _stream_retries:
                    await asyncio.sleep(0.5 * (_attempt + 1))
                    continue
                yield {"content": f"\n[流中断: {type(e).__name__}]", "_finish": "error"}
                return
