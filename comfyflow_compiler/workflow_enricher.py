"""ComfyFlow Compiler — 工作流增强层

自动给生成的工作流加增强链路：
- Detailer（面部修复、细节增强）
- Upscaler（高清放大）
- Refiner（精修）
- ControlNet（控制条件）
- LoRA（风格增强）
- 元数据/注释（可追溯）
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple
import copy

from .models import TaskSpec, Blueprint, RuntimeBudget, EnvironmentProfile
from .parameter_table import get_param


# =============================================================================
# 增强阶段定义
# =============================================================================

ENRICHMENT_STAGES = {
    "detailer": {
        "name": "面部/细节增强",
        "min_budget_score": 5.0,
        "min_vram_gb": 8.0,
        "requires": ["FaceDetailer", "Detailer"],
        "nodes": {
            "detailer": {
                "class_type": "FaceDetailer",
                "inputs": {
                    "image": "",            # 从解码节点接入
                    "model": "",             # 复用主模型
                    "clip": "",
                    "vae": "",
                    "positive": "",
                    "negative": "",
                    "bbox_detector": "bbox/bbox_yolov8m.pt",
                    "sam_model": "sam/sam_vit_h_4b8939.pth",
                    "detailer_hook": None,
                    "feather": 20,
                    "noise_mask": 0,
                    "force_inpaint": False,
                    "guide_size": 512,
                    "max_size": 1024,
                    "steps": 20,
                    "cfg": 7.0,
                    "denoise": 0.4,
                },
            },
        },
    },

    "upscale_2x": {
        "name": "2倍高清放大",
        "min_budget_score": 4.0,
        "min_vram_gb": 6.0,
        "requires": ["UpscaleModelLoader", "ImageUpscaleWithModel"],
        "nodes": {
            "upscale_loader": {
                "class_type": "UpscaleModelLoader",
                "inputs": {"model_name": ""},
            },
            "upscale_exec": {
                "class_type": "ImageUpscaleWithModel",
                "inputs": {
                    "upscale_model": "",  # ← upscale_loader
                    "image": "",          # ← 解码节点
                },
            },
        },
    },

    "refiner": {
        "name": "SDXL Refiner 精修",
        "min_budget_score": 5.5,
        "min_vram_gb": 12.0,
        "requires": ["CheckpointLoaderSimple", "VAEDecode"],
        "nodes": {
            "refiner_ckpt": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": ""},
            },
            "refiner_encode": {
                "class_type": "VAEEncode",
                "inputs": {"pixels": "", "vae": ""},
            },
            "refiner_sampler": {
                "class_type": "KSampler",
                "inputs": {
                    "model": "", "positive": "", "negative": "",
                    "latent_image": "", "seed": 0,
                    "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "denoise": 0.3,
                },
            },
        },
    },

    "controlnet_tile": {
        "name": "Tile ControlNet（保证结构一致）",
        "min_budget_score": 6.0,
        "min_vram_gb": 10.0,
        "requires": ["ControlNetLoader", "ControlNetApply"],
        "nodes": {
            "cn_loader": {
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": "tile.safetensors"},
            },
            "cn_apply": {
                "class_type": "ControlNetApply",
                "inputs": {
                    "conditioning": "", "control_net": "", "image": "",
                    "strength": 0.6,
                },
            },
        },
    },

    "lora_style": {
        "name": "风格 LoRA 增强",
        "min_budget_score": 3.0,
        "min_vram_gb": 4.0,
        "requires": ["LoraLoader", "LoraLoaderModelOnly"],
        "nodes": {
            "lora": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": "", "lora_name": "",
                    "strength_model": 0.6,
                },
            },
        },
    },
}


# =============================================================================
# 工作流分析器
# =============================================================================

class WorkflowAnalyzer:
    """分析已有 Workflow 的结构，找出可增强的连接点"""

    @staticmethod
    def find_output_image_node(workflow: Dict[str, Any]) -> Optional[str]:
        """找到输出图像的那个节点 ID（VAEDecode 或 ImageUpscaleWithModel）"""
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct == "VAEDecode" or ct == "VAEDecodeTiled":
                return nid
            if ct == "ImageUpscaleWithModel":
                return nid
        return None

    @staticmethod
    def find_model_node(workflow: Dict[str, Any]) -> Optional[str]:
        """找到主模型加载节点 ID"""
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct in ("CheckpointLoaderSimple", "UNETLoader", "UnetLoaderGGUF"):
                return nid
        return None

    @staticmethod
    def find_clip_node(workflow: Dict[str, Any]) -> Optional[str]:
        """找到 CLIP 加载节点 ID"""
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct in ("CLIPLoader", "DualCLIPLoader"):
                return nid
        return None

    @staticmethod
    def find_vae_node(workflow: Dict[str, Any]) -> Optional[str]:
        """找到 VAE 加载节点 ID"""
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct == "VAELoader":
                return nid
        return None

    @staticmethod
    def find_save_node(workflow: Dict[str, Any]) -> Optional[str]:
        """找到 SaveImage 节点 ID"""
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct == "SaveImage":
                return nid
        return None

    @staticmethod
    def find_conditioning_nodes(workflow: Dict[str, Any]) -> Dict[str, str]:
        """找到 positive 和 negative conditioning 的来源"""
        result = {}
        for nid, node in workflow.items():
            ct = node["class_type"]
            if ct == "CLIPTextEncode":
                if "positive" not in result:
                    result["positive"] = nid
                elif "negative" not in result:
                    result["negative"] = nid
        return result

    @staticmethod
    def find_last_node_id(workflow: Dict[str, Any]) -> int:
        """找最大的节点 ID"""
        ids = [int(k) for k in workflow.keys() if k.isdigit()]
        return max(ids) if ids else 100

    @staticmethod
    def get_workflow_type(workflow: Dict[str, Any]) -> str:
        """判断工作流类型（txt2img / img2img / video）"""
        has_load_image = any(n["class_type"] == "LoadImage" for n in workflow.values())
        has_video = any(n["class_type"] in ("VHS_VideoCombine", "EmptyLTXVLatentVideo")
                       for n in workflow.values())
        if has_video:
            return "video"
        if has_load_image:
            return "img2img"
        return "txt2img"


# =============================================================================
# 增强器
# =============================================================================

class WorkflowEnricher:
    """工作流增强器 — 给基础工作流添加高级链路"""

    def __init__(self, budget: RuntimeBudget, env: EnvironmentProfile):
        self.budget = budget
        self.env = env
        self.analyzer = WorkflowAnalyzer()

    def enrich(self, workflow: Dict[str, Any],
               task: TaskSpec,
               quality_mode: str = "balanced",
               stages: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        增强工作流。

        Args:
            workflow: 原始工作流 JSON
            task: 任务规格
            quality_mode: 质量模式
            stages: 要添加的增强阶段（None = 自动选择）

        Returns:
            增强后的工作流 JSON
        """
        workflow = copy.deepcopy(workflow)

        # 自动选择增强阶段
        if stages is None:
            stages = self._auto_select_stages(quality_mode)

        next_id = self.analyzer.find_last_node_id(workflow) + 1
        wf_type = self.analyzer.get_workflow_type(workflow)

        # 图像输出节点（用于串联增强）
        image_node = self.analyzer.find_output_image_node(workflow)
        model_node = self.analyzer.find_model_node(workflow)
        clip_node = self.analyzer.find_clip_node(workflow)
        vae_node = self.analyzer.find_vae_node(workflow)
        save_node = self.analyzer.find_save_node(workflow)
        cond_nodes = self.analyzer.find_conditioning_nodes(workflow)

        # 跳过视频工作流的增强（视频链路不同）
        if wf_type == "video":
            return workflow

        for stage_name in stages:
            stage = ENRICHMENT_STAGES.get(stage_name)
            if not stage:
                continue

            # 检查硬件条件
            if self.budget.score < stage["min_budget_score"]:
                continue
            if self.budget.vram_gb < stage["min_vram_gb"]:
                continue

            # 应用增强
            if stage_name == "upscale_2x" and image_node:
                # 检查是否有放大模型可用
                upscale_models = getattr(self.env, 'upscale_models', [])
                if not upscale_models:
                    continue  # 无放大模型，跳过
                workflow = self._apply_upscale(
                    workflow, stage, next_id, image_node, save_node
                )
                next_id = self.analyzer.find_last_node_id(workflow) + 1
                image_node = str(next_id - 1)  # upscale 的输出是新的图像节点

            elif stage_name == "detailer" and image_node:
                if model_node:
                    # 检查 FaceDetailer 和 sam/bbox 模型是否存在（简化为无条件尝试）
                    workflow = self._apply_detailer(
                        workflow, stage, next_id,
                        image_node, model_node, clip_node, vae_node,
                        cond_nodes,
                    )
                    next_id = self.analyzer.find_last_node_id(workflow) + 1
                    image_node = str(next_id - 1)

            elif stage_name == "refiner" and image_node and model_node and vae_node:
                workflow = self._apply_refiner(
                    workflow, stage, next_id,
                    image_node, model_node, vae_node, cond_nodes,
                )
                next_id = self.analyzer.find_last_node_id(workflow) + 1
                image_node = str(next_id - 1)

            elif stage_name == "lora_style" and model_node:
                workflow = self._apply_lora(
                    workflow, stage, next_id, model_node
                )
                next_id = self.analyzer.find_last_node_id(workflow) + 1

        return workflow

    def _auto_select_stages(self, quality_mode: str) -> List[str]:
        """根据质量模式自动选择增强阶段"""
        presets = {
            "fast": [],
            "balanced": [],
            "high": [],
            "cinematic": ["lora_style"],
        }
        return presets.get(quality_mode, presets["balanced"])

    def _apply_upscale(self, workflow: Dict[str, Any],
                       stage: Dict, next_id: int,
                       image_node: str, save_node: Optional[str]) -> Dict[str, Any]:
        """应用 2x upscale"""
        # 加载器
        loader_id = str(next_id)
        workflow[loader_id] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": ""},
        }
        next_id += 1

        # 放大执行
        upscale_id = str(next_id)
        workflow[upscale_id] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": [loader_id, "upscale_model"],
                "image": [image_node, "image"],
            },
        }
        next_id += 1

        # 重连 SaveImage
        if save_node and save_node in workflow:
            if "images" in workflow[save_node]["inputs"]:
                workflow[save_node]["inputs"]["images"] = [upscale_id, "image"]

        return workflow

    def _apply_detailer(self, workflow: Dict[str, Any],
                        stage: Dict, next_id: int,
                        image_node: str, model_node: str,
                        clip_node: str, vae_node: str,
                        cond_nodes: Dict[str, str]) -> Dict[str, Any]:
        """应用面部/细节增强"""
        # CheckpointLoaderSimple 内置 clip 和 vae
        actual_clip = clip_node or model_node
        actual_vae = vae_node or model_node
        
        detailer_id = str(next_id)
        workflow[detailer_id] = {
            "class_type": "FaceDetailer",
            "inputs": {
                "image": [image_node, "image"],
                "model": [model_node, "model"],
                "clip": [actual_clip, "clip"],
                "vae": [actual_vae, "vae"],
                "positive": [cond_nodes.get("positive", ""), "conditioning"],
                "negative": [cond_nodes.get("negative", ""), "conditioning"],
                "bbox_detector": "bbox/bbox_yolov8m.pt",
                "guide_size": 512,
                "max_size": 1024,
                "steps": 20,
                "cfg": 7.0,
                "denoise": 0.4,
                "feather": 20,
                "noise_mask": 0,
                "force_inpaint": False,
                "sam_model": "sam/sam_vit_h_4b8939.pth",
                "detailer_hook": None,
            },
        }
        return workflow

    def _apply_refiner(self, workflow: Dict[str, Any],
                       stage: Dict, next_id: int,
                       image_node: str, model_node: str,
                       vae_node: str,
                       cond_nodes: Dict[str, str]) -> Dict[str, Any]:
        """应用 SDXL Refiner 精修"""
        # 简化版 refiner
        refiner_id = str(next_id)
        workflow[refiner_id] = {
            "class_type": "KSampler",
            "inputs": {
                "model": [model_node, "model"],
                "positive": [cond_nodes.get("positive", ""), "conditioning"],
                "negative": [cond_nodes.get("negative", ""), "conditioning"],
                "latent_image": [vae_node, "latent"] if vae_node else [model_node, "latent"],
                "seed": 0, "steps": 20, "cfg": 7.0,
                "sampler_name": "euler", "scheduler": "normal",
                "denoise": 0.3,
            },
        }
        return workflow

    def _apply_lora(self, workflow: Dict[str, Any],
                    stage: Dict, next_id: int,
                    model_node: str) -> Dict[str, Any]:
        """应用 LoRA 增强"""
        lora_id = str(next_id)
        workflow[lora_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [model_node, "model"],
                "lora_name": "",
                "strength_model": 0.6,
            },
        }
        # 重连后续节点的 model 引用（排除 LoRA 节点自身和 model 加载节点）
        new_model_ref = [lora_id, "model"]
        for nid, node in workflow.items():
            if nid == lora_id or nid == model_node:
                continue
            for key, val in list(node.get("inputs", {}).items()):
                if isinstance(val, (list, tuple)) and len(val) == 2:
                    if str(val[0]) == model_node and key in ("model",):
                        node["inputs"][key] = new_model_ref
        return workflow
