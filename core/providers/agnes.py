"""
Agnes AI Provider — 统一多模态接入层

封装 Agnes API 的文本/图像/视频三类接口，处理所有 API 级细节：
- 图生图参数强制 extra_body
- 视频异步任务 create → persist video_id → poll → download
- 尺寸校验与对齐
- RPM 友好的退避策略

Usage:
    from core.providers.agnes import AgnesProvider
    provider = AgnesProvider()

    # 文生图
    result = provider.generate_image("a cat", model="agnes-image-2.1-flash")

    # 图生图
    result = provider.image_to_image("make it cyberpunk", image_url="https://...")

    # 文生视频（异步）
    task = provider.create_video_task("a dog running")
    # ... 稍后
    result = provider.get_video_result(task["video_id"])
"""

import base64
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
import requests

logger = logging.getLogger("crux.agnes")


# 视频 ID 清洗工具
def _clean_video_id(raw: str) -> str:
    """清洗 litellm 包装的 video_id，提取真实 ID"""
    if not raw or not raw.startswith("video_"):
        return raw
    try:
        b64_part = raw[6:]
        decoded = base64.b64decode(b64_part).decode("utf-8")
        if "video_id:" in decoded:
            idx = decoded.rfind("video_id:")
            return decoded[idx + len("video_id:") :]
    except (ValueError, UnicodeDecodeError):
        pass
    if "litellm:" in raw and ";video_id:" in raw:
        idx = raw.rfind("video_id:")
        if idx >= 0:
            return raw[idx + len("video_id:") :]
    return raw


# 标准尺寸白名单（Agnes 支持的尺寸）
VALID_IMAGE_SIZES = frozenset(
    {
        "1024x1024",
        "1024x768",
        "768x1024",
        "1152x768",
        "768x1152",
        "1152x864",
        "864x1152",
        "1280x720",
        "720x1280",
        "1280x768",
        "768x1280",
        "1080x1080",
        "576x1024",
        "1024x576",
    }
)

# 视频帧数必须满足 8n+1
VALID_VIDEO_FRAMES = frozenset({81, 121, 161, 201, 241, 281, 321, 361, 401, 441})

# 默认参数
DEFAULT_IMAGE_MODEL = "agnes-image-2.1-flash"
DEFAULT_IMAGE_SIZE = "1024x768"
DEFAULT_VIDEO_MODEL = "agnes-video-v2.0"
DEFAULT_VIDEO_SIZE = "1152x768"
DEFAULT_NUM_FRAMES = 81
DEFAULT_FRAME_RATE = 24

OUTPUT_DIR = Path(os.getcwd()) / "output" / "videos"


