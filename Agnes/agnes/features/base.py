"""Feature 协议 — 定义 Tab 功能页的生命周期接口。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
import tkinter as tk

from agnes.runtime.app_context import AppContext


@runtime_checkable
class Feature(Protocol):
    """Tab 功能页协议。

    所有 Feature 实现必须满足此接口。
    生命周期：mount → activate ↔ deactivate → dispose
    """

    def mount(
        self,
        parent: tk.Misc,
        context: AppContext,
    ) -> tk.Widget:
        """第一次打开功能时创建界面。返回主 Widget。"""
        ...

    def activate(self) -> None:
        """切换到功能时调用（恢复/刷新）。"""
        ...

    def deactivate(self) -> None:
        """离开功能时调用（暂停/释放临时资源）。"""
        ...

    def dispose(self) -> None:
        """应用退出或功能卸载时释放资源。"""
        ...
