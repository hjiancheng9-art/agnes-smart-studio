"""CRUX API 统一客户端 - 支持 OpenAI 兼容接口、视频代理、双通道查询、自动重试"""

import json
import time
import httpx
from typing import Any
from collections.abc import Iterator

from .config import SETTINGS


__all__ = ["CruxClient", "ContentPolicyError"]
class ContentPolicyError(Exception):
    """内容安全过滤异常 - 提示词触发 API 安全策略"""
    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


class CruxClient:
    """CRUX AI API 统一客户端，封装文本/图像/视频三类端点"""

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
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试的HTTP请求"""
        retries = kwargs.pop("retries", self.max_retries)
        last_exc = None
        for attempt in range(retries):
            try:
                resp = self._http.post(url, **kwargs) if method == "POST" else self._http.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                continue
            except httpx.HTTPStatusError as e:
                # 429 Too Many Requests 和 5xx 可重试，其他 4xx 不重试
                if attempt < retries - 1 and (
                    e.response.status_code == 429 or e.response.status_code >= 500
                ):
                    # 429 指数退避：1s, 2s, 4s...；5xx 线性退避
                    wait = (2 ** attempt) if e.response.status_code == 429 else (0.5 * (attempt + 1))
                    time.sleep(wait)
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
                    safe_detail = {k: v for k, v in safe_detail.items()
                                   if k not in ("api_key", "token", "secret", "password")}
                raise httpx.HTTPStatusError(
                    f"{e.response.status_code} {e.response.reason_phrase} - {safe_detail}",
                    request=e.request, response=e.response,
                ) from e
        # 所有重试耗尽
        assert last_exc is not None  # guaranteed by loop logic
        raise last_exc

    # ── 文本 ──────────────────────────────────────────────
    def chat(
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
        """调用文本对话接口 /v1/chat/completions"""
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

        resp = self._request_with_retry("POST", "/chat/completions", json=body)
        return resp.json()

    def chat_multimodal(
        self,
        text: str,
        image_url: str,
        model: str = "agnes-1.5-flash",
        **kwargs,
    ) -> dict:
        """调用 1.5-flash 多模态接口（文本+图像理解）"""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        return self.chat(model=model, messages=messages, **kwargs)

    def chat_stream(
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
    ) -> Iterator[dict]:
        """流式调用 /chat/completions，逐增量 yield delta 字典。

        注意：不修改 chat() 的 stream 参数（其当前行为是整块 JSON，多个调用方依赖）。
        本方法独立用 httpx stream + SSE 解析，yield 格式：
            {"content": "..."}              文本增量
            {"reasoning_content": "..."}    thinking 增量（pro 模型）
            {"tool_calls": [...]}           工具调用分片（需上层按 index 合并）
            {"_finish": "stop|tool_calls"}  终止原因
        用法: for delta in client.chat_stream(...): ...
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

        # 流式不套 _request_with_retry（重试难以处理已建立的流），
        # 但捕获网络异常并优雅降级，避免静默失败。
        try:
            with self._http.stream(
                "POST", "/chat/completions", json=body,
                timeout=httpx.Timeout(timeout, connect=30.0),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
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
                    if out:
                        yield out
        except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError,
                httpx.PoolTimeout, httpx.TimeoutException) as e:
            # 网络层错误：yield 错误信息让上层优雅降级
            yield {"content": f"\n[流中断: {type(e).__name__}]", "_finish": "error"}
        except httpx.HTTPStatusError as e:
            yield {"content": f"\n[HTTP {e.response.status_code}]", "_finish": "error"}

    # ── 图像 ──────────────────────────────────────────────
    def create_image(
        self,
        prompt: str,
        model: str = "agnes-image-2.1-flash",
        size: str = "1024x768",
        seed: int | None = None,
        negative_prompt: str | None = None,
        return_base64: bool = False,
        extra_body: dict | None = None,
    ) -> dict:
        """调用图像生成接口 /v1/images/generations

        return_base64=True 时通过 extra_body.response_format=\"b64_json\" 请求 base64 输出。
        根据官方文档，response_format 必须放在 extra_body 内，不能放请求顶层。
        extra_body 中的其他字段（如 image）也会被一起嵌套发送。
        """
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }
        if seed is not None:
            body["seed"] = seed
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        # 构建 extra_body，response_format 和 image 都必须在 extra_body 内
        merged_extra = dict(extra_body) if extra_body else {}
        if return_base64:
            merged_extra.setdefault("response_format", "b64_json")
        if merged_extra:
            body["extra_body"] = merged_extra

        resp = self._request_with_retry("POST", "/images/generations", json=body)
        return resp.json()

    # ── 视频 ──────────────────────────────────────────────
    def create_video(
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
        """创建视频任务 POST /v1/videos
        
        单图视频：image 放在请求体顶层。
        多图/关键帧：通过 extra_body 传入 image 和 mode（嵌套格式）。
        """
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if image:
            # 视频 API 的 image 字段只接受纯 base64 或 HTTP URL
            # data URI 格式需剥离前缀，否则 API 解析 base64 长度不对
            if isinstance(image, str) and image.startswith("data:image/"):
                # 提取 data:image/png;base64,XXXXXX 中的 XXXXXX 部分
                before, sep, b64_data = image.partition(";base64,")
                if sep:  # 仅当 ;base64, 分隔符存在时才剥离，防止空字符串
                    image = b64_data
            body["image"] = image
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if num_inference_steps is not None:
            body["num_inference_steps"] = num_inference_steps
        if seed is not None:
            body["seed"] = seed
        if extra_body:
            # extra_body 中的 image 如果是 data URI，也需转为纯 base64
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

        resp = self._request_with_retry("POST", "/videos", json=body)
        return resp.json()

    def get_video_status(self, video_id: str) -> dict:
        """查询视频任务状态

        必须使用 video_id 查询（GET /agnesapi?video_id=），不要使用 task_id，
        后者会导致排队异常延长（超过5分钟）。
        """
        if not video_id:
            raise ValueError(
                "必须提供 video_id 查询视频状态。"
                "请勿使用 task_id，否则会导致排队异常延长。"
                "video_id 可在创建视频任务的响应中获取。"
            )

        agnesapi_url = self.base_url
        if agnesapi_url.endswith("/v1"):
            agnesapi_url = agnesapi_url[:-3]
        resp = self._request_with_retry(
            "GET",
            f"{agnesapi_url}/agnesapi",
            params={"video_id": video_id},
            timeout=30.0,
        )
        return resp.json()

    def check_video(self, video_id: str) -> dict:
        """查询单次视频任务状态（不轮询），返回当前状态 dict"""
        return self.get_video_status(video_id=video_id)

    def _poll_video_loop(self, video_id: str,
                          deadline: float = 0, interval: float = 5.0,
                          on_progress: Any | None = None, raise_on_fail: bool = True) -> dict | None:
        """内部轮询循环：进度防回退，共享逻辑。超时返回 None。"""
        last_progress = 0

        while time.time() < deadline:
            data = self.get_video_status(video_id=video_id)
            status = data.get("status", "unknown")
            raw_progress = data.get("progress", 0)

            # 进度防回退：API 偶发简化响应
            current_progress = max(last_progress, raw_progress if isinstance(raw_progress, (int, float)) else last_progress)
            last_progress = current_progress

            if on_progress:
                on_progress(status, current_progress, data)

            if status == "completed":
                return data
            if status == "failed":
                if raise_on_fail:
                    raise RuntimeError(f"视频生成失败: {data.get('error', '未知错误')}")
                return data

            # 兼容新版API的 in_progress 状态
            if status == "in_progress":
                pass

            time.sleep(interval)

        return None  # 超时

    def poll_video(
        self,
        video_id: str,
        interval: float = 5.0,
        max_wait: float = 600.0,
        on_progress: Any | None = None,
    ) -> dict:
        """
        轮询视频任务直到完成/失败。
        on_progress: 回调函数 (status, progress, data)
        返回最终结果 dict，含 remixed_from_video_id
        """
        deadline = time.time() + max_wait
        result = self._poll_video_loop(video_id=video_id,
                                        deadline=deadline, interval=interval,
                                        on_progress=on_progress, raise_on_fail=True)
        if result is None:
            raise TimeoutError(f"视频生成超时 ({max_wait}s)")
        return result

    def wait_for_video(
        self,
        video_id: str,
        timeout: float = 120.0,
        interval: float = 5.0,
        on_progress: Any | None = None,
    ) -> dict:
        """
        限时轮询视频任务。超时返回当前状态（不抛异常）。
        适合IDE等有总执行时间限制的环境。
        """
        deadline = time.time() + timeout
        result = self._poll_video_loop(video_id=video_id,
                                        deadline=deadline, interval=interval,
                                        on_progress=on_progress, raise_on_fail=False)
        if result is not None:
            return result

        # 超时：返回当前状态，附加 _timed_out 标记
        data = self.get_video_status(video_id=video_id)
        data["_timed_out"] = True
        return data

    # ── 下载 ──────────────────────────────────────────────
    def download_video(self, url: str, save_path: str) -> str:
        """下载视频文件。CDN/GCS URL 为公开链接，无需 Authorization 头。

        安全策略：仅在 URL 与当前 base_url 同源时才附加认证头，
        防止 Bearer token 被重定向泄露到第三方 CDN。
        """
        from urllib.parse import urlparse

        same_origin = urlparse(url).netloc == urlparse(self.base_url).netloc

        # 策略1：无认证头直接下载（CDN 公开链接）
        try:
            with httpx.Client(follow_redirects=True, timeout=120.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    return save_path
        except (httpx.HTTPError, httpx.TimeoutException):
            pass

        # 策略2：仅同源 URL 使用认证头（私有存储）
        if same_origin:
            try:
                with httpx.Client(follow_redirects=True, timeout=120.0) as client:
                    resp = client.get(url, headers={"Authorization": f"Bearer {self.api_key}"})
                    if resp.status_code == 200:
                        with open(save_path, "wb") as f:
                            f.write(resp.content)
                        return save_path
            except (httpx.HTTPError, httpx.TimeoutException):
                pass

        raise RuntimeError(f"视频下载失败: {url}")

    def download_image(self, url: str, save_path: str) -> str:
        """下载图片文件。CDN URL 为公开链接，无需 Authorization 头（带了反而 401）。

        安全策略：仅在 URL 与当前 base_url 同源时才附加认证头。
        """
        from urllib.parse import urlparse

        same_origin = urlparse(url).netloc == urlparse(self.base_url).netloc

        # 策略1：无认证头直接下载（CDN 公开链接）
        try:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    return save_path
        except (httpx.HTTPError, httpx.TimeoutException):
            pass

        # 策略2：仅同源 URL 使用认证头（私有存储）
        if same_origin:
            try:
                with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                    resp = client.get(url, headers={"Authorization": f"Bearer {self.api_key}"})
                    if resp.status_code == 200:
                        with open(save_path, "wb") as f:
                            f.write(resp.content)
                        return save_path
            except (httpx.HTTPError, httpx.TimeoutException):
                pass

        raise RuntimeError(f"图片下载失败: {url}")

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
