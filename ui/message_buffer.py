"""Message buffer — Rich Panel 气泡渲染。

每条消息渲染为独立的 Rich Panel，按角色区分颜色和缩进：
  - user:      右侧缩进 + 青龙色左边框 + 微蓝底
  - assistant: 左侧无边栏 + surface 底 + Markdown 渲染
  - system:    居中 + 细灰线框 + 小字灰色
  - tool:      左侧 + 麒麟色左边框 + 微绿底 + 紧凑

线程安全：所有 add_* / commit 方法持有 _lock。
输出同时写入 Rich 控制台面板和 ANSI 后备缓冲区。
"""

import threading
import time as _time
from typing import Optional

from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.panel import Panel
from rich.padding import Padding
from rich.text import Text

from ui.theme import COLORS, GLYPHS


class MessageBlock:
    """单条消息的气泡数据。"""

    __slots__ = ("role", "content", "timestamp", "panel")

    def __init__(self, role: str, content: str):
        self.role = role          # "user" | "assistant" | "system" | "tool"
        self.content = content
        self.timestamp = _time.time()
        self.panel: Optional[Panel] = None


def _build_panel(block: MessageBlock) -> Panel:
    """根据角色构建 Rich Panel 气泡。"""
    role = block.role
    content = block.content

    if role == "user":
        # 右侧缩进，青龙色左边框
        text = Text(content)
        text.stylize(COLORS["text"])
        return Panel(
            text,
            border_style=COLORS["user_bubble_border"],
            style=f"on {COLORS['user_bubble_bg']}",
            padding=(0, 1),
            title=GLYPHS["send"],
            title_align="right",
            subtitle="",
            width=None,
        )

    elif role == "assistant":
        # 左侧无缩进，Markdown 渲染，低调边框
        md = Markdown(content, code_theme="github-dark")
        return Panel(
            md,
            border_style=COLORS["assistant_bubble_border"],
            style=f"on {COLORS['assistant_bubble_bg']}",
            padding=(1, 2),
            title="",
            title_align="left",
            subtitle="",
            width=None,
        )

    elif role == "tool":
        # 紧凑工具调用，麒麟色左边框
        text = Text(content)
        text.stylize(COLORS["text_secondary"])
        return Panel(
            Padding(text, (0, 1)),
            border_style=COLORS["tool_bubble_border"],
            style=f"on {COLORS['tool_bubble_bg']}",
            padding=(0, 0),
            title=f" {GLYPHS['hammer']} ",
            title_align="left",
            width=None,
        )

    else:  # system
        text = Text(content)
        text.stylize(f"italic {COLORS['text_tertiary']}")
        return Panel(
            Padding(text, (0, 2)),
            border_style=COLORS["system_bubble_border"],
            style=f"on {COLORS['system_bubble_bg']}",
            padding=(0, 0),
            width=None,
        )


class MessageBuffer:
    """线程安全的消息气泡缓冲区。

    用法:
        buf = MessageBuffer()
        buf.add_message("user", "你好")
        buf.add_message("assistant", "你好，有什么可以帮你的？")
        panels = buf.render_all()
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._blocks: list[MessageBlock] = []

    def add_message(self, role: str, content: str):
        """追加一条完整消息。"""
        with self._lock:
            block = MessageBlock(role, content)
            block.panel = _build_panel(block)
            self._blocks.append(block)

    def update_last(self, content: str):
        """更新最后一条消息的内容（用于流式输出）。"""
        with self._lock:
            if self._blocks:
                last = self._blocks[-1]
                last.content = content
                last.panel = _build_panel(last)

    def append_last(self, chunk: str):
        """追加文本到末尾消息。"""
        with self._lock:
            if self._blocks:
                last = self._blocks[-1]
                last.content += chunk
                last.panel = _build_panel(last)
            else:
                # 第一条 chunk 从哪来就按什么角色
                self.add_message("assistant", chunk)

    def render_all(self) -> list[Panel]:
        """返回所有气泡面板列表。"""
        with self._lock:
            return [b.panel for b in self._blocks if b.panel is not None]

    def render_latest(self, n: int = 5) -> list[Panel]:
        """返回最近 n 条消息的面板。"""
        with self._lock:
            blocks = self._blocks[-n:] if n > 0 else self._blocks
            return [b.panel for b in blocks if b.panel is not None]

    def clear(self):
        """清空所有消息。"""
        with self._lock:
            self._blocks.clear()

    def __len__(self):
        return len(self._blocks)

    def __bool__(self):
        return bool(self._blocks)
