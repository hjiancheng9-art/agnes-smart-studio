"""ComfyFlow Compiler — 生产蓝图自动加载器

启动时自动扫描真实工作流目录，挖掘并注册生产级蓝图。
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from .blueprint_miner import BlueprintMiner, ProductionBlueprint
from .blueprint_registry import BlueprintRegistry, Blueprint, Recipe, BlueprintRequirement


DEFAULT_WORKFLOW_DIRS = [
    # 常见的真实工作流存放位置
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents/ComfyUI/workflows"),
]


def auto_mine_blueprints(
    registry: BlueprintRegistry,
    custom_dirs: Optional[List[str]] = None,
    min_workflows: int = 2,
    cache_path: Optional[str] = None,
) -> int:
    """
    自动扫描并注册生产蓝图到 registry。

    Args:
        registry: BlueprintRegistry 实例（会直接修改）
        custom_dirs: 自定义工作流目录（优先级高）
        min_workflows: 最少工作流数要求
        cache_path: 缓存路径（避免每次重新扫描）

    Returns:
        新注册的蓝图数
    """
    # 确定扫描目录
    scan_dirs = custom_dirs or DEFAULT_WORKFLOW_DIRS
    existing = [d for d in scan_dirs if os.path.exists(d)]

    if not existing:
        return 0

    # 尝试从缓存加载
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached:
                return _load_cached(registry, cached)
        except Exception:
            pass

    # 扫描
    miner = BlueprintMiner()
    count = miner.scan(existing)
    if count < min_workflows:
        return 0

    # 挖掘
    mined = miner.mine_blueprints(min_workflows=1, min_confidence=0.1)

    # 注册
    task_map = {
        "ltx_video": "video", "flux": "txt2img", "wan_video": "video",
        "video": "video", "image_edit": "img2img", "lipsync": "video",
        "action_transfer": "video", "txt2img": "txt2img", "img2img": "img2img",
    }

    registered = 0
    for mb in mined:
        if mb.category in ("other", ""):
            continue
        name = f"auto_{mb.category}"
        if name in registry.blueprints:
            continue

        bp = Blueprint(
            name=name,
            display_name=f"生产:{mb.display_name}",
            description=f"从 {mb.source_workflow_count} 个工作流自动挖掘",
            task_type=task_map.get(mb.category, "txt2img"),
            style_tags=[mb.category, "production"],
            required_nodes=mb.required_nodes,
            optional_nodes=mb.optional_nodes,
            min_vram_gb=8.0,
            min_budget_score=4.0,
            quality_score=min(1.0, mb.confidence_score * 1.2),
            chain_depth=0,
        )
        registry.blueprints[name] = bp
        registry.requirements[name] = BlueprintRequirement(
            blueprint_name=name, min_vram_gb=6.0, min_budget_score=3.0,
            quality_weight=max(0.5, mb.confidence_score),
        )
        registered += 1

    # 写缓存
    if cache_path and mined:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump([
                    {"category": mb.category, "display_name": mb.display_name,
                     "required_nodes": mb.required_nodes, "optional_nodes": mb.optional_nodes,
                     "confidence_score": mb.confidence_score,
                     "source_workflow_count": mb.source_workflow_count}
                    for mb in mined
                ], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return registered


def _load_cached(registry: BlueprintRegistry, cached: list) -> int:
    task_map = {
        "ltx_video": "video", "flux": "txt2img", "wan_video": "video",
        "video": "video", "image_edit": "img2img", "lipsync": "video",
    }
    registered = 0
    for item in cached:
        name = f"auto_{item['category']}"
        if name in registry.blueprints:
            continue
        bp = Blueprint(
            name=name,
            display_name=f"生产:{item['display_name']}",
            description=f"从 {item['source_workflow_count']} 个工作流自动挖掘（缓存）",
            task_type=task_map.get(item["category"], "txt2img"),
            style_tags=[item["category"], "production"],
            required_nodes=item["required_nodes"],
            optional_nodes=item.get("optional_nodes", []),
            min_vram_gb=8.0, min_budget_score=4.0,
            quality_score=min(1.0, item["confidence_score"] * 1.2),
            chain_depth=0,
        )
        registry.blueprints[name] = bp
        registry.requirements[name] = BlueprintRequirement(
            blueprint_name=name, min_vram_gb=6.0, min_budget_score=3.0,
            quality_weight=max(0.5, item["confidence_score"]),
        )
        registered += 1
    return registered
