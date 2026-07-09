"""ComfyFlow Compiler — 工作流组装器"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import copy
import json

from .models import TaskSpec, Blueprint, EnvironmentProfile, RuntimeBudget


def compose_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """
    根据 TaskSpec + Blueprint + Environment 组装完整的 Workflow JSON。
    """
    workflow = copy.deepcopy(blueprint.nodes)

    if not workflow:
        # 根据蓝图类型选择不同的构建器
        bp_name = blueprint.name.lower()
        if "ltx" in bp_name:
            if "i2v" in bp_name or "img2video" in bp_name:
                workflow = _build_ltx_i2v_workflow(task, blueprint, env, budget)
            else:
                workflow = _build_ltx_t2v_workflow(task, blueprint, env, budget)
        elif "flux_module" in bp_name or "flux" in bp_name:
            workflow = _build_flux_modular_workflow(task, blueprint, env, budget)
        elif "wan" in bp_name:
            workflow = _build_wan_workflow(task, blueprint, env, budget)
        else:
            workflow = _build_standard_workflow(task, blueprint, env, budget)

    # 填充参数
    _apply_task_params(workflow, task, budget)

    # 自动选择模型
    _select_models(workflow, task, env)

    # 调整分辨率
    _apply_resolution(workflow, task, budget)

    # 添加 prompt 增强
    _apply_prompt_enhancement(workflow, task)

    # 添加元数据
    workflow = _add_metadata(workflow, task, blueprint.name)

    # 添加中文说明 Note 节点
    workflow = _add_note_nodes(workflow, task, blueprint)

    # 后处理：将命名槽位引用转换为整数索引，并填充模型名
    workflow = _postprocess_for_comfyui(workflow, env)

    return workflow


def _postprocess_for_comfyui(workflow: Dict[str, Any], env: EnvironmentProfile) -> Dict[str, Any]:
    slot_to_int = {
        "model": 0, "clip": 1, "vae": 2,
        "conditioning": 0, "latent": 0, "image": 0,
        "images": 0, "samples": 0, "noise": 0, "guider": 1,
        "sampler": 2, "sigmas": 3, "upscale_model": 0,
        "output": 0, "positive": 0, "negative": 1,
    }
    for nid, node in workflow.items():
        for key, val in list(node["inputs"].items()):
            if isinstance(val, (list, tuple)) and len(val) == 2:
                slot_name = str(val[1])
                if isinstance(val[1], str):
                    node["inputs"][key] = [str(val[0]), slot_to_int.get(slot_name, 0)]
        ct = node["class_type"]
        if ct == "CheckpointLoaderSimple":
            if not node["inputs"].get("ckpt_name") and env.checkpoints:
                ckpt = next((c for c in env.checkpoints if "xl" in c.lower()), None)
                if not ckpt:
                    ckpt = env.checkpoints[0]
                node["inputs"]["ckpt_name"] = ckpt
        if ct == "UNETLoader":
            if not node["inputs"].get("unet_name") and env.checkpoints:
                unet = next((c for c in env.checkpoints if "ltx" in c.lower() or "flux" in c.lower()), None)
                if unet:
                    node["inputs"]["unet_name"] = unet
    return workflow


def _add_note_nodes(workflow: Dict[str, Any], task: TaskSpec, blueprint: Blueprint) -> Dict[str, Any]:
    """为工作流添加 MarkdownNote 中文说明节点"""
    # 找一个不冲突的 node_id
    existing_ids = [int(k) for k in workflow.keys() if k.isdigit()]
    next_id = max(existing_ids) + 1 if existing_ids else 100

    task_names = {
        "txt2img": "文生图",
        "img2img": "图生图",
        "video": "视频生成",
        "controlnet": "控制生成",
        "upscale": "高清放大",
    }

    quality_names = {
        "fast": "快速",
        "balanced": "均衡",
        "high": "高清",
        "cinematic": "电影级",
    }

    lines = [
        f"# {task_names.get(task.task_type, task.task_type)} 工作流",
        f"",
        f"**描述**: {task.subject or '自动生成'}",
        f"**质量模式**: {quality_names.get(task.quality_mode, task.quality_mode)}",
        f"**方案**: {blueprint.display_name}",
        f"",
        f"> 由 ComfyFlow Compiler 自动生成",
        f"> 直接拖入 ComfyUI 即可使用",
    ]

    note_text = "\n".join(lines)

    # Add Note node (non-functional, just for display)
    workflow[str(next_id)] = {
        "class_type": "Note",
        "inputs": {"text": note_text},
    }

    return workflow



# =============================================================================
# Flux 模块化构建器
# =============================================================================

def _build_flux_modular_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """Flux 模块化加载 + 高级采样链"""
    wf = {}
    nid = 1

    # 1. UNETLoader (Flux 模型)
    wf[str(nid)] = {"class_type": "UNETLoader", "inputs": {"unet_name": "", "weight_dtype": "fp8_e4m3fn"}}
    model_node = str(nid); nid += 1

    # 2. CLIPLoader
    wf[str(nid)] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "", "type": "flux"}}
    clip_node = str(nid); nid += 1

    # 3. VAELoader
    wf[str(nid)] = {"class_type": "VAELoader", "inputs": {"vae_name": ""}}
    vae_node = str(nid); nid += 1

    # 4. CLIPTextEncode (positive)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_prompt(task), "clip": (clip_node, "clip")}}
    pos_node = str(nid); nid += 1

    # 5. CLIPTextEncode (negative)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_negative_prompt(task), "clip": (clip_node, "clip")}}
    neg_node = str(nid); nid += 1

    # 6. EmptyLatentImage
    w, h = _resolve_resolution(task.aspect_ratio, budget)
    wf[str(nid)] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    latent_node = str(nid); nid += 1

    # 7. RandomNoise
    wf[str(nid)] = {"class_type": "RandomNoise", "inputs": {"seed": 0}}
    noise_node = str(nid); nid += 1

    # 8. KSamplerSelect
    wf[str(nid)] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    sampler_node = str(nid); nid += 1

    # 9. ManualSigmas
    steps = _resolve_steps(task.quality_mode)
    wf[str(nid)] = {"class_type": "ManualSigmas", "inputs": {"sigma": "", "sigma_num": steps}}
    sigmas_node = str(nid); nid += 1

    # 10. CFGGuider
    cfg = _resolve_cfg(task.quality_mode) if task.quality_mode != "fast" else 1.0
    wf[str(nid)] = {"class_type": "CFGGuider", "inputs": {
        "model": (model_node, "model"), "positive": (pos_node, "conditioning"),
        "negative": (neg_node, "conditioning"), "cfg": cfg if cfg > 1 else 1.0,
    }}
    guider_node = str(nid); nid += 1

    # 11. SamplerCustomAdvanced
    wf[str(nid)] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": (noise_node, "noise"), "guider": (guider_node, "guider"),
        "sampler": (sampler_node, "sampler"), "sigmas": (sigmas_node, "sigmas"),
        "model": (model_node, "model"), "positive": (pos_node, "conditioning"),
        "negative": (neg_node, "conditioning"), "latent_image": (latent_node, "latent"),
    }}
    output_node = str(nid); nid += 1

    # 12. VAEDecode
    wf[str(nid)] = {"class_type": "VAEDecode", "inputs": {"samples": (output_node, "output"), "vae": (vae_node, "vae")}}
    img_node = str(nid); nid += 1

    # 13. SaveImage
    wf[str(nid)] = {"class_type": "SaveImage", "inputs": {"images": (img_node, "image"), "filename_prefix": "ComfyFlow_Flux"}}

    return _add_metadata_all(wf)


# =============================================================================
# LTX 视频构建器
# =============================================================================

def _build_ltx_t2v_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """LTX 文生视频全链路"""
    wf = {}
    nid = 1

    # 1. UNETLoader
    wf[str(nid)] = {"class_type": "UNETLoader", "inputs": {"unet_name": "", "weight_dtype": "default"}}
    model_node = str(nid); nid += 1

    # 2. CLIPLoader
    wf[str(nid)] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "", "type": "ltxv"}}
    clip_node = str(nid); nid += 1

    # 3. VAELoader
    wf[str(nid)] = {"class_type": "VAELoader", "inputs": {"vae_name": ""}}
    vae_node = str(nid); nid += 1

    # 4. CLIPTextEncode (positive)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_prompt(task), "clip": (clip_node, "clip")}}
    pos_node = str(nid); nid += 1

    # 5. CLIPTextEncode (negative)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_negative_prompt(task), "clip": (clip_node, "clip")}}
    neg_node = str(nid); nid += 1

    # 6. LTXVConditioning
    wf[str(nid)] = {"class_type": "LTXVConditioning", "inputs": {
        "positive": (pos_node, "conditioning"),
        "negative": (neg_node, "conditioning"),
        "clip_sequence": (clip_node, "clip"),
        "frame_rate": 24, "start_percent": 0.0, "end_percent": 1.0,
    }}
    ltx_cond_node = str(nid); nid += 1

    # 7. EmptyLTXVLatentVideo
    w, h = _resolve_resolution(task.aspect_ratio, budget)
    # 视频用更保守的分辨率
    w = min(w, 768); h = min(h, 768)
    wf[str(nid)] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w, "height": h, "length": 49, "batch_size": 1}}
    latent_node = str(nid); nid += 1

    # 8. RandomNoise
    wf[str(nid)] = {"class_type": "RandomNoise", "inputs": {"seed": 0}}
    noise_node = str(nid); nid += 1

    # 9. KSamplerSelect
    wf[str(nid)] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    sampler_node = str(nid); nid += 1

    # 10. CFGGuider
    wf[str(nid)] = {"class_type": "CFGGuider", "inputs": {
        "model": (model_node, "model"),
        "positive": (ltx_cond_node, "positive"),
        "negative": (ltx_cond_node, "negative"),
        "cfg": 4.0,
    }}
    guider_node = str(nid); nid += 1

    # 11. SamplerCustomAdvanced
    wf[str(nid)] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": (noise_node, "noise"), "guider": (guider_node, "guider"),
        "sampler": (sampler_node, "sampler"), "sigmas": (sampler_node, "sampler"),
        "model": (model_node, "model"), "positive": (ltx_cond_node, "positive"),
        "negative": (ltx_cond_node, "negative"), "latent_image": (latent_node, "latent"),
    }}
    output_node = str(nid); nid += 1

    # 12. VAEDecode
    wf[str(nid)] = {"class_type": "VAEDecode", "inputs": {"samples": (output_node, "output"), "vae": (vae_node, "vae")}}
    img_node = str(nid); nid += 1

    # 13. VHS_VideoCombine
    wf[str(nid)] = {"class_type": "VHS_VideoCombine", "inputs": {
        "images": (img_node, "image"), "frame_rate": 24, "loop_count": 0, "format": "video/h264-mp4",
    }}

    return _add_metadata_all(wf)


def _build_ltx_i2v_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """LTX 图生视频全链路"""
    wf = {}
    nid = 1

    # 1. UNETLoader
    wf[str(nid)] = {"class_type": "UNETLoader", "inputs": {"unet_name": "", "weight_dtype": "default"}}
    model_node = str(nid); nid += 1

    # 2. CLIPLoader
    wf[str(nid)] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "", "type": "ltxv"}}
    clip_node = str(nid); nid += 1

    # 3. VAELoader
    wf[str(nid)] = {"class_type": "VAELoader", "inputs": {"vae_name": ""}}
    vae_node = str(nid); nid += 1

    # 4. LoadImage (参考图)
    wf[str(nid)] = {"class_type": "LoadImage", "inputs": {"image": task.reference_image or ""}}
    image_node = str(nid); nid += 1

    # 5. LTXVPreprocess
    wf[str(nid)] = {"class_type": "LTXVPreprocess", "inputs": {
        "image": (image_node, "image"), "width": 640, "height": 640, "length": 49,
    }}
    preproc_node = str(nid); nid += 1

    # 6. CLIPTextEncode (positive)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_prompt(task), "clip": (clip_node, "clip")}}
    pos_node = str(nid); nid += 1

    # 7. CLIPTextEncode (negative)
    wf[str(nid)] = {"class_type": "CLIPTextEncode", "inputs": {"text": _build_negative_prompt(task), "clip": (clip_node, "clip")}}
    neg_node = str(nid); nid += 1

    # 8. 后续同类
    w, h = 640, 640
    wf[str(nid)] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w, "height": h, "length": 49, "batch_size": 1}}
    latent_node = str(nid); nid += 1

    wf[str(nid)] = {"class_type": "RandomNoise", "inputs": {"seed": 0}}
    noise_node = str(nid); nid += 1
    wf[str(nid)] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    sampler_node = str(nid); nid += 1
    wf[str(nid)] = {"class_type": "CFGGuider", "inputs": {
        "model": (model_node, "model"), "positive": (pos_node, "conditioning"),
        "negative": (neg_node, "conditioning"), "cfg": 4.0,
    }}
    guider_node = str(nid); nid += 1
    wf[str(nid)] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": (noise_node, "noise"), "guider": (guider_node, "guider"),
        "sampler": (sampler_node, "sampler"), "sigmas": (sampler_node, "sampler"),
        "model": (model_node, "model"), "positive": (pos_node, "conditioning"),
        "negative": (neg_node, "conditioning"),
        "latent_image": (latent_node, "latent"),
    }}
    output_node = str(nid); nid += 1
    wf[str(nid)] = {"class_type": "VAEDecode", "inputs": {"samples": (output_node, "output"), "vae": (vae_node, "vae")}}
    img_node = str(nid); nid += 1
    wf[str(nid)] = {"class_type": "VHS_VideoCombine", "inputs": {
        "images": (img_node, "image"), "frame_rate": 24, "loop_count": 0, "format": "video/h264-mp4",
    }}

    return _add_metadata_all(wf)


def _build_wan_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """Wan 视频工作流（基础版，与 LTX 结构类似）"""
    return _build_ltx_t2v_workflow(task, blueprint, env, budget)


def _add_metadata_all(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """给所有节点加 _meta"""
    for nid, node in workflow.items():
        node["_meta"] = {"title": f"{node['class_type']}_{nid}"}
    return workflow


def _build_standard_workflow(
    task: TaskSpec,
    blueprint: Blueprint,
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> Dict[str, Any]:
    """从零构建标准工作流（SDXL/SD1.5 用 CheckpointLoaderSimple）"""
    workflow = {}
    node_id = 1

    # 1. checkpoint 加载器
    workflow[str(node_id)] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": ""}
    }
    checkpoint_node = str(node_id)
    node_id += 1

    # 2. CLIP编码 (positive)
    workflow[str(node_id)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": (checkpoint_node, "clip")}
    }
    positive_node = str(node_id)
    node_id += 1

    # 3. CLIP编码 (negative)
    workflow[str(node_id)] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": (checkpoint_node, "clip")}
    }
    negative_node = str(node_id)
    node_id += 1

    latent_node = ""
    if task.task_type in ("txt2img",):
        # 4. 空潜变量
        w, h = _resolve_resolution(task.aspect_ratio, budget)
        workflow[str(node_id)] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1}
        }
        latent_node = str(node_id)
        node_id += 1

    elif task.task_type in ("img2img", "controlnet"):
        # 4. 加载图像
        workflow[str(node_id)] = {
            "class_type": "LoadImage",
            "inputs": {"image": task.reference_image or ""}
        }
        load_image_node = str(node_id)
        node_id += 1
        # 5. VAE编码
        workflow[str(node_id)] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": (load_image_node, "image"), "vae": (checkpoint_node, "vae")}
        }
        latent_node = str(node_id)
        node_id += 1

    # ControlNet 特殊处理
    if task.task_type == "controlnet" and task.needs_controlnet:
        pass  # 简化版，后续扩展

    # 采样器
    steps = _resolve_steps(task.quality_mode)
    workflow[str(node_id)] = {
        "class_type": "KSampler",
        "inputs": {
            "model": (checkpoint_node, "model"),
            "positive": (positive_node, "conditioning"),
            "negative": (negative_node, "conditioning"),
            "latent_image": (latent_node, "latent"),
            "seed": 0,
            "steps": steps,
            "cfg": _resolve_cfg(task.quality_mode),
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0 if task.task_type == "txt2img" else 0.6,
        }
    }
    sampler_node = str(node_id)
    node_id += 1

    # VAE解码
    workflow[str(node_id)] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": (sampler_node, "latent"), "vae": (checkpoint_node, "vae")}
    }
    decode_node = str(node_id)
    node_id += 1

    # 保存图像
    prefix = _sanitize_prefix(task.subject)
    workflow[str(node_id)] = {
        "class_type": "SaveImage",
        "inputs": {"images": (decode_node, "image"), "filename_prefix": f"ComfyFlow_{prefix}"}
    }

    return workflow


def _apply_task_params(workflow: Dict[str, Any], task: TaskSpec, budget: RuntimeBudget):
    """根据任务参数填充各个节点的 inputs"""
    for node_id, node in workflow.items():
        ct = node["class_type"]
        if ct == "CLIPTextEncode":
            if "positive" not in node_id and "2" in node_id:
                # 正面 prompt
                prompt = _build_prompt(task)
                node["inputs"]["text"] = prompt
            else:
                node["inputs"]["text"] = _build_negative_prompt(task)


def _select_models(workflow: Dict[str, Any], task: TaskSpec, env: EnvironmentProfile):
    """自动选择本机可用模型"""
    for node_id, node in workflow.items():
        ct = node["class_type"]
        if ct == "CheckpointLoaderSimple":
            # 策略：优先 SDXL，其次 SD1.5
            if env.has_sdxl and env.checkpoints:
                ckpt = _pick_model(env.checkpoints, ["xl", "sdxl"])
                node["inputs"]["ckpt_name"] = ckpt or (env.checkpoints[0] if env.checkpoints else "")
            elif env.has_sd15 and env.checkpoints:
                ckpt = _pick_model(env.checkpoints, ["sd1.5", "sd15", "v1-5", "1.5"])
                node["inputs"]["ckpt_name"] = ckpt or (env.checkpoints[0] if env.checkpoints else "")
            elif env.checkpoints:
                node["inputs"]["ckpt_name"] = env.checkpoints[0]


def _apply_resolution(workflow: Dict[str, Any], task: TaskSpec, budget: RuntimeBudget):
    """设置分辨率"""
    w, h = _resolve_resolution(task.aspect_ratio, budget)
    for node_id, node in workflow.items():
        if node["class_type"] == "EmptyLatentImage":
            node["inputs"]["width"] = w
            node["inputs"]["height"] = h


def _apply_prompt_enhancement(workflow: Dict[str, Any], task: TaskSpec):
    """增强 prompt 质量"""
    pass  # 后续可以接入 prompt 优化器


def _add_metadata(workflow: Dict[str, Any], task: TaskSpec, blueprint_name: str) -> Dict[str, Any]:
    """添加 ComfyUI _meta 元数据"""
    for node_id, node in workflow.items():
        node["_meta"] = {"title": f"{node['class_type']}_{node_id}"}
    return workflow


# =============================================================================
# 辅助函数
# =============================================================================

def _build_prompt(task: TaskSpec) -> str:
    """构建正向 prompt — SDXL/Flux 优化版"""
    subject = task.subject

    # 核心名词提取 + 英文翻译
    cn_to_en = {
        "猫": "cat", "狗": "dog", "龙": "dragon", "鸟": "bird", "鱼": "fish",
        "少女": "beautiful girl", "男孩": "boy", "女孩": "girl",
        "战士": "warrior", "骑士": "knight", "精灵": "elf",
        "城市": "city", "建筑": "building",
        "赛博朋克": "cyberpunk", "霓虹": "neon", "雨夜": "rainy night",
        "电影感": "cinematic", "冷峻": "cool color tone",
        "奇幻": "fantasy", "魔法": "magic", "火焰": "fire",
        "温暖": "warm atmosphere", "写实": "photorealistic",
    }
    core_nouns = ["猫", "狗", "龙", "鸟", "鱼", "马", "虎", "狼", "兔", "少女", "男孩", "女孩"]
    core = ""
    for n in core_nouns:
        if n in subject:
            core = n
            break
    if not core:
        core = subject[:6]

    en_desc = cn_to_en.get(core, core)
    extras = []
    for cn, en in cn_to_en.items():
        if cn in subject and cn != core:
            extras.append(en)

    # ===== 质量增强修饰语（按质量模式） =====
    quality_boosters = {
        "fast": "high quality",
        "balanced": "high quality, detailed",
        "high": "masterpiece, highly detailed, sharp focus, 8k",
        "cinematic": "masterpiece, cinematic lighting, volumetric lighting, dramatic shadows, sharp focus, intricate details, 8k, ultra detailed, award winning",
    }
    booster = quality_boosters.get(task.quality_mode, quality_boosters["balanced"])

    # ===== 风格描述 =====
    style_desc = ""
    if "cinematic" in task.style:
        style_desc = "cinematic epic scene, dramatic lighting, film grain"
    elif "anime" in task.style:
        style_desc = "anime style, cel shading, vibrant colors"
    elif "fantasy" in task.style:
        style_desc = "fantasy art, ethereal, magical atmosphere"
    elif "cyberpunk" in task.style:
        style_desc = "cyberpunk, neon lights, rain, wet streets, reflection"
    else:
        style_desc = ", ".join(task.style)

    extra_str = ", ".join(extras)
    
    # 最终 prompt：主体 + 场景/动作 + 风格 + 质量
    if extra_str:
        prompt = f"{en_desc}, {extra_str}, {style_desc}, {booster}"
    else:
        prompt = f"{en_desc}, {style_desc}, {booster}"
    
    return prompt


def _build_negative_prompt(task: TaskSpec) -> str:
    """构建负向 prompt"""
    negatives = ["nsfw", "lowres", "bad anatomy", "bad hands", "text", "error",
                 "missing fingers", "extra digit", "fewer digits", "cropped",
                 "worst quality", "low quality", "normal quality", "jpeg artifacts",
                 "signature", "watermark", "username", "blurry"]
    return ", ".join(negatives)


def _resolve_resolution(aspect_ratio: str, budget: RuntimeBudget) -> tuple:
    """根据宽高比和预算计算分辨率"""
    base_res = budget.max_resolution
    base_w, base_h = map(int, base_res.split("x"))
    max_area = base_w * base_h

    ratio_map = {
        "1:1": (1, 1),
        "3:2": (3, 2),
        "4:3": (4, 3),
        "16:9": (16, 9),
        "9:16": (9, 16),
        "2:3": (2, 3),
        "3:4": (3, 4),
        "21:9": (21, 9),
    }
    if aspect_ratio not in ratio_map:
        return base_w, base_h

    rw, rh = ratio_map[aspect_ratio]
    h = int((max_area * rh / rw) ** 0.5)
    w = int(h * rw / rh)
    # 对齐到 8 的倍数
    w = (w // 8) * 8
    h = (h // 8) * 8
    return max(w, 64), max(h, 64)


def _resolve_steps(quality_mode: str) -> int:
    return {"fast": 18, "balanced": 25, "high": 30, "cinematic": 35}.get(quality_mode, 25)


def _resolve_cfg(quality_mode: str) -> float:
    return {"fast": 6.0, "balanced": 7.0, "high": 7.5, "cinematic": 8.0}.get(quality_mode, 7.0)


def _pick_model(models: List[str], keywords: List[str]) -> Optional[str]:
    for m in models:
        ml = m.lower()
        if any(k in ml for k in keywords):
            return m
    return None


def _sanitize_prefix(text: str) -> str:
    import re
    text = re.sub(r'[^\w\u4e00-\u9fff]', '_', text)
    return text[:30].strip("_")
