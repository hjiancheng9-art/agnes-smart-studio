"""ComfyFlow Compiler — 生产蓝图打包器

把挖掘出的 ProductionBlueprint（节点列表+连接模式）打包成真实的 Blueprint 对象
（带完整节点拓扑、参数默认值、可执行的 Workflow JSON 骨架）。
"""

from __future__ import annotations
import json
import copy
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import Blueprint, BlueprintRequirement
from .blueprint_miner import ProductionBlueprint
from .node_catalog import BUILTIN_NODES
from .parameter_table import get_param, PARAMETERS


# =============================================================================
# 节点输入/输出槽位映射
# =============================================================================

# 已知的 slot 映射（class_type → {input_name: (source_ct, source_slot_name)}）
# 用于自动推断连接
KNOWN_SLOT_MAP: Dict[str, Dict[str, Tuple[str, str]]] = {
    "CheckpointLoaderSimple": {
        "model": ("", "model"),
        "clip": ("", "clip"),
        "vae": ("", "vae"),
    },
    "UNETLoader": {
        "model": ("", "model"),
    },
    "CLIPLoader": {
        "clip": ("", "clip"),
    },
    "DualCLIPLoader": {
        "clip": ("", "clip"),
    },
    "VAELoader": {
        "vae": ("", "vae"),
    },
    "CLIPTextEncode": {
        "clip": ("CLIPLoader", "clip"),
        "text": ("", ""),
    },
    "KSampler": {
        "model": ("CheckpointLoaderSimple", "model"),
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "latent_image": ("EmptyLatentImage", "latent"),
    },
    "KSamplerAdvanced": {
        "model": ("CheckpointLoaderSimple", "model"),
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "latent_image": ("EmptyLatentImage", "latent"),
    },
    "SamplerCustomAdvanced": {
        "noise": ("RandomNoise", "noise"),
        "guider": ("CFGGuider", "guider"),
        "sampler": ("KSamplerSelect", "sampler"),
        "sigmas": ("ManualSigmas", "sigmas"),
        "model": ("UNETLoader", "model"),
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "latent_image": ("EmptyLatentImage", "latent"),
    },
    "EmptyLatentImage": {
        "width": ("", ""),
        "height": ("", ""),
        "batch_size": ("", ""),
    },
    "EmptyLTXVLatentVideo": {
        "width": ("", ""),
        "height": ("", ""),
        "length": ("", ""),
        "batch_size": ("", ""),
    },
    "VAEDecode": {
        "samples": ("KSampler", "latent"),
        "vae": ("VAELoader", "vae"),
    },
    "VAEEncode": {
        "pixels": ("LoadImage", "image"),
        "vae": ("VAELoader", "vae"),
    },
    "LoadImage": {
        "image": ("", ""),
    },
    "SaveImage": {
        "images": ("VAEDecode", "image"),
        "filename_prefix": ("", ""),
    },
    "PreviewImage": {
        "images": ("VAEDecode", "image"),
    },
    "VHS_VideoCombine": {
        "images": ("VAEDecode", "image"),
        "frame_rate": ("", ""),
        "loop_count": ("", ""),
        "format": ("", ""),
    },
    "RandomNoise": {
        "seed": ("", ""),
    },
    "CFGGuider": {
        "model": ("UNETLoader", "model"),
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "cfg": ("", ""),
    },
    "KSamplerSelect": {
        "sampler_name": ("", ""),
    },
    "ManualSigmas": {
        "sigma": ("", ""),
        "sigma_num": ("", ""),
    },
    "ControlNetLoader": {
        "control_net_name": ("", ""),
    },
    "ControlNetApply": {
        "conditioning": ("CLIPTextEncode", "conditioning"),
        "control_net": ("ControlNetLoader", "control_net"),
        "image": ("LoadImage", "image"),
        "strength": ("", ""),
    },
    "LoraLoader": {
        "model": ("CheckpointLoaderSimple", "model"),
        "clip": ("CheckpointLoaderSimple", "clip"),
        "lora_name": ("", ""),
        "strength_model": ("", ""),
        "strength_clip": ("", ""),
    },
    "LoraLoaderModelOnly": {
        "model": ("UNETLoader", "model"),
        "lora_name": ("", ""),
        "strength_model": ("", ""),
    },
    "UpscaleModelLoader": {
        "model_name": ("", ""),
    },
    "ImageUpscaleWithModel": {
        "upscale_model": ("UpscaleModelLoader", "upscale_model"),
        "image": ("VAEDecode", "image"),
    },
    "LTXVConditioning": {
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "clip_sequence": ("CLIPLoader", "clip"),
        "frame_rate": ("", ""),
        "start_percent": ("", ""),
        "end_percent": ("", ""),
    },
    "LTXVImgToVideoInplace": {
        "image": ("LoadImage", "image"),
        "model": ("UNETLoader", "model"),
        "positive": ("CLIPTextEncode", "conditioning"),
        "negative": ("CLIPTextEncode", "conditioning"),
        "vae": ("VAELoader", "vae"),
        "latent": ("EmptyLTXVLatentVideo", "latent"),
        "seed": ("", ""),
        "steps": ("", ""),
        "cfg": ("", ""),
        "denoise": ("", ""),
    },
    "LTXVPreprocess": {
        "image": ("LoadImage", "image"),
        "width": ("", ""),
        "height": ("", ""),
        "length": ("", ""),
    },
    "LTXVCropGuides": {
        "images": ("LoadImage", "image"),
        "width": ("", ""),
        "height": ("", ""),
    },
}


