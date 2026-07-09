"""Blueprint Loader — 加载蓝图 JSON 文件

包装现有 blueprint_loader.py，提供统一接口。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .errors import BlueprintLoadError, BlueprintNotFoundError
from .validator import BlueprintValidator

# 蓝图资产目录
BLUEPRINTS_DIR = Path(__file__).parent.parent / "blueprints"


class BlueprintLoader:
    """从 blueprints/*.json 加载蓝图"""

    def __init__(self, blueprints_dir: str | Path | None = None):
        self.blueprints_dir = Path(blueprints_dir) if blueprints_dir else BLUEPRINTS_DIR
        self._cache: dict[str, dict] = {}
        self._validator = BlueprintValidator()

    def load(self, blueprint_id: str) -> dict:
        """按 ID 加载蓝图"""
        if blueprint_id in self._cache:
            return self._cache[blueprint_id]

        # 尝试直接按文件名加载
        for ext in [".json", ".yaml", ".yml"]:
            path = self.blueprints_dir / f"{blueprint_id}{ext}"
            if path.exists():
                return self._load_file(path)

        # 遍历目录匹配 id 字段
        if self.blueprints_dir.exists():
            for f in self.blueprints_dir.glob("*.json"):
                data = self._load_file(f, cache=False)
                if data.get("id") == blueprint_id:
                    self._cache[blueprint_id] = data
                    return data

        raise BlueprintNotFoundError(f"Blueprint '{blueprint_id}' not found in {self.blueprints_dir}")

    def load_all(self) -> list[dict]:
        """加载所有蓝图"""
        results = []
        if not self.blueprints_dir.exists():
            return results
        for f in sorted(self.blueprints_dir.glob("*.json")):
            try:
                data = self._load_file(f)
                results.append(data)
            except Exception as e:
                print(f"  [blueprint] skip {f.name}: {e}")
        return results

    def list_ids(self) -> list[str]:
        """列出所有可用蓝图 ID"""
        return [b.get("id", f.stem) for f in sorted(self.blueprints_dir.glob("*.json"))
                if (b := self._load_file(f, cache=False))]

    def _load_file(self, path: Path, cache: bool = True) -> dict:
        """加载单个蓝图文件并校验"""
        if str(path) in self._cache:
            return self._cache[str(path)]

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BlueprintLoadError(f"Invalid JSON in {path}: {e}")
        except FileNotFoundError:
            raise BlueprintNotFoundError(f"File not found: {path}")

        # 跳过非蓝图文件（没有 schema_version 或 id）
        if not isinstance(data, dict) or "id" not in data:
            raise BlueprintLoadError(f"Not a blueprint file (missing 'id'): {path.name}")

        # 校验 schema
        issues = self._validator.validate(data)
        if issues:
            print(f"  [blueprint] schema issues in {path.name}: {issues}")

        bp_id = data.get("id", path.stem)
        if cache:
            self._cache[bp_id] = data
            self._cache[str(path)] = data
        return data

    def reload(self):
        """清空缓存"""
        self._cache.clear()



