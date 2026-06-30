"""CRUX Terminal Application — 七兽工坊 · 暗夜终端。

Layout:
  ┌──────────────────────────────────────────────────────┐
  │  ◈ CRUX Studio v6.0 · deepseek-v4-pro · 3 消息      │  ← 1行状态栏
  ├──────────────────────────────────────────────────────┤
  │  ┌─ user ───────────────────────────────────────┐    │
  │  │  你好                                      │    │  ← 消息面板
  │  └──────────────────────────────────────────────┘    │  (ScrollablePane,
  │  ┌─ assistant ─────────────────────────────────┐    │   可滚动)
  │  │  你好！有什么可以帮你的？                    │    │
  │  └──────────────────────────────────────────────┘    │
  ├──────────────────────────────────────────────────────┤
  │  ⯈ 输入你的消息...                          Ctrl+Enter│  ← 输入区（固定高度）
  └──────────────────────────────────────────────────────┘
"""

import asyncio
import threading
import time as _time
from typing import Callable, Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    FormattedTextControl,
    HSplit,
    Layout,
    ScrollablePane,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.styles import Style as PtkStyle
from prompt_toolkit.widgets import TextArea

from ui.theme import COLORS, GLYPHS
from ui.message_buffer import MessageBuffer

# ── 斜杠命令补全 ──────────────────────────────────────────
SLASH_COMMANDS = [
    "/chat", "/skill", "/tool", "/agent", "/provider",
    "/beast", "/exit", "/quit", "/clear", "/help",
    "/code", "/image", "/video", "/browser",
]

class SlashCompleter(Completer):
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

# ── ptk 样式 ─────────────────────────────────────────────
def build_ptk_style() -> PtkStyle:
    return PtkStyle.from_dict({
        "status-bar":        f"bg:{COLORS['surface']}",
        "status-bar.bright": f"bg:{COLORS['surface']} bold {COLORS['primary']}",
        "message-area":      f"bg:{COLORS['base']}",
        "separator-line":    f"fg:{COLORS['separator_thin']}",
        "input-field":       f"bg:{COLORS['surface']} {COLORS['text']}",
        "scrollbar":         f"fg:{COLORS['text_tertiary']} bg:{COLORS['surface']}",
        "scrollbar.arrow":   f"fg:{COLORS['text_tertiary']}",
    })

# ── Rich → ANSI 辅助 ──────────────────────────────────────
def _rich_to_ansi(rich_obj) -> "ANSI":
    """将 Rich 对象转换为 prompt_toolkit ANSI 文本。"""
    import io
    from rich.console import Console as RichConsole
    buf = io.StringIO()
    console = RichConsole(file=buf, force_terminal=True, color_system="truecolor")
    console.print(rich_obj)
    return ANSI(buf.getvalue())


