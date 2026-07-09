"""ComfyFlow Compiler — Workflow 格式解析器

支持三种 ComfyUI Workflow 格式：
- API Prompt:  {node_id: {class_type, inputs}}  → POST /prompt
- Save V1:     {version:1, state, nodes, links, models}  → 前端拖入
- Legacy:      老 LiteGraph 格式兼容
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import json


class WorkflowFormat(Enum):
    API_PROMPT = "api_prompt"
    SAVE_V1 = "save_v1"
    LEGACY = "legacy"
    UNKNOWN = "unknown"


def detect_format(workflow: Any) -> WorkflowFormat:
    """自动检测 Workflow JSON 格式"""
    if not isinstance(workflow, dict):
        return WorkflowFormat.UNKNOWN

    # Save V1: 有 version 且 version == 1，且有 state 和 nodes
    if "version" in workflow and workflow.get("version") == 1:
        if "state" in workflow and "nodes" in workflow:
            return WorkflowFormat.SAVE_V1

    # API Prompt: key 是字符串数字，每项有 class_type 和 inputs
    keys = list(workflow.keys())
    if keys and all(k.isdigit() for k in keys[:5]):
        first = workflow[keys[0]]
        if isinstance(first, dict) and "class_type" in first and "inputs" in first:
            return WorkflowFormat.API_PROMPT

    # Legacy: 有 nodes / links / groups 顶层数组
    if "nodes" in workflow and isinstance(workflow["nodes"], list):
        return WorkflowFormat.LEGACY

    return WorkflowFormat.UNKNOWN


# =============================================================================
# API Prompt Format 操作
# =============================================================================

def to_api_prompt(workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """任意格式 → API Prompt Format"""
    fmt = detect_format(workflow)

    if fmt == WorkflowFormat.API_PROMPT:
        return workflow

    if fmt == WorkflowFormat.SAVE_V1:
        return _save_v1_to_api(workflow)

    if fmt == WorkflowFormat.LEGACY:
        return _legacy_to_api(workflow)

    return None


def _save_v1_to_api(save_v1: Dict[str, Any]) -> Dict[str, Any]:
    """Save V1 → API Prompt"""
    api = {}
    nodes = save_v1.get("nodes", [])

    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue

        api_node = {
            "class_type": node.get("type", ""),
            "inputs": {},
        }

        # 处理 widgets_values（直接输入）
        widgets = node.get("widgets_values", [])
        # 从 type 的定义推断 widget 名称需要 object_info，这里简化
        # 只处理已知的 widgets 顺序
        if api_node["class_type"] == "KSampler" and len(widgets) >= 5:
            api_node["inputs"] = {
                "seed": widgets[0],
                "steps": widgets[1],
                "cfg": widgets[2],
                "sampler_name": widgets[3],
                "scheduler": widgets[4],
                "denoise": widgets[5] if len(widgets) > 5 else 1.0,
            }
        elif api_node["class_type"] == "CLIPTextEncode" and len(widgets) >= 1:
            api_node["inputs"]["text"] = widgets[0]
        elif api_node["class_type"] == "EmptyLatentImage" and len(widgets) >= 3:
            api_node["inputs"]["width"] = widgets[0]
            api_node["inputs"]["height"] = widgets[1]
            api_node["inputs"]["batch_size"] = widgets[2]
        elif api_node["class_type"] == "CheckpointLoaderSimple" and len(widgets) >= 1:
            api_node["inputs"]["ckpt_name"] = widgets[0]

        # 处理连接 (inputs 引用)
        for inp in node.get("inputs", []):
            name = inp.get("name", "")
            if inp.get("link") is not None:
                # 查找 link 对象获取来源
                link_id = inp["link"]
                for link in save_v1.get("links", []):
                    if isinstance(link, dict) and link.get("id") == link_id:
                        api_node["inputs"][name] = [str(link["origin_id"]), link["origin_slot"]]
                        break
                    elif isinstance(link, list) and len(link) >= 5 and link[0] == link_id:
                        api_node["inputs"][name] = [str(link[1]), link[2]]
                        break
            elif inp.get("widget") is not None:
                pass  # 已通过 widgets_values 处理

        api[node_id] = api_node

    return api


def _legacy_to_api(legacy: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy LiteGraph → API Prompt"""
    api = {}
    nodes = legacy.get("nodes", [])

    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue

        api_node = {
            "class_type": node.get("type", ""),
            "inputs": {},
        }

        # 读取 widget values
        widgets = node.get("widgets_values", [])

        # 读 inputs 数组中的连接
        for inp in node.get("inputs", []):
            name = inp.get("name", "")
            if inp.get("link") is not None:
                link_id = inp["link"]
                for link in legacy.get("links", []):
                    if isinstance(link, list) and len(link) >= 5 and link[0] == link_id:
                        api_node["inputs"][name] = [str(link[1]), link[2]]
                        break

        # 如果 inputs 为空，尝试从 widgets 推断
        if not api_node["inputs"]:
            ct = api_node["class_type"]
            if ct == "CheckpointLoaderSimple" and len(widgets) >= 1:
                api_node["inputs"]["ckpt_name"] = widgets[0]
            elif ct == "CLIPTextEncode" and len(widgets) >= 1:
                api_node["inputs"]["text"] = widgets[0]

        api[node_id] = api_node

    return api


# =============================================================================
# API Prompt → Save V1
# =============================================================================