class AgnesProvider:
    """Agnes API 统一接入层"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        from dotenv import load_dotenv

        load_dotenv()

        self.api_key = api_key or os.getenv("CRUX_API_KEY", "")
        self.base_url = (base_url or os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")).rstrip("/")

        if not self.api_key:
            logger.warning("AgnesProvider: CRUX_API_KEY 未设置")

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(timeout=60.0, headers=self._headers)

        # 确保输出目录存在
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 文本/Agent API ──────────────────────────────────────

    def chat_completion(
        self,
        messages: list[dict],
        model: str = "agnes-2.0-flash",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """调用 Agnes 文本/Agent API（OpenAI 兼容格式）"""
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        resp = self._client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        return resp.json()

    # ── 图像 API ────────────────────────────────────────────

    @staticmethod
    def infer_size_from_text(text: str, default: str = "1024x768") -> str:
        """从自然语言推理图片/视频尺寸。
        "竖屏" / "9:16" / "reels" → 768x1024
        "方" / "1:1" → 1024x1024
        "横" / "16:9" → 1024x768
        """
        t = text.lower()
        if any(w in t for w in ["竖屏", "9:16", "9比16", "portrait", "reels", "shorts", "tiktok", "story", "stories"]):
            return "768x1024"
        if any(w in t for w in ["方", "1:1", "square", "正方形"]):
            return "1024x1024"
        if any(w in t for w in ["横屏", "横", "16:9", "landscape", "youtube", "bilibili"]):
            return "1024x768"
        return default

    def generate_image(
        self,
        prompt: str,
        model: str = DEFAULT_IMAGE_MODEL,
        size: str = DEFAULT_IMAGE_SIZE,
        seed: int | None = None,
        negative_prompt: str | None = None,
        image_url: str | None = None,  # 图生图输入
        image_urls: list[str] | None = None,  # 多图合成输入
        response_format: str | None = None,  # "url" 或 "b64_json"
        n: int = 1,
    ) -> dict:
        """
        文生图 / 图生图 / 多图合成 — 统一接口。

        图生图时 image_url/image_urls 自动放入 extra_body。
        """
        size = self._validate_image_size(size)
        body = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        if seed is not None:
            body["seed"] = seed

        extra_body = {}

        # 图生图参数必须放在 extra_body
        if image_urls:
            extra_body["image"] = image_urls
        elif image_url:
            extra_body["image"] = [image_url]

        if negative_prompt:
            extra_body["negative_prompt"] = negative_prompt

        if response_format:
            extra_body["response_format"] = response_format

        if extra_body:
            body["extra_body"] = extra_body

        # 日志（脱敏）
        logger.debug("generate_image: model=%s size=%s image=%s", model, size, bool(image_url or image_urls))

        resp = self._client.post(f"{self.base_url}/images/generations", json=body)
        resp.raise_for_status()
        result = resp.json()

        # 标准化返回
        return self._normalize_image_result(result, prompt, model, size, seed)

    def _validate_image_size(self, size: str) -> str:
        """尺寸校验，不符合时映射到最近的合法值"""
        if size in VALID_IMAGE_SIZES:
            return size
        logger.warning("图片尺寸 %s 不在白名单，使用默认 %s", size, DEFAULT_IMAGE_SIZE)
        return DEFAULT_IMAGE_SIZE

    def _normalize_image_result(self, raw: dict, prompt: str, model: str, size: str, seed: int | None) -> dict:
        """标准化图像返回"""
        data = raw.get("data", [{}])
        first = data[0] if data else {}
        url = first.get("url", "")
        b64 = first.get("b64_json", "")

        return {
            "url": url,
            "b64_json": b64,
            "revised_prompt": first.get("revised_prompt") or prompt,
            "model": model,
            "size": size,
            "seed": seed,
            "raw": raw,
        }

    # ── 视频 API ────────────────────────────────────────────

    def create_video_task(
        self,
        prompt: str,
        model: str = DEFAULT_VIDEO_MODEL,
        size: str = DEFAULT_VIDEO_SIZE,
        num_frames: int = DEFAULT_NUM_FRAMES,
        frame_rate: int = DEFAULT_FRAME_RATE,
        seed: int | None = None,
        negative_prompt: str | None = None,
        image_url: str | None = None,  # 图生视频
        image_urls: list[str] | None = None,  # 多图/关键帧
        mode: str = "text2video",
        timeout: float = 300.0,
    ) -> dict:
        """
        提交视频生成任务，立即返回 task_id 和 video_id。

        返回:
            {
                "task_id": "...",
                "video_id": "...",
                "status": "processing",
                "model": "...",
                "prompt": "...",
                "size": "...",
                "num_frames": ...,
                "frame_rate": ...,
                "seed": ...,
            }
        """
        size = self._validate_video_size(size)
        num_frames = self._validate_num_frames(num_frames)
        frame_rate = self._validate_frame_rate(frame_rate)

        body = {
            "model": model,
            "prompt": prompt,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
            "size": size,
        }
        if seed is not None:
            body["seed"] = seed
        if negative_prompt:
            body["negative_prompt"] = negative_prompt

        # 图生视频 / 多图关键帧
        if image_urls:
            if len(image_urls) == 1:
                body["image"] = image_urls[0]
            else:
                body["extra_body"] = body.get("extra_body", {})
                body["extra_body"]["image"] = image_urls
                body["extra_body"]["mode"] = "keyframes"
        elif image_url:
            body["image"] = image_url

        logger.debug("create_video_task: model=%s size=%s frames=%d fps=%d", model, size, num_frames, frame_rate)

        resp = self._client.post(f"{self.base_url}/videos", json=body, timeout=timeout)
        resp.raise_for_status()
        result = resp.json()

        video_id = _clean_video_id(result.get("video_id") or result.get("id", ""))
        task_id = result.get("task_id") or result.get("id", "")

        return {
            "task_id": task_id,
            "video_id": video_id,
            "video_id_raw": result.get("video_id", ""),
            "status": result.get("status", "processing"),
            "model": model,
            "prompt": prompt,
            "size": size,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
            "seed": seed,
            "progress": result.get("progress", 0),
            "raw": result,
        }

    def get_video_result(self, video_id: str, timeout: float = 30.0) -> dict:
        """
        按 video_id 查询视频结果。
        通过 CruxClient 查询，兼容 Agnes API 的 multipart response。
        """
        from core.client import CruxClient

        client = CruxClient()
        data = client.check_video(video_id)

        url = data.get("url") or data.get("video_url", "")
        return {
            "video_id": video_id,
            "status": data.get("status", "unknown"),
            "progress": data.get("progress", data.get("internal_progress", 0)),
            "url": url or "",
            "error": data.get("error"),
            "seconds": data.get("seconds"),
            "size": data.get("size"),
            "model": data.get("model"),
            "raw": data,
        }

    def wait_for_video(
        self,
        video_id: str,
        poll_interval: float = 5.0,
        max_wait: float = 300.0,
        on_progress=None,
    ) -> dict:
        """
        轮询等待视频生成完成，自动下载到本地。

        Args:
            video_id: 视频 ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间
            on_progress: 进度回调 fn(status, progress, data)

        Returns:
            {"status": ..., "url": ..., "local_path": ..., "video_id": ...}
        """
        start = time.time()
        last_progress = -1

        while time.time() - start < max_wait:
            elapsed = time.time() - start
            result = self.get_video_result(video_id)

            status = result.get("status", "")
            progress = result.get("progress", 0)

            if progress != last_progress:
                logger.debug("video %s: %.0f%% (%s, %.0fs)", video_id, progress, status, elapsed)
                last_progress = progress

            if on_progress:
                on_progress(status, progress, result)

            if status in ("completed", "SUCCESS", "done"):
                url = result.get("url") or result.get("video_url", "")
                if url:
                    local_path = self._download_video(url, video_id)
                    result["local_path"] = local_path
                return result

            if status in ("failed", "FAILED", "error", "ERROR"):
                error = result.get("error", "unknown")
                logger.error("video %s failed: %s", video_id, error)
                return {"status": "failed", "error": error, "video_id": video_id}

            time.sleep(poll_interval)

        return {
            "status": "timeout",
            "video_id": video_id,
            "progress": progress,
            "message": f"等待超时 ({max_wait:.0f}s)",
        }

    def submit_and_wait(
        self,
        prompt: str,
        **kwargs,
    ) -> dict:
        """一键提交 + 等待完成（同步阻塞）"""
        task = self.create_video_task(prompt, **kwargs)
        video_id = task.get("video_id", "")
        if not video_id:
            return {"status": "error", "message": "未获取到 video_id", "task": task}

        return self.wait_for_video(video_id)

    def _download_video(self, url: str, video_id: str) -> str:
        """下载视频到本地"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = video_id[-12:] if len(video_id) > 12 else video_id
        save_path = str(OUTPUT_DIR / f"vid_{ts}_{short_id}.mp4")

        try:
            r = requests.get(url, timeout=300, stream=True)
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = os.path.getsize(save_path)
            logger.info("视频下载完成: %s (%dKB)", save_path, size / 1024)
            return save_path
        except Exception as e:
            logger.warning("视频下载失败: %s: %s", url, e)
            return ""

    def _validate_video_size(self, size: str) -> str:
        """视频尺寸校验"""
        try:
            w_str, h_str = size.split("x")
            w, h = int(w_str), int(h_str)
            # Agnes 要求宽高为 64 的倍数
            w = (w // 64) * 64
            h = (h // 64) * 64
            if w < 64:
                w = 1152
            if h < 64:
                h = 768
            return f"{w}x{h}"
        except (ValueError, AttributeError):
            return DEFAULT_VIDEO_SIZE

    def _validate_num_frames(self, num_frames: int) -> int:
        """帧数校验：必须 8n+1 且 ≤441"""
        if num_frames in VALID_VIDEO_FRAMES:
            return num_frames
        # 映射到最近的合法值
        for valid in sorted(VALID_VIDEO_FRAMES):
            if num_frames <= valid:
                return valid
        return 441

    def _validate_frame_rate(self, frame_rate: int) -> int:
        """帧率校验"""
        return max(1, min(60, frame_rate))

    def _normalize_video_result(self, raw: dict, video_id: str) -> dict:
        """标准化视频查询结果"""
        url = raw.get("url") or raw.get("video_url", "")
        return {
            "video_id": video_id,
            "status": raw.get("status", raw.get("task_status", "unknown")),
            "progress": raw.get("progress", raw.get("internal_progress", 0)),
            "url": url,
            "error": raw.get("error"),
            "seconds": raw.get("seconds"),
            "size": raw.get("size"),
            "model": raw.get("model"),
            "raw": raw,
        }

    # ── 工具方法 ──────────────────────────────────────────

    def image_to_data_uri(self, image_path: str) -> str:
        """本地图片转 Data URI Base64（用于 Agnes 图生图输入）"""
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = Path(image_path).suffix.lstrip(".").lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "gif": "image/gif",
        }.get(ext, "image/png")
        return f"data:{mime};base64,{data}"

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
