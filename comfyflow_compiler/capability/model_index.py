"""ModelIndex — 模型索引

将探测到的模型列表转为可查询的索引结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelEntry:
    """单个模型条目"""
    name: str
    folder: str
    size_bytes: int = 0
    hash: str = ""
    metadata: dict = field(default_factory=dict)


class ModelIndex:
    """模型索引 — 支持按名称/类型查找"""

    def __init__(self):
        self._models: dict[str, list[ModelEntry]] = {}

    def update(self, raw: dict[str, list[str]]) -> None:
        """从探测原始数据更新索引"""
        self._models = {}
        for folder, names in raw.items():
            entries = [ModelEntry(name=n, folder=folder) for n in names]
            self._models[folder] = entries

    def find(self, name: str, folder: str = "") -> Optional[ModelEntry]:
        """查找模型"""
        folders = [folder] if folder else list(self._models.keys())
        for f in folders:
            for entry in self._models.get(f, []):
                if name.lower() in entry.name.lower():
                    return entry
        return None

    def list_by_folder(self, folder: str) -> list[ModelEntry]:
        """列出指定目录的模型"""
        return self._models.get(folder, [])

    def list_all(self) -> list[ModelEntry]:
        """列出所有模型"""
        result = []
        for entries in self._models.values():
            result.extend(entries)
        return result

    def count(self) -> int:
        """模型总数"""
        return sum(len(v) for v in self._models.values())

    def summary(self) -> dict:
        """按目录汇总"""
        return {folder: len(entries) for folder, entries in self._models.items()}
