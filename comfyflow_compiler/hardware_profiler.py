"""ComfyFlow Compiler — 硬件探测器"""

from __future__ import annotations
import platform
import subprocess
import re
from pathlib import Path
from typing import Optional

from .models import HardwareProfile, RuntimeBudget


# =============================================================================
# GPU 检测
# =============================================================================

def detect_gpu() -> HardwareProfile:
    """
    检测 GPU 硬件配置。
    优先级: pynvml > nvidia-smi > torch > fallback
    """
    profile = HardwareProfile(source="unknown")

    # 1. pynvml (最精确)
    try:
        return _detect_with_pynvml()
    except Exception:
        pass

    # 2. nvidia-smi (最通用)
    try:
        return _detect_with_nvidia_smi()
    except Exception:
        pass

    # 3. torch
    try:
        return _detect_with_torch()
    except Exception:
        pass

    # 4. fallback
    profile.source = "fallback"
    profile.error = "未检测到 NVIDIA GPU"
    return profile


def _detect_with_pynvml() -> HardwareProfile:
    import pynvml
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    name = pynvml.nvmlDeviceGetName(handle)
    if isinstance(name, bytes):
        name = name.decode()
    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    vram_gb = info.total / (1024**3)
    cap = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
    cc = f"{cap[0]}.{cap[1]}"
    pynvml.nvmlShutdown()
    return HardwareProfile(
        gpu_name=name,
        vram_gb=round(vram_gb, 1),
        ram_gb=_get_ram_gb(),
        cuda_available=True,
        compute_capability=cc,
        source="pynvml",
    )


def _detect_with_nvidia_smi() -> HardwareProfile:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError("nvidia-smi failed")

    line = result.stdout.strip().split("\n")[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 2:
        name = parts[0]
        # Parse VRAM: might be "12288 MiB" or just "12288"
        vram_str = parts[1].split()[0]
        try:
            vram_gb = float(vram_str) / 1024
        except ValueError:
            vram_gb = 0.0
        cc = parts[2] if len(parts) >= 3 else ""
        return HardwareProfile(
            gpu_name=name,
            vram_gb=round(vram_gb, 1),
            ram_gb=_get_ram_gb(),
            cuda_available=True,
            compute_capability=cc,
            source="nvidia-smi",
        )
    raise RuntimeError("unparsable nvidia-smi output")


def _detect_with_torch() -> HardwareProfile:
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("torch.cuda not available")
    idx = torch.cuda.current_device()
    name = torch.cuda.get_device_name(idx)
    try:
        vram_gb = torch.cuda.get_device_properties(idx).total_memory / (1024**3)
    except Exception:
        vram_gb = 0.0
    cap = torch.cuda.get_device_capability(idx)
    cc = f"{cap[0]}.{cap[1]}" if cap else ""
    return HardwareProfile(
        gpu_name=name,
        vram_gb=round(vram_gb, 1),
        ram_gb=_get_ram_gb(),
        cuda_available=True,
        compute_capability=cc,
        source="torch",
    )


def _get_ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return 0.0


# =============================================================================
# 预算计算
# =============================================================================

def compute_runtime_budget(hw: HardwareProfile) -> RuntimeBudget:
    """基于硬件配置计算运行时预算"""
    vram = hw.vram_gb

    if vram <= 0:
        return RuntimeBudget(tier="unknown", score=0.0)

    budget = RuntimeBudget(
        vram_gb=vram,
        max_batch_size=1,
    )

    if vram < 4:
        budget.tier = "minimal"
        budget.max_resolution = "512x512"
        budget.score = 1.0
    elif vram < 6:
        budget.tier = "low"
        budget.max_resolution = "512x768"
        budget.supports_sd15 = True
        budget.supports_flux_gguf = True  # NF4/Q4 量化 Flux
        budget.score = 2.5
    elif vram < 8:
        budget.tier = "low_plus"
        budget.max_resolution = "768x768"
        budget.supports_sd15 = True
        budget.supports_upscale = True
        budget.supports_flux_gguf = True
        budget.supports_wan = True        # Wan 1.3B
        budget.supports_ltx = True        # LTX fp8
        budget.score = 4.0
    elif vram < 12:
        budget.tier = "medium"
        budget.max_resolution = "1024x1024"
        budget.supports_sdxl = True
        budget.supports_sd15 = True
        budget.supports_upscale = True
        budget.supports_controlnet = 1
        budget.supports_flux_gguf = True  # GGUF Q5/Q8
        budget.supports_wan = True
        budget.supports_ltx = True
        budget.score = 5.5
    elif vram < 16:
        budget.tier = "medium_plus"
        budget.max_resolution = "1024x1024"
        budget.supports_sdxl = True
        budget.supports_refiner = True
        budget.supports_upscale = True
        budget.supports_controlnet = 2
        budget.supports_flux = True       # Flux FP8 cautious
        budget.supports_flux_gguf = True
        budget.supports_wan = True
        budget.supports_ltx = True
        budget.score = 7.0
    elif vram < 24:
        budget.tier = "high"
        budget.max_resolution = "1024x1536"
        budget.supports_sdxl = True
        budget.supports_refiner = True
        budget.supports_upscale = True
        budget.supports_controlnet = 3
        budget.supports_video = True
        budget.supports_flux = True       # Flux FP8/INT8 主力
        budget.supports_flux_gguf = True
        budget.supports_wan = True
        budget.supports_ltx = True
        budget.score = 8.5
    else:
        budget.tier = "ultra"
        budget.max_resolution = "1024x1792"
        budget.supports_sdxl = True
        budget.supports_flux = True       # Flux FP16 full
        budget.supports_flux_gguf = True
        budget.supports_refiner = True
        budget.supports_upscale = True
        budget.supports_controlnet = 4
        budget.supports_video = True
        budget.supports_wan = True        # Wan 14B full
        budget.supports_ltx = True        # LTX full + upscale
        budget.max_batch_size = 2
        budget.score = 10.0

    return budget
