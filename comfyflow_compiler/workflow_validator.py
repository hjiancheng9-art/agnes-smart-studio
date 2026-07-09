"""ComfyFlow Compiler — Workflow JSON 校验器"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import json


class WorkflowValidationError(Exception):
    """工作流校验错误"""
    pass


def validate_workflow(workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    校验生成的 Workflow JSON 是否合法。
    返回 (is_valid, errors)
    """
    errors = []

    if not workflow:
        errors.append("工作流为空")
        return False, errors

    if not isinstance(workflow, dict):
        errors.append("工作流必须是 JSON 对象")
        return False, errors

    # 1. 检查每个节点
    for node_id, node in workflow.items():
        _validate_node(node_id, node, errors)

    # 2. 检查连接完整性
    _validate_connections(workflow, errors)

    # 3. 检查必要节点
    _validate_required_nodes(workflow, errors)

    # 4. 检查循环依赖
    _validate_no_cycles(workflow, errors)

    return len(errors) == 0, errors


def _validate_node(node_id: str, node: Any, errors: List[str]):
    """校验单个节点"""
    if not isinstance(node, dict):
        errors.append(f"节点 [{node_id}] 必须是对象")
        return

    if "class_type" not in node:
        errors.append(f"节点 [{node_id}] 缺少 class_type")
        return

    if not isinstance(node["class_type"], str) or not node["class_type"]:
        errors.append(f"节点 [{node_id}] class_type 必须是非空字符串")

    if "inputs" not in node:
        errors.append(f"节点 [{node_id}] 缺少 inputs")
        return

    if not isinstance(node["inputs"], dict):
        errors.append(f"节点 [{node_id}] inputs 必须是对象")

    # 检查 inputs 中的引用格式
    for key, val in node["inputs"].items():
        if isinstance(val, (list, tuple)):
            if len(val) != 2:
                errors.append(f"节点 [{node_id}] inputs.{key} 引用格式错误，应为 [node_id, slot_name]")
            elif not isinstance(val[0], (str, int)):
                errors.append(f"节点 [{node_id}] inputs.{key} 引用 node_id 必须是字符串或数字")


def _validate_connections(workflow: Dict[str, Any], errors: List[str]):
    """检查所有连接的目标节点是否存在"""
    defined_ids = set(workflow.keys())

    for node_id, node in workflow.items():
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                ref_id = str(val[0])
                if ref_id not in defined_ids:
                    errors.append(f"节点 [{node_id}] 引用了不存在的节点 [{ref_id}]")


def _validate_required_nodes(workflow: Dict[str, Any], errors: List[str]):
    """检查是否包含必要节点"""
    class_types = {n["class_type"] for n in workflow.values()}

    # 输出节点
    has_output = any("SaveImage" in ct or "PreviewImage" in ct or "VHS_VideoCombine" in ct for ct in class_types)
    if not has_output:
        errors.append("缺少输出节点 (SaveImage/PreviewImage/VHS_VideoCombine)")

    # 潜变量来源
    has_latent_source = any(
        ct in ("EmptyLatentImage", "VAEEncode", "VAEDecode") for ct in class_types
    )
    if not has_latent_source:
        errors.append("缺少潜变量来源节点 (EmptyLatentImage/VAEEncode)")


def _validate_no_cycles(workflow: Dict[str, Any], errors: List[str]):
    """检测循环依赖"""
    graph = {}
    for node_id, node in workflow.items():
        deps = []
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                deps.append(str(val[0]))
        graph[node_id] = deps

    # DFS 检测环
    visited = set()
    rec_stack = set()

    def dfs(nid):
        visited.add(nid)
        rec_stack.add(nid)
        for dep in graph.get(nid, []):
            if dep not in visited:
                if dfs(dep):
                    return True
            elif dep in rec_stack:
                errors.append(f"检测到循环依赖: 节点 [{nid}] 和 [{dep}]")
                return True
        rec_stack.discard(nid)
        return False

    for nid in graph:
        if nid not in visited:
            dfs(nid)


def validate_for_api(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    清理并转换为 ComfyUI API 格式。
    API 格式 = {"prompt": workflow}
    """
    cleaned = {}
    for node_id, node in workflow.items():
        cleaned[node_id] = {
            "class_type": node["class_type"],
            "inputs": dict(node["inputs"]),
        }
        # 移除非 ComfyUI 标准字段
        cleaned[node_id]["inputs"].pop("_meta", None)

    return {"prompt": cleaned}


def validate_for_ui(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    添加 UI 布局信息，生成可直接拖入 ComfyUI 的完整 workflow。
    """
    full_workflow = {}
    x_offset = 0
    y_offset = 0

    for node_id, node in workflow.items():
        full_node = {
            "class_type": node["class_type"],
            "inputs": dict(node["inputs"]),
            "_meta": {
                "title": node.get("_meta", {}).get("title", node["class_type"]),
            },
        }
        full_workflow[node_id] = full_node
        x_offset += 200

    # 添加额外 UI 所需的键
    return {
        "last_node_id": len(workflow),
        "last_link_id": 0,
        "nodes": list(_build_ui_nodes(workflow)),
        "links": [],
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }


def _build_ui_nodes(workflow: Dict[str, Any]) -> List[Dict]:
    """构建 UI 节点列表"""
    ui_nodes = []
    x, y = 100, 100
    slot_map = {
        "CheckpointLoaderSimple": {"model": 0, "clip": 1, "vae": 2},
        "CLIPTextEncode": {"conditioning": 0},
        "EmptyLatentImage": {"latent": 0},
        "KSampler": {"latent": 0},
        "VAEDecode": {"image": 0},
        "SaveImage": {"images": 0},
    }

    for node_id, node in workflow.items():
        ct = node["class_type"]
        ui_node = {
            "id": int(node_id),
            "type": ct,
            "pos": [x, y],
            "size": [400, 200],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [],
            "outputs": [],
            "properties": {"Node name for S&R": ct},
        }
        x += 250
        if x > 1200:
            x = 100
            y += 300
        ui_nodes.append(ui_node)

    return ui_nodes
