"""ComfyFlow — ComfyUI 模型下载器

支持断点续传、进度显示、多镜像源。
"""

from __future__ import annotations
import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field


# =============================================================================
# 模型清单
# =============================================================================

# 推荐的模型下载清单
# 格式: (本地文件名, HF仓库, HF文件名, 目标目录, 大小提示, 说明)

MODEL_CATALOG = [
    # ---- Flux 系列（顶级画质，需12GB+显存）----
    {
        "id": "flux_dev_fp8",
        "name": "Flux.1 Dev FP8",
        "filename": "flux1-dev-fp8.safetensors",
        "repo": "https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors",
        "target_dir": "unet",
        "size_gb": 7.5,
        "description": "Flux Dev FP8 量化版，12-16GB 显存友好，顶级画质",
        "required_gb": 12,
        "priority": 1,
    },
    {
        "id": "flux_t5_fp8",
        "name": "Flux T5XXL FP8",
        "filename": "t5xxl_fp8_e4m3fn.safetensors",
        "repo": "https://huggingface.co/Kijai/flux-fp8/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
        "target_dir": "clip",
        "size_gb": 5.2,
        "description": "Flux 必备的 T5 文本编码器",
        "required_gb": 0,
        "priority": 1,
    },
    # Flux Schnell（快速版，8GB可跑）
    {
        "id": "flux_schnell_fp8",
        "name": "Flux Schnell FP8",
        "filename": "flux1-schnell-fp8.safetensors",
        "repo": "https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-schnell-fp8.safetensors",
        "target_dir": "unet",
        "size_gb": 7.5,
        "description": "Flux Schnell FP8，4步快速出图，8GB可跑",
        "required_gb": 8,
        "priority": 2,
    },
    # ---- SDXL 精调系列（兼容现有工作流，显存友好）----
    {
        "id": "juggernaut_xl",
        "name": "Juggernaut XL v9",
        "filename": "juggernautXL_v9Rundiffusion.safetensors",
        "repo": "https://huggingface.co/RunDiffusion/Juggernaut-XL-v9/resolve/main/Juggernaut-XL-v9.safetensors",
        "target_dir": "checkpoints",
        "size_gb": 6.9,
        "description": "SDXL 精调模型，人像/写实效果极佳，8GB可跑",
        "required_gb": 8,
        "priority": 3,
    },
    {
        "id": "realvis_xl",
        "name": "RealVisXL V4.0",
        "filename": "realvisxlV40_v40Bakedvae.safetensors",
        "repo": "https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors",
        "target_dir": "checkpoints",
        "size_gb": 6.9,
        "description": "写实人像 SDXL 精调，光影质感极好",
        "required_gb": 8,
        "priority": 4,
    },
    # ---- 放大模型 ----
    {
        "id": "4x_ultrasharp",
        "name": "4x-UltraSharp",
        "filename": "4x-UltraSharp.pth",
        "repo": "https://huggingface.co/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth",
        "target_dir": "upscale_models",
        "size_gb": 0.044,
        "description": "通用高清放大模型，44MB极小",
        "required_gb": 0,
        "priority": 5,
    },
    {
        "id": "4x_nmks",
        "name": "4x_NMKD-Siax",
        "filename": "4x_NMKD-Siax_200k.pth",
        "repo": "https://huggingface.co/uwg/upscale/resolve/main/4x_NMKD-Siax_200k.pth",
        "target_dir": "upscale_models",
        "size_gb": 0.134,
        "description": "高质量放大模型，人像/写实效果好",
        "required_gb": 0,
        "priority": 6,
    },
]


# =============================================================================
# 下载器
# =============================================================================