# ── 主应用类 ──────────────────────────────────────────────
class CruxTerminalApp:
    """CRUX 终端应用 — 状态栏 + 可滚动消息面板 + 固定输入框。"""

    def __init__(
        self,
        submit_callback: Optional[Callable[[str], None]] = None,
        provider: str = "deepseek-v4-pro",
        version: str = "v6.0",
    ):
        self.submit_callback = submit_callback
        self.provider = provider
        self.version = version
        self._start_time = _time.time()
        self._message_count = 0
        self._generating = False
        self._stream_buffer = ""
        self._lock = threading.Lock()
        self._custom_status = ""
        self._active_beast = "zhuque"
        self._sparkle_count = 0
        self._error_flash = False

        # ── 消息缓冲 ──
        self.buffer = MessageBuffer()

        # ── 状态栏 ──
        self._status_control = FormattedTextControl(
            text=self._get_status_text,
            style="class:status-bar",
        )
        status_window = Window(
            self._status_control,
            height=1,
            style="class:status-bar",
        )

        # ── 消息面板 (ScrollablePane) ──
        self._message_control = FormattedTextControl(
            text=self._render_messages,
            style="class:message-area",
        )
        message_window = Window(
            self._message_control,
            wrap_lines=True,
            always_hide_cursor=True,
        )
        self._scrollable_pane = ScrollablePane(
            message_window,
            show_scrollbar=True,
            display_arrows=False,
        )

        # ── 输入区 (固定高度，在 ScrollablePane 外部) ──
        self._input_area = TextArea(
            height=3,
            prompt=f"{GLYPHS['send']} ",
            style="class:input-field",
            multiline=True,
            completer=SlashCompleter(),
            complete_while_typing=True,
        )

        # ── 整体布局 ──
        # 输入区独立于 ScrollablePane，不受消息滚动影响
        root_container = HSplit([
            status_window,
            Window(height=1, char=GLYPHS["hbar"], style="class:separator-line"),
            self._scrollable_pane,   # flex: 占据剩余空间
            Window(height=1, char=GLYPHS["hbar"], style="class:separator-line"),
            self._input_area,        # height=3: 固定底部
        ])

        self.layout = Layout(root_container)

        # ── 快捷键 ──
        self._kb = self._build_keybindings()

        # ── Application ──
        self._app = Application(
            layout=self.layout,
            key_bindings=self._kb,
            style=build_ptk_style(),
            full_screen=True,
            mouse_support=True,
        )

    # ── 快捷键绑定 ────────────────────────────────────────
    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _exit(event):
            self.exit()

        @kb.add("c-l")
        def _clear(event):
            self.clear()

        @kb.add("escape")
        def _toggle_focus(event):
            if self._app.layout.has_focus(self._input_area):
                self._app.layout.focus(self._scrollable_pane)
            else:
                self._app.layout.focus(self._input_area)

        @kb.add("escape", "c")
        def _focus_input(event):
            self._app.layout.focus(self._input_area)

        @kb.add("c-j", eager=True)
        def _send(event):
            self._do_submit()

        return kb

    def _do_submit(self):
        """提交输入文本。"""
        text = self._input_area.text.strip()
        if not text:
            return
        self._input_area.text = ""
        if self.submit_callback:
            try:
                self.submit_callback(text)
            except Exception:
                pass

    # ── 自动滚底 ──────────────────────────────────────────
    def _scroll_to_bottom(self) -> None:
        """强制滚动消息面板到底部。

        将 vertical_scroll 设为极大值，在下一帧渲染时
        ScrollablePane._make_window_visible 会自动夹到合法最大值。
        """
        self._scrollable_pane.vertical_scroll = 10 ** 9

    # ── 状态栏文本 ────────────────────────────────────────
    def _get_status_text(self) -> list:
        """构建状态栏 formatted_text 列表。"""
        gen_status = f"{GLYPHS['fire']} 生成中" if self._generating else f"{GLYPHS['dot']} 就绪"
        sparkle = f" {GLYPHS['star']}x{self._sparkle_count}" if self._sparkle_count > 0 else ""
        error = f" {GLYPHS['cross']} 错误" if self._error_flash else ""

        custom = self._custom_status
        if custom:
            return [
                ("class:status-bar.bright", f" {GLYPHS['logo']} CRUX Studio {self.version}  "),
                ("class:status-bar", f"·  {custom}  "),
            ]

        return [
            ("class:status-bar.bright", f" {GLYPHS['logo']} CRUX Studio {self.version}  "),
            ("class:status-bar", f"·  {self.provider}  "),
            ("class:status-bar", f"·  {self._message_count} 消息  "),
            ("class:status-bar", f"·  {gen_status}{sparkle}{error}  "),
        ]

    # ── 消息渲染 ──────────────────────────────────────────
    def _render_messages(self) -> list:
        """将 MessageBuffer 中的所有气泡渲染为 ANSI 文本。"""
        from rich.console import Console as RichConsole
        from rich.text import Text as RichText
        import io

        all_panels = self.buffer.render_all()

        # 流式预览
        if self._generating and self._stream_buffer:
            from rich.panel import Panel
            from rich.markdown import Markdown
            stream_panel = Panel(
                Markdown(self._stream_buffer + GLYPHS["cursor"]),
                border_style=COLORS["assistant_bubble_border"],
                style=f"on {COLORS['assistant_bubble_bg']}",
                padding=(1, 2),
            )
            all_panels = all_panels + [stream_panel]

        if not all_panels:
            welcome = RichText()
            welcome.append(GLYPHS["logo"] + " 欢迎使用 CRUX Studio",
                           style=f"bold {COLORS['text_secondary']}")
            welcome.append("\n")
            welcome.append("输入消息后 Ctrl+Enter 发送，Ctrl+L 清屏",
                           style=COLORS["text_tertiary"])
            return _rich_to_ansi(welcome)

        buf = io.StringIO()
        console = RichConsole(file=buf, force_terminal=True, color_system="truecolor")
        for i, panel in enumerate(all_panels):
            console.print(panel)
            if i < len(all_panels) - 1:
                console.print("")

        return ANSI(buf.getvalue())

    # ── 公共 API ──────────────────────────────────────────
    def add_message(self, role: str, content: str):
        """添加一条完整消息并滚动到底部。"""
        with self._lock:
            self.buffer.add_message(role, content)
            self._message_count = len(self.buffer)
        if self._app:
            self._app.invalidate()
            self._scroll_to_bottom()

    def add_stream_chunk(self, chunk: str):
        """追加流式输出文本。"""
        with self._lock:
            self._stream_buffer += chunk
        if self._app:
            self._app.invalidate()
            self._scroll_to_bottom()

    def commit_stream(self):
        """结束流式输出，将缓冲提交为完整消息。"""
        with self._lock:
            if self._stream_buffer:
                self.buffer.add_message("assistant", self._stream_buffer)
                self._stream_buffer = ""
                self._generating = False
                self._message_count = len(self.buffer)
        if self._app:
            self._app.invalidate()
            self._scroll_to_bottom()

    def start_generating(self):
        """标记开始生成。"""
        self._generating = True
        self._stream_buffer = ""
        if self._app:
            self._app.invalidate()
            self._scroll_to_bottom()

    def stop_generating(self):
        """停止生成。"""
        self._generating = False
        if self._app:
            self._app.invalidate()

    def clear(self):
        """清空所有消息。"""
        self.buffer.clear()
        self._stream_buffer = ""
        self._message_count = 0
        self._generating = False
        if self._app:
            self._app.invalidate()

    def set_header(self, text: str) -> None:
        """设置状态栏自定义文本（兼容旧接口）。"""
        self._custom_status = text
        if self._app:
            self._app.invalidate()

    def set_status(self, text: str) -> None:
        """设置状态栏右侧文本。"""
        self._custom_status = text
        if self._app:
            self._app.invalidate()

    def set_beast(self, name: str) -> str:
        """切换兽魂主题。"""
        from ui.flourish import BEAST_THEMES
        name = name.lower().strip()
        if name in BEAST_THEMES:
            self._active_beast = name
            return f"已切换至 {BEAST_THEMES[name]['label']}"
        available = ", ".join(BEAST_THEMES.keys())
        return f"未知兽魂：{name}，可用：{available}"

    @property
    def beast_theme(self) -> str:
        return self._active_beast

    def sparkle(self):
        """添加闪光计数。"""
        self._sparkle_count = getattr(self, '_sparkle_count', 0) + 1
        if self._app:
            self._app.invalidate()

    def flash_error(self):
        """短暂显示错误指示。"""
        self._error_flash = True
        if self._app:
            self._app.invalidate()
        def _clear():
            import time
            time.sleep(0.5)
            self._error_flash = False
            if self._app:
                self._app.invalidate()
        threading.Thread(target=_clear, daemon=True).start()

    def run(self):
        """启动终端应用。"""
        self._app.run()

    def exit(self):
        """退出终端应用。"""
        self._app.exit()

    async def run_async(self):
        """异步运行。"""
        return await self._app.run_async()
