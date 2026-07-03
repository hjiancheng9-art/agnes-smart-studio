"""
Agnes API 客户端 v2.0 — 多模态图片 & 视频生成
支持: 文生图 / 图生图 / 文生视频 / 图生视频 / 视频查询(video_id)
"""

import os
import time
import json
import requests
from typing import Optional
from dataclasses import dataclass
from enum import Enum


# ============================================================
# 配置
# ============================================================

class VideoModel(str, Enum):
    """Agnes 视频模型"""
    V2_FAST = "agnes-video-v2-fast"
    V2_PRO = "agnes-video-v2-pro"
    V1 = "agnes-video-v1"


# 图片尺寸预设
IMAGE_SIZE_PRESETS = {
    "1:1 方形":   "1024x1024",
    "4:3 横向":   "1024x768",
    "3:4 竖屏":   "768x1024",
    "16:9 宽屏":  "1024x576",
    "9:16 手机":  "576x1024",
    "3:2 摄影":   "1024x684",
    "2:3 人像":   "684x1024",
    "21:9 超宽":  "1024x448",
    "9:21 超长":  "448x1024",
}

# 视频分辨率预设
VIDEO_RESOLUTION_PRESETS = {
    "720P (1280×720)":     (1280, 720),
    "1080P (1920×1080)":   (1920, 1080),
    "480P (854×480)":      (854, 480),
    "1:1 (1024×1024)":     (1024, 1024),
    "4:3 (1024×768)":      (1024, 768),
    "3:4 (768×1024)":      (768, 1024),
    "9:16 (720×1280)":     (720, 1280),
}

# 视频时长预设 (秒)
VIDEO_DURATION_PRESETS = [5, 8, 10, 15, 20, 30, 60]


@dataclass
class AgnesConfig:
    """Agnes API 配置"""
    api_key: str = ""
    base_url: str = "https://api.agnes-ai.com/v1"
    image_endpoint: str = "/images/generations"
    video_endpoint: str = "/video/generations"
    video_result_endpoint: str = "/video/result"
    default_image_size: str = "1024x1024"
    default_video_width: int = 1280
    default_video_height: int = 720
    default_video_duration: int = 5
    default_video_fps: int = 24
    default_video_model: VideoModel = VideoModel.V2_FAST
    poll_interval: float = 2.0
    max_poll_time: float = 600.0

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


# ============================================================
# 客户端
# ============================================================

class AgnesClient:
    """Agnes 多模态客户端"""

    def __init__(self, config: Optional[AgnesConfig] = None):
        self.config = config or AgnesConfig(
            api_key=os.environ.get("AGNES_API_KEY", ""),
        )

    # ----- 图片生成 -----

    def text_to_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        num_images: int = 1,
        quality: str = "standard",
        style: str = "vivid",
        seed: Optional[int] = None,
    ) -> dict:
        """文生图"""
        payload = {
            "prompt": prompt,
            "size": size,
            "n": num_images,
            "quality": quality,
            "style": style,
        }
        if seed is not None:
            payload["seed"] = seed
        return self._post(self.config.image_endpoint, payload)

    def image_to_image(
        self,
        prompt: str,
        image_url: str,
        size: str = "1024x1024",
        strength: float = 0.7,
        steps: int = 30,
        cfg_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> dict:
        """图生图"""
        payload = {
            "prompt": prompt,
            "image": image_url,
            "size": size,
            "strength": strength,
            "steps": steps,
            "cfg_scale": cfg_scale,
        }
        if seed is not None:
            payload["seed"] = seed
        return self._post(self.config.image_endpoint, payload)

    # ----- 视频生成 -----

    def text_to_video(
        self,
        prompt: str,
        model: VideoModel = VideoModel.V2_FAST,
        width: int = 1280,
        height: int = 720,
        duration: int = 5,
        fps: int = 24,
        seed: Optional[int] = None,
        negative_prompt: str = "",
    ) -> dict:
        """文生视频 — v2.0"""
        payload = {
            "prompt": prompt,
            "model": model.value if isinstance(model, VideoModel) else model,
            "width": width,
            "height": height,
            "duration": duration,
            "fps": fps,
            "negative_prompt": negative_prompt,
        }
        if seed is not None:
            payload["seed"] = seed

        result = self._post(self.config.video_endpoint, payload)
        vid = result.get("video_id") or result.get("id") or result.get("task_id")
        if vid:
            result["video_id"] = vid
        return result

    def image_to_video(
        self,
        prompt: str,
        image_url: str,
        model: VideoModel = VideoModel.V2_FAST,
        width: int = 1280,
        height: int = 720,
        duration: int = 5,
        fps: int = 24,
        seed: Optional[int] = None,
    ) -> dict:
        """图生视频 — v2.0"""
        payload = {
            "prompt": prompt,
            "image": image_url,
            "model": model.value if isinstance(model, VideoModel) else model,
            "width": width,
            "height": height,
            "duration": duration,
            "fps": fps,
        }
        if seed is not None:
            payload["seed"] = seed

        result = self._post(self.config.video_endpoint, payload)
        vid = result.get("video_id") or result.get("id") or result.get("task_id")
        if vid:
            result["video_id"] = vid
        return result

    # ----- 视频查询 -----

    def query_video(self, video_id: str) -> dict:
        """按 video_id 查询视频状态"""
        return self._get(f"{self.config.video_result_endpoint}/{video_id}")

    def wait_for_video(
        self,
        video_id: str,
        poll_interval: Optional[float] = None,
        max_wait: Optional[float] = None,
    ) -> dict:
        """轮询等待视频完成"""
        interval = poll_interval or self.config.poll_interval
        max_time = max_wait or self.config.max_poll_time
        elapsed = 0.0

        while elapsed < max_time:
            result = self.query_video(video_id)
            status = result.get("status", "").lower()
            if status == "completed":
                result["_poll_elapsed"] = elapsed
                return result
            elif status == "failed":
                result["_poll_elapsed"] = elapsed
                return result
            time.sleep(interval)
            elapsed += interval

        return {"status": "timeout", "video_id": video_id, "_poll_elapsed": elapsed}

    # ----- 内部方法 -----

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.config.base_url}{endpoint}"
        try:
            resp = requests.post(url, headers=self.config.headers, json=payload, timeout=60)
            return self._handle_response(resp)
        except requests.exceptions.Timeout:
            return {"error": "请求超时", "url": url}
        except requests.exceptions.ConnectionError:
            return {"error": "无法连接 Agnes API", "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}

    def _get(self, endpoint: str) -> dict:
        url = f"{self.config.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self.config.headers, timeout=30)
            return self._handle_response(resp)
        except Exception as e:
            return {"error": str(e), "url": url}

    def _handle_response(self, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except json.JSONDecodeError:
            return {"error": f"JSON 解析失败: {resp.text[:500]}", "status_code": resp.status_code}
        if resp.status_code >= 400:
            data["_http_error"] = resp.status_code
        return data


def create_client(api_key: Optional[str] = None) -> AgnesClient:
    """创建 Agnes 客户端"""
    key = api_key or os.environ.get("AGNES_API_KEY", "")
    return AgnesClient(AgnesConfig(api_key=key))
