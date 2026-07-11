"""Feature 管理器 — 延迟加载 + 生命周期管理。"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

import tkinter as tk

if TYPE_CHECKING:
    from agnes.features.base import Feature
    from agnes.runtime.app_context import AppContext

logger = logging.getLogger(__name__)


class FeatureInfo:
    """注册信息：一个 Feature 的元数据和工厂。"""

    def __init__(
        self,
        name: str,
        module_path: str,
        class_name: str,
        title: str = "",
        icon: str = "",
    ):
        self.name = name
        self.module_path = module_path
        self.class_name = class_name
        self.title = title or name
        self.icon = icon
        self._instance: Feature | None = None

    @property
    def loaded(self) -> bool:
        return self._instance is not None

    def load(self) -> Feature:
        """懒加载：首次调用时 import + 实例化。"""
        if self._instance is not None:
            return self._instance

        module = importlib.import_module(self.module_path)
        cls = getattr(module, self.class_name)
        self._instance = cls()
        logger.info(f"Feature loaded: {self.name} -> {self.module_path}.{self.class_name}")
        return self._instance

    def dispose(self) -> None:
        if self._instance is not None:
            try:
                self._instance.dispose()
            except Exception as e:
                logger.warning(f"Feature dispose error ({self.name}): {e}")
            self._instance = None


class FeatureManager:
    """管理所有 Feature 的注册、加载、切换。"""

    def __init__(self, notebook: tk.ttk.Notebook, context: AppContext):
        self.notebook = notebook
        self.context = context
        self._registry: dict[str, FeatureInfo] = {}
        self._widgets: dict[str, tk.Widget] = {}
        self._current: str | None = None

    def register(self, info: FeatureInfo) -> None:
        """注册一个 Feature 到管理器。"""
        self._registry[info.name] = info
        # 创建占位 Tab（空白页，Feature 加载后才填充内容）
        frame = tk.Frame(self.notebook, bg="#1e1e1e")
        self.notebook.add(frame, text=info.title)
        self._widgets[info.name] = frame

        # 绑定切换事件 —— 进入 Tab 时触发加载
        # tkinter 没有直接的 tab-change 事件，用 <ButtonRelease-1> 近似
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _event=None) -> None:
        """Tab 切换回调：加载 Feature 并激活。"""
        selected = self.notebook.select()
        if not selected:
            return

        # 找到对应的 name
        for name, frame in self._widgets.items():
            if str(frame) == selected:
                if name != self._current:
                    # 停用上一个
                    if self._current:
                        self._deactivate(self._current)
                    # 激活新的
                    self._activate(name)
                    self._current = name
                break

    def _activate(self, name: str) -> None:
        """加载（若未加载）并激活 Feature。"""
        info = self._registry.get(name)
        if not info:
            return

        feature = info.load()
        frame = self._widgets[name]

        # 首次加载：mount 界面
        if not hasattr(frame, "_feature_mounted"):
            feature.mount(frame, self.context)
            frame._feature_mounted = True  # type: ignore[attr-defined]

        feature.activate()

    def _deactivate(self, name: str) -> None:
        """停用 Feature。"""
        info = self._registry.get(name)
        if info and info.loaded:
            info._instance.deactivate()  # type: ignore[union-attr]

    def dispose_all(self) -> None:
        """释放所有 Feature。"""
        for name, info in self._registry.items():
            info.dispose()
        self._registry.clear()
        self._widgets.clear()
