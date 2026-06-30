"""CRUX API 异步客户端 - asyncio 原生版，支持 OpenAI 兼容接口、视频代理、自动重试

与 core/client.py 同步版 CruxClient 对应，提供完全 async 的 API 调用能力。
所有 HTTP 调用使用 httpx.AsyncClient，阻塞点替换为 asyncio.sleep / async for。

使用模式：
    async with AsyncCruxClient() as client:
        result = await client.chat(model="agnes-2.0-flash", messages=[...])
        async for delta in client.chat_stream(model="agnes-2.0-flash", messages=[...]):
            print(delta.get("content", ""), end="")
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .client import ContentPolicyError
from .config import SETTINGS

__all__ = ["AsyncCruxClient"]


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
    """CRUX AI API 异步客户端，封装文本/图像/视频三类端点 (asyncio 原生)"""

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

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的异步 HTTP 请求"""
        retries = kwargs.pop("retries", self.max_retries)
        last_exc = None
        for attempt in range(retries):
            try:
                resp = await self._http.post(url, **kwargs) if method == "POST" else await self._http.get(url, **kwargs)
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
                # 429 Too Many Requests 和 5xx 可重试，其他 4xx 不重试
                if attempt < retries - 1 and (e.response.status_code == 429 or e.response.status_code >= 500):
                    # 429 指数退避：1s, 2s, 4s...；5xx 线性退避
                    wait = (2**attempt) if e.response.status_code == 429 else (0.5 * (attempt + 1))
                    await asyncio.sleep(wait)
                    last_exc = e
                    continue
                # 4xx: 解析响应体，提供可操作的错误信息（不泄露敏感字段）
                detail = ""
                raw = ""
                try:
                    raw = e.response.text[:1000]
                    detail = json.loads(raw)
                except (json.JSONDecodeError, ValueError, KeyError):
                    detail = raw[:500]
                # 内容安全过滤 → 提供重新措辞建议
                if isinstance(detail, dict) and detail.get("code") == "content_policy_violation":
                    msg = (
                        "提示词触发了内容安全过滤，请尝试：\n"
                        "1. 用更温和的词汇替换攻击性描述（如'对抗'代替'打架'）\n"
                        "2. 删除暴力/血腥/武器相关的视觉描述\n"
                        "3. 以'科幻场景、非攻击性互动'重述你的创意"
                    )
                    raise ContentPolicyError(msg, detail) from None
                # 从错误详情中剥离可能的敏感字段再拼入异常消息
                safe_detail = detail
                if isinstance(safe_detail, dict):
                    safe_detail = {
                        k: v for k, v in safe_detail.items() if k not in ("api_key", "token", "secret", "password")
                    }
                raise httpx.HTTPStatusError(
                    f"{e.response.status_code} {e.response.reason_phrase} - {safe_detail}",
                    request=e.request,
                    response=e.response,
                ) from e
        # 所有重试耗尽
        assert last_exc is not None  # guaranteed by loop logic
        raise last_exc

    # ── 文本 ──────────────────────────────────────────────

    async def chat(
        self,
        model: str = "agnes-2.0-flash",
        messages: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        enable_thinking: bool = False,
        frequency_penalty: float = 0.3,
        presence_penalty: float = 0.3,
        **kwargs,
    ) -> dict:
        """异步调用文本对话接口 /v1/chat/completions"""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages or [],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
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
        model: str = "agnes-1.5-flash",
        **kwargs,
    ) -> dict:
        """异步调用多模态接口（文本+图像理解）"""
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
    ) -> AsyncIterator[dict]:
        """异步流式调用 /chat/completions，逐增量 yield delta 字典。

        async for 用法:
            async for delta in client.chat_stream(...):
                print(delta.get("content", ""), end="")

        yield 格式与同步版一致：
            {"content": "..."}              文本增量
            {"reasoning_content": "..."}    thinking 增量（pro 模型）
            {"tool_calls": [...]}           工具调用分片（需上层按 index 合并）
            {"_finish": "stop|tool_calls"}  终止原因
        """
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

        # 流式连接重试（与同步版一致：最多 2 次额外尝试）
        stream_retries = 2
        last_stream_error = None
        for stream_attempt in range(stream_retries + 1):
            try:
                async with self._http.stream(
                    "POST",
                    "/chat/completions",
                    json=body,
                    timeout=httpx.Timeout(timeout, connect=30.0),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
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
                    return  # 成功完成，不再重试
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.PoolTimeout,
                httpx.TimeoutException,
            ) as e:
                last_stream_error = e
                if stream_attempt < stream_retries:
                    await asyncio.sleep(1.0 * (stream_attempt + 1))
                    continue
                yield {"content": f"\n[流中断: {type(e).__name__} (retries exhausted)]", "_finish": "error"}
            except httpx.HTTPStatusError as e:
                yield {"content": f"\n[HTTP {e.response.status_code}]", "_finish": "error"}
                return

    # ── 图像 ──────────────────────────────────────────────

    async def create_image(
        self,
        prompt: str,
        model: str = "agnes-image-2.1-flash",
        size: str = "1024x768",
        seed: int | None = None,
        negative_prompt: str | None = None,
        return_base64: bool = False,
        extra_body: dict | None = None,
    ) -> dict:
        """异步调用图像生成接口 /v1/images/generations"""
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }
        if seed is not None:
            body["seed"] = seed
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        merged_extra = dict(extra_body) if extra_body else {}
        if return_base64:
            merged_extra.setdefault("response_format", "b64_json")
        if merged_extra:
            body["extra_body"] = merged_extra

        resp = await self._request_with_retry("POST", "/images/generations", json=body)
        return resp.json()

    # ── 视频 ──────────────────────────────────────────────

    async def create_video(
        self,
        prompt: str,
        model: str = "agnes-video-v2.0",
        width: int = 1152,
        height: int = 768,
        num_frames: int = 121,
        frame_rate: int = 24,
        image: str | list[str] | None = None,
        negative_prompt: str | None = None,
        num_inference_steps: int | None = None,
        seed: int | None = None,
        extra_body: dict | None = None,
    ) -> dict:
        """异步创建视频任务 POST /v1/videos"""
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if image:
            if isinstance(image, str) and image.startswith("data:image/"):
                before, sep, b64_data = image.partition(";base64,")
                if sep:
                    image = b64_data
            body["image"] = image
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if num_inference_steps is not None:
            body["num_inference_steps"] = num_inference_steps
        if seed is not None:
            body["seed"] = seed
        if extra_body:
            if "image" in extra_body:
                imgs = extra_body["image"]
                if isinstance(imgs, str):
                    if imgs.startswith("data:image/"):
                        before, sep, b64 = imgs.partition(";base64,")
                        if sep:
                            extra_body = {**extra_body, "image": b64}
                elif isinstance(imgs, list):
                    converted = []
                    for img in imgs:
                        if isinstance(img, str) and img.startswith("data:image/"):
                            before, sep, b64 = img.partition(";base64,")
                            converted.append(b64 if sep else img)
                        else:
                            converted.append(img)
                    extra_body = {**extra_body, "image": converted}
            body["extra_body"] = extra_body

        resp = await self._request_with_retry("POST", "/videos", json=body)
        return resp.json()

    async def get_video_status(self, video_id: str) -> dict:
        """异步查询视频任务状态"""
        if not video_id:
            raise ValueError(
                "必须提供 video_id 查询视频状态。"
                "请勿使用 task_id，否则会导致排队异常延长。"
                "video_id 可在创建视频任务的响应中获取。"
            )

        agnesapi_url = self.base_url
        if agnesapi_url.endswith("/v1"):
            agnesapi_url = agnesapi_url[:-3]
        resp = await self._request_with_retry(
            "GET",
            f"{agnesapi_url}/agnesapi",
            params={"video_id": video_id},
            timeout=30.0,
        )
        return resp.json()

    async def check_video(self, video_id: str) -> dict:
        """异步查询单次视频任务状态（不轮询），返回当前状态 dict"""
        return await self.get_video_status(video_id=video_id)

    async def _poll_video_loop(
        self,
        video_id: str,
        deadline: float = 0,
        interval: float = 5.0,
        on_progress: Any | None = None,
        raise_on_fail: bool = True,
    ) -> dict | None:
        """异步内部轮询循环：进度防回退，共享逻辑。超时返回 None。"""
        last_progress = 0

        while time.time() < deadline:
            data = await self.get_video_status(video_id=video_id)
            status = data.get("status", "unknown")
            raw_progress = data.get("progress", 0)

            # 进度防回退：API 偶发简化响应
            current_progress = max(
                last_progress,
                raw_progress if isinstance(raw_progress, (int, float)) else last_progress,
            )
            last_progress = current_progress

            if on_progress:
                on_progress(status, current_progress, data)

            if status == "completed":
                return data
            if status == "failed":
                if raise_on_fail:
                    raise RuntimeError(f"视频生成失败: {data.get('error', '未知错误')}")
                return data

            await asyncio.sleep(interval)

        return None  # 超时

    async def poll_video(
        self,
        video_id: str,
        interval: float = 5.0,
        max_wait: float = 600.0,
        on_progress: Any | None = None,
    ) -> dict:
        """异步轮询视频任务直到完成/失败。超时抛 TimeoutError。"""
        deadline = time.time() + max_wait
        result = await self._poll_video_loop(
            video_id=video_id,
            deadline=deadline,
            interval=interval,
            on_progress=on_progress,
            raise_on_fail=True,
        )
        if result is None:
            raise TimeoutError(f"视频生成超时 ({max_wait}s)")
        return result

    async def wait_for_video(
        self,
        video_id: str,
        timeout: float = 120.0,
        interval: float = 5.0,
        on_progress: Any | None = None,
    ) -> dict:
        """异步限时轮询视频任务。超时返回当前状态（不抛异常）。"""
        deadline = time.time() + timeout
        result = await self._poll_video_loop(
            video_id=video_id,
            deadline=deadline,
            interval=interval,
            on_progress=on_progress,
            raise_on_fail=False,
        )
        if result is not None:
            return result

        # 超时：返回当前状态，附加 _timed_out 标记
        data = await self.get_video_status(video_id=video_id)
        data["_timed_out"] = True
        return data

    # ── 下载 ──────────────────────────────────────────────

    async def download_video(self, url: str, save_path: str) -> str:
        """异步下载视频文件。安全策略与同步版一致。"""
        from urllib.parse import urlparse

        same_origin = urlparse(url).netloc == urlparse(self.base_url).netloc

        # 策略1：无认证头直接下载（CDN 公开链接）
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    await asyncio.to_thread(self._write_file, save_path, resp.content)
                    return save_path
        except (httpx.HTTPError, httpx.TimeoutException):
            pass

        # 策略2：仅同源 URL 使用认证头（私有存储）
        if same_origin:
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                    resp = await client.get(url, headers={"Authorization": f"Bearer {self.api_key}"})
                    if resp.status_code == 200:
                        await asyncio.to_thread(self._write_file, save_path, resp.content)
                        return save_path
            except (httpx.HTTPError, httpx.TimeoutException):
                pass

        raise RuntimeError(f"视频下载失败: {url}")

    async def download_image(self, url: str, save_path: str) -> str:
        """异步下载图片文件。安全策略与同步版一致。"""
        from urllib.parse import urlparse

        same_origin = urlparse(url).netloc == urlparse(self.base_url).netloc

        # 策略1：无认证头直接下载（CDN 公开链接）
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    await asyncio.to_thread(self._write_file, save_path, resp.content)
                    return save_path
        except (httpx.HTTPError, httpx.TimeoutException):
            pass

        # 策略2：仅同源 URL 使用认证头（私有存储）
        if same_origin:
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                    resp = await client.get(url, headers={"Authorization": f"Bearer {self.api_key}"})
                    if resp.status_code == 200:
                        await asyncio.to_thread(self._write_file, save_path, resp.content)
                        return save_path
            except (httpx.HTTPError, httpx.TimeoutException):
                pass

        raise RuntimeError(f"图片下载失败: {url}")

    @staticmethod
    def _write_file(path: str, content: bytes) -> None:
        """线程安全的文件写入（供 asyncio.to_thread 调用）"""
        with open(path, "wb") as f:
            f.write(content)

    # ── 生命周期 ──────────────────────────────────────────────

    async def close(self):
        if getattr(self, '_closed', False):
            return
        self._closed = True
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
