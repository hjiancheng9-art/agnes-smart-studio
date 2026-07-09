"""ComfyFlow Compiler — 节点能力图谱"""

from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path

from .models import NodeContract


# =============================================================================
# 内置节点能力图谱
# =============================================================================

BUILTIN_NODES: Dict[str, NodeContract] = {
    "KSampler": NodeContract(
        class_type="KSampler",
        category="sampling",
        display_name="K采样器",
        inputs=["model", "positive", "negative", "latent_image"],
        outputs=["latent"],
        task_fit=["txt2img", "img2img"],
        quality_role="core_sampling",
        required=True,
        risk="high_if_bad_params",
        preferred_params={"steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal"},
        vram_cost="medium",
    ),
    "KSamplerAdvanced": NodeContract(
        class_type="KSamplerAdvanced",
        category="sampling",
        display_name="高级K采样器",
        inputs=["model", "add_noise", "noise_seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative", "latent_image", "start_at_step", "end_at_step", "return_with_leftover_noise"],
        outputs=["latent"],
        task_fit=["txt2img", "img2img"],
        quality_role="core_sampling",
        required=False,
        risk="high_if_bad_params",
        vram_cost="medium",
    ),
    "CLIPTextEncode": NodeContract(
        class_type="CLIPTextEncode",
        category="conditioning",
        display_name="CLIP文本编码",
        inputs=["text", "clip"],
        outputs=["conditioning"],
        task_fit=["txt2img", "img2img", "controlnet"],
        quality_role="conditioning",
        required=True,
        risk="low",
        vram_cost="low",
    ),
    "VAEDecode": NodeContract(
        class_type="VAEDecode",
        category="latent",
        display_name="VAE解码",
        inputs=["samples", "vae"],
        outputs=["image"],
        task_fit=["txt2img", "img2img"],
        quality_role="decode",
        required=True,
        risk="low",
        vram_cost="low",
    ),
    "VAEEncode": NodeContract(
        class_type="VAEEncode",
        category="latent",
        display_name="VAE编码",
        inputs=["pixels", "vae"],
        outputs=["latent"],
        task_fit=["img2img"],
        quality_role="encode",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "EmptyLatentImage": NodeContract(
        class_type="EmptyLatentImage",
        category="latent",
        display_name="空潜变量",
        inputs=["width", "height", "batch_size"],
        outputs=["latent"],
        task_fit=["txt2img"],
        quality_role="init_latent",
        required=True,
        risk="low",
        preferred_params={"width": 1024, "height": 1024, "batch_size": 1},
        vram_cost="low",
    ),
    "SaveImage": NodeContract(
        class_type="SaveImage",
        category="io",
        display_name="保存图像",
        inputs=["images", "filename_prefix"],
        outputs=[],
        task_fit=["txt2img", "img2img", "upscale"],
        quality_role="output",
        required=True,
        risk="low",
        vram_cost="low",
    ),
    "LoadImage": NodeContract(
        class_type="LoadImage",
        category="io",
        display_name="加载图像",
        inputs=["image"],
        outputs=["image", "mask"],
        task_fit=["img2img", "controlnet"],
        quality_role="input",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "ControlNetLoader": NodeContract(
        class_type="ControlNetLoader",
        category="controlnet",
        display_name="ControlNet加载器",
        inputs=["control_net_name"],
        outputs=["control_net"],
        task_fit=["controlnet"],
        quality_role="control",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "ControlNetApply": NodeContract(
        class_type="ControlNetApply",
        category="controlnet",
        display_name="ControlNet应用",
        inputs=["conditioning", "control_net", "image", "strength"],
        outputs=["conditioning"],
        task_fit=["controlnet"],
        quality_role="control",
        required=False,
        risk="medium",
        preferred_params={"strength": 0.8},
        vram_cost="medium",
    ),
    "UpscaleModelLoader": NodeContract(
        class_type="UpscaleModelLoader",
        category="upscale",
        display_name="放大模型加载器",
        inputs=["model_name"],
        outputs=["upscale_model"],
        task_fit=["upscale"],
        quality_role="upscale",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "ImageUpscaleWithModel": NodeContract(
        class_type="ImageUpscaleWithModel",
        category="upscale",
        display_name="模型放大图像",
        inputs=["upscale_model", "image"],
        outputs=["image"],
        task_fit=["upscale"],
        quality_role="upscale",
        required=False,
        risk="low",
        vram_cost="high",
    ),
    "CheckpointLoaderSimple": NodeContract(
        class_type="CheckpointLoaderSimple",
        category="io",
        display_name="checkpoint加载器",
        inputs=["ckpt_name"],
        outputs=["model", "clip", "vae"],
        task_fit=["txt2img", "img2img", "controlnet"],
        quality_role="model_loading",
        required=True,
        risk="low",
        vram_cost="low",
    ),
    "LoraLoader": NodeContract(
        class_type="LoraLoader",
        category="conditioning",
        display_name="LoRA加载器",
        inputs=["model", "clip", "lora_name", "strength_model", "strength_clip"],
        outputs=["model", "clip"],
        task_fit=["txt2img", "img2img"],
        quality_role="enhancement",
        required=False,
        risk="low",
        preferred_params={"strength_model": 0.6, "strength_clip": 0.6},
        vram_cost="low",
    ),

    # =============================================================================
    # 2026 新增节点：Flux/LTX 模块化加载
    # =============================================================================

    "UNETLoader": NodeContract(
        class_type="UNETLoader",
        category="io",
        display_name="UNET加载器（Flux用）",
        inputs=["unet_name", "weight_dtype"],
        outputs=["model"],
        task_fit=["txt2img", "img2img", "video", "flux"],
        quality_role="model_loading",
        required=True,
        risk="low",
        vram_cost="high",
    ),
    "UnetLoaderGGUF": NodeContract(
        class_type="UnetLoaderGGUF",
        category="io",
        display_name="UNET加载器GGUF（量化Flux用）",
        inputs=["unet_name"],
        outputs=["model"],
        task_fit=["txt2img", "flux"],
        quality_role="model_loading",
        required=False,
        risk="low",
        vram_cost="medium",
    ),
    "CLIPLoader": NodeContract(
        class_type="CLIPLoader",
        category="io",
        display_name="CLIP加载器",
        inputs=["clip_name", "type"],
        outputs=["clip"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="model_loading",
        required=True,
        risk="low",
        vram_cost="low",
    ),
    "DualCLIPLoader": NodeContract(
        class_type="DualCLIPLoader",
        category="io",
        display_name="双CLIP加载器（Flux用）",
        inputs=["clip_name1", "clip_name2", "type"],
        outputs=["clip"],
        task_fit=["txt2img", "flux"],
        quality_role="model_loading",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "VAELoader": NodeContract(
        class_type="VAELoader",
        category="io",
        display_name="VAE加载器",
        inputs=["vae_name"],
        outputs=["vae"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="model_loading",
        required=True,
        risk="low",
        vram_cost="low",
    ),

    # =============================================================================
    # 高级采样链
    # =============================================================================

    "SamplerCustomAdvanced": NodeContract(
        class_type="SamplerCustomAdvanced",
        category="sampling",
        display_name="高级自定义采样",
        inputs=["noise", "guider", "sampler", "sigmas", "model", "positive", "negative", "latent_image"],
        outputs=["output"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="core_sampling",
        required=False,
        risk="high_if_bad_params",
        vram_cost="medium",
    ),
    "RandomNoise": NodeContract(
        class_type="RandomNoise",
        category="sampling",
        display_name="随机噪声",
        inputs=["seed"],
        outputs=["noise"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="noise",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "ManualSigmas": NodeContract(
        class_type="ManualSigmas",
        category="sampling",
        display_name="手动Sigma调度",
        inputs=["sigma", "sigma_num"],
        outputs=["sigmas"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="sigmas",
        required=False,
        risk="medium",
        vram_cost="low",
    ),
    "CFGGuider": NodeContract(
        class_type="CFGGuider",
        category="sampling",
        display_name="CFG引导器",
        inputs=["model", "positive", "negative", "cfg"],
        outputs=["guider"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="guider",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "KSamplerSelect": NodeContract(
        class_type="KSamplerSelect",
        category="sampling",
        display_name="采样器选择",
        inputs=["sampler_name"],
        outputs=["sampler"],
        task_fit=["txt2img", "img2img", "video", "flux", "ltx"],
        quality_role="sampler_select",
        required=False,
        risk="low",
        vram_cost="low",
    ),

    # =============================================================================
    # LTX 视频节点
    # =============================================================================

    "EmptyLTXVLatentVideo": NodeContract(
        class_type="EmptyLTXVLatentVideo",
        category="latent",
        display_name="LTX空视频潜变量",
        inputs=["width", "height", "length", "batch_size"],
        outputs=["latent"],
        task_fit=["video", "ltx"],
        quality_role="init_latent",
        required=False,
        risk="low",
        vram_cost="medium",
    ),
    "LTXVConditioning": NodeContract(
        class_type="LTXVConditioning",
        category="conditioning",
        display_name="LTX视频条件",
        inputs=["positive", "negative", "clip_sequence", "frame_rate", "start_percent", "end_percent"],
        outputs=["positive", "negative"],
        task_fit=["video", "ltx"],
        quality_role="conditioning",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "LTXVImgToVideoInplace": NodeContract(
        class_type="LTXVImgToVideoInplace",
        category="video",
        display_name="LTX图生视频",
        inputs=["image", "model", "positive", "negative", "vae", "latent", "seed", "steps", "cfg", "denoise"],
        outputs=["latent", "image"],
        task_fit=["video", "ltx"],
        quality_role="video_gen",
        required=False,
        risk="medium",
        vram_cost="high",
    ),
    "LTXVPreprocess": NodeContract(
        class_type="LTXVPreprocess",
        category="video",
        display_name="LTX预处理",
        inputs=["image", "width", "height", "length"],
        outputs=["image", "width", "height", "length"],
        task_fit=["video", "ltx"],
        quality_role="video_preprocess",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "LTXVCropGuides": NodeContract(
        class_type="LTXVCropGuides",
        category="video",
        display_name="LTX裁剪引导",
        inputs=["images", "width", "height"],
        outputs=["images"],
        task_fit=["video", "ltx"],
        quality_role="video_preprocess",
        required=False,
        risk="low",
        vram_cost="low",
    ),
    "VHS_VideoCombine": NodeContract(
        class_type="VHS_VideoCombine",
        category="video",
        display_name="视频合成",
        inputs=["images", "frame_rate", "loop_count", "format"],
        outputs=["video"],
        task_fit=["video", "ltx", "wan"],
        quality_role="video_output",
        required=False,
        risk="low",
        vram_cost="low",
    ),

    # =============================================================================
    # 工作流基础设施
    # =============================================================================

    "Reroute": NodeContract(
        class_type="Reroute",
        category="utility",
        display_name="线路",
        inputs=[],
        outputs=[],
        task_fit=["*"],
        quality_role="utility",
        required=False,
        risk="low",
        vram_cost="zero",
    ),
    "Note": NodeContract(
        class_type="Note",
        category="utility",
        display_name="备注",
        inputs=[],
        outputs=[],
        task_fit=["*"],
        quality_role="utility",
        required=False,
        risk="low",
        vram_cost="zero",
    ),
}


def build_node_catalog(custom_nodes_dir: Optional[Path] = None) -> Dict[str, NodeContract]:
    """
    构建节点能力图谱。
    先加载内置节点，再扫描 custom_nodes 目录补充。
    """
    catalog = dict(BUILTIN_NODES)

    if custom_nodes_dir and custom_nodes_dir.exists():
        scanned = _scan_custom_nodes(custom_nodes_dir)
        catalog.update(scanned)

    return catalog


def _scan_custom_nodes(custom_nodes_dir: Path) -> Dict[str, NodeContract]:
    """扫描 custom_nodes 目录，尝试提取节点映射"""
    nodes = {}
    for node_dir in custom_nodes_dir.iterdir():
        if not node_dir.is_dir() or node_dir.name.startswith("."):
            continue
        # 尝试读取 __init__.py 或 py 文件中的 NODE_CLASS_MAPPINGS
        for py_file in node_dir.glob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "NODE_CLASS_MAPPINGS" in content:
                    # 简单的类名提取
                    import re
                    class_names = re.findall(r'class\s+(\w+)\s*\(', content)
                    for name in class_names[:10]:
                        nodes[name] = NodeContract(
                            class_type=name,
                            category="custom",
                            display_name=name,
                            quality_role="custom",
                            required=False,
                            risk="low",
                            depends_on_custom_node=node_dir.name,
                            vram_cost="medium",
                        )
            except Exception:
                pass
    return nodes
