"""Blueprint Validator — 校验蓝图 JSON 是否符合 schema"""

from __future__ import annotations
from typing import Any
from .schema import BLUEPRINT_JSON_SCHEMA


class BlueprintValidator:
    """校验蓝图数据是否符合 BLUEPRINT_JSON_SCHEMA"""

    def __init__(self):
        self._schema = BLUEPRINT_JSON_SCHEMA

    def validate(self, blueprint: dict) -> list[str]:
        """校验蓝图，返回所有问题列表"""
        issues: list[str] = []
        self._check_required(blueprint, self._schema.get("required", []), issues)
        self._check_properties(blueprint, self._schema.get("properties", {}), issues)
        return issues

    def is_valid(self, blueprint: dict) -> bool:
        """快速校验：是否有致命问题"""
        return len(self.validate(blueprint)) == 0

    def _check_required(self, data: dict, required: list[str], issues: list[str], prefix: str = ""):
        for field in required:
            if field not in data:
                issues.append(f"{prefix}缺少必需字段: {field}")

    def _check_properties(self, data: dict, properties: dict, issues: list[str], prefix: str = ""):
        for key, value in data.items():
            if key not in properties:
                continue  # additionalProperties: False 但宽松处理
            prop = properties[key]
            self._check_value(key, value, prop, issues, prefix)

    def _check_value(self, key: str, value: Any, prop: dict, issues: list[str], prefix: str = ""):
        path = f"{prefix}.{key}" if prefix else key
        expected_type = prop.get("type")

        if expected_type == "object":
            if not isinstance(value, dict):
                issues.append(f"{path}: 期望 object，得到 {type(value).__name__}")
            else:
                required = prop.get("required", [])
                self._check_required(value, required, issues, path)
                sub_props = prop.get("properties", {})
                self._check_properties(value, sub_props, issues, path)

        elif expected_type == "array":
            if not isinstance(value, list):
                issues.append(f"{path}: 期望 array，得到 {type(value).__name__}")
            elif "items" in prop and prop["items"].get("type") == "object":
                items_required = prop["items"].get("required", [])
                items_props = prop["items"].get("properties", {})
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self._check_required(item, items_required, issues, f"{path}[{i}]")
                        self._check_properties(item, items_props, issues, f"{path}[{i}]")

        elif expected_type == "string":
            if value is not None and not isinstance(value, str):
                issues.append(f"{path}: 期望 string，得到 {type(value).__name__}")
            if "enum" in prop and isinstance(value, str) and value not in prop["enum"]:
                issues.append(f"{path}: '{value}' 不在允许值 {prop['enum']} 中")

        elif expected_type in ("integer", "number"):
            if value is not None and not isinstance(value, (int, float)):
                issues.append(f"{path}: 期望 {expected_type}，得到 {type(value).__name__}")
            if expected_type == "integer" and isinstance(value, float):
                issues.append(f"{path}: 期望 integer，得到 float")

    def validate_slots(self, slots: dict, graph_nodes: list[dict]) -> list[str]:
        """校验 slot 引用的节点是否在图模板中存在"""
        issues = []
        node_ids = {n["id"] for n in graph_nodes}
        for slot_name, slot in slots.items():
            if not isinstance(slot, dict):
                continue
            nid = slot.get("node_id")
            if nid and nid not in node_ids:
                issues.append(f"Slot '{slot_name}' 引用的节点 '{nid}' 在图模板中不存在")
        return issues
