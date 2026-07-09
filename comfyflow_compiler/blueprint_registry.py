"""ComfyFlow Compiler — 蓝图注册表 + 场景配方"""

from __future__ import annotations
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .models import Blueprint, Recipe, BlueprintRequirement


# =============================================================================
# 内置场景配方
# =============================================================================

BUILTIN_RECIPES: Dict[str, Recipe] = {
    "cinematic_realistic": Recipe(
        name="cinematic_realistic",
        user_label="电影感写实图片",
        description="电影级光影和色彩的真实感图像",
        fits=["电影", "写实", "真实", "摄影", "照片", "大片", "cinematic", "realistic"],
        preferred_blueprints=["txt2img_sdxl_high_quality", "txt2img_sdxl_basic", "txt2img_sd15_basic"],
        default_quality_mode="high",
    ),
    "anime_character": Recipe(
        name="anime_character",
        user_label="二次元角色图",
        description="动漫风格的插画角色",
        fits=["动漫", "二次元", "anime", "角色", "插画", "日系"],
        preferred_blueprints=["txt2img_sdxl_basic", "txt2img_sd15_basic"],
        default_quality_mode="balanced",
    ),
    "cyberpunk_scene": Recipe(
        name="cyberpunk_scene",
        user_label="赛博朋克场景",
        description="霓虹光影的未来科幻场景",
        fits=["赛博", "cyberpunk", "未来", "科幻", "霓虹", "机械"],
        preferred_blueprints=["txt2img_sdxl_high_quality", "txt2img_sdxl_basic"],
        default_quality_mode="high",
    ),
    "product_photo": Recipe(
        name="product_photo",
        user_label="产品摄影图",
        description="商品展示、白底图、棚拍效果",
        fits=["产品", "商品", "电商", "白底", "展示"],
        preferred_blueprints=["txt2img_sdxl_basic", "txt2img_sd15_basic"],
        default_quality_mode="balanced",
    ),
    "portrait": Recipe(
        name="portrait",
        user_label="人像写真",
        description="人物肖像、写真风格",
        fits=["人像", "肖像", "写真", "人物"],
        preferred_blueprints=["txt2img_sdxl_high_quality", "txt2img_sdxl_basic"],
        default_quality_mode="high",
    ),
    "img2img_restyle": Recipe(
        name="img2img_restyle",
        user_label="参考图重绘",
        description="以一张图为基础改变风格",
        fits=["重绘", "改图", "换风格", "以图生图"],
        preferred_blueprints=["img2img_sdxl_basic", "img2img_sd15_basic"],
        default_quality_mode="balanced",
    ),
    "pose_control": Recipe(
        name="pose_control",
        user_label="姿态控制生成",
        description="按照指定姿态生成人物",
        fits=["姿态", "姿势", "骨架", "openpose", "动作"],
        preferred_blueprints=["txt2img_sdxl_basic", "txt2img_sd15_basic"],
        default_quality_mode="balanced",
    ),
    "video_short": Recipe(
        name="video_short",
        user_label="短视频镜头",
        description="生成短视频或动图片段",
        fits=["视频", "动图", "镜头", "动画"],
        preferred_blueprints=["ltx_full_t2v", "video_ltx_t2v", "video_wan_t2v"],
        default_quality_mode="balanced",
    ),

    # =========================================================================
    # 2026 新配方
    # =========================================================================

    "flux_quick": Recipe(
        name="flux_quick",
        user_label="Flux 快速生成",
        description="使用 Flux 模型快速出图，画质优秀",
        fits=["flux", "快速出图", "高质量", "下一代"],
        preferred_blueprints=["flux_module_t2v", "flux_schnell_fast", "flux_dev_fp8", "flux_gguf", "txt2img_sdxl_high_quality"],
        default_quality_mode="high",
    ),

    "flux_premium": Recipe(
        name="flux_premium",
        user_label="Flux 旗舰画质",
        description="Flux Dev FP16 最高质量方案",
        fits=["flux", "顶级", "旗舰", "专业"],
        preferred_blueprints=["flux_module_t2v", "flux_dev_fp8", "flux_schnell_fast", "txt2img_sdxl_high_quality"],
        default_quality_mode="cinematic",
    ),

    "video_wan": Recipe(
        name="video_wan",
        user_label="Wan 视频生成",
        description="基于 Wan 模型的文生视频/图生视频",
        fits=["视频", "wan", "wan视频", "动画"],
        preferred_blueprints=["video_wan_t2v", "video_wan_i2v"],
        default_quality_mode="balanced",
    ),

    "video_ltx": Recipe(
        name="video_ltx",
        user_label="LTX 视频生成",
        description="基于 LTX-2.3 的视频生成，支持竖屏",
        fits=["视频", "ltx", "ltx视频", "短视频"],
        preferred_blueprints=["auto_ltx_video", "ltx_full_t2v", "ltx_full_i2v", "video_ltx_t2v", "video_ltx_i2v"],
        default_quality_mode="balanced",
    ),
    
    # =========================================================================
    # 生产挖掘配方（从真实工作流自动发现）
    # =========================================================================

    "lipsync": Recipe(
        name="lipsync",
        user_label="数字人对口型",
        description="数字人视频对口型生成",
        fits=["数字人", "对口型", "lipsync", "说话", "讲话", "虚拟人"],
        preferred_blueprints=["auto_lipsync", "ltx_full_t2v"],
        default_quality_mode="balanced",
    ),
    "mined_flux": Recipe(
        name="mined_flux",
        user_label="Flux 生产级",
        description="从 15 个真实 Flux 工作流挖掘的生产方案",
        fits=["flux", "高质量", "生产级", "专业"],
        preferred_blueprints=["auto_flux", "flux_module_t2v", "flux_dev_fp8", "flux_schnell_fast"],
        default_quality_mode="high",
    ),
    "mined_ltx": Recipe(
        name="mined_ltx",
        user_label="LTX 生产级视频",
        description="从 31 个真实 LTX 工作流挖掘的视频方案",
        fits=["ltx", "视频"],
        preferred_blueprints=["auto_ltx_video", "ltx_full_t2v", "ltx_full_i2v"],
        default_quality_mode="balanced",
    ),
    "mined_wan": Recipe(
        name="mined_wan",
        user_label="Wan 生产级视频",
        description="从 7 个真实 Wan 工作流挖掘的视频方案",
        fits=["wan", "视频"],
        preferred_blueprints=["auto_wan_video", "video_wan_t2v"],
        default_quality_mode="balanced",
    ),
    "video_t2v_ltx": Recipe(
        name="video_t2v_ltx",
        user_label="文生视频 (LTX)",
        description="纯文本直接生成视频 — LTX",
        fits=["视频", "文生视频", "生成视频"],
        preferred_blueprints=["ltx_t2v_basic"],
        default_quality_mode="balanced",
    ),
    "video_t2v_wan": Recipe(
        name="video_t2v_wan",
        user_label="文生视频 (WAN)",
        description="纯文本直接生成视频 — WAN",
        fits=["视频", "文生视频", "生成视频"],
        preferred_blueprints=["wan_t2v_basic"],
        default_quality_mode="balanced",
    ),
}


