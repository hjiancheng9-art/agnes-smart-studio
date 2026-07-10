"""Agnes AI API 客户端 — 完整封装。

支持能力：
  Chat (文本 + 多模态 + Tools + Thinking + 流式)
  Image (文生图 + 图生图 + 多尺寸)
  Video (文生视频 + 图生视频 + 轮询查询)
"""

import os
import time
import json
import base64
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

import requests


# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgnesConfig:
    api_key: str = ""
    api_base: str = "https://apihub.agnes-ai.com/v1"
    timeout: int = 600

    @classmethod
    def from_env(cls) -> "AgnesConfig":
        return cls(
            api_key=os.getenv("AGNES_API_KEY", ""),
            api_base=os.getenv("AGNES_API_BASE", "https://apihub.agnes-ai.com/v1"),
            timeout=int(os.getenv("AGNES_TIMEOUT", "600")),
        )


# ═══════════════════════════════════════════════════════════════
# Model registry
# ═══════════════════════════════════════════════════════════════

IMAGE_SIZES = {
    "1K": ["1024x768", "1024x1024", "768x1024"],
    "2K": ["2048x2048", "2048x1536", "1536x2048"],
    "3K": ["3072x3072", "3072x2304", "2304x3072"],
    "4K": ["4096x4096", "4096x3072", "3072x4096"],
}
ALL_IMAGE_SIZES = [s for group in IMAGE_SIZES.values() for s in group]

CHAT_MODELS = {
    "agnes-1.5-flash": {
        "context": 512000, "max_output": 64000,
        "stream": False, "tools": False, "thinking": False, "vision": False,
    },
    "agnes-2.0-flash": {
        "context": 512000, "max_output": 64000,
        "stream": True, "tools": True, "thinking": True, "vision": True,
    },
}

IMAGE_MODELS = {
    "agnes-image-2.0-flash": {"max_size": "4K", "img2img": True},
    "agnes-image-2.1-flash": {"max_size": "4K", "img2img": True},
}

VIDEO_MODELS = {
    "agnes-video-v2.0": {"default_size": "1152x768", "max_frames": 441, "img2video": True},
}


# ═══════════════════════════════════════════════════════════════
# Client
# ═══════════════════════════════════════════════════════════════

# ── 输出目录 ──────────────────────────────────────────
OUTPUT_BASE = Path(__file__).resolve().parent.parent / "outputs"
OUTPUT_IMAGES = OUTPUT_BASE / "images"
OUTPUT_VIDEOS = OUTPUT_BASE / "videos"


def _ensure_output_dirs():
    """确保输出目录存在。"""
    OUTPUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUTPUT_VIDEOS.mkdir(parents=True, exist_ok=True)



def _load_dotenv():
    """加载配置（兼容旧版 — 委托给 config 模块）"""
    from agnes.config import load_env_into_os
    load_env_into_os()

# Auto-load .env at import time
_load_dotenv()

