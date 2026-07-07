"""YAML Workflow 模板解析器 — 从模板文件提取 Motif (B2+B3)

解析 YAML 格式的 ComfyUI 工作流模板，提取子图模式和连接模式，
归一化后注册到 MotifRegistry。

参考: COMFYUI_METHODOLOGY.md 原则 2 (优先复用)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import json
import logging
import re

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 模板解析
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ParsedBinding:
    """从模板中解析出的节点绑定信息。"""

    node_id: str
    class_type: str
    input_name: str
    param_value: Any = None
    param_type: str = "string"  # string / integer / float / boolean
    param_range: dict | None = None  # {min, max, default, step} for numeric params


@dataclass
class ParsedWorkflowTemplate:
    """解析后的工作流模板。"""

    workflow_id: str
    name: str
    task_type: str
    category: str
    description: str
    bindings: list[ParsedBinding] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    estimated_vram_gb: int = 8
    timeout_seconds: int = 900

    def get_node_class_types(self) -> dict[str, str]:
        """获取 {node_id → class_type} 映射。"""
        return {b.node_id: b.class_type for b in self.bindings}

    def get_param_for_node(self, node_id: str) -> dict:
        """获取节点的参数配置。"""
        return {
            b.input_name: b.param_value for b in self.bindings if b.node_id == node_id and b.param_value is not None
        }


def _normalize_yaml(text: str) -> str:
    """在压缩的 YAML 键之间插入换行。"""
    # Known YAML keys that start on the same line as previous values
    keys = r"(name:|version:|category:|task_type:|description:|crux:|requirements:|inputs:|outputs:|recommendation:|runtime:|workflow_id:)"
    # Insert newline before these keys if not already there
    text = re.sub(r"(\S)(" + keys + r")", r"\1\n\2", text)
    # Also handle nested keys
    text = re.sub(r"(\S)(\n\s+min:)", r"\1\2", text)
    return text


def parse_yaml_template(yaml_text: str) -> ParsedWorkflowTemplate | None:
    """解析一段 YAML 工作流模板文本为结构化数据。"""
    text = _normalize_yaml(yaml_text.strip())
    if not text or not text.startswith("workflow_id:"):
        return None

    try:
        # Extract basic fields
        wf_id = _extract_field(text, "workflow_id:", r"(\S+)")
        name = _extract_field(text, "name:", r"(.+)")
        task_type = _extract_field(text, "task_type:", r"(\S+)")
        category = _extract_field(text, "category:", r"(\S+)")
        desc = _extract_field(text, "description:", r"(.+)")
        vram = _extract_int(text, "estimated_vram_gb:", 8)

        # Extract models
        models = _extract_list_items(text, "models:", "name:")

        # Extract tags
        tags = _extract_list_items(text, "tags:", r"- (.+)")

        # Extract input bindings
        inputs_section = _extract_section(text, "inputs:", "outputs:")
        bindings = _parse_bindings(inputs_section)

        return ParsedWorkflowTemplate(
            workflow_id=wf_id or "",
            name=name or "",
            task_type=task_type or "txt2img",
            category=category or "image",
            description=desc or "",
            bindings=bindings,
            models=models,
            tags=tags,
            estimated_vram_gb=vram,
        )
    except Exception as e:
        logger.warning("解析模板失败: %s", e)
        return None


def _extract_field(text: str, key: str, pattern: str) -> str | None:
    """提取字段值（无换行的简单字段）。"""
    # Build a regex that matches key + value on the same line
    # The key should be at the start of a line
    escaped_key = re.escape(key)
    m = re.search(r"^" + escaped_key + r"\s*(.*?)$", text, re.MULTILINE)
    if m:
        line = m.group(1).strip()
        if line:
            return line.strip("\"'")
    return None


def _extract_int(text: str, key: str, default: int = 0) -> int:
    val = _extract_field(text, key, r"")
    if val and val.lstrip("-").isdigit():
        return int(val)
    return default


def _extract_section(text: str, start_key: str, end_key: str) -> str:
    """提取两个 key 之间的段落。"""
    start = text.find(start_key)
    if start < 0:
        return ""
    end = text.find(end_key, start + len(start_key))
    if end < 0:
        return text[start + len(start_key) :].strip()
    return text[start + len(start_key) : end].strip()


def _extract_list_items(text: str, list_key: str, item_pattern: str) -> list[str]:
    """提取列表项。"""
    section = _extract_section(text, list_key, "")
    if not section:
        # Try inline
        idx = text.find(list_key)
        if idx < 0:
            return []
        after = text[idx + len(list_key) :].strip()
        lines_after = []
        for l in after.split("\n"):
            if l.strip().startswith("- "):
                lines_after.append(l)
            else:
                break
        section = "\n".join(lines_after)

    items = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            val = line[2:].strip("\"'")
            # Try to match the item pattern for sub-field extraction
            if item_pattern:
                m = re.search(item_pattern, line)
                if m:
                    try:
                        val = m.group(1).strip("\"'")
                    except (IndexError, AttributeError):
                        pass
            if val and val != "null":
                items.append(val)
    return items


def _parse_bindings(inputs_section: str) -> list[ParsedBinding]:
    """解析 inputs 部分的绑定信息。"""
    bindings = []
    if not inputs_section:
        return bindings

    # Split by "- id:" blocks
    blocks = re.split(r"\n\s*- id:", inputs_section)
    for block in blocks:
        if not block.strip():
            continue
        block = "- id:" + block  # restore the split marker

        # Get param id
        param_id = _extract_field(block, "id:", r"(\S+)")
        # Get binding info
        binding_node = _extract_field(block, "node_id:", r'"(\d+)"')
        binding_class = _extract_field(block, "class_type:", r"(\S+)")
        binding_input = _extract_field(block, "input:", r"(\S+)")
        default_val = _extract_field(block, "default:", r"(.+)")

        # Get param range
        param_range = None
        pmin = _extract_field(block, "min:", r"(-?\d+)")
        pmax = _extract_field(block, "max:", r"(-?\d+)")
        pstep = _extract_field(block, "step:", r"(-?\d+)")
        if pmin and pmax:
            param_range = {
                "min": int(pmin),
                "max": int(pmax),
                "default": int(default_val) if default_val and default_val.lstrip("-").isdigit() else None,
                "step": int(pstep) if pstep else 1,
            }

        # Get type
        ptype = _extract_field(block, "type:", r"(\S+)")
        if not ptype and default_val:
            ptype = "number" if default_val.replace(".", "", 1).lstrip("-").isdigit() else "string"

        if binding_node and binding_class:
            bindings.append(
                ParsedBinding(
                    node_id=binding_node,
                    class_type=binding_class,
                    input_name=binding_input or param_id or "",
                    param_value=int(default_val) if default_val and default_val.lstrip("-").isdigit() else default_val,
                    param_type=ptype or "string",
                    param_range=param_range,
                )
            )

    return bindings


# ═══════════════════════════════════════════════════════════════════
# 模板归一化 → Motif 提取
# ═══════════════════════════════════════════════════════════════════


def template_to_motif(template: ParsedWorkflowTemplate) -> tuple | None:
    """将解析后的模板转换为 MotifDefinition 并注册到 Registry。

    Returns:
        (MotifDefinition, edges) or None if parsing fails
    """
    from core.comfyui_motif import MotifDefinition, MotifNode, MotifEdge

    if not template.bindings:
        return None

    # Extract unique class_types as nodes
    node_ids = {}
    motif_nodes = []
    node_counter = 0

    for binding in template.bindings:
        nid = binding.node_id
        if nid not in node_ids:
            node_counter += 1
            role_id = f"n{node_counter}"
            node_ids[nid] = role_id

            params = {}
            param_ranges = {}
            if binding.param_value is not None:
                params[binding.input_name] = binding.param_value
            if binding.param_range:
                param_ranges[binding.input_name] = binding.param_range

            motif_nodes.append(
                MotifNode(
                    role=role_id,
                    class_type=binding.class_type,
                    params=params,
                    param_ranges=param_ranges,
                )
            )
        else:
            # Update params for existing node
            role_id = node_ids[nid]
            for mn in motif_nodes:
                if mn.role == role_id and binding.param_value is not None:
                    mn.params[binding.input_name] = binding.param_value
                    if binding.param_range:
                        mn.param_ranges[binding.input_name] = binding.param_range

    # Infer edges from common patterns
    # (Actual edge extraction from topology requires full workflow JSON)
    # For now, use heuristics based on class types
    inferred_edges = _infer_edges(node_ids, template.bindings)

    # Create MotifDefinition
    motif = MotifDefinition(
        motif_id=template.workflow_id,
        name=template.name,
        description=template.description,
        category=template.category,
        task_types=[template.task_type],
        nodes=motif_nodes,
        edges=[MotifEdge(s, "out", t, "in") for s, t in inferred_edges],
        source_templates=[template.workflow_id],
        quality_score=0.7,  # default, will be updated after validation
        compatible_models=list(set(m.split("/")[-1] for m in template.models)),
        min_vram_gb=template.estimated_vram_gb,
        version="1.0.0",
    )

    return motif, inferred_edges


def _infer_edges(node_ids: dict[str, str], bindings: list[ParsedBinding]) -> list[tuple[str, str]]:
    """根据节点类型推断连接关系。"""
    # Build class_type to role_id mapping
    class_to_role = {}
    for nid, role in node_ids.items():
        for b in bindings:
            if b.node_id == nid:
                class_to_role[b.class_type] = role
                break

    # Common pipeline patterns
    edges = []
    class_types = list(class_to_role.keys())

    # CheckpointLoader → others
    if "CheckpointLoaderSimple" in class_types:
        ckpt = class_to_role["CheckpointLoaderSimple"]
        if "CLIPTextEncode" in class_types:
            clip = class_to_role["CLIPTextEncode"]
            edges.append((ckpt, clip))
        if "KSampler" in class_types:
            sampler = class_to_role["KSampler"]
            edges.append((ckpt, sampler))
        if "VAEDecode" in class_types:
            decode = class_to_role["VAEDecode"]
            edges.append((ckpt, decode))

    # CLIPTextEncode → KSampler
    if "CLIPTextEncode" in class_types and "KSampler" in class_types:
        edges.append((class_to_role["CLIPTextEncode"], class_to_role["KSampler"]))

    # EmptyLatentImage → KSampler
    if "EmptyLatentImage" in class_types and "KSampler" in class_types:
        edges.append((class_to_role["EmptyLatentImage"], class_to_role["KSampler"]))

    # KSampler → VAEDecode
    if "KSampler" in class_types and "VAEDecode" in class_types:
        edges.append((class_to_role["KSampler"], class_to_role["VAEDecode"]))

    # VAEDecode → SaveImage
    if "VAEDecode" in class_types and "SaveImage" in class_types:
        edges.append((class_to_role["VAEDecode"], class_to_role["SaveImage"]))

    # LoadImage → VAEEncode → KSampler (img2img)
    if "LoadImage" in class_types and "VAEEncode" in class_types:
        edges.append((class_to_role["LoadImage"], class_to_role["VAEEncode"]))
        if "KSampler" in class_types:
            edges.append((class_to_role["VAEEncode"], class_to_role["KSampler"]))

    return edges


# ═══════════════════════════════════════════════════════════════════
# 批量解析 — 从文本批量提取模板并注册为 Motif
# ═══════════════════════════════════════════════════════════════════


def parse_and_register(text: str, registry=None, source: str = "text") -> tuple[int, int, list[str]]:
    """从文本中批量解析 YAML 模板并注册到 MotifRegistry。

    Returns:
        (成功数, 总数, 错误列表)
    """
    from core.comfyui_motif import get_registry, reset_registry

    reg = registry or get_registry()
    errors: list[str] = []

    # Split by "workflow_id:" markers
    blocks = re.split(r"(?=workflow_id:)", text)
    blocks = [b.strip() for b in blocks if b.strip()]

    success = 0
    for block in blocks:
        try:
            template = parse_yaml_template(block)
            if not template:
                continue
            result = template_to_motif(template)
            if not result:
                continue
            motif, edges = result
            if reg.register(motif, source=source):
                success += 1
        except Exception as e:
            errors.append(f"解析失败: {e}")

    return success, len(blocks), errors


def save_registry_snapshot(registry=None, path: str = "motif_registry_snapshot.json"):
    """保存 MotifRegistry 快照到 JSON 文件。"""
    from core.comfyui_motif import get_registry

    reg = registry or get_registry()
    snapshot = {
        "total": len(reg.list_all()),
        "motifs": [m.to_dict() for m in reg.list_all()],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"Motif 快照已保存: {path}")
    return path
