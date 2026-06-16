"""下载管理器 - 图片/视频下载（带认证头降级重试）"""

import re
from datetime import datetime
from pathlib import Path

import httpx

from core.config import OUTPUT_DIR, SETTINGS


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)[:80]


def _guess_ext(url: str, default: str = ".png") -> str:
    path = url.split("?")[0].lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".gif"):
        if path.endswith(ext):
            return ext
    return default


def _auth_headers() -> dict:
    """获取 API 认证头"""
    return {"Authorization": f"Bearer {SETTINGS.api_key}"}


def download_image(url: str, filename: str | None = None) -> str:
    """下载图片到 output/images/（b64_json 模式下通常不需要此方法，作为降级备用）"""
    out_dir = OUTPUT_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        ext = _guess_ext(url, ".png")
        filename = f"img_{ts}{ext}"

    save_path = out_dir / filename

    # 策略1：无认证头下载（CDN 公开链接，带 Authorization 头反而可能 401）
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=60.0)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return str(save_path)
    except (httpx.HTTPError, httpx.TimeoutException):
        pass

    # 策略2：带认证头重试（部分私有 URL 可能需要）
    try:
        resp = httpx.get(url, headers=_auth_headers(), follow_redirects=True, timeout=60.0)
        if resp.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return str(save_path)
    except (httpx.HTTPError, httpx.TimeoutException):
        pass

    raise RuntimeError(f"图片下载失败: {url}")


def download_video(url: str, filename: str | None = None) -> str:
    """下载视频到 output/videos/，自动处理认证和降级"""
    out_dir = OUTPUT_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"vid_{ts}.mp4"

    save_path = out_dir / filename

    # 策略1：无认证头下载（CDN 公开链接，带 Authorization 头反而可能 401）
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=180.0)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return str(save_path)
    except (httpx.HTTPError, httpx.TimeoutException):
        pass

    # 策略2：带认证头重试（部分私有 URL 可能需要）
    try:
        resp = httpx.get(url, headers=_auth_headers(), follow_redirects=True, timeout=180.0)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return str(save_path)
    except (httpx.HTTPError, httpx.TimeoutException):
        pass

    raise RuntimeError(f"视频下载失败: {url}")
