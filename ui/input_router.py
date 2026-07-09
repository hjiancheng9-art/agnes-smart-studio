"""InputRouter — 统一键盘调度、聚焦状态、剪贴板适配

GPT Review M2/M3/S1 要求：
- InputRouter 管理输入模式 (NORMAL/FOCUS/DETAIL/COPY/NATIVE)
- FocusState 从 CopyManager 独立
- ClipboardAdapter 统一剪贴板操作
"""

import contextlib
import enum
import threading
from collections.abc import Callable
from dataclasses import dataclass

# ── 输入模式 ──────────────────────────────────────────────


class InputMode(enum.Enum):
    NORMAL = "normal"  # 默认：可输入、鼠标滚轮滚动
    FOCUS_MESSAGE = "focus"  # 消息聚焦模式：↑↓切换消息
    DETAIL_VIEW = "detail"  # 消息详情：独立滚动
    COPY_MODE = "copy"  # 复制模式：选择范围
    NATIVE_SELECT = "native"  # 原生选择：TUI 松开鼠标


# ── 聚焦状态（独立于 CopyManager） ─────────────────────────


@dataclass
class FocusState:
    """消息聚焦状态 — 独立组件。"""

    enabled: bool = False
    index: int = -1
    total: int = 0

    def next(self) -> int:
        if not self.enabled:
            self.enabled = True
            self.index = max(0, self.total - 1)
        else:
            self.index = min(self.total - 1, self.index + 1)
        return self.index

    def prev(self) -> int:
        if not self.enabled:
            self.enabled = True
            self.index = max(0, self.total - 1)
        else:
            self.index = max(0, self.index - 1)
        return self.index

    def is_focused(self, msg_index: int) -> bool:
        return self.enabled and self.index == msg_index


# ── 剪贴板适配器 ─────────────────────────────────────────


class ClipboardAdapter:
    """统一剪贴板操作，自动处理不可用场景。"""

    def __init__(self):
        self._available = True
        self._test()

    def _test(self):
        try:
            import pyperclip

            pyperclip.copy("")
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def copy(self, text: str) -> bool:
        if not self._available or not text:
            return False
        try:
            import pyperclip

            pyperclip.copy(text)
            return True
        except Exception:
            self._available = False
            return False

    def copy_and_report(self, text: str, label: str = "已复制") -> tuple[bool, str]:
        ok = self.copy(text)
        snippet = text[:80].replace("\n", " ")
        if ok:
            return True, f"{label}: {snippet}"
        return False, f"复制失败: {snippet}"


# ── 输入路由器 ────────────────────────────────────────────


class InputRouter:
    """统一键盘调度器。

    各组件不直接绑键，而是注册 handler，由 Router 根据当前模式分发：
        router.add_handler("up", InputMode.NORMAL, lambda: scroll_up())
        router.add_handler("up", InputMode.FOCUS_MESSAGE, lambda: focus_prev())
        router.add_handler("up", InputMode.DETAIL_VIEW, lambda: detail_scroll_up())
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._mode = InputMode.NORMAL
        self._handlers: dict[str, list[tuple[InputMode, Callable[[], bool]]]] = {}
        self._on_mode_change: list[Callable[[InputMode], None]] = []

    @property
    def mode(self) -> InputMode:
        return self._mode

    def set_mode(self, mode: InputMode) -> None:
        old = self._mode
        self._mode = mode
        if old != mode:
            for cb in self._on_mode_change:
                with contextlib.suppress(Exception):
                    cb(mode)

    def on_mode_change(self, callback: Callable[[InputMode], None]) -> None:
        self._on_mode_change.append(callback)

    def add_handler(self, key: str, mode: InputMode, handler: Callable[[], bool]) -> None:
        """注册按键处理。handler 返回 True=已消费。"""
        self._handlers.setdefault(key, []).append((mode, handler))

    def dispatch(self, key: str) -> bool:
        """根据当前模式分发按键。返回 True=已消费。

        优先级: 精确模式匹配 > NORMAL 兜底
        """
        handlers = self._handlers.get(key, [])
        # 先试精确模式匹配
        for mode, handler in handlers:
            if mode == self._mode and handler():
                return True
        # 再试 NORMAL 兜底
        return any(mode == InputMode.NORMAL and handler() for mode, handler in handlers)

    def remove_handlers(self, key: str) -> None:
        self._handlers.pop(key, None)

    def clear(self) -> None:
        self._handlers.clear()


# ── 全局实例 ──────────────────────────────────────────────
_clipboard: ClipboardAdapter | None = None


def get_clipboard() -> ClipboardAdapter:
    global _clipboard
    if _clipboard is None:
        _clipboard = ClipboardAdapter()
    return _clipboard
