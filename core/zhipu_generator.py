"""
Zhipu GLM Image/Video Generator — 智谱免费生图/生视频备用通道。

当 CRUX 主引擎失败时作为 fallback。CogView-3-Flash 免费生图，
CogVideoX-Flash 免费生视频。

Usage:
    from core.zhipu_generator import generate_image, generate_video
    result = generate_image("一只猫", key="your-api-key")
    task_id = generate_video("海浪拍打沙滩", key="your-api-key")
"""

from __future__ import annotations

import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path

import requests

logger = logging.getLogger("crux.zhipu.gen")

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
IMAGE_OUT = OUTPUT_DIR / "images"
VIDEO_OUT = OUTPUT_DIR / "videos"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

__all__ = [
    "generate_image",
    "generate_video",
    "get_zhipu_api_key",
    "poll_video",
    "zhipu_image_pipeline",
]


def get_zhipu_api_key() -> str | None:
    """从 models.json 读取智谱 API key。"""
    try:
        cfg_path = ROOT / "models.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("providers", {}).get("zhipu", {}).get("api_key")
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def generate_image(
    prompt: str,
    key: str | None = None,
    model: str = "cogview-3-flash",
    save: bool = True,
) -> dict:
    """文生图 — CogView-3-Flash 免费。

    Args:
        prompt: 图片描述
        key: API key（不传则自动读取 models.json）
        model: 模型 ID
        save: 是否下载并保存到本地

    Returns:
        {"status": "ok", "url": ..., "local_path": ...} 或 {"status": "error", "message": ...}
    """
    api_key = key or get_zhipu_api_key()
    if not api_key:
        return {"status": "error", "message": "未找到智谱 API key"}

    try:
        resp = requests.post(
            f"{BASE_URL}/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt},
            timeout=60,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text)
            return {"status": "error", "message": f"HTTP {resp.status_code}: {err}"}

        data = resp.json()
        url = data["data"][0]["url"]

        result = {"status": "ok", "url": url, "local_path": ""}

        if save and url:
            try:
                os.makedirs(IMAGE_OUT, exist_ok=True)
                ts = int(time.time() * 1000)
                fname = f"cogview_{ts}.png"
                fpath = IMAGE_OUT / fname
                img_resp = requests.get(url, timeout=30)
                if img_resp.status_code == 200:
                    with open(fpath, "wb") as f:
                        f.write(img_resp.content)
                    result["local_path"] = str(fpath)
                    logger.info("CogView image saved: %s", fpath)
            except (OSError, requests.RequestException) as e:
                logger.warning("CogView failed to save image: %s", e)

        return result

    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def generate_video(
    prompt: str,
    key: str | None = None,
    model: str = "cogvideox-flash",
) -> dict:
    """文生视频 — CogVideoX-Flash 免费。

    提交异步任务，返回 task_id 用于轮询。

    Returns:
        {"status": "processing", "task_id": "..."} 或 {"status": "error", ...}
    """
    api_key = key or get_zhipu_api_key()
    if not api_key:
        return {"status": "error", "message": "未找到智谱 API key"}

    try:
        resp = requests.post(
            f"{BASE_URL}/videos/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt},
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", resp.text)
            return {"status": "error", "message": f"HTTP {resp.status_code}: {err}"}

        data = resp.json()
        return {
            "status": "processing",
            "task_id": data.get("id", ""),
            "task_status": data.get("task_status", "PROCESSING"),
        }

    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def poll_video(task_id: str, key: str | None = None, save: bool = True) -> dict:
    """轮询视频生成结果。

    Args:
        task_id: generate_video 返回的 task_id
        key: API key
        save: 是否下载保存

    Returns:
        {"status": "ok", "url": ..., "local_path": ...}
        或 {"status": "processing"}
        或 {"status": "error", ...}
    """
    api_key = key or get_zhipu_api_key()
    if not api_key:
        return {"status": "error", "message": "未找到智谱 API key"}

    try:
        resp = requests.get(
            f"{BASE_URL}/async-result/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"status": "error", "message": f"HTTP {resp.status_code}"}

        data = resp.json()
        status = data.get("task_status", "PROCESSING")

        if status == "SUCCESS":
            video_result = data.get("video_result", [{}])
            url = video_result[0].get("url", "") if video_result else ""
            result = {"status": "ok", "url": url, "local_path": "", "task_status": "SUCCESS"}

            if save and url:
                try:
                    os.makedirs(VIDEO_OUT, exist_ok=True)
                    ts = int(time.time() * 1000)
                    fname = f"cogvideo_{ts}.mp4"
                    fpath = VIDEO_OUT / fname
                    vid_resp = requests.get(url, timeout=120)
                    if vid_resp.status_code == 200:
                        with open(fpath, "wb") as f:
                            f.write(vid_resp.content)
                        result["local_path"] = str(fpath)
                        logger.info("CogVideoX video saved: %s", fpath)
                except (OSError, requests.RequestException) as e:
                    logger.warning("CogVideoX failed to save video: %s", e)

            return result

        elif status == "FAIL":
            return {"status": "error", "message": "视频生成失败", "task_status": "FAIL"}

        else:
            return {"status": "processing", "task_status": status}

    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def zhipu_image_pipeline(prompt: str, negative_prompt: str | None = None, **kwargs) -> dict:
    """与 CRUX TextToImageEngine 接口兼容的包装器。

    当 CRUX 生图失败时，可直接替换调用。
    """
    return generate_image(prompt, **kwargs)