class AgnesError(Exception):
    """Agnes API 错误。"""

    def __init__(self, message: str, status_code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AgnesClient:
    """Agnes AI API 客户端。"""

    def __init__(self, config: AgnesConfig | None = None):
        self.config = config or AgnesConfig.from_env()
        if not self.config.api_key:
            raise AgnesError(
                "API Key 未设置。\n"
                "  方式1: set AGNES_API_KEY=sk-your-key\n"
                "  方式2: 在 .env 文件中设置 AGNES_API_KEY=sk-your-key\n"
                "  获取 Key: https://platform.agnes-ai.com/settings/apiKeys"
            )
        self._headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """统一请求处理。"""
        url = path if path.startswith("http") else f"{self.config.api_base}{path}"
        kwargs.setdefault("timeout", self.config.timeout)
        resp = requests.request(method, url, headers=self._headers, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"error": resp.text}
            # 友好提示
            hint = ""
            if resp.status_code == 401:
                hint = " → API Key 无效，请检查并重新生成"
            elif resp.status_code == 400:
                msg = str(body.get("message", body.get("error", ""))).lower()
                if "size" in msg or "multiple" in msg:
                    hint = " → 图片的宽和高必须为 16 的倍数（例如 1024×768）"
                elif "rate" in msg or "rpm" in msg or "limit" in msg:
                    hint = " → 请求频率超限（RPM 限制），请稍后重试"
            elif resp.status_code == 500:
                hint = " → 服务内部错误，请检查参数格式后重试"
            raise AgnesError(
                f"HTTP {resp.status_code}: {body.get('message', body.get('error', resp.text[:200]))}{hint}",
                status_code=resp.status_code,
                response=body,
            )
        return resp.json()

    # ── Chat ────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        model: str = "agnes-2.0-flash",
        temperature: float = 0.7,
        top_p: float = 1.0,
        max_tokens: int = 4096,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        thinking: bool = False,
        stop: list[str] | None = None,
        seed: int | None = None,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        repetition_penalty: float = 1.0,
    ) -> dict:
        """发送 对话补全请求。

        Args:
            messages: 消息列表，格式：{"role": "system|user|assistant|tool", "content": "..."}
                       agnes-2.0-flash 支持 content 为数组格式（多模态图片输入）：
                       [{"type":"text","text":"..."},{"type":"image_url","image_url":{"url":"..."}}]
            model: 模型 ID
            temperature: 采样温度，范围 0-2
            top_p: 核采样参数
            max_tokens: 最大输出 Token 数
            stream: 是否启用流式输出
            tools: 工具定义列表（仅 agnes-2.0-flash 支持）
            tool_choice: "auto" / "none" / 指定工具名
            thinking: 是否启用深度思考模式（仅 agnes-2.0-flash）
            stop: 停止词列表
            seed: 随机种子
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        if thinking:
            body["chat_template_kwargs"] = {"thinking": True}
        if stop:
            body["stop"] = stop
        if seed is not None:
            body["seed"] = seed
        if frequency_penalty:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty:
            body["presence_penalty"] = presence_penalty
        if repetition_penalty != 1.0:
            body["repetition_penalty"] = repetition_penalty

        # 流式模式：直接发请求 + SSE 解析
        if stream:
            url = f"{self.config.api_base}/chat/completions"
            resp = requests.post(
                url, json=body, headers=self._headers,
                timeout=self.config.timeout, stream=True,
            )
            resp.raise_for_status()
            return self._parse_sse(resp)

        return self._request("POST", "/chat/completions", json=body)

    def _parse_sse(self, resp):
        """解析 Server-Sent Events 流，逐 chunk yield delta content。"""
        import json as _json
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = _json.loads(data_str)
                except _json.JSONDecodeError:
                    continue
                choices = data.get("choices", [])
                for choice in choices:
                    delta = choice.get("delta", {}) or {}
                    if delta.get("content"):
                        yield delta["content"]

    def chat_text(
        self,
        prompt: str,
        model: str = "agnes-2.0-flash",
        system: str | None = None,
        **kwargs,
    ) -> str:
        """快速文本对话，直接返回回复文字。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self.chat(messages, model=model, **kwargs)
        return resp["choices"][0]["message"]["content"]

    def chat_with_image(
        self,
        prompt: str,
        image_url: str,
        model: str = "agnes-2.0-flash",
        **kwargs,
    ) -> str:
        """多模态对话 — 带图片输入（仅 agnes-2.0-flash 支持）。"""
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }]
        return self.chat(messages, model=model, **kwargs)["choices"][0]["message"]["content"]

    # ── Image Generation ─────────────────────────────────

    def generate_image(
        self,
        prompt: str,
        model: str = "agnes-image-2.0-flash",
        size: str = "1024x768",
        n: int = 1,
        response_format: str = "url",  # url | b64_json
        image_urls: list[str] | None = None,  # 图生图参考图
        seed: int | None = None,
    ) -> list[dict]:
        """生成或编辑图片。

        Args:
            prompt: 图片描述文本
            model: 模型 ID
            size: 输出尺寸，宽和高必须为 16 的倍数
            n: 生成数量
            response_format: "url"（返回链接）或 "b64_json"（返回 Base64）
            image_urls: 图生图的参考图片 URL 列表
            seed: 随机种子

        Returns:
            [{"url": "..."}] 或 [{"b64_json": "..."}]
        """
        self._validate_size(size)

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "extra_body": {"response_format": response_format},
        }

        if image_urls:
            body["extra_body"]["image"] = image_urls
        if seed is not None:
            body["seed"] = seed

        resp = self._request("POST", "/images/generations", json=body)
        return resp.get("data", [])

    def generate_image_and_save(
        self,
        prompt: str,
        save_path: str | None = None,
        model: str = "agnes-image-2.0-flash",
        size: str = "1024x768",
        **kwargs,
    ) -> str:
        """生成图片并保存到本地，返回保存路径。"""
        images = self.generate_image(prompt, model=model, size=size, **kwargs)
        url = images[0].get("url", "")
        if not url:
            raise AgnesError("图片生成成功但未返回图片 URL")

        if not save_path:
            _ensure_output_dirs()
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_path = str(OUTPUT_IMAGES / f"agnes_image_{ts}.png")

        return self.download_file(url, save_path)

    @staticmethod
    def _validate_size(size: str) -> None:
        """验证尺寸是 16 的倍数。"""
        try:
            w, h = map(int, size.split("x"))
            if w % 16 != 0 or h % 16 != 0:
                raise ValueError(f"尺寸 {size} 不是 16 的倍数")
        except ValueError:
            valid = ", ".join(ALL_IMAGE_SIZES[:6]) + "..."
            raise AgnesError(
                f"无效的图片尺寸： {size}\n"
                f"  尺寸格式: WxH (宽x高)，必须为 16 的倍数\n"
                f"  常用尺寸: {valid}"
            )

    # ── Video Generation ─────────────────────────────────

    def generate_video(
        self,
        prompt: str,
        model: str = "agnes-video-v2.0",
        image_url: str | None = None,        # 图生视频参考图
        mode: str | None = None,              # 生成模式
        width: int = 1152,
        height: int = 768,
        num_frames: int | None = None,
        frame_rate: int = 24,
        num_inference_steps: int | None = None,
        seed: int | None = None,
        negative_prompt: str | None = None,
        wait: bool = True,
        poll_interval: int = 5,
    ) -> dict:
        """生成视频。

        Args:
            prompt: 视频描述文本
            model: 模型 ID
            image_url: 起始图片 URL（图生视频）
            mode: 生成模式
            width: 宽（默认 1152）
            height: 高（默认 768）
            num_frames: 总帧数（8n+1，最大 441）
            frame_rate: 帧率（默认 24）
            num_inference_steps: 推理步数
            seed: 随机种子
            negative_prompt: 负面提示词
            wait: 是否等待生成完成
            poll_interval: 轮询间隔（秒）

        Returns:
            wait=False: 创建任务的响应 (含 video_id)
            wait=True:  完成后的视频信息 (含 url)
        """
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "extra_body": {},
        }

        if image_url:
            body["extra_body"]["image"] = image_url
        if mode:
            body["extra_body"]["mode"] = mode
        if width:
            body["width"] = width
        if height:
            body["height"] = height
        if num_frames:
            body["num_frames"] = num_frames
        if frame_rate:
            body["frame_rate"] = frame_rate
        if num_inference_steps:
            body["num_inference_steps"] = num_inference_steps
        if seed is not None:
            body["seed"] = seed
        if negative_prompt:
            body["negative_prompt"] = negative_prompt

        resp = self._request("POST", "/videos", json=body)

        if not wait:
            return resp

        # 等待完成
        video_id = resp.get("video_id", "")
        if not video_id:
            raise AgnesError(f"视频创建成功但响应中缺少 video_id: {json.dumps(resp, ensure_ascii=False)[:200]}")

        print(f"  ⏳ 视频生成中... (video_id: {video_id[:40]}...)")
        dots = 0
        while True:
            time.sleep(poll_interval)
            dots += 1
            status = self.get_video(video_id)
            state = status.get("internal_status", status.get("status", ""))

            # 进度显示
            progress = status.get("progress", 0)
            bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
            print(f"\r  [{bar}] {progress}%  {state}", end="")

            if state in ("completed", "done", "succeeded"):
                print()  # 换行
                # 再次查询获取完整结果（含 URL）
                return self.get_video(video_id)
            elif state in ("failed", "error"):
                print()
                raise AgnesError(f"视频生成失败: {json.dumps(status, ensure_ascii=False)[:300]}")

    def get_video(self, video_id: str) -> dict:
        """通过 video_id 查询视频生成状态。"""
        return self._request("GET",
            f"{self.config.api_base.replace('/v1','')}/agnesapi?video_id={video_id}",
            timeout=30
        )

    # ── Models ──────────────────────────────────────────

    def generate_video_and_save(
        self,
        prompt: str,
        save_path: str | None = None,
        model: str = "agnes-video-v2.0",
        image_url: str | None = None,
        mode: str | None = None,
        width: int = 1152,
        height: int = 768,
        num_frames: int | None = None,
        frame_rate: int = 24,
        seed: int | None = None,
        negative_prompt: str | None = None,
        poll_interval: int = 5,
        on_progress = None,
    ) -> str:
        """生成视频 -> 等待完成 -> 下载到本地，返回保存路径。

        on_progress(state, progress): 进度回调。
        """
        # 1. 提交生成任务（不等待）
        task = self.generate_video(
            prompt=prompt,
            model=model,
            image_url=image_url,
            mode=mode,
            width=width,
            height=height,
            num_frames=num_frames,
            frame_rate=frame_rate,
            seed=seed,
            negative_prompt=negative_prompt,
            wait=False,
        )

        video_id = task.get("video_id", "")
        if not video_id:
            raise AgnesError(f"视频创建失败，未返回 video_id: {json.dumps(task, ensure_ascii=False)[:200]}")

        if on_progress:
            on_progress("queued", 0)

        # 2. 自己轮询（最长等 12 分钟）
        waited = 0
        max_wait = 720  # 12 分钟
        while waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval
            status = self.get_video(video_id)
            state = status.get("internal_status", status.get("status", ""))
            progress = status.get("progress", 0)

            if on_progress:
                on_progress(state, progress)

            if state in ("completed", "done", "succeeded", "ready"):
                break
            elif state in ("failed", "error"):
                raise AgnesError(f"视频生成失败: {json.dumps(status, ensure_ascii=False)[:300]}")
        else:
            # 超时但仍在生成中，再查一次试试
            status = self.get_video(video_id)
            state = status.get("internal_status", status.get("status", ""))
            if state in ("completed", "done", "succeeded", "ready"):
                pass  # 刚好在超时前完成了
            else:
                raise AgnesError(
                    f"视频生成超时（已等待 {waited//60} 分钟）\n"
                    f"  video_id: {video_id[:40]}...\n"
                    f"  当前状态: {state} ({status.get('progress', 0)}%)\n"
                    f"  请稍后用查询工具输入 video_id 查看结果"
                )

        # 3. 获取成品 URL
        url = status.get("url") or ""
        if not url:
            final = self.get_video(video_id)
            url = final.get("url") or final.get("video_url") or final.get("download_url") or ""
        if not url:
            raise AgnesError(f"视频完成但未返回下载 URL\n  response: {json.dumps(status, ensure_ascii=False)[:300]}")

        # 4. 下载到本地
        if not save_path:
            _ensure_output_dirs()
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_path = str(OUTPUT_VIDEOS / f"agnes_video_{ts}.mp4")

        if on_progress:
            on_progress("downloading", 0)

        saved = self.download_file(url, save_path)
        print(f"  ✅ 视频已保存至：{saved}")

        if on_progress:
            on_progress("done", 100)

        return saved

    def list_models(self) -> list[dict]:
        """列出所有可用模型。"""
        return self._request("GET", "/models").get("data", [])

    @staticmethod
    def get_model_info(model_id: str) -> dict:
        """获取模型能力信息。"""
        for group in [CHAT_MODELS, IMAGE_MODELS, VIDEO_MODELS]:
            if model_id in group:
                return group[model_id]
        return {}

    @staticmethod
    def get_model_type(model_id: str) -> str:
        """返回模型类型：chat（对话）/ image（图片）/ video（视频）/ unknown（未知）。"""
        if model_id in CHAT_MODELS:
            return "chat"
        elif model_id in IMAGE_MODELS:
            return "image"
        elif model_id in VIDEO_MODELS:
            return "video"
        return "unknown"

    # ── Utils ───────────────────────────────────────────

    def download_file(self, url: str, save_path: str) -> str:
        """下载文件到本地，返回完整路径。"""
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        out = Path(save_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        return str(out.resolve())

    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """将本地图片转为 Data URI 格式（用于图生图）。"""
        ext = Path(image_path).suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
        data = base64.b64encode(Path(image_path).read_bytes()).decode()
        return f"data:{mime};base64,{data}"
