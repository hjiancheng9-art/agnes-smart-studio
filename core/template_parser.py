"""Workflow Template Parser v2 — 使用 PyYAML 解析模板 (B2+B3)

比 v1 更健壮：使用 yaml.safe_load 解析，支持 YAML 和 JSON 两种格式。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json
import logging
import re

logger = logging.getLogger(__name__)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    logger.warning("PyYAML 未安装，使用回退解析器")


# ═══════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TemplateNode:
    name: str
    class_type: str
    params: dict = field(default_factory=dict)
    param_ranges: dict = field(default_factory=dict)


@dataclass
class ParsedTemplate:
    workflow_id: str
    name: str
    task_type: str
    category: str
    description: str
    nodes: list[TemplateNode] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    estimated_vram_gb: int = 8


# ═══════════════════════════════════════════════════════════════════
# 解析器
# ═══════════════════════════════════════════════════════════════════

def parse_template_json(text: str) -> ParsedTemplate | None:
    """从 JSON 格式解析模板。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    wf_id = data.get("workflow_id") or data.get("id", "")
    if not wf_id:
        return None

    # Extract nodes from inputs bindings
    nodes: dict[str, TemplateNode] = {}
    for inp in data.get("inputs", []):
        binding = inp.get("binding", {})
        nid = binding.get("node_id", "")
        ct = binding.get("class_type", "")
        iname = binding.get("input", "")
        default = inp.get("default")
        
        if not nid or not ct:
            continue
        
        if nid not in nodes:
            nodes[nid] = TemplateNode(name=nid, class_type=ct)
        
        if default is not None:
            nodes[nid].params[iname] = default
        
        # Param ranges
        if "min" in inp and "max" in inp:
            nodes[nid].param_ranges[iname] = {
                "min": inp["min"],
                "max": inp["max"],
                "default": default,
                "step": inp.get("step", 1),
            }
        elif inp.get("ui", {}).get("widget") == "slider":
            nodes[nid].param_ranges[iname] = {
                "default": default or 20,
                "min": inp.get("min", 1),
                "max": inp.get("max", 80),
            }

    return ParsedTemplate(
        workflow_id=wf_id,
        name=data.get("name", wf_id),
        task_type=data.get("task_type", "txt2img"),
        category=data.get("category", "image"),
        description=data.get("description", ""),
        nodes=list(nodes.values()),
        models=[m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)],
        tags=data.get("recommendation", {}).get("tags", []),
        estimated_vram_gb=data.get("runtime", {}).get("estimated_vram_gb", 8),
    )


def parse_template_yaml(text: str) -> ParsedTemplate | None:
    """从 YAML 格式解析模板。"""
    if not HAS_YAML:
        return None
    
    text = _preprocess_yaml(text)
    
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    
    if not isinstance(data, dict) or not data.get("workflow_id"):
        return None
    
    return _from_yaml_dict(data)


def _preprocess_yaml(text: str) -> str:
    """预处理压缩的 YAML，插入缺失的换行。"""
    # Keys that should start on a new line
    root_keys = [
        r'workflow_id:', r'name:', r'version:', r'category:', r'task_type:',
        r'description:', r'crux:', r'requirements:', r'inputs:', r'outputs:',
        r'recommendation:', r'runtime:',
    ]
    pattern = r'(\S)(' + '|'.join(root_keys) + r')'
    text = re.sub(pattern, r'\1\n\2', text)
    
    # Handle nested: indent before sub-keys
    text = re.sub(r'(\S)(\n\s+(?:stages|comfyui|custom_nodes|models|min_version|type|name):)', r'\1\2', text)
    
    return text


def _from_yaml_dict(data: dict) -> ParsedTemplate | None:
    """从 YAML dict 构建 ParsedTemplate。"""
    wf_id = data.get("workflow_id")
    if not wf_id:
        return None
    
    # Extract from inputs
    nodes: dict[str, TemplateNode] = {}
    for inp in data.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        binding = inp.get("binding", {})
        nid = str(binding.get("node_id", "")) if binding else ""
        ct = str(binding.get("class_type", "")) if binding else ""
        iname = str(binding.get("input", "")) if binding else ""
        default = inp.get("default")
        
        if not nid or not ct:
            continue
        if nid not in nodes:
            nodes[nid] = TemplateNode(name=nid, class_type=ct)
        if default is not None:
            nodes[nid].params[iname] = default
        if "min" in inp and "max" in inp:
            nodes[nid].param_ranges[iname] = {
                "min": inp["min"],
                "max": inp["max"],
                "default": default,
            }
    
    # Models
    models = []
    for m in data.get("models", []):
        if isinstance(m, dict) and "name" in m:
            models.append(m["name"])
        elif isinstance(m, str):
            models.append(m)
    
    # Tags
    rec = data.get("recommendation", {})
    tags = rec.get("tags", []) if isinstance(rec, dict) else []
    
    return ParsedTemplate(
        workflow_id=str(wf_id),
        name=str(data.get("name", wf_id)),
        task_type=str(data.get("task_type", "txt2img")),
        category=str(data.get("category", "image")),
        description=str(data.get("description", "")),
        nodes=list(nodes.values()),
        models=models,
        tags=tags,
        estimated_vram_gb=data.get("runtime", {}).get("estimated_vram_gb", 8),
    )


