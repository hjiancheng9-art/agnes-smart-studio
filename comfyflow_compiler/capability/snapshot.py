"""CapabilitySnapshot — 统一运行时能力快照

整合探测、索引、兼容性检查为一体。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from .comfy_probe import ComfyProbe, ComfyProbeError
from .model_index import ModelIndex
from .node_index import NodeIndex
from .errors import ComfyOfflineError, MissingNodeError, MissingModelError


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class CapabilitySnapshot:
    """运行时能力快照 — 记录当前环境已知的全部能力"""

    comfyui_online: bool = False
    comfyui_version: str = ""
    comfyui_url: str = "http://127.0.0.1:8188"

    node_count: int = 0
    custom_node_count: int = 0
    model_count: int = 0

    nodes: list[str] = field(default_factory=list)
    models: dict[str, list[str]] = field(default_factory=dict)
    system: dict = field(default_factory=dict)
    queue: dict = field(default_factory=dict)
    generated_at: str = ""

    node_index: Optional[NodeIndex] = None
    model_index: Optional[ModelIndex] = None

    _missing: list[dict] = field(default_factory=list)

    def has_node(self, class_type: str) -> bool:
        """检查节点是否存在"""
        if self.node_index:
            return self.node_index.exists(class_type)
        return class_type in self.nodes

    def has_model(self, name: str, folder: str = "") -> bool:
        """检查模型是否存在"""
        if self.model_index:
            return self.model_index.find(name, folder) is not None
        if folder:
            return any(name in m for m in self.models.get(folder, []))
        for models in self.models.values():
            if any(name in m for m in models):
                return True
        return False

    def check_blueprint_compatibility(self, blueprint: dict) -> list[dict]:
        """检查蓝图与当前环境的兼容性"""
        issues = []
        required_nodes = blueprint.get("requirements", {}).get("required_nodes", [])
        for req in required_nodes:
            ct = req.get("class_type", "")
            if not self.has_node(ct):
                issue = {
                    "type": "missing_node",
                    "class_type": ct,
                    "reason": req.get("reason", ""),
                    "severity": "error",
                }
                issues.append(issue)
                self._missing.append(issue)

        models = blueprint.get("capability", {}).get("models", [])
        for m in models:
            if m.get("required") and not self.has_model(m["name"], m.get("type", "")):
                issue = {
                    "type": "missing_model",
                    "model": m["name"],
                    "severity": "error",
                }
                issues.append(issue)
                self._missing.append(issue)

        vram = blueprint.get("validation", {}).get("required_vram_gb", 0)
        if vram > 0 and self.system:
            total_vram = self.system.get("device", {}).get("vram_total_gb", 0)
            if total_vram and vram > total_vram:
                issues.append({
                    "type": "insufficient_vram",
                    "required_gb": vram,
                    "available_gb": total_vram,
                    "severity": "warning",
                })

        return issues

    @property
    def summary(self) -> dict:
        """简洁摘要"""
        return {
            "comfyui_online": self.comfyui_online,
            "version": self.comfyui_version or "unknown",
            "nodes": f"{self.node_count} total ({self.custom_node_count} custom)",
            "models": f"{self.model_count} across {len(self.models)} categories",
            "issues": len(self._missing),
            "generated_at": self.generated_at,
        }


def probe_comfyui(url: str = "http://127.0.0.1:8188",
                   timeout: float = 5.0) -> CapabilitySnapshot:
    """探测 ComfyUI 并返回能力快照"""
    probe = ComfyProbe(base_url=url, timeout=timeout)

    snapshot = CapabilitySnapshot(comfyui_url=url)

    # 健康检查
    try:
        snapshot.comfyui_online = probe.check_online()
        if not snapshot.comfyui_online:
            return snapshot
    except Exception:
        return snapshot

    # 版本
    snapshot.comfyui_version = probe.get_version()

    # 节点
    node_data = probe.get_nodes()
    if node_data:
        idx = NodeIndex()
        idx.update(node_data)
        snapshot.node_index = idx
        snapshot.nodes = list(idx._nodes.keys())
        snapshot.node_count = idx.count()
        snapshot.custom_node_count = len(idx.list_custom_nodes())

    # 模型
    model_data = probe.get_all_models()
    if model_data:
        midx = ModelIndex()
        midx.update(model_data)
        snapshot.model_index = midx
        snapshot.models = model_data
        snapshot.model_count = midx.count()

    # 系统/队列
    snapshot.system = probe.get_system_stats()
    snapshot.queue = probe.get_queue()

    snapshot.generated_at = _now()
    return snapshot
