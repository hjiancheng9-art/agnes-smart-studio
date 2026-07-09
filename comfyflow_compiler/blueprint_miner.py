"""ComfyFlow Compiler — 生产蓝图挖掘器

从真实 ComfyUI 工作流 JSON 中挖掘生产级蓝图模式。

核心方法：
1. 解析真实工作流的节点拓扑
2. 统计节点共现频率 → 发现高频组合
3. 分析连接模式 → 提取阶段结构
4. 生成 ProductionBlueprint（可直接注册进 compiler）
"""

from __future__ import annotations
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# 挖掘结果数据模型
# =============================================================================

@dataclass
class ProductionBlueprint:
    """从真实工作流挖掘出的生产蓝图"""
    name: str
    display_name: str
    category: str                        # flux / ltx / wan / sdxl / sd15
    source_workflow_count: int
    confidence_score: float              # 0-1
    required_nodes: List[str] = field(default_factory=list)
    optional_nodes: List[str] = field(default_factory=list)
    common_edges: List[Tuple[str, str, str, str]] = field(default_factory=list)  # (from_ct, from_slot, to_ct, to_slot)
    estimated_node_count: int = 0
    typical_pipeline: List[str] = field(default_factory=list)       # 阶段描述
    model_type: str = ""


@dataclass
class MinedWorkflow:
    """单个工作流的挖掘中间结果"""
    path: str
    folder: str
    node_count: int
    class_types: List[str]
    unique_types: int
    has_load_image: bool
    has_save_image: bool
    has_video_output: bool
    category: str                        # 自动分类
    node_graph: Dict[str, List[str]]     # node_id → connected_to_ids
    edges: List[Tuple[str, str, str, str]]  # (from_ct, from_slot, to_ct, to_slot)


# =============================================================================
# 工作流加载器
# =============================================================================