# ═══════════════════════════════════════════════════════════════════
# 转换为 Motif
# ═══════════════════════════════════════════════════════════════════

def parsed_to_motif(template: ParsedTemplate, registry=None) -> bool:
    """将解析后的模板注册为 Motif。"""
    from core.comfyui_motif import MotifDefinition, MotifNode, MotifEdge, get_registry
    
    reg = registry or get_registry()
    
    motif_nodes = [
        MotifNode(
            role=n.name,
            class_type=n.class_type,
            params=dict(n.params),
            param_ranges=dict(n.param_ranges),
        )
        for n in template.nodes
    ]
    
    # Infer edges from class types
    edges = _infer_edges(template.nodes)
    
    motif = MotifDefinition(
        motif_id=template.workflow_id,
        name=template.name,
        description=template.description,
        category=template.category,
        task_types=[template.task_type],
        nodes=motif_nodes,
        edges=[MotifEdge(s, "out", t, "in") for s, t in edges],
        source_templates=[template.workflow_id],
        quality_score=0.7,
        compatible_models=template.models,
        min_vram_gb=template.estimated_vram_gb,
        version="1.0.0",
    )
    
    return reg.register(motif, source="template_parser")


def _infer_edges(nodes: list[TemplateNode]) -> list[tuple[str, str]]:
    """根据节点 class_types 推断连接。"""
    edges = []
    class_map = {n.name: n.class_type for n in nodes}
    names = [n.name for n in nodes]
    
    # Checkpoint → sampler / clip / vae
    ckpt = next((n for n in names if 'Checkpoint' in (class_map.get(n, ''))), None)
    clip = next((n for n in names if 'CLIPTextEncode' in (class_map.get(n, ''))), None)
    sampler = next((n for n in names if 'KSampler' in (class_map.get(n, ''))), None)
    latent = next((n for n in names if 'EmptyLatentImage' in (class_map.get(n, ''))), None)
    vae_decode = next((n for n in names if 'VAEDecode' in (class_map.get(n, ''))), None)
    save = next((n for n in names if 'SaveImage' in (class_map.get(n, ''))), None)
    load_img = next((n for n in names if 'LoadImage' in (class_map.get(n, ''))), None)
    vae_encode = next((n for n in names if 'VAEEncode' in (class_map.get(n, ''))), None)
    lora = next((n for n in names if 'LoraLoader' in (class_map.get(n, ''))), None)
    
    if ckpt and sampler:
        edges.append((ckpt, sampler))
    if ckpt and clip:
        edges.append((ckpt, clip))
    if ckpt and vae_decode:
        edges.append((ckpt, vae_decode))
    if ckpt and vae_encode:
        edges.append((ckpt, vae_encode))
    if ckpt and lora:
        edges.append((ckpt, lora))
    if lora and sampler:
        edges.append((lora, sampler))
    if lora and clip:
        edges.append((lora, clip))
    if clip and sampler:
        edges.append((clip, sampler))
    if latent and sampler:
        edges.append((latent, sampler))
    if sampler and vae_decode:
        edges.append((sampler, vae_decode))
    if vae_decode and save:
        edges.append((vae_decode, save))
    if load_img and vae_encode:
        edges.append((load_img, vae_encode))
    if vae_encode and sampler:
        edges.append((vae_encode, sampler))
    
    return edges


# ═══════════════════════════════════════════════════════════════════
# 批量处理
# ═══════════════════════════════════════════════════════════════════

def parse_many(text: str, format: str = "auto") -> tuple[int, int, list[str]]:
    """从文本中批量解析模板并注册。
    
    Returns:
        (成功数, 识别数, 错误列表)
    """
    from core.comfyui_motif import get_registry
    
    reg = get_registry()
    errors = []
    
    if format == "json":
        blocks = re.split(r'\n\s*\n', text)
        blocks = [b.strip() for b in blocks if b.strip()]
    else:
        # Split by workflow_id
        blocks = re.split(r'(?=workflow_id:)', text)
        blocks = [b.strip() for b in blocks if b.strip() and 'workflow_id' in b[:50]]
    
    success = 0
    for block in blocks:
        parsed = None
        if format == "json" or (format == "auto" and block.startswith('{')):
            parsed = parse_template_json(block)
        if not parsed:
            parsed = parse_template_yaml(block)
        if parsed:
            if parsed_to_motif(parsed, reg):
                success += 1
    
    return success, len(blocks), errors


def save_snapshot(reg=None, path: str = "motif_snapshot.json"):
    """保存 Motif 快照。"""
    from core.comfyui_motif import get_registry
    r = reg or get_registry()
    snapshot = {
        "total": len(r.list_all()),
        "motifs": [m.to_dict() for m in r.list_all()],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return path
