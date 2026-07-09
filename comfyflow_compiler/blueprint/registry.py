"""Blueprint Registry — 蓝图注册表薄封装

包装现有 blueprint_registry.BlueprintRegistry，提供统一接口。
"""

from __future__ import annotations

from typing import Optional

from comfyflow_compiler.blueprint_registry import BlueprintRegistry as _OldRegistry

from .loader import BlueprintLoader
from .errors import BlueprintNotFoundError


class BlueprintRegistry:
    """蓝图注册表 — 管理蓝图检索和匹配"""

    def __init__(self):
        self._old_registry = _OldRegistry()
        self._loader = BlueprintLoader()

    def get(self, blueprint_id: str) -> Optional[dict]:
        """按 ID 获取蓝图"""
        # 优先从新格式加载
        try:
            return self._loader.load(blueprint_id)
        except BlueprintNotFoundError:
            pass

        # 回退到旧注册表
        old_bp = self._old_registry.get_blueprint(blueprint_id)
        if old_bp:
            return self._old_to_new(old_bp)

        return None

    def list_all(self) -> list[dict]:
        """列出所有蓝图"""
        results = []

        # 加载新格式蓝图
        results.extend(self._loader.load_all())

        # 补充旧格式蓝图
        known_ids = {r.get("id") for r in results if isinstance(r, dict)}
        # 旧注册表没有 list_all，遍历 get_blueprint
        for task in ["txt2img", "img2img", "t2v", "i2v", "upscale", "edit"]:
            bp = self._old_registry.get_blueprint(task)
            if bp and bp.name not in known_ids:
                results.append(self._old_to_new(bp))
                known_ids.add(bp.name)

        return results

    def match(self, task_type: str, styles: list[str] | None = None,
              subject: str = "") -> list[dict]:
        """按任务类型和风格匹配蓝图"""
        old_recipes = self._old_registry.match_recipe(
            task_type, styles or [], subject
        )
        results = []
        for recipe in old_recipes:
            bp = self._old_registry.select_best_blueprint(task_type, recipe)
            if bp:
                results.append(self._old_to_new(bp))
        return results

    def _old_to_new(self, old_bp) -> dict:
        """将旧 Blueprint 转换为新格式字典"""
        return {
            "schema_version": "1.0.0",
            "id": old_bp.name,
            "name": getattr(old_bp, "display_name", old_bp.name),
            "version": "1.0.0",
            "status": "stable",
            "source": {"origin": "migrated", "workflow_id": old_bp.name, "mined_at": ""},
            "capability": {
                "task_type": old_bp.name,
                "description": "",
                "tags": [],
                "styles": [],
                "models": [],
            },
            "requirements": {
                "min_nodes": 0,
                "required_nodes": [],
                "recommended_nodes": [],
            },
            "input_contract": {"fields": []},
            "output_contract": {"fields": []},
            "graph_template": {
                "nodes": [],
                "edges": [],
                "entry_points": [],
                "exit_points": [],
            },
            "slots": {},
            "quality_modes": {
                "draft": {"steps": 20, "cfg": 3.5, "sampler": "euler", "scheduler": "normal", "resolution": "512x512"},
                "standard": {"steps": 30, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "resolution": "1024x1024"},
                "quality": {"steps": 50, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras", "resolution": "1024x1024"},
            },
            "validation": {"known_issues": [], "tested_models": []},
            "metadata": {"total_nodes": 0, "total_edges": 0},
        }

    def get_fallback_chain(self, task_type: str, budget_score: float = 0.5):
        """获取降级备选链"""
        return self._old_registry.get_fallback_chain(task_type, budget_score)
