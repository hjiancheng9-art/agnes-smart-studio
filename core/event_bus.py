"""Event Bus — CRUX 中枢神经。

五兽互相感知的工具。模块间零耦合，挂载即生效。

Events:
  tool:before     → 玄武 Schema 校验  (zcode_dna)
  tool:after      → 朱雀 反思 critique (claude_dna)
  file:changed    → 青龙 冲击分析     (codex_dna)
  error           → 白虎 容灾自愈     (crux_dna)
  session:start   → 麒麟 记忆加载     (codebuddy_dna)
  session:end     → 麒麟 记忆写入     (codebuddy_dna)

Usage:
  from core.event_bus import bus
  bus.on("tool:before", my_validator)
  bus.emit("tool:before", tool_name="write_file", args={...})
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("crux.event_bus")


class EventBus:
    """发布-订阅中枢。同步触发，保证顺序。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._once_handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """注册持久监听器。"""
        self._handlers[event].append(handler)

    def once(self, event: str, handler: Callable[..., Any]) -> None:
        """注册一次性监听器，触发后自动移除。"""
        self._once_handlers[event].append(handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """移除监听器。"""
        self._handlers[event] = [h for h in self._handlers[event] if h is not handler]
        self._once_handlers[event] = [h for h in self._once_handlers[event] if h is not handler]

    def emit(self, event: str, **kwargs: Any) -> None:
        """同步触发事件。所有处理器同步执行，异常不中断后续处理器。"""
        handlers = self._handlers.get(event, []) + self._once_handlers.pop(event, [])
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception:
                logger.exception("Event handler failed: %s → %s", event, handler.__name__)

    def clear(self) -> None:
        """清空所有监听器（测试用）。"""
        self._handlers.clear()
        self._once_handlers.clear()


# 全局中枢
bus = EventBus()