# =============================================================================
# 蓝图打包器
# =============================================================================

class BlueprintPacker:
    """把 ProductionBlueprint → 真实 Blueprint"""

    def __init__(self):
        self._node_id_counter = 0

    def _next_id(self) -> str:
        self._node_id_counter += 1
        return str(self._node_id_counter)

    def pack(self, mined: ProductionBlueprint) -> Optional[Blueprint]:
        """打包一个生产蓝图"""
        self._node_id_counter = 0
        workflow, edges = self._build_topology(mined)
        if not workflow:
            return None

        model_type = mined.model_type or "sdxl"
        task_map = {
            "ltx_video": "video", "flux": "txt2img", "wan_video": "video",
            "video": "video", "image_edit": "img2img", "lipsync": "video",
            "action_transfer": "video", "txt2img": "txt2img", "img2img": "img2img",
            "controlnet": "controlnet", "ipadapter": "img2img",
        }

        # 质量分
        quality = min(0.95, mined.confidence_score * 1.3)

        return Blueprint(
            name=f"packed_{mined.category}",
            display_name=f"专业:{mined.display_name}",
            description=f"从 {mined.source_workflow_count} 个真实工作流打包的生产蓝图",
            task_type=task_map.get(mined.category, "txt2img"),
            style_tags=[mined.category, "production", "packed"],
            required_nodes=mined.required_nodes,
            optional_nodes=mined.optional_nodes,
            required_models=[model_type],
            min_vram_gb=8.0,
            min_budget_score=4.0,
            quality_score=round(quality, 3),
            chain_depth=0,
            nodes=workflow,
            edges=edges,
        )

    def _build_topology(self, mined: ProductionBlueprint) -> Tuple[Dict, List]:
        """根据必需节点列表和常见连接构建拓扑"""
        required = list(mined.required_nodes)
        if not required:
            return [], {}
        ordered = self._order_pipeline(required, mined.category)
        if not ordered:
            return [], {}
        workflow = {}
        edges = []
        node_refs = {}
        model_id = None
        clip_id = None
        vae_id = None
        clip_encode_ids = []
        ltx_cond_ids = []
        for ct in ordered:
            nid = self._next_id()
            node_def = KNOWN_SLOT_MAP.get(ct, {})
            inputs = {}
            for input_name, (source_ct, source_slot) in node_def.items():
                if not source_ct:
                    inputs[input_name] = self._default_param(ct, input_name, mined.category)
                else:
                    src_nid = None
                    if source_ct in ("CheckpointLoaderSimple", "UNETLoader", "UnetLoaderGGUF"):
                        src_nid = model_id
                    elif source_ct == "VAELoader":
                        src_nid = vae_id
                    elif source_ct in ("CLIPLoader", "DualCLIPLoader"):
                        src_nid = clip_id
                    elif source_ct == "CLIPTextEncode":
                        src_nid = clip_encode_ids[-1] if clip_encode_ids else None
                    elif source_ct == "EmptyLatentImage":
                        src_nid = node_refs.get("EmptyLatentImage") or node_refs.get("EmptyLTXVLatentVideo")
                    elif source_ct == "LoadImage":
                        src_nid = node_refs.get("LoadImage") or node_refs.get("LTXVPreprocess")
                    elif source_ct in ("KSampler", "SamplerCustomAdvanced"):
                        src_nid = node_refs.get("KSampler") or node_refs.get("SamplerCustomAdvanced")
                    else:
                        src_nid = node_refs.get(source_ct)
                    if src_nid is not None:
                        inputs[input_name] = [src_nid, source_slot]
            workflow[nid] = {"class_type": ct, "inputs": inputs}
            if ct in ("CheckpointLoaderSimple", "UNETLoader", "UnetLoaderGGUF"):
                model_id = nid
            elif ct == "VAELoader":
                vae_id = nid
            elif ct in ("CLIPLoader", "DualCLIPLoader"):
                clip_id = nid
            elif ct == "CLIPTextEncode":
                clip_encode_ids.append(nid)
                node_refs[ct] = nid
            elif ct == "LTXVConditioning":
                ltx_cond_ids.append(nid)
                node_refs[ct] = nid
            else:
                node_refs[ct] = nid
        if ltx_cond_ids and len(clip_encode_ids) >= 1:
            lx_nid = ltx_cond_ids[0]
            workflow[lx_nid]["inputs"]["positive"] = [clip_encode_ids[0], "conditioning"]
            workflow[lx_nid]["inputs"]["negative"] = [clip_encode_ids[-1], "conditioning"]
        workflow = self._wire_connections(workflow, ordered, mined.common_edges)
        return workflow, edges

    def _order_pipeline(self, nodes: List[str], category: str) -> List[str]:
        """按执行顺序排列节点"""
        node_set = set(nodes)

        if category in ("ltx_video", "wan_video", "flux"):
            preferred_model_loaders = ["UNETLoader", "CLIPLoader", "VAELoader"]
        else:
            preferred_model_loaders = ["CheckpointLoaderSimple"]

        model_stage = [ct for ct in preferred_model_loaders if ct in node_set]

        order_map = {
            "input": ["LoadImage", "LoadVideo", "LTXVPreprocess"],
            "model": model_stage + ["DualCLIPLoader"],
            "lora": ["LoraLoader", "LoraLoaderModelOnly"],
            "condition": ["CLIPTextEncode", "CLIPTextEncode", "LTXVConditioning"],
            "audio": ["LTXVAudioVAELoader", "LTXVAudioVAEDecode", "EmptyLTXVLatentAudio"],
            "latent": ["EmptyLatentImage", "EmptyLTXVLatentVideo"],
            "sampler": ["RandomNoise", "ManualSigmas", "KSamplerSelect",
                        "CFGGuider", "SamplerCustomAdvanced",
                        "KSampler", "KSamplerAdvanced",
                        "LTXVImgToVideoInplace"],
            "decode": ["VAEDecode", "VAEDecodeTiled", "VAEEncode"],
            "output": ["SaveImage", "PreviewImage", "VHS_VideoCombine",
                       "LTXVConcatAVLatent", "LTXVSeparateAVLatent"],
            "image_proc": ["ImageScaleBy", "ImageScaleToTotalPixels",
                          "ImageResizeKJv2", "GetImageSize", "LTXVCropGuides"],
            "control": ["ControlNetLoader", "ControlNetApply"],
            "enhance": ["UpscaleModelLoader", "ImageUpscaleWithModel",
                       "LatentUpscaleModelLoader"],
            "utility": ["PrimitiveNode", "Reroute", "Note", "MarkdownNote",
                       "ImpactExecutionOrderController", "ReferenceLatent"],
        }

        stage_nodes = {}
        placed = set()
        for stage_name, stage_cts in order_map.items():
            for ct in stage_cts:
                if ct in node_set and ct not in placed:
                    if stage_name not in stage_nodes:
                        stage_nodes[stage_name] = []
                    stage_nodes[stage_name].append(ct)
                    placed.add(ct)

        for ct in nodes:
            if ct not in placed:
                if "utility" not in stage_nodes:
                    stage_nodes["utility"] = []
                stage_nodes["utility"].append(ct)
                placed.add(ct)

        result = []
        stage_order = ["input", "model", "lora", "condition", "audio", "latent",
                       "sampler", "decode", "output", "image_proc", "control",
                       "enhance", "utility"]
        for stage in stage_order:
            if stage in stage_nodes:
                result.extend(stage_nodes[stage])

        return result

    def _wire_connections(self, workflow: Dict[str, Any],
                          ordered: List[str],
                          common_edges: List[Tuple]) -> Dict[str, Any]:
        """使用 common_edges 信息增强连接"""
        # 收集所有节点 ID 和类型
        type_to_ids = defaultdict(list)
        for nid, node in workflow.items():
            type_to_ids[node["class_type"]].append(nid)

        # 对每个 common edge，尝试添加连接
        for from_ct, from_slot, to_ct, to_slot in common_edges:
            # 找到源和目标节点
            src_ids = type_to_ids.get(from_ct, [])
            tgt_ids = type_to_ids.get(to_ct, [])
            if not src_ids or not tgt_ids:
                continue
            src_id = src_ids[0]
            tgt_id = tgt_ids[0]

            # 如果目标节点的对应 input 是空的，填入连接
            for input_name, val in workflow[tgt_id]["inputs"].items():
                if not isinstance(val, (list, tuple)):
                    # widget 值，非连接
                    if val == "" or val == 0:
                        # 尝试填入连接
                        if "clip" in input_name.lower() and from_ct in ("CLIPLoader",):
                            workflow[tgt_id]["inputs"][input_name] = [src_id, "clip"]
                            break
                        elif "model" in input_name.lower() and from_ct in ("CheckpointLoaderSimple", "UNETLoader"):
                            workflow[tgt_id]["inputs"][input_name] = [src_id, "model"]
                            break
                        elif "vae" in input_name.lower() and from_ct == "VAELoader":
                            workflow[tgt_id]["inputs"][input_name] = [src_id, "vae"]
                            break
                        elif "image" in input_name.lower() or "images" in input_name.lower():
                            if from_ct in ("LoadImage", "VAEDecode"):
                                workflow[tgt_id]["inputs"][input_name] = [src_id, "image"]
                                break
                        elif "conditioning" in input_name.lower() and from_ct == "CLIPTextEncode":
                            workflow[tgt_id]["inputs"][input_name] = [src_id, "conditioning"]
                            break
                        elif "latent" in input_name.lower() and from_ct in ("EmptyLatentImage", "EmptyLTXVLatentVideo"):
                            workflow[tgt_id]["inputs"][input_name] = [src_id, "latent"]
                            break

        return workflow

    def _default_param(self, class_type: str, input_name: str, category: str) -> Any:
        """获取默认参数值"""
        # 从 parameter_table 获取
        param_key = f"{class_type.lower()}_{input_name.lower()}"
        try:
            return get_param(param_key)
        except KeyError:
            pass

        # 从类别级参数获取
        cat_prefix = category.split("_")[0]
        try:
            return get_param(f"{cat_prefix}_{input_name.lower()}")
        except KeyError:
            pass

        # 硬编码默认值
        defaults = {
            "seed": 0, "steps": 25, "cfg": 7.0,
            "denoise": 1.0, "batch_size": 1,
            "width": 1024, "height": 1024, "length": 49,
            "frame_rate": 24, "loop_count": 0,
            "format": "video/h264-mp4",
            "start_percent": 0.0, "end_percent": 1.0,
            "strength": 0.8, "strength_model": 0.6, "strength_clip": 0.6,
            "filename_prefix": "ComfyFlow",
            "sampler_name": "euler",
            "sigma": "", "sigma_num": 25,
            "ckpt_name": "", "unet_name": "",
            "clip_name": "", "vae_name": "",
            "lora_name": "", "model_name": "",
            "control_net_name": "",
            "image": "",
            "text": "",
        }
        return defaults.get(input_name, "")

    def pack_all(self, mined_list: List[ProductionBlueprint],
                 min_confidence: float = 0.2) -> List[Blueprint]:
        """批量打包"""
        bps = []
        for mb in mined_list:
            if mb.confidence_score < min_confidence:
                continue
            bp = self.pack(mb)
            if bp:
                bps.append(bp)
        return bps