# =============================================================================
# 内置蓝图
# =============================================================================

BUILTIN_BLUEPRINTS: Dict[str, Blueprint] = {
    "txt2img_sdxl_high_quality": Blueprint(
        name="txt2img_sdxl_high_quality",
        display_name="SDXL 高清生成",
        description="基于 SDXL 的高质量文生图，包含 Refiner 和放大",
        task_type="txt2img",
        style_tags=["cinematic", "realistic", "high-quality"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        optional_nodes=["LoraLoader", "UpscaleModelLoader", "ImageUpscaleWithModel"],
        required_models=["sd_xl_base"],
        min_vram_gb=10.0,
        min_budget_score=5.5,
        quality_score=0.9,
        chain_depth=0,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 30, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow"}},
        },
        edges=[("1", "model", "5", "model"), ("1", "clip", "2", "clip"), ("1", "clip", "3", "clip"),
               ("1", "vae", "6", "vae"), ("2", "conditioning", "5", "positive"),
               ("3", "conditioning", "5", "negative"), ("4", "latent", "5", "latent_image"),
               ("5", "latent", "6", "samples"), ("6", "image", "7", "images")],
    ),
    "txt2img_sdxl_basic": Blueprint(
        name="txt2img_sdxl_basic",
        display_name="SDXL 基础生成",
        description="基于 SDXL 的标准文生图",
        task_type="txt2img",
        style_tags=["general", "standard"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.75,
        chain_depth=1,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 25, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow"}},
        },
        edges=[("1", "model", "5", "model"), ("1", "clip", "2", "clip"), ("1", "clip", "3", "clip"),
               ("1", "vae", "6", "vae"), ("2", "conditioning", "5", "positive"),
               ("3", "conditioning", "5", "negative"), ("4", "latent", "5", "latent_image"),
               ("5", "latent", "6", "samples"), ("6", "image", "7", "images")],
    ),
    "txt2img_sd15_basic": Blueprint(
        name="txt2img_sd15_basic",
        display_name="SD1.5 基础生成",
        description="基于 SD1.5 的轻量文生图，低显存友好",
        task_type="txt2img",
        style_tags=["general", "lightweight"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        min_vram_gb=4.0,
        min_budget_score=1.0,
        quality_score=0.5,
        chain_depth=2,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow"}},
        },
        edges=[("1", "model", "5", "model"), ("1", "clip", "2", "clip"), ("1", "clip", "3", "clip"),
               ("1", "vae", "6", "vae"), ("2", "conditioning", "5", "positive"),
               ("3", "conditioning", "5", "negative"), ("4", "latent", "5", "latent_image"),
               ("5", "latent", "6", "samples"), ("6", "image", "7", "images")],
    ),
    "img2img_sdxl_basic": Blueprint(
        name="img2img_sdxl_basic",
        display_name="SDXL 图生图",
        description="基于参考图进行重绘",
        task_type="img2img",
        style_tags=["img2img"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "LoadImage", "VAEEncode", "KSampler", "VAEDecode", "SaveImage"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.7,
        chain_depth=1,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "LoadImage", "inputs": {"image": ""}},
            "5": {"class_type": "VAEEncode", "inputs": {"pixels": ("4", "image"), "vae": ("1", "vae")}},
            "6": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("5", "latent"),
                "seed": 0, "steps": 25, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 0.6
            }},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ("6", "latent"), "vae": ("1", "vae")}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ("7", "image"), "filename_prefix": "ComfyFlow"}},
        },
        edges=[("1", "model", "6", "model"), ("1", "clip", "2", "clip"), ("1", "clip", "3", "clip"),
               ("1", "vae", "5", "vae"), ("1", "vae", "7", "vae"),
               ("2", "conditioning", "6", "positive"), ("3", "conditioning", "6", "negative"),
               ("4", "image", "5", "pixels"), ("5", "latent", "6", "latent_image"),
               ("6", "latent", "7", "samples"), ("7", "image", "8", "images")],
    ),
    "img2img_sd15_basic": Blueprint(
        name="img2img_sd15_basic",
        display_name="SD1.5 图生图",
        description="轻量图生图重绘",
        task_type="img2img",
        style_tags=["img2img", "lightweight"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "LoadImage", "VAEEncode", "KSampler", "VAEDecode", "SaveImage"],
        min_vram_gb=4.0,
        min_budget_score=1.0,
        quality_score=0.45,
        chain_depth=2,
        nodes={},
        edges=[],
    ),
    "txt2img_minimal": Blueprint(
        name="txt2img_minimal",
        display_name="最简生成",
        description="最低配置保底方案，只含核心节点",
        task_type="txt2img",
        style_tags=["minimal"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        min_vram_gb=3.0,
        min_budget_score=0.5,
        quality_score=0.3,
        chain_depth=3,
        nodes={},
        edges=[],
    ),

    # =========================================================================
    # Flux 蓝图（2026 主力）
    # =========================================================================

    "flux_schnell_fast": Blueprint(
        name="flux_schnell_fast",
        display_name="Flux Schnell 快速出图",
        description="Flux Schnell 4 步快速出图，低显存友好",
        task_type="txt2img",
        style_tags=["flux", "fast", "low-vram"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        optional_nodes=["LoraLoader"],
        required_models=["flux"],
        min_vram_gb=6.0,
        min_budget_score=2.5,
        quality_score=0.65,
        chain_depth=0,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow_Flux"}},
        },
        edges=[],
    ),

    "flux_dev_fp8": Blueprint(
        name="flux_dev_fp8",
        display_name="Flux Dev FP8 高清生成",
        description="Flux Dev FP8 主力高质量方案，16GB 显存友好",
        task_type="txt2img",
        style_tags=["flux", "high-quality"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["flux_fp8"],
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_score=0.88,
        chain_depth=0,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 25, "cfg": 3.5, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow_Flux"}},
        },
        edges=[],
    ),

    "flux_gguf": Blueprint(
        name="flux_gguf",
        display_name="Flux GGUF 量化方案",
        description="Flux GGUF Q4/Q5/Q8 量化版，低显存运行 Flux",
        task_type="txt2img",
        style_tags=["flux", "quantized", "low-vram"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["flux_gguf"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.7,
        chain_depth=1,
        nodes={
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("1", "clip")}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ("1", "model"), "positive": ("2", "conditioning"),
                "negative": ("3", "conditioning"), "latent_image": ("4", "latent"),
                "seed": 0, "steps": 20, "cfg": 3.5, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0
            }},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ("5", "latent"), "vae": ("1", "vae")}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ("6", "image"), "filename_prefix": "ComfyFlow_Flux"}},
        },
        edges=[],
    ),

    # =========================================================================
    # Wan Video 蓝图（2026 视频主力）
    # =========================================================================

    "video_wan_i2v": Blueprint(
        name="video_wan_i2v",
        display_name="Wan I2V 图生视频",
        description="基于 Wan2.1/2.2 的图生视频",
        task_type="video",
        style_tags=["video", "wan"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "LoadImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["wan_video"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.8,
        chain_depth=0,
        nodes={},
        edges=[],
    ),

    "video_wan_t2v": Blueprint(
        name="video_wan_t2v",
        display_name="Wan T2V 文生视频",
        description="基于 Wan2.1/2.2 的文生视频",
        task_type="video",
        style_tags=["video", "wan"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["wan_video"],
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_score=0.85,
        chain_depth=0,
        nodes={},
        edges=[],
    ),

    # =========================================================================
    # LTX Video 蓝图
    # =========================================================================

    "video_ltx_i2v": Blueprint(
        name="video_ltx_i2v",
        display_name="LTX I2V 图生视频",
        description="基于 LTX-2.3 的图生视频（支持 9:16 竖屏）",
        task_type="video",
        style_tags=["video", "ltx"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode", "CLIPTextEncode",
                        "LoadImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["ltx_video"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.78,
        chain_depth=0,
        nodes={},
        edges=[],
    ),

    "video_ltx_t2v": Blueprint(
        name="video_ltx_t2v",
        display_name="LTX T2V 文生视频",
        description="基于 LTX-2.3 的文生视频",
        task_type="video",
        style_tags=["video", "ltx"],
        required_nodes=["CheckpointLoaderSimple", "CLIPTextEncode",
                        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"],
        required_models=["ltx_video"],
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_score=0.82,
        chain_depth=0,
        nodes={},
        edges=[],
    ),

    # =========================================================================
    # 2026 新范式：Flux 模块化加载 + 高级采样链
    # =========================================================================

    "flux_module_t2v": Blueprint(
        name="flux_module_t2v",
        display_name="Flux 模块化生成",
        description="UNETLoader+CLIPLoader+VAELoader 模块化加载 + 高级采样链",
        task_type="txt2img",
        style_tags=["flux", "modular", "premium"],
        required_nodes=["UNETLoader", "CLIPLoader", "VAELoader",
                        "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLatentImage", "RandomNoise", "CFGGuider",
                        "KSamplerSelect", "ManualSigmas", "SamplerCustomAdvanced",
                        "VAEDecode", "SaveImage"],
        optional_nodes=["LoraLoaderModelOnly"],
        required_models=["flux", "flux_clip", "flux_vae"],
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_score=0.90,
        chain_depth=0,
        nodes={
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "", "weight_dtype": "fp8_e4m3fn"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "", "type": "flux"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": ""}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("2", "clip")}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ("2", "clip")}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "7": {"class_type": "RandomNoise", "inputs": {"seed": 0}},
            "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "9": {"class_type": "ManualSigmas", "inputs": {"sigma": "", "sigma_num": 20}},
            "10": {"class_type": "CFGGuider", "inputs": {
                "model": ("1", "model"), "positive": ("4", "conditioning"),
                "negative": ("5", "conditioning"), "cfg": 3.5
            }},
            "11": {"class_type": "SamplerCustomAdvanced", "inputs": {
                "noise": ("7", "noise"), "guider": ("10", "guider"),
                "sampler": ("8", "sampler"), "sigmas": ("9", "sigmas"),
                "model": ("1", "model"), "positive": ("4", "conditioning"),
                "negative": ("5", "conditioning"), "latent_image": ("6", "latent"),
            }},
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ("11", "output"), "vae": ("3", "vae")}},
            "13": {"class_type": "SaveImage", "inputs": {"images": ("12", "image"), "filename_prefix": "ComfyFlow_Flux"}},
        },
        edges=[],
    ),

    # =========================================================================
    # 2026 新范式：LTX 视频全链路
    # =========================================================================

    "ltx_full_t2v": Blueprint(
        name="ltx_full_t2v",
        display_name="LTX 文生视频全链路",
        description="基于 LTX-2.3 的完整文生视频链路",
        task_type="video",
        style_tags=["video", "ltx", "premium"],
        required_nodes=["UNETLoader", "CLIPLoader", "VAELoader",
                        "CLIPTextEncode", "CLIPTextEncode",
                        "EmptyLTXVLatentVideo", "LTXVConditioning",
                        "RandomNoise", "KSamplerSelect", "ManualSigmas",
                        "CFGGuider", "SamplerCustomAdvanced",
                        "VAEDecode", "VHS_VideoCombine"],
        optional_nodes=["LTXVCropGuides", "LoraLoaderModelOnly", "LTXVLatentUpsampler"],
        required_models=["ltx_video"],
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_score=0.88,
        chain_depth=0,
        nodes={},
        edges=[],
    ),

    "ltx_full_i2v": Blueprint(
        name="ltx_full_i2v",
        display_name="LTX 图生视频全链路",
        description="基于 LTX-2.3 的完整图生视频链路",
        task_type="video",
        style_tags=["video", "ltx", "img2video"],
        required_nodes=["UNETLoader", "CLIPLoader", "VAELoader",
                        "CLIPTextEncode", "CLIPTextEncode",
                        "LoadImage", "LTXVPreprocess",
                        "EmptyLTXVLatentVideo", "LTXVConditioning",
                        "RandomNoise", "KSamplerSelect", "ManualSigmas",
                        "CFGGuider", "SamplerCustomAdvanced",
                        "VAEDecode", "VHS_VideoCombine"],
        optional_nodes=["LTXVCropGuides", "LoraLoaderModelOnly"],
        required_models=["ltx_video"],
        min_vram_gb=10.0,
        min_budget_score=5.0,
        quality_score=0.86,
        chain_depth=0,
        nodes={},
        edges=[],
    ),
    "ltx_t2v_basic": Blueprint(
        name="ltx_t2v_basic",
        display_name="LTX 文生视频",
        description="基于 LTX 的文生视频",
        task_type="t2v",
        style_tags=["cinematic", "realistic"],
        required_nodes=["CLIPTextEncode", "LTXVideoSampler"],
        optional_nodes=["EmptyLatentVideo", "VAEDecode", "VHS_VideoCombine"],
        required_models=["ltx-video-2b-v0.9.safetensors"],
        min_vram_gb=16.0,
        min_budget_score=4.0,
        quality_score=0.7,
        chain_depth=1,
        nodes={},
        edges=[],
    ),
    "wan_t2v_basic": Blueprint(
        name="wan_t2v_basic",
        display_name="WAN 文生视频",
        description="基于 WAN 的文生视频",
        task_type="t2v",
        style_tags=["cinematic", "realistic"],
        required_nodes=["CLIPTextEncode", "WANVideoSampler"],
        optional_nodes=["VAEDecode", "VHS_VideoCombine"],
        required_models=["WAN2.1-T2V"],
        min_vram_gb=16.0,
        min_budget_score=4.0,
        quality_score=0.7,
        chain_depth=1,
        nodes={},
        edges=[],
    ),
}


# =============================================================================
# 蓝图要求（用于硬件感知选择）
# =============================================================================

BUILTIN_REQUIREMENTS: Dict[str, BlueprintRequirement] = {
    "txt2img_sdxl_high_quality": BlueprintRequirement(
        blueprint_name="txt2img_sdxl_high_quality",
        min_vram_gb=10.0,
        min_budget_score=5.5,
        quality_weight=1.0,
    ),
    "txt2img_sdxl_basic": BlueprintRequirement(
        blueprint_name="txt2img_sdxl_basic",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.8,
    ),
    "txt2img_sd15_basic": BlueprintRequirement(
        blueprint_name="txt2img_sd15_basic",
        min_vram_gb=4.0,
        min_budget_score=1.0,
        quality_weight=0.5,
    ),
    "img2img_sdxl_basic": BlueprintRequirement(
        blueprint_name="img2img_sdxl_basic",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.8,
    ),
    "img2img_sd15_basic": BlueprintRequirement(
        blueprint_name="img2img_sd15_basic",
        min_vram_gb=4.0,
        min_budget_score=1.0,
        quality_weight=0.5,
    ),
    "txt2img_minimal": BlueprintRequirement(
        blueprint_name="txt2img_minimal",
        min_vram_gb=3.0,
        min_budget_score=0.5,
        quality_weight=0.3,
    ),

    # Flux 方案
    "flux_schnell_fast": BlueprintRequirement(
        blueprint_name="flux_schnell_fast",
        min_vram_gb=6.0,
        min_budget_score=2.5,
        quality_weight=0.7,
    ),
    "flux_dev_fp8": BlueprintRequirement(
        blueprint_name="flux_dev_fp8",
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_weight=0.9,
    ),
    "flux_gguf": BlueprintRequirement(
        blueprint_name="flux_gguf",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.7,
    ),

    # Wan 视频
    "video_wan_i2v": BlueprintRequirement(
        blueprint_name="video_wan_i2v",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.8,
    ),
    "video_wan_t2v": BlueprintRequirement(
        blueprint_name="video_wan_t2v",
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_weight=0.85,
    ),

    # LTX 视频
    "video_ltx_i2v": BlueprintRequirement(
        blueprint_name="video_ltx_i2v",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.8,
    ),
    "video_ltx_t2v": BlueprintRequirement(
        blueprint_name="video_ltx_t2v",
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_weight=0.82,
    ),

    # =========================================================================
    # 2026 新范式要求
    # =========================================================================

    "flux_module_t2v": BlueprintRequirement(
        blueprint_name="flux_module_t2v",
        min_vram_gb=8.0,
        min_budget_score=4.0,
        quality_weight=0.85,
    ),
    "ltx_full_t2v": BlueprintRequirement(
        blueprint_name="ltx_full_t2v",
        min_vram_gb=12.0,
        min_budget_score=5.5,
        quality_weight=0.85,
    ),
    "ltx_full_i2v": BlueprintRequirement(
        blueprint_name="ltx_full_i2v",
        min_vram_gb=10.0,
        min_budget_score=5.0,
        quality_weight=0.83,
    ),
}


# =============================================================================
# 检索器
# =============================================================================

class BlueprintRegistry:
    """蓝图注册表，管理所有蓝图和配方"""

    def __init__(self):
        self.blueprints: Dict[str, Blueprint] = dict(BUILTIN_BLUEPRINTS)
        self.recipes: Dict[str, Recipe] = dict(BUILTIN_RECIPES)
        self.requirements: Dict[str, BlueprintRequirement] = dict(BUILTIN_REQUIREMENTS)

    def get_blueprint(self, name: str) -> Optional[Blueprint]:
        return self.blueprints.get(name)

    def get_recipe(self, name: str) -> Optional[Recipe]:
        return self.recipes.get(name)

    def get_requirement(self, name: str) -> Optional[BlueprintRequirement]:
        return self.requirements.get(name)

    def match_recipe(self, task_type: str, styles: List[str], subject: str) -> List[Recipe]:
        """根据任务特征匹配最合适的配方"""
        scored = []
        subject_lower = subject.lower()
        for recipe in self.recipes.values():
            score = 0
            # 任务类型匹配
            if recipe.preferred_blueprints:
                for bp_name in recipe.preferred_blueprints:
                    bp = self.blueprints.get(bp_name)
                    if bp and bp.task_type == task_type:
                        score += 3
            # 风格匹配
            for style in styles:
                if style in recipe.fits or any(f in recipe.fits for f in [style]):
                    score += 2
            # 关键词匹配
            for keyword in recipe.fits:
                if keyword in subject_lower:
                    score += 1
            if score > 0:
                scored.append((score, recipe))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored]

    def select_best_blueprint(self, task_type: str, recipe: Optional[Recipe],
                              budget_score: float, vram_gb: float,
                              has_sdxl: bool = False, has_sd15: bool = False,
                              has_flux: bool = False, has_ltx: bool = False,
                              has_wan: bool = False) -> Optional[Blueprint]:
        """在硬件约束内选择最高质量的蓝图"""
        candidates = []

        # 优先从 recipe 的 preferred_blueprints 选
        blueprints_to_check = []
        if recipe:
            for bp_name in recipe.preferred_blueprints:
                bp = self.blueprints.get(bp_name)
                if bp:
                    blueprints_to_check.append(bp)
        else:
            blueprints_to_check = [bp for bp in self.blueprints.values()
                                   if bp.task_type == task_type]

        for bp in blueprints_to_check:
            req = self.requirements.get(bp.name)
            if not req:
                continue

            # 硬件预算检查
            if budget_score < req.min_budget_score:
                continue
            if vram_gb < req.min_vram_gb:
                continue

            # 环境检查
            bp_name_lower = bp.name.lower()
            if "sdxl" in bp_name_lower and not has_sdxl:
                continue
            if "sd15" in bp_name_lower and not has_sd15:
                continue
            if "flux" in bp_name_lower and not has_flux:
                continue
            if "ltx" in bp_name_lower and not has_ltx and not has_flux:
                # 没有 LTX 模型但有 Flux 也能用 Flux 方案替代
                if "flux" not in bp_name_lower:
                    continue
            if "wan" in bp_name_lower and not has_wan:
                continue

            # 计算最终得分 = 质量分 * 权重
            score = bp.quality_score * req.quality_weight
            candidates.append((score, bp))

        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1] if candidates else None

    def get_fallback_chain(self, recipe: Recipe, budget_score: float,
                           vram_gb: float, has_sdxl: bool, has_sd15: bool) -> List[Blueprint]:
        """获取降级链：从最佳到保底"""
        chain = []
        for bp_name in recipe.fallback_chain if recipe.fallback_chain else recipe.preferred_blueprints:
            bp = self.blueprints.get(bp_name)
            if bp:
                req = self.requirements.get(bp.name)
                if req and budget_score >= req.min_budget_score and vram_gb >= req.min_vram_gb:
                    chain.append(bp)
        return chain
