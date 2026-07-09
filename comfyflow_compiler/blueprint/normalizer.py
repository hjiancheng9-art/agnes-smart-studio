"""Workflow Normalizer — 统一归一化 ComfyUI workflow

将 ComfyUI 的两种格式（UI workflow JSON / API prompt）统一为 NormalizedWorkflow。
"""

from __future__ import annotations

from typing import Any

from .types import NormalizedWorkflow


class WorkflowNormalizer:
    """ComfyUI workflow 归一化器"""

    @staticmethod
    def normalize(data: dict, source_format: str | None = None) -> NormalizedWorkflow:
        """归一化 workflow 为统一格式

        Args:
            data: ComfyUI workflow 数据
            source_format: 格式提示 ("api" / "ui" / None=自动检测)

        Returns:
            NormalizedWorkflow
        """
        if source_format is None:
            source_format = WorkflowNormalizer._detect_format(data)

        if source_format == "api":
            prompt = data
        elif source_format == "ui":
            prompt = WorkflowNormalizer._convert_ui_to_api(data)
        elif source_format == "history":
            prompt = WorkflowNormalizer._extract_from_history(data)
        else:
            raise ValueError(f"Unknown source format: {source_format}")

        return NormalizedWorkflow(
            prompt=prompt,
            source_format=source_format,
            workflow_id=data.get("id", data.get("workflow_id", "")),
        )

    @staticmethod
    def _detect_format(data: dict) -> str:
        """自动检测 workflow 格式"""
        # UI workflow: 每个节点有 "inputs" 和 "class_type"，可能有 widgets/colors
        # API prompt: 每个节点有 "inputs" 和 "class_type"，无 UI 字段
        # History: 有 prompt_id / outputs / status
        if "prompt_id" in data or "outputs" in data:
            return "history"
        # UI workflow 通常有 extra 字段
        if any(isinstance(v, dict) and "widgets_values" in v for v in data.values()):
            return "ui"
        return "api"

    @staticmethod
    def _convert_ui_to_api(ui_data: dict) -> dict[str, dict[str, Any]]:
        """UI workflow → API prompt 格式"""
        api = {}
        for node_id, node in ui_data.items():
            if not isinstance(node, dict) or "class_type" not in node:
                continue
            inputs = dict(node.get("inputs", {}))
            # UI 中 widget 值在 _meta 里，可能需要补充
            api[node_id] = {
                "class_type": node["class_type"],
                "inputs": inputs,
            }
        return api

    @staticmethod
    def _extract_from_history(history_data: dict) -> dict[str, dict[str, Any]]:
        """从 ComfyUI /history 响应中提取 prompt"""
        # history[prompt_id]["prompt"][2] == API prompt
        for prompt_id, entry in history_data.items():
            if isinstance(entry, dict) and "prompt" in entry:
                prompt_entry = entry["prompt"]
                # prompt 可能是 [node_id, ...] 或 {node_id: ...} 格式
                if isinstance(prompt_entry, list) and len(prompt_entry) > 2:
                    return prompt_entry[2] if isinstance(prompt_entry[2], dict) else prompt_entry[0]
                if isinstance(prompt_entry, dict):
                    return prompt_entry
        # fallback: 直接返回原始数据
        return history_data