class WorkflowLoader:
    """加载和解析真实 ComfyUI 工作流文件"""

    SAVE_FORMATS = {"save_v1", "save_api", "unknown"}

    @staticmethod
    def load(path: str) -> Optional[Dict]:
        """加载 JSON 文件（支持多种格式）"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            try:
                with open(path, "r", encoding="gbk") as f:
                    return json.load(f)
            except Exception:
                return None

    @staticmethod
    def find_all(root_dirs: List[str]) -> List[str]:
        """递归扫描所有工作流 JSON 文件"""
        found = []
        for root in root_dirs:
            if not os.path.exists(root):
                continue
            for dirpath, _, files in os.walk(root):
                for f in files:
                    if f.endswith(".json"):
                        found.append(os.path.join(dirpath, f))
        return found


# =============================================================================
# 工作流分类器
# =============================================================================

class WorkflowClassifier:
    """根据节点类型自动分类工作流用途"""

    FLUX_NODES = {"UNETLoader", "DualCLIPLoader", "UnetLoaderGGUF", "Flux"}
    LTX_NODES = {"LTXVConditioning", "LTXVImgToVideoInplace", "LTXVPreprocess",
                 "EmptyLTXVLatentVideo", "LTXVAudioVAELoader", "LTXVAudioVAEDecode",
                 "LTXVConcatAVLatent", "LTXVSeparateAVLatent", "LTXV"}
    WAN_NODES = {"WanVideo", "Wan", "WanInfiniteTalkToVideo"}
    SDXL_NODES = {"CheckpointLoaderSimple", "SDXL", "sdxl"}
    CONTROLNET_NODES = {"ControlNetLoader", "ControlNetApply", "AIO_Preprocessor",
                        "QwenImageDiffsynthControlnet"}
    IPADAPTER_NODES = {"IPAdapter", "IPAdapterUnified", "IP_"}
    VIDEO_NODES = {"VHS_VideoCombine", "VHS_VideoInfo", "VideoCombine"}

    CATEGORY_KEYWORDS = {
        "image_edit": ["编辑", "edit", "inpaint", "替换", "换"],
        "action_transfer": ["动作", "motion", "跳舞", "迁移"],
        "character_replace": ["换装", "换衣服", "角色替换"],
        "face_swap": ["换脸", "face", "reactor", "faceid"],
        "lipsync": ["对口型", "数字人", "lipsync", "talk"],
        "flux": ["flux"],
        "ltx_video": ["ltx", "ltx2"],
        "wan_video": ["wan"],
        "video": ["视频", "video", "animate"],
        "txt2img": ["生成", "文生图", "txt2img"],
        "img2img": ["图生图", "img2img", "重绘"],
        "upscale": ["放大", "upscale", "高清"],
        "controlnet": ["controlnet", "canny", "depth", "pose"],
    }

    @classmethod
    def classify(cls, types: Set[str], filename: str, folder: str) -> str:
        """分类工作流类型"""
        name_lower = (filename + " " + folder).lower()

        # 文件名关键词优先
        for cat, keywords in cls.CATEGORY_KEYWORDS.items():
            if any(k in name_lower for k in keywords):
                return cat

        # 节点类型推断
        if cls.LTX_NODES & types:
            return "ltx_video"
        if cls.WAN_NODES & types:
            return "wan_video"
        if cls.FLUX_NODES & types:
            return "flux"
        if cls.CONTROLNET_NODES & types:
            return "controlnet"
        if cls.IPADAPTER_NODES & types:
            return "ipadapter"
        if cls.VIDEO_NODES & types:
            return "video"

        return "other"


# =============================================================================
# 蓝图挖掘器
# =============================================================================

class BlueprintMiner:
    """核心：从批量真实工作流中挖掘生产蓝图"""

    def __init__(self):
        self.workflows: List[MinedWorkflow] = []
        self.node_counter: Counter = Counter()
        self.edge_counter: Counter = Counter()
        self.pipeline_counter: Counter = Counter()
        self.category_workflows: Dict[str, List[MinedWorkflow]] = defaultdict(list)

    def scan(self, root_dirs: List[str]) -> int:
        """扫描并分析所有工作流"""
        files = WorkflowLoader.find_all(root_dirs)
        for path in files:
            wf = self._analyze_single(path)
            if wf and wf.node_count >= 3:
                self.workflows.append(wf)
                self.category_workflows[wf.category].append(wf)
                for ct in set(wf.class_types):
                    self.node_counter[ct] += 1
                for edge in set(wf.edges):
                    self.edge_counter[edge] += 1
        return len(self.workflows)

    def _analyze_single(self, path: str) -> Optional[MinedWorkflow]:
        """分析单个工作流文件"""
        data = WorkflowLoader.load(path)
        if not data:
            return None

        folder = os.path.basename(os.path.dirname(path))
        class_types = []
        edges = []

        # 尝试解析 Save V1 格式
        nodes = data.get("nodes", [])
        links = data.get("links", [])
        if not nodes and isinstance(data, dict):
            # 可能是 API Prompt 格式
            for node_id, node in data.items():
                if isinstance(node, dict) and "class_type" in node:
                    class_types.append(node["class_type"])
                    for key, val in node.get("inputs", {}).items():
                        if isinstance(val, (list, tuple)) and len(val) == 2:
                            edges.append((node["class_type"], key, str(val[0]), ""))
        else:
            for node in nodes:
                ct = node.get("type", "")
                if ct:
                    class_types.append(ct)
                # 提取 edges
                for inp in node.get("inputs", []):
                    if inp.get("link") is not None:
                        # 查找 link 获取来源
                        link_id = inp["link"]
                        for link in links:
                            if isinstance(link, dict) and link.get("id") == link_id:
                                edges.append((ct, inp.get("name", ""),
                                             str(link.get("origin_id", "")), ""))
                            elif isinstance(link, list) and len(link) >= 5 and link[0] == link_id:
                                edges.append((ct, inp.get("name", ""), str(link[1]), ""))

        if not class_types:
            return None

        types_set = set(class_types)
        cat = WorkflowClassifier.classify(types_set, os.path.basename(path), folder)

        # 构建节点连接图
        node_graph = defaultdict(list)
        for ct, key, src, _ in edges:
            node_graph[ct].append(src)

        return MinedWorkflow(
            path=path,
            folder=folder,
            node_count=len(class_types),
            class_types=class_types,
            unique_types=len(types_set),
            has_load_image="LoadImage" in types_set,
            has_save_image="SaveImage" in types_set or "PreviewImage" in types_set,
            has_video_output="VHS_VideoCombine" in types_set,
            category=cat,
            node_graph=dict(node_graph),
            edges=edges,
        )

    def mine_blueprints(self, min_workflows: int = 2,
                        min_confidence: float = 0.3) -> List[ProductionBlueprint]:
        """从所有工作流中挖掘生产蓝图"""
        blueprints = []

        for category, wfs in self.category_workflows.items():
            if len(wfs) < min_workflows:
                continue

            bp = self._mine_category(category, wfs)
            if bp and bp.confidence_score >= min_confidence:
                blueprints.append(bp)

        blueprints.sort(key=lambda x: -x.confidence_score)
        return blueprints

    def _mine_category(self, category: str,
                       workflows: List[MinedWorkflow]) -> Optional[ProductionBlueprint]:
        """从同类工作流中挖掘一个蓝图"""
        total = len(workflows)
        if total < 2:
            return None

        # 节点频率统计
        node_counter: Counter = Counter()
        edge_counter: Counter = Counter()
        node_counts = []

        for wf in workflows:
            for ct in set(wf.class_types):
                node_counter[ct] += 1
            for edge in set(wf.edges):
                edge_counter[edge] += 1
            node_counts.append(wf.node_count)

        # 高频节点（出现率 >= 60%）
        required_nodes = sorted([
            node for node, count in node_counter.items()
            if count / total >= 0.6
        ])

        # 中等频率节点（25%-60%）
        optional_nodes = sorted([
            node for node, count in node_counter.items()
            if 0.25 <= count / total < 0.6
        ])

        # 高频连接
        common_edges = [
            (ct1, slot1, ct2, slot2)
            for (ct1, slot1, ct2, slot2), count in edge_counter.most_common(20)
            if count / total >= 0.3
        ]

        # 置信度 = 节点覆盖率 * 重复数因子
        if required_nodes and node_counter:
            covered_ratio = len(required_nodes) / max(len(node_counter), 1)
            confidence = min(1.0, covered_ratio * (1 + total * 0.1))

        # 阶段结构推断
        pipeline = self._infer_pipeline(required_nodes, optional_nodes, category)

        # 模型类型
        model_type = self._detect_model_type(required_nodes, category)

        # 显示名
        name_map = {
            "ltx_video": "LTX 视频", "flux": "Flux 图像",
            "wan_video": "Wan 视频", "video": "通用视频",
            "txt2img": "文生图", "img2img": "图生图",
            "controlnet": "控制生成", "ipadapter": "参考图",
            "image_edit": "图像编辑", "action_transfer": "动作迁移",
            "character_replace": "换装", "face_swap": "换脸",
            "lipsync": "数字人对口型",
        }

        return ProductionBlueprint(
            name=f"mined_{category}",
            display_name=name_map.get(category, category),
            category=category,
            source_workflow_count=total,
            confidence_score=round(confidence, 3),
            required_nodes=required_nodes,
            optional_nodes=optional_nodes,
            common_edges=common_edges[:10],
            estimated_node_count=round(sum(node_counts) / total),
            typical_pipeline=pipeline,
            model_type=model_type,
        )

    def _infer_pipeline(self, required: List[str], optional: List[str],
                        category: str) -> List[str]:
        """推断工作流的阶段结构"""
        stages = []
        has_input = any(n in required for n in ["LoadImage"])
        has_model = any(n in required for n in ["CheckpointLoaderSimple", "UNETLoader"])
        has_clip = any(n in required for n in ["CLIPTextEncode", "DualCLIPLoader"])
        has_latent = any(n in required for n in ["EmptyLatentImage", "EmptyLTXVLatentVideo"])
        has_sampler = any("Sampler" in n for n in required)
        has_vae = any("VAE" in n for n in required)
        has_video = any(n in required for n in ["VHS_VideoCombine"])
        has_controlnet = any("ControlNet" in n for n in required + optional)

        if has_input: stages.append("图输入")
        if has_model: stages.append("模型加载")
        elif "flux" in category: stages.append("Flux 模型加载")
        if has_clip: stages.append("文本编码")
        if has_latent: stages.append("潜变量初始化")
        if has_controlnet: stages.append("控制条件")
        if has_sampler: stages.append("采样")
        if has_vae: stages.append("解码")
        if has_video: stages.append("视频合成")
        else: stages.append("输出")

        return stages

    def _detect_model_type(self, required: List[str], category: str) -> str:
        if category in ("flux",): return "flux"
        if category in ("ltx_video",): return "ltx"
        if category in ("wan_video",): return "wan"
        if any("XL" in n for n in required): return "sdxl"
        return "sdxl"

    def report(self) -> Dict:
        """生成挖掘报告"""
        return {
            "total_workflows": len(self.workflows),
            "categories": {
                cat: len(wfs) for cat, wfs in
                sorted(self.category_workflows.items(), key=lambda x: -len(x[1]))
            },
            "top_nodes": self.node_counter.most_common(20),
            "top_edges": self.edge_counter.most_common(15),
        }

    def save_blueprints(self, blueprints: List[ProductionBlueprint],
                        output_dir: str = "mined_blueprints"):
        """将挖掘出的蓝图保存为 JSON 文件"""
        os.makedirs(output_dir, exist_ok=True)
        for bp in blueprints:
            path = os.path.join(output_dir, f"{bp.name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "name": bp.name,
                    "display_name": bp.display_name,
                    "category": bp.category,
                    "source_workflow_count": bp.source_workflow_count,
                    "confidence_score": bp.confidence_score,
                    "required_nodes": bp.required_nodes,
                    "optional_nodes": bp.optional_nodes,
                    "common_edges": bp.common_edges,
                    "estimated_node_count": bp.estimated_node_count,
                    "typical_pipeline": bp.typical_pipeline,
                    "model_type": bp.model_type,
                }, f, ensure_ascii=False, indent=2)
        return output_dir
