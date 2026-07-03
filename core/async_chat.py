"""CRUX API 异步客户端 — 真异步 httpx.AsyncClient 实现。

与 core/client.py (同步 CruxClient) API 对齐但全部 async/await。
用于需要非阻塞调用的场景（后台任务 / 并发请求 / IDE 集成）。
"""

import asyncio
import json as _json
from typing import Any

import httpx

from core.config import SETTINGS


def _sanitize_json(data: Any) -> Any:
    """Recursively remove surrogate characters from JSON data."""
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

    # 全局限流：防止并发请求过多挤爆模型 → 触发 429
    _global_semaphore: "asyncio.Semaphore | None" = None

    @classmethod
    def set_max_concurrency(cls, limit: int) -> None:
        """设置全局并发上限（模块级，所有 AsyncCruxClient 实例共享）"""
        if limit > 0:
            cls._global_semaphore = asyncio.Semaphore(limit)

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
        self._closed = False
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的异步 HTTP 请求（含全局限流 + 429/503 快速降级）。"""
        retries = kwargs.pop("retries", self.max_retries)
        last_exc = None

        # 全局限流：获取信号量再进入重试循环，防并发挤爆
        sem = self._global_semaphore
        if sem is not None:
            await sem.acquire()

        try:
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
                    status = e.response.status_code
                    # ── 429/503 过载快速降级：短退避 → 连续 hit → 抛出让上游切换模型 ──
                    if status in (429, 503):
                        wait = min(2**attempt, 4.0)  # 上限 4 秒
                        await asyncio.sleep(wait)
                        if attempt >= 1:  # 连续 2 次限流/过载 → 立即抛出触发 fallback
                            raise RuntimeError(
                                f"Model rate-limited ({status}) after {attempt+1} attempts, "
                                f"triggering fallback to next provider"
                            ) from e
                        last_exc = e
                        continue
                    if attempt < retries - 1 and status >= 500:
                        wait = 0.5 * (attempt + 1)
                        await asyncio.sleep(wait)
                        last_exc = e
                        continue
                    raise
        finally:
            # 确保信号量释放
            if sem is not None:
                sem.release()

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Retry loop exhausted with no captured exception")

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
        response_format: dict | None = None,
        **kwargs,
    ) -> dict:
        """多轮对话（异步）。"""
        messages = messages or []
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if frequency_penalty != 0.0:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0.0:
            body["presence_penalty"] = presence_penalty
        if enable_thinking:
            body["enable_thinking"] = True
        if response_format:
            body["response_format"] = response_format
        body.update(kwargs)

        resp = await self._request_with_retry(
            "POST", "/v1/chat/completions", json=body
        )
        return resp.json()

    async def chat_multimodal(
        self,
        text: str,
        image_url: str,
        model: str = "agnes-2.0-flash",
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
        enable_thinking: bool = False,
        frequency_penalty: float = 0.3,
        presence_penalty: float = 0.3,
        response_format: dict | None = None,
        **kwargs,
    ):
        """流式对话（异步生成器）。"""
        messages = messages or []
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if frequency_penalty != 0.0:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0.0:
            body["presence_penalty"] = presence_penalty
        if enable_thinking:
            body["enable_thinking"] = True
        if response_format:
            body["response_format"] = response_format
        body.update(kwargs)

        resp = await self._request_with_retry(
            "POST", "/v1/chat/completions", json=body
        )

        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    yield _json.loads(data_str)
                except _json.JSONDecodeError:
                    continue

    async def chat_stream_json(
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
        response_format: dict | None = None,
        **kwargs,
    ):
        """流式对话（异步生成器），返回 (delta, finish_reason) 元组。"""
        async for chunk in self.chat_stream(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            enable_thinking=enable_thinking,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format=response_format,
            **kwargs,
        ):
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")
                yield delta, finish_reason
