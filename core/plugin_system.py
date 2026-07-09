"""Plugin System — CRUX 可生长的骨架。

每个插件是一个独立目录，包含 plugin.json + main.py。
Plugin 类有标准生命周期，带权限声明和 Schema 校验。

目录结构:
  output/plugins/my_plugin/
    plugin.json  → {name, version, permissions, hooks, schema_version}
    main.py      → Plugin 类

生命周期:
  load() → validate() → activate() → [RUN] → deactivate() → unload()

Usage:
  from core.plugin_system import PluginManager
  pm = PluginManager()
  pm.load_all()
  pm.activate("my_plugin")
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger("crux.plugins")

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "output" / "plugins"
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA_VERSION = "crux.plugin.v1"


# ── Data ─────────────────────────────────────────────────────────


@dataclass
class PluginManifest:
    """玄武 Schema 守卫：插件声明必须可校验。"""

    name: str
    version: str
    permissions: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> PluginManifest:
        return cls(
            name=data["name"],
            version=data.get("version", "0.1.0"),
            permissions=data.get("permissions", []),
            hooks=data.get("hooks", []),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            description=data.get("description", ""),
            author=data.get("author", ""),
            dependencies=data.get("dependencies", []),
        )

    def validate(self) -> tuple[bool, str]:
        """玄武校验：schema_version + 插件名 + permissions 三关。"""
        if self.schema_version != SCHEMA_VERSION:
            return False, f"Schema mismatch: expected {SCHEMA_VERSION}, got {self.schema_version}"
        # ZCode Gene 3: 插件名校验
        plugin_name_re = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
        if not plugin_name_re.match(self.name):
            return False, f"Invalid plugin name '{self.name}': must match ^[a-z0-9][a-z0-9._-]{{0,127}}$"
        valid_perms = {"fs", "network", "gpu", "browser", "audio", "process", "self"}
        stray = set(self.permissions) - valid_perms
        if stray:
            return False, f"Unknown permissions: {stray}"
        return True, "ok"


@dataclass
class PluginInstance:
    manifest: PluginManifest
    module: ModuleType | None = None
    instance: Any = None
    state: str = "unloaded"  # unloaded → loaded → validated → active → inactive


# ── Manager ─────────────────────────────────────────────────────


class PluginManager:
    """插件管理器：加载、校验、激活、停用。"""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInstance] = {}
        self._active: set[str] = set()

    # ── scan ──────────────────────────────────────────────────

    def discover(self) -> list[Path]:
        """扫描所有插件发现路径（ZCode 兼容多路径）。

        搜索优先级:
        1. output/plugins/          — CRUX 主目录（已有）
        2. .zcode-plugin/          — ZCode 标准插件发现
        3. .claude-plugin/         — Claude 兼容发现
        4. .codex-plugin/          — Codex 兼容发现
        """
        plugins: list[Path] = []
        scan_dirs = [
            PLUGIN_DIR,
            Path(__file__).resolve().parent.parent / ".zcode-plugin",
            Path(__file__).resolve().parent.parent / ".claude-plugin",
            Path(__file__).resolve().parent.parent / ".codex-plugin",
        ]
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for d in sorted(scan_dir.iterdir()):
                if d.is_dir() and (d / "plugin.json").exists() and (d / "main.py").exists():
                    plugins.append(d)
        return plugins

    # ── load ──────────────────────────────────────────────────

    def load(self, plugin_path: Path) -> PluginInstance | None:
        """加载单个插件（不激活）。"""
        manifest_path = plugin_path / "plugin.json"
        main_path = plugin_path / "main.py"

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = PluginManifest.from_json(manifest_data)
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.exception("Failed to load plugin manifest: %s → %s", plugin_path.name, e)
            return None

        ok, err = manifest.validate()
        if not ok:
            logger.error("Plugin validation failed: %s → %s", manifest.name, err)
            return None

        if manifest.name in self._plugins:
            logger.warning("Plugin already loaded: %s, skipping", manifest.name)
            return self._plugins[manifest.name]

        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{manifest.name}", str(main_path))
            if spec is None or spec.loader is None:
                logger.error("Failed to create module spec: %s", manifest.name)
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            instance = module.Plugin() if hasattr(module, "Plugin") else None
        except (RuntimeError, OSError, ImportError, TypeError, ValueError) as e:
            logger.exception("Failed to load plugin module: %s → %s", manifest.name, e)
            return None

        pi = PluginInstance(manifest=manifest, module=module, instance=instance, state="loaded")
        self._plugins[manifest.name] = pi
        logger.info("Plugin loaded: %s v%s", manifest.name, manifest.version)
        return pi

    def load_all(self) -> int:
        """加载所有已发现的插件。返回成功加载数。"""
        count = 0
        for path in self.discover():
            if self.load(path):
                count += 1
        return count

    # ── activate / deactivate ─────────────────────────────────

    def activate(self, name: str) -> bool:
        """激活插件（运行 activate() 生命周期方法）。"""
        pi = self._plugins.get(name)
        if pi is None:
            logger.error("Plugin not loaded: %s", name)
            return False
        if pi.state == "active":
            return True

        try:
            if pi.instance and hasattr(pi.instance, "activate"):
                pi.instance.activate()
            pi.state = "active"
            self._active.add(name)
            logger.info("Plugin activated: %s", name)
            return True
        except (RuntimeError, OSError, TypeError, ValueError) as e:
            logger.exception("Failed to activate plugin: %s → %s", name, e)
            return False

    def deactivate(self, name: str) -> bool:
        """停用插件（运行 deactivate() 生命周期方法）。"""
        pi = self._plugins.get(name)
        if pi is None or pi.state != "active":
            return False

        try:
            if pi.instance and hasattr(pi.instance, "deactivate"):
                pi.instance.deactivate()
            pi.state = "loaded"
            self._active.discard(name)
            logger.info("Plugin deactivated: %s", name)
            return True
        except (RuntimeError, OSError, TypeError, ValueError) as e:
            logger.exception("Failed to deactivate plugin: %s → %s", name, e)
            return False

    def unload(self, name: str) -> bool:
        """卸载插件。"""
        if name in self._active:
            self.deactivate(name)
        pi = self._plugins.pop(name, None)
        if pi and pi.module and pi.module.__name__ in sys.modules:
            del sys.modules[pi.module.__name__]
        logger.info("Plugin unloaded: %s", name)
        return pi is not None

    # ── query ─────────────────────────────────────────────────

    @property
    def loaded_names(self) -> list[str]:
        return list(self._plugins.keys())

    @property
    def active_names(self) -> list[str]:
        return list(self._active)

    def get(self, name: str) -> PluginInstance | None:
        return self._plugins.get(name)

    def summary(self) -> str:
        if not self._plugins:
            return "  [插件] 无已加载插件"
        lines = ["\n## 插件系统（已加载）"]
        for name, pi in self._plugins.items():
            status = "●" if pi.state == "active" else "○"
            lines.append(f"  {status} {name} v{pi.manifest.version} — {pi.manifest.description}")
        return "\n".join(lines)