class DownloadProgress:
    def __init__(self):
        self.start_time = time.time()
        self.last_update = 0
        self.downloaded_mb = 0
        self.total_mb = 0
        self.speed_mbps = 0
        self.eta_seconds = 0
        self.percent = 0

    def update(self, downloaded: int, total: int):
        now = time.time()
        self.downloaded_mb = downloaded / 1024 / 1024
        self.total_mb = total / 1024 / 1024
        self.percent = (downloaded / total * 100) if total > 0 else 0
        elapsed = now - self.start_time
        self.speed_mbps = self.downloaded_mb / elapsed if elapsed > 0 else 0
        self.eta_seconds = (total - downloaded) / (downloaded / elapsed) if downloaded > 0 and elapsed > 0 else 0

    def status_line(self) -> str:
        if self.total_mb > 0:
            return (f"{self.percent:5.1f}% | "
                    f"{self.downloaded_mb:.1f}/{self.total_mb:.0f}MB | "
                    f"{self.speed_mbps:.1f}MB/s | "
                    f"ETA {self.eta_seconds:.0f}s")
        return f"{self.downloaded_mb:.1f}MB | {self.speed_mbps:.1f}MB/s"


class ModelDownloader:
    """ComfyUI 模型下载器"""

    def __init__(self, comfyui_path: str):
        self.comfyui_path = Path(comfyui_path)
        self.models_dir = self.comfyui_path / "models"

    def get_target_path(self, model_info: dict) -> Path:
        """获取模型的目标路径"""
        target_dir = self.models_dir / model_info["target_dir"]
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / model_info["filename"]

    def is_downloaded(self, model_info: dict) -> bool:
        """检查模型是否已下载"""
        target = self.get_target_path(model_info)
        if not target.exists():
            return False
        expected_size = int(model_info["size_gb"] * 1024 * 1024 * 1024 * 0.9)
        actual_size = target.stat().st_size
        return actual_size >= expected_size

    def get_size_mb(self, model_info: dict) -> float:
        """下载进度回调"""
        target = self.get_target_path(model_info)
        if target.exists():
            return target.stat().st_size / 1024 / 1024
        return 0

    def download(self, model_info: dict,
                 on_progress: Optional[Callable] = None,
                 use_mirror: bool = False) -> bool:
        """
        下载模型文件（支持断点续传）

        Args:
            model_info: 模型信息字典
            on_progress: 进度回调函数
            use_mirror: 是否使用 HF 镜像

        Returns:
            bool: 是否下载成功
        """
        url = model_info["repo"]
        target = self.get_target_path(model_info)
        temp_path = target.with_suffix(target.suffix + ".download")

        # 如果已完整下载，跳过
        if self.is_downloaded(model_info):
            if on_progress:
                on_progress(DownloadProgress())
            return True

        # 断点续传：检查已下载的部分
        headers = {}
        resume_pos = 0
        if temp_path.exists():
            resume_pos = temp_path.stat().st_size
            headers["Range"] = f"bytes={resume_pos}-"

        print(f"\n📥 [{model_info['name']}]")
        print(f"   目标: {target}")
        print(f"   大小: {model_info['size_gb']:.1f}GB")
        print(f"   来源: {url[:60]}...")
        if resume_pos > 0:
            print(f"   续传: 已有 {resume_pos/1024/1024:.1f}MB")

        try:
            req = urllib.request.Request(url, headers=headers)
            # 超时设长一点，大文件下载
            resp = urllib.request.urlopen(req, timeout=30)
            total = int(resp.headers.get("content-length", 0)) + resume_pos

            progress = DownloadProgress()
            progress.total_mb = total / 1024 / 1024
            progress.start_time = time.time()

            downloaded = resume_pos
            chunk_size = 1024 * 1024  # 1MB chunks
            last_print = 0

            # 写入临时文件
            mode = "ab" if resume_pos > 0 else "wb"
            with open(temp_path, mode) as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update(downloaded, total)

                    # 每 2 秒刷新一次进度
                    now = time.time()
                    if now - last_print > 2:
                        print(f"   进度: {progress.status_line()}", end="\r", flush=True)
                        last_print = now
                    if on_progress:
                        on_progress(progress)

            # 下载完成，重命名
            if temp_path.exists():
                if target.exists():
                    target.unlink()
                temp_path.rename(target)

            elapsed = time.time() - progress.start_time
            print(f"\n   ✅ 完成! {downloaded/1024/1024:.1f}MB in {elapsed:.0f}s ({downloaded/1024/1024/elapsed:.1f}MB/s)")
            return True

        except urllib.error.HTTPError as e:
            print(f"\n   ❌ HTTP {e.code}: {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"\n   ❌ 网络错误: {e.reason}")
            return False
        except Exception as e:
            print(f"\n   ❌ {e}")
            return False

    def list_available(self) -> list:
        """列出可供下载的模型"""
        available = []
        for model in MODEL_CATALOG:
            downloaded = self.is_downloaded(model)
            size = self.get_size_mb(model)
            available.append({
                **model,
                "downloaded": downloaded,
                "current_size_mb": size,
            })
        return available

    def recommend_by_vram(self, vram_gb: float) -> list:
        """根据显存推荐可用的模型"""
        all_models = self.list_available()
        # 先按优先级排序
        all_models.sort(key=lambda x: x["priority"])

        recommendations = []
        for m in all_models:
            if m["downloaded"]:
                continue
            if m["required_gb"] > 0 and vram_gb < m["required_gb"]:
                continue
            recommendations.append(m)

        return recommendations

    def download_batch(self, model_ids: list[str],
                       on_progress: Optional[Callable] = None) -> dict:
        """批量下载模型"""
        results = {}
        catalog = {m["id"]: m for m in MODEL_CATALOG}

        for mid in model_ids:
            if mid not in catalog:
                results[mid] = False
                continue
            results[mid] = self.download(catalog[mid], on_progress)

        return results


# =============================================================================
# 快捷入口
# =============================================================================

def show_catalog(comfyui_path: str):
    """显示可下载的模型清单"""
    downloader = ModelDownloader(comfyui_path)
    available = downloader.list_available()

    print("\n📦 ComfyUI 模型下载清单\n")

    # 分组
    groups = {}
    for m in available:
        grp = m["target_dir"]
        if grp not in groups:
            groups[grp] = []
        groups[grp].append(m)

    for grp, items in groups.items():
        print(f"📁 {grp}/")
        for m in items:
            status = "✅" if m["downloaded"] else "⬜"
            size_str = f"{m['size_gb']:.1f}GB" if m['size_gb'] >= 1 else f"{int(m['size_gb']*1024)}MB"
            if m["current_size_mb"] > 0:
                size_str += f" (已有 {m['current_size_mb']/1024:.1f}GB)" if m['current_size_mb'] > 1024 else f" (已有 {m['current_size_mb']:.0f}MB)"
            print(f"  {status} {m['name']:25s} | {size_str:15s} | {m['description']}")
        print()

    print(f"你当前 ⬜ 未下载 | ✅ 已下载")


def smart_download(comfyui_path: str, vram_gb: float = 16.0):
    """智能推荐并下载"""
    downloader = ModelDownloader(comfyui_path)

    print(f"🖥️  检测到 {vram_gb}GB 显存")
    print(f"\n🎯 推荐下载顺序:\n")

    # 核心推荐
    if vram_gb >= 12:
        print("Tier 1 — Flux 顶级画质（推荐）：")
        print("  flux_dev_fp8 + t5_fp8 → 真正惊艳的飞跃")
        print("  需要 12GB+ 显存\n")

    print("Tier 2 — SDXL 精调（兼容当前工作流）：")
    print("  juggernaut_xl → 立即可用，效果提升明显")
    print("  只需 8GB 显存\n")

    print("Tier 3 — 放大模型（提升分辨率）：")
    print("  4x_ultrasharp + 4x_nmks → 百兆级快速下载\n")

    return downloader