def to_save_v1(api_workflow: Dict[str, Any]) -> Dict[str, Any]:
    """API Prompt → Save V1 格式（可拖入 ComfyUI 前端）"""
    nodes = []
    links = []
    link_id = 1
    # 连接去重
    link_map = {}

    for node_id_str, node in api_workflow.items():
        node_id = int(node_id_str)
        ct = node.get("class_type", "")

        # 收集 widgets (非连接参数)
        widgets = []
        inputs_list = []
        input_idx = 0
        output_idx = 0

        for key, val in node.get("inputs", {}).items():
            if isinstance(val, (list, tuple)):
                # 这是个连接
                src_id = val[0]
                src_slot = val[1]
                link_key = f"{src_id}-{src_slot}-{node_id}-{input_idx}"
                if link_key not in link_map:
                    link_map[link_key] = link_id
                    links.append({
                        "id": link_id,
                        "origin_id": int(src_id),
                        "origin_slot": src_slot,
                        "target_id": node_id,
                        "target_slot": input_idx,
                        "type": _infer_link_type(ct, key),
                    })
                    link_id += 1
                inputs_list.append({
                    "name": key,
                    "type": key,
                    "link": link_map[link_key],
                    "slot_index": input_idx,
                })
                input_idx += 1
            else:
                # 普通 widget 值
                widgets.append(val)

        nodes.append({
            "id": node_id,
            "type": ct,
            "pos": [100 + (node_id % 5) * 300, 100 + (node_id // 5) * 300],
            "size": [300, 200],
            "flags": {},
            "order": node_id,
            "mode": 0,
            "inputs": inputs_list,
            "outputs": [],
            "properties": {"Node name for S&R": ct},
            "widgets_values": widgets,
        })

    return {
        "version": 1,
        "config": {},
        "state": {},
        "nodes": nodes,
        "links": links,
        "groups": [],
        "reroutes": [],
        "extra": {},
        "models": [],
    }


def _infer_link_type(class_type: str, input_name: str) -> str:
    """推断连接类型"""
    type_map = {
        "model": "MODEL",
        "clip": "CLIP",
        "vae": "VAE",
        "conditioning": "CONDITIONING",
        "latent": "LATENT",
        "latent_image": "LATENT",
        "image": "IMAGE",
        "images": "IMAGE",
        "samples": "LATENT",
        "positive": "CONDITIONING",
        "negative": "CONDITIONING",
        "control_net": "CONTROL_NET",
        "upscale_model": "UPSCALE_MODEL",
    }
    return type_map.get(input_name, "*")


# =============================================================================
# 校验（扩展版）
# =============================================================================

class WorkflowValidationError(Exception):
    pass


def validate_workflow(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """校验 API Prompt 格式的 Workflow"""
    errors = []
    if not workflow or not isinstance(workflow, dict):
        errors.append("工作流为空")
        return False, errors

    # 检查每个节点
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            errors.append(f"节点 [{node_id}] 必须是对象")
            continue
        if "class_type" not in node:
            errors.append(f"节点 [{node_id}] 缺少 class_type")
            continue
        if "inputs" not in node:
            errors.append(f"节点 [{node_id}] 缺少 inputs")
            continue

        for key, val in node["inputs"].items():
            if isinstance(val, (list, tuple)):
                if len(val) != 2:
                    errors.append(f"节点 [{node_id}] inputs.{key} 引用格式错误")
                elif not str(val[0]) in workflow:
                    errors.append(f"节点 [{node_id}] 引用不存在的节点 [{val[0]}]")

    # 检测循环依赖
    _check_cycles(workflow, errors)

    # 必要节点
    class_types = set()
    for nid, node in workflow.items():
        if isinstance(node, dict) and "class_type" in node:
            class_types.add(node["class_type"])
    
    has_output = any("SaveImage" in ct or "PreviewImage" in ct or "VHS_VideoCombine" in ct for ct in class_types)
    if not has_output:
        errors.append("缺少输出节点 (SaveImage/PreviewImage/VHS_VideoCombine)")

    return len(errors) == 0, errors


def _check_cycles(workflow: Dict[str, Any], errors: List[str]):
    """DFS 检测循环依赖"""
    graph = {}
    for nid, node in workflow.items():
        deps = []
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                deps.append(str(val[0]))
        graph[nid] = deps

    visited = set()
    rec = set()

    def dfs(nid):
        visited.add(nid)
        rec.add(nid)
        for dep in graph.get(nid, []):
            if dep not in visited:
                if dfs(dep):
                    return True
            elif dep in rec:
                errors.append(f"循环依赖: [{nid}] ↔ [{dep}]")
                return True
        rec.discard(nid)
        return False

    for nid in graph:
        if nid not in visited:
            dfs(nid)


def validate_for_api(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """清理成 /prompt 可用的格式"""
    cleaned = {}
    for nid, node in workflow.items():
        cleaned[nid] = {
            "class_type": node["class_type"],
            "inputs": dict(node["inputs"]),
        }
    return {"prompt": cleaned}


def convert_to_api(workflow: Any) -> Optional[Dict[str, Any]]:
    """万能转换：任意格式 → API Prompt"""
    fmt = detect_format(workflow)
    if fmt == WorkflowFormat.API_PROMPT:
        return workflow
    return to_api_prompt(workflow)


def convert_to_save_v1(workflow: Any) -> Optional[Dict[str, Any]]:
    """万能转换：任意格式 → Save V1"""
    api = convert_to_api(workflow)
    if api:
        return to_save_v1(api)
    return None


def parse_workflow_file(path: str) -> Optional[Dict[str, Any]]:
    """从 JSON 文件读取工作流"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return convert_to_api(data)
