"""NodeIndex — 节点索引

将 ComfyUI /object_info 响应转为可查询的节点目录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NodeEntry:
    """单个节点条目"""
    class_type: str
    display_name: str = ""
    description: str = ""
    category: str = ""
    input_types: dict = field(default_factory=dict)
    output_types: list = field(default_factory=list)
    python_module: str = ""

    @property
    def is_custom_node(self) -> bool:
        """是否为自定义节点"""
        return "custom_nodes" in self.python_module or not self.python_module.startswith("comfy")


class NodeIndex:
    """节点索引 — 按名称/类别/来源查询"""

    def __init__(self):
        self._nodes: dict[str, NodeEntry] = {}

    def update(self, raw: dict[str, Any]) -> None:
        """从 /object_info 原始数据更新索引"""
        self._nodes = {}
        for class_type, info in raw.items():
            if not isinstance(info, dict):
                continue
            entry = NodeEntry(
                class_type=class_type,
                display_name=info.get("display_name", class_type),
                description=info.get("description", ""),
                category=info.get("category", ""),
                input_types=info.get("input", {}),
                output_types=info.get("output", []),
                python_module=info.get("python_module", ""),
            )
            self._nodes[class_type] = entry

    def get(self, class_type: str) -> Optional[NodeEntry]:
        """按 class_type 查找"""
        return self._nodes.get(class_type)

    def exists(self, class_type: str) -> bool:
        """节点是否存在"""
        return class_type in self._nodes

    def search(self, keyword: str) -> list[NodeEntry]:
        """按关键词搜索"""
        kw = keyword.lower()
        return [
            n for n in self._nodes.values()
            if kw in n.class_type.lower() or kw in n.display_name.lower()
        ]

    def list_by_category(self, category: str) -> list[NodeEntry]:
        """按分类列出"""
        return [n for n in self._nodes.values() if n.category == category]

    def list_custom_nodes(self) -> list[NodeEntry]:
        """列出所有自定义节点"""
        return [n for n in self._nodes.values() if n.is_custom_node]

    def count(self) -> int:
        return len(self._nodes)
