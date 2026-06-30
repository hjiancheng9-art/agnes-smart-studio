"""ChatLayout — 固定输入框 · 消息面板 · 暗夜工坊风格。

核心设计：
- 全屏 Live 渲染，终端上半为消息历史，下半为固定输入栏
- 非阻塞输入（msvcrt/termios），输入框永不消失
- 流式输出注入消息区，不干扰输入框
- 保持 StreamingRenderer 的"输出不重复"DNA 契约

用法：
    layout = ChatLayout(console, colors=COLORS, layout_cfg=LAYOUT)
    layout.run(on_submit=handle_message)
"""

from __future__ import annotations

import sys
import time
import threading
from typing import Callable, Optional

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.console import Console, Group
from rich.align import Align
from rich.box import ROUNDED
from rich.style import Style

# ── 平台无关的非阻塞按键 ──────────────────────────────
if sys.platform == "win32":
    import msvcrt

    def _getch() -> bytes | None:
        if msvcrt.kbhit():
            return msvcrt.getch()
        return None
else:
    import select
    import tty
    import termios

    def _getch() -> bytes | None:
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1).encode()
        return None


class ChatLayout:
    """全屏聊天布局：消息区 + 固定输入栏。"""

    # 最大消息历史行数
    MAX_HISTORY_LINES = 1000

    def __init__(
        self,
        console: Console,
        colors: dict,
        layout_cfg: dict | None = None,
        title: str = "CRUX Studio",
    ):
        self.console = console
        self.C = colors
        self.L = layout_cfg or {}

        # ── 状态 ──
        self.messages: list[tuple[str, str]] = []  # (role, text)
        self.streaming_role: str = ""  # 当前流式角色（"ai" 或空）
        self.streaming_text: str = ""  # 当前流式文本
        self.input_buffer: str = ""
        self.cursor_pos: int = 0
        self.status_text: str = title
        self.running: bool = False
        self._live: Optional[Live] = None
        self._on_submit: Optional[Callable] = None
        self._pending_inputs: list[str] = []  # 排队输入
        self._input_lock = threading.Lock()
        self._input_cond = threading.Condition()

    # ═══════════════════════════════════════════════════════
    #  公开 API
    # ═══════════════════════════════════════════════════════

    def add_message(self, role: str, text: str):
        """添加一条完整消息到历史。"""
        self.messages.append((role, text))
        # 截断过长的消息列表
        if len(self.messages) > self.MAX_HISTORY_LINES:
            self.messages = self.messages[-self.MAX_HISTORY_LINES:]

    def start_streaming(self, role: str = "ai"):
        """开始流式输出（重置流式文本）。"""
        self.streaming_role = role
        self.streaming_text = ""

    def append_stream(self, delta: str):
        """追加流式增量文本。"""
        if self.streaming_role:
            self.streaming_text += delta

    def commit_stream(self):
        """结束流式输出，文本归档到消息历史。"""
        if self.streaming_role and self.streaming_text:
            self.add_message(self.streaming_role, self.streaming_text)
            self.streaming_role = ""
            self.streaming_text = ""

    def set_status(self, text: str):
        self.status_text = text

    def run(self, on_submit: Callable[[str], None]):
        """启动全屏聊天界面。

        on_submit: 用户按回车时回调，传入输入文本。
                   回调在渲染线程中执行，如需耗时操作请自行异步化。
        """
        self._on_submit = on_submit
        self.running = True

        # 启动输入线程
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()

        # 全屏 Live 渲染
        with Live(
            self._render(),
            console=self.console,
            refresh_per_second=20,
            screen=True,
            transient=False,
        ) as live:
            self._live = live
            try:
                while self.running:
                    live.update(self._render())
                    time.sleep(0.05)
            except KeyboardInterrupt:
                pass
            finally:
                self.running = False

    def stop(self):
        """停止聊天界面。"""
        self.running = False

    def poll_input(self, timeout: float = 0) -> str | None:
        """非阻塞获取已提交的用户输入（返回 None 表示没有）。"""
        with self._input_lock:
            if self._pending_inputs:
                return self._pending_inputs.pop(0)
        return None

    def wait_input(self, timeout: float | None = None) -> str | None:
        """阻塞等待用户输入（timeout=None 则一直等）。"""
        with self._input_cond:
            while not self._pending_inputs and self.running:
                if not self._input_cond.wait(timeout):
                    return None
            if self._pending_inputs:
                return self._pending_inputs.pop(0)
        return None

    # ═══════════════════════════════════════════════════════
    #  内部渲染
    # ═══════════════════════════════════════════════════════

    def _render(self) -> Layout:
        """构建完整布局树。"""
        root = Layout()

        # ── Header ──
        header = self._render_header()

        # ── Messages ──
        messages = self._render_messages()

        # ── Input ──
        input_panel = self._render_input()

        # 垂直分割：header(固定2行) | messages(弹性) | input(固定4行)
        root.split(
            Layout(header, name="header", size=2),
            Layout(messages, name="messages"),
            Layout(input_panel, name="input", size=4),
        )
        return root

    def _render_header(self) -> Panel:
        """顶部状态栏。"""
        style = Style(color=self.C.get("accent", "#58a6ff"), bold=True)
        header_text = Text.assemble(
            ("◆ ", Style(color=self.C.get("zhuque", "#ff6b6b"))),
            (self.status_text, style),
            (" " * 4, ""),
            ("— 固定输入 · 流式输出", Style(color=self.C.get("text_tertiary", "#484f58"), dim=True)),
        )

        return Panel(
            header_text,
            style=Style(color=self.C.get("border", "#30363d")),
            padding=(0, 2),
            height=2,
        )

    def _render_messages(self) -> Panel | Group:
        """消息历史区域。"""
        rendered = []

        # 取最近的消息（适应终端高度）
        terminal_height = self.console.height or 40
        available = max(terminal_height - 8, 5)  # 减去 header+input+padding

        # 估算可用行数
        visible_messages = []
        total_lines = 0
        for role, text in reversed(self.messages):
            line_count = text.count("\n") + 1
            if role == "user":
                line_count += 1  # bubble overhead
            if total_lines + line_count > available:
                break
            visible_messages.insert(0, (role, text))
            total_lines += line_count

        for role, text in visible_messages:
            if role == "user":
                rendered.append(self._user_bubble(text))
            else:
                rendered.append(self._ai_bubble(text))

        # 流式输出气泡
        if self.streaming_role and self.streaming_text:
            rendered.append(self._streaming_bubble(self.streaming_text))

        # 空状态提示
        if not rendered:
            hint = Text(
                "输入消息开始对话 · /help 查看命令",
                style=Style(color=self.C.get("text_tertiary", "#484f58"), italic=True),
            )
            rendered.append(Align.center(hint, vertical="middle"))

        return Group(*rendered)

    def _render_input(self) -> Panel:
        """固定输入栏。"""
        C = self.C

        # 输入提示符
        prompt_style = Style(color=C.get("zhuque", "#ff6b6b"), bold=True)
        text_style = Style(color=C.get("text", "#e6edf3"))
        cursor_style = Style(color=C.get("accent", "#58a6ff"), blink=True, bold=True)

        if self.input_buffer:
            # 有输入：显示 prompt + buffer + cursor
            display = Text.assemble(
                ("❯ ", prompt_style),
                (self.input_buffer, text_style),
                ("█", cursor_style),
            )
        else:
            # 空输入
            display = Text.assemble(
                ("❯ ", prompt_style),
                ("█", cursor_style),
                ("  输入消息...", Style(color=C.get("text_tertiary", "#484f58"), dim=True)),
            )

        # 如果 AI 在流式输出，显示状态
        if self.streaming_role:
            status_line = Text.assemble(
                ("◉ ", Style(color=C.get("success", "#3fb950"), blink=False)),
                ("CRUX 正在生成...", Style(color=C.get("text_secondary", "#8b949e"))),
                ("  (可排队输入，回车后等待)", Style(color=C.get("text_tertiary", "#484f58"), dim=True)),
            )
            content = Group(display, status_line)
        else:
            content = display

        panel_style = Style(color=C.get("border_focus", "#58a6ff") if self.input_buffer else C.get("border", "#30363d"))

        return Panel(
            Align.left(content),
            title="[输入]",
            title_align="left",
            border_style=panel_style,
            padding=(0, 2),
            height=4,
        )

    def _user_bubble(self, text: str) -> Panel:
        """用户消息气泡。"""
        C = self.C
        content = Text(text.strip(), style=Style(color=C.get("text", "#e6edf3")))
        return Panel(
            content,
            title="You",
            title_align="left",
            border_style=Style(color=C.get("qinglong", "#3fb950")),
            style=Style(bgcolor=C.get("surface", "#161b22")),
            padding=(0, 1),
        )

    def _ai_bubble(self, text: str) -> Panel:
        """AI 回复气泡。"""
        C = self.C
        content = Text.from_markup(text.strip()) if text.strip() else Text("")
        return Panel(
            content,
            title="CRUX",
            title_align="left",
            border_style=Style(color=C.get("zhuque", "#ff6b6b")),
            style=Style(bgcolor=C.get("elevated", "#1c2128")),
            padding=(0, 1),
        )

    def _streaming_bubble(self, text: str) -> Panel:
        """流式输出气泡（带光标闪烁效果）。"""
        C = self.C
        display = Text.assemble(
            (text.strip(), Style(color=C.get("text", "#e6edf3"))),
            (" ▌", Style(color=C.get("accent", "#58a6ff"), bold=True)),
        )
        return Panel(
            display,
            title="CRUX ◉",
            title_align="left",
            border_style=Style(color=C.get("zhuque", "#ff6b6b"), dim=False),
            style=Style(bgcolor=C.get("elevated", "#1c2128")),
            padding=(0, 1),
        )

    # ═══════════════════════════════════════════════════════
    #  非阻塞输入线程
    # ═══════════════════════════════════════════════════════

    def _input_loop(self):
        """后台线程：捕获按键，更新 input_buffer，识别回车提交。"""
        while self.running:
            ch = _getch()
            if ch is None:
                time.sleep(0.03)
                continue

            with self._input_lock:
                if ch == b"\r" or ch == b"\n":
                    # 回车：提交当前输入
                    text = self.input_buffer.strip()
                    self.input_buffer = ""
                    self.cursor_pos = 0
                    if text:
                        self.add_message("user", text)
                        self._pending_inputs.append(text)
                        with self._input_cond:
                            self._input_cond.notify_all()
                        # 回调提交处理器（在输入线程中执行）
                        if self._on_submit:
                            try:
                                self._on_submit(text)
                            except Exception:
                                pass
                elif ch == b"\x08" or ch == b"\x7f":
                    # 退格
                    if self.input_buffer:
                        self.input_buffer = self.input_buffer[:-1]
                elif ch == b"\x1b":
                    # ESC：清空输入
                    self.input_buffer = ""
                elif ch == b"\x03":
                    # Ctrl+C：停止
                    self.running = False
                    with self._input_cond:
                        self._input_cond.notify_all()
                elif len(ch) == 1 and 32 <= ch[0] < 127:
                    # 可打印字符
                    try:
                        self.input_buffer += ch.decode("utf-8", errors="replace")
                    except Exception:
                        pass
                # 忽略其他控制字符
