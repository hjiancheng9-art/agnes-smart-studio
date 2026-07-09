"""ComfyFlow Compiler — 参数表

所有硬编码参数的集中管理，带单位、范围和原因说明。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ParameterDef:
    """参数定义"""
    default: Any
    min: Optional[Any] = None
    max: Optional[Any] = None
    unit: str = ""
    reason: str = ""
    quality_overrides: Optional[Dict[str, Any]] = None  # quality_mode 覆盖


PARAMETERS: Dict[str, ParameterDef] = {
    # =========================================================================
    # SDXL 参数
    # =========================================================================
    "sdxl_steps": ParameterDef(
        default=25, min=15, max=40, unit="步",
        reason="SDXL 20-30 步质量趋于收敛，低于 15 步细节不足",
        quality_overrides={"fast": 18, "high": 30, "cinematic": 35},
    ),
    "sdxl_cfg": ParameterDef(
        default=7.0, min=3.0, max=12.0, unit="",
        reason="SDXL 典型 CFG 7-9，低于 5 会欠约束，高于 12 会过饱和",
        quality_overrides={"fast": 6.0, "high": 7.5, "cinematic": 8.0},
    ),
    "sdxl_sampler": ParameterDef(
        default="euler", unit="", reason="euler 是最通用的采样器，质量和速度均衡"
    ),
    "sdxl_scheduler": ParameterDef(
        default="normal", unit="", reason="normal 调度器适合大多数场景"
    ),

    # =========================================================================
    # SD1.5 参数
    # =========================================================================
    "sd15_steps": ParameterDef(
        default=20, min=10, max=40, unit="步",
        reason="SD1.5 收敛更快，20 步已足够",
        quality_overrides={"fast": 15, "high": 28, "cinematic": 30},
    ),
    "sd15_cfg": ParameterDef(
        default=7.0, min=3.0, max=15.0, unit="",
        reason="SD1.5 典型 CFG 7",
        quality_overrides={"fast": 6.0, "high": 8.0, "cinematic": 8.5},
    ),

    # =========================================================================
    # Flux 参数
    # =========================================================================
    "flux_steps": ParameterDef(
        default=25, min=4, max=50, unit="步",
        reason="Flux 需要更多步数才能收敛，Schnell 模式 4 步即可",
        quality_overrides={"fast": 4, "balanced": 20, "high": 25, "cinematic": 30},
    ),
    "flux_cfg": ParameterDef(
        default=3.5, min=1.0, max=10.0, unit="",
        reason="Flux 使用低 CFG（1-5），高于 5 反而降低质量",
        quality_overrides={"fast": 1.0, "balanced": 3.5, "high": 3.5, "cinematic": 4.0},
    ),
    "flux_sampler": ParameterDef(
        default="euler", unit="", reason="Flux 官方推荐 euler"
    ),
    "flux_scheduler": ParameterDef(
        default="simple", unit="", reason="Flux 用 simple 调度器"
    ),
    "flux_weight_dtype": ParameterDef(
        default="fp8_e4m3fn", unit="",
        reason="FP8 在质量和显存之间最佳平衡"
    ),

    # =========================================================================
    # LTX 视频参数
    # =========================================================================
    "ltx_steps": ParameterDef(
        default=25, min=10, max=50, unit="步",
        reason="LTX 视频需要 20-30 步保证画面连贯性",
        quality_overrides={"fast": 15, "high": 30, "cinematic": 40},
    ),
    "ltx_cfg": ParameterDef(
        default=4.0, min=2.0, max=8.0, unit="",
        reason="LTX 推荐 CFG 3-5",
    ),
    "ltx_frame_rate": ParameterDef(
        default=24, min=8, max=30, unit="fps",
        reason="24fps 是标准电影帧率",
    ),
    "ltx_length": ParameterDef(
        default=49, min=25, max=97, unit="帧",
        reason="49 帧 ≈ 2 秒 @24fps，平衡质量和生成时间",
    ),

    # =========================================================================
    # Wan 视频参数
    # =========================================================================
    "wan_steps": ParameterDef(
        default=25, min=10, max=50, unit="步",
        reason="Wan 推荐 20-30 步",
    ),
    "wan_cfg": ParameterDef(
        default=4.0, min=2.0, max=8.0, unit="",
        reason="Wan 推荐 CFG 3-5",
    ),

    # =========================================================================
    # 通用参数
    # =========================================================================
    "denoise_strength": ParameterDef(
        default=1.0, min=0.0, max=1.0, unit="",
        reason="1.0 = 全新生成，0.5-0.7 = 图生图重绘",
        quality_overrides={"img2img": 0.6},
    ),
    "batch_size": ParameterDef(
        default=1, min=1, max=4, unit="张",
        reason="batch_size > 1 需要更多显存",
    ),
}


def get_param(name: str, quality_mode: str = "balanced") -> Any:
    """获取参数值，支持 quality_mode 覆盖"""
    param = PARAMETERS.get(name)
    if not param:
        raise KeyError(f"参数 '{name}' 未定义")

    if param.quality_overrides and quality_mode in param.quality_overrides:
        return param.quality_overrides[quality_mode]

    return param.default


def get_param_def(name: str) -> ParameterDef:
    """获取参数定义"""
    return PARAMETERS[name]


def resolve_resolution(aspect_ratio: str, budget_score: float) -> tuple:
    """根据宽高比和预算得分计算分辨率"""
    base_size_map = {
        10.0: (1024, 1792), 8.5: (1024, 1536), 7.0: (1024, 1024),
        5.5: (1024, 1024), 4.0: (768, 768), 2.5: (512, 768), 1.0: (512, 512),
    }
    # 找到不超过 budget 的最大分辨率
    max_w, max_h = 512, 512
    for score, (w, h) in sorted(base_size_map.items(), reverse=True):
        if budget_score >= score:
            max_w, max_h = w, h
            break

    ratio_map = {
        "1:1": (1, 1), "3:2": (3, 2), "4:3": (4, 3),
        "16:9": (16, 9), "9:16": (9, 16), "2:3": (2, 3), "3:4": (3, 4),
    }
    if aspect_ratio not in ratio_map:
        return max_w, max_h

    rw, rh = ratio_map[aspect_ratio]
    area = max_w * max_h
    h = int((area * rh / rw) ** 0.5)
    w = int(h * rw / rh)
    w = (w // 8) * 8
    h = (h // 8) * 8
    return max(w, 64), max(h, 64)
