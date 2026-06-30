"""CRUX 第二屏 — Windows 终端 TUI · 固定对话框 · 七兽面板。

基于 Rich Layout + prompt_toolkit，暗夜工坊配色。
第一屏 (CLI 主壳) 与第二屏 (本模块) 互不干扰，独立运行。

架构:
    ┌─────────────────────────────────────────────┐
    │  ◆ CRUX Studio  七兽工坊 · 暗夜终端          │ header
    ├──────────┬──────────────────────────────────┤
    │ ● 朱雀    │                                   │
    │ ● 青龙    │  消息区 (Live 渲染, 可滚动)        │ body
    │ ● 白虎    │                                   │
    │   ...     │                                   │
    ├──────────┴──────────────────────────────────┤
    │ ◆ 朱雀·洞察  │ [___________________] [↑]    │ footer(固定)
    └─────────────────────────────────────────────┘

用法:
    python -m ui.beast_screen           # 独立启动
    from ui.beast_screen import BeastScreen
    screen = BeastScreen()
    screen.run()
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.align import Align
from rich.columns import Columns
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PTKStyle
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import PromptSession as PS

from .theme import COLORS, BADGE_ICONS, BADGE_STYLES

# ═══════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════

BEASTS = {
    "zhuque":   {"name": "朱雀", "role": "洞察",  "color": COLORS["zhuque"],   "icon": "◆"},
    "qinglong": {"name": "青龙", "role": "并行",  "color": COLORS["qinglong"], "icon": "〰"},
    "baihu":    {"name": "白虎", "role": "容灾",  "color": COLORS["baihu"],    "icon": "▲"},
    "xuanwu":   {"name": "玄武", "role": "存储",  "color": COLORS["xuanwu"],   "icon": "●"},
    "qilin":    {"name": "麒麟", "role": "验证",  "color": COLORS["qilin"],    "icon": "◇"},
    "tengshe":  {"name": "螣蛇", "role": "记忆",  "color": COLORS["tengshe"],  "icon": "◎"},
    "yinglong": {"name": "应龙", "role": "号令",  "color": COLORS["yinglong"], "icon": "⬡"},
}

BEAST_ORDER = ["zhuque", "qinglong", "baihu", "xuanwu", "qilin", "tengshe", "yinglong"]

MAX_MESSAGES = 200
HEADER_SIZE = 3
FOOTER_SIZE = 6
BEAST_PANEL_WIDTH = 22

# ── 状态图标 ──
STATUS_ICONS = {"online": "●", "idle": "○", "busy": "◉", "error": "✕"}

# ── 兽键盘快捷键 ──
BEAST_KEYS = {
    "1": "zhuque", "2": "qinglong", "3": "baihu",
    "4": "xuanwu", "5": "qilin", "6": "tengshe", "7": "yinglong",
}

# ═══════════════════════════════════════════════
# 消息数据结构
# ═══════════════════════════════════════════════


@dataclass
class Message:
    """一条对话消息"""
    text: str
    role: str = "user"          # user | system | beast
    beast: str = "zhuque"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def __post_init__(self):
        if self.role == "beast" and self.beast:
            self.role = "beast"


# ═══════════════════════════════════════════════
# 主类
# ═══════════════════════════════════════════════


class BeastScreen:
    """CRUX 第二屏 — 固定对话框终端界面。

    属性:
        messages: 消息列表
        active_beast: 当前选中的兽
        beast_statuses: 各兽状态 {key: 'online'|'idle'|'busy'|'error'}
        on_send: 可选回调, 处理用户输入
    """

    def __init__(self, title: str = "CRUX Studio"):
        self.console = Console()
        self.messages: List[Message] = []
        self.active_beast = "zhuque"
        self.beast_statuses = {k: "online" for k in BEAST_ORDER}
        self.beast_statuses["xuanwu"] = "idle"
        self.beast_statuses["yinglong"] = "idle"
        self.title = title
        self.running = False
        self.on_send: Optional[Callable[[str, str], Optional[str]]] = None
        self._scroll_offset = 0

        # ── 构造布局 ──
        self.layout = self._make_layout()

        # ── Prompt session ──
        self._prompt_session: Optional[PS] = None
        self._history = InMemoryHistory()
        self._bindings = KeyBindings()

        self._setup_keybindings()

    # ═══ 布局构造 ═══

    def _make_layout(self) -> Layout:
        """构造三区网格布局: header | body(beasts+msgs) | footer"""
        root = Layout(name="root")
        root.split_column(
            Layout(name="header", size=HEADER_SIZE),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=FOOTER_SIZE),
        )
        root["body"].split_row(
            Layout(name="beasts", size=BEAST_PANEL_WIDTH),
            Layout(name="messages", ratio=1),
        )
        return root

    # ═══ 渲染 ═══

    def _render_header(self) -> RenderableType:
        """渲染顶部标题栏"""
        C = COLORS
        title = Text()
        title.append("◆ ", Style(color=C["zhuque"], bold=True))
        title.append("CRUX Studio", Style(color=C["text"], bold=True))
        title.append("  ", "")
        title.append("七兽工坊 · 暗夜终端", Style(color=C["text_secondary"]))

        # 右侧信息
        right = Text()
        right.append(datetime.now().strftime("%H:%M:%S"), Style(color=C["text_secondary"]))
        right.append("  ", "")
        right.append("MCP 互联", Style(color="#3FB950"))

        # 用 table 实现左右对齐
        tbl = Table(show_header=False, box=None, padding=0, expand=True)
        tbl.add_column("left", ratio=1)
        tbl.add_column("right", justify="right")
        tbl.add_row(title, right)

        return Panel(
            tbl,
            style=Style(color=C["border"]),
            padding=(0, 2),
            height=HEADER_SIZE,
        )

    def _render_beast_panel(self) -> RenderableType:
        """渲染左侧七兽状态面板"""
        C = COLORS
        tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True,
                    show_edge=False, pad_edge=False)
        tbl.add_column("icon", width=2)
        tbl.add_column("name", width=6)
        tbl.add_column("role", width=6)
        tbl.add_column("status", width=3, justify="right")

        for key in BEAST_ORDER:
            b = BEASTS[key]
            active = key == self.active_beast
            status = self.beast_statuses.get(key, "idle")

            # 活跃兽高亮
            name_style = Style(color=b["color"], bold=active)
            icon_style = Style(color=b["color"], bold=active)
            role_style = Style(color=C["text_secondary"], dim=not active)
            status_color = {
                "online": "#3FB950", "idle": C["text_secondary"],
                "busy": "#D29922", "error": "#F85149"
            }.get(status, C["text_secondary"])

            # 活跃指示线
            prefix = "▌" if active else " "

            tbl.add_row(
                Text(prefix + " " + b["icon"], style=icon_style),
                Text(b["name"], style=name_style),
                Text(b["role"], style=role_style),
                Text(STATUS_ICONS.get(status, "○"), style=Style(color=status_color)),
            )

        return Panel(
            tbl,
            title=Text("七兽", style=Style(color=C["text_secondary"], bold=True)),
            title_align="left",
            style=Style(color=C["border"]),
            border_style=Style(color=C["border"]),
            padding=(0, 0),
        )

    def _render_messages(self) -> RenderableType:
        """渲染消息区"""
        C = COLORS
        tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True,
                    show_edge=False)
        tbl.add_column("gutter", width=2)
        tbl.add_column("content", ratio=1)

        # 取最后 N 条消息适配可视区
        visible = self.messages[-50:]

        if not visible:
            # 空状态
            empty = Text("\n\n    七兽就绪 · 输入指令开始协作\n",
                         style=Style(color=C["text_secondary"], dim=True),
                         justify="center")
            tbl.add_row("", empty)
            return Panel(tbl, style=Style(color=C["border"]), padding=(0, 0))

        for msg in visible:
            b = BEASTS.get(msg.beast, BEASTS["zhuque"])
            color = b["color"]

            # 左边色条
            gutter = Text("▌", style=Style(color=color, bold=True))

            # 消息行
            line = Text()
            # 标签
            tag = msg.beast if msg.role == "beast" else msg.role.upper()
            line.append(f"[{tag}] ", Style(color=color, bold=True))
            # 时间
            line.append(f"{msg.timestamp} ", Style(color=C["text_secondary"], dim=True))
            # 内容
            line.append(msg.text[:200], Style(color=C["text"]))

            tbl.add_row(gutter, line)

        return Panel(
            tbl,
            style=Style(color=C["border"]),
            padding=(0, 0),
        )

    def _render_footer(self) -> RenderableType:
        """渲染底部固定区域 (不含 input，仅上下文提示)"""
        C = COLORS
        b = BEASTS[self.active_beast]
        color = b["color"]

        ctx = Text()
        ctx.append("◆ ", Style(color=color))
        ctx.append(f"{b['name']}·{b['role']}模式", Style(color=C["text"], bold=True))
        ctx.append(f"  共 {len(self.messages)} 条消息", Style(color=C["text_secondary"]))
        ctx.append("  │  ", Style(color=C["border_bright"]))
        ctx.append("Enter 发送", Style(color=C["text_secondary"], dim=True))
        ctx.append(" · ", Style(color=C["border"]))
        ctx.append("Ctrl+1~7 切换兽", Style(color=C["text_secondary"], dim=True))
        ctx.append(" · ", Style(color=C["border"]))
        ctx.append("Ctrl+C 退出", Style(color=C["text_secondary"], dim=True))

        return Panel(
            Align(ctx, align="left", vertical="middle"),
            style=Style(color=C["border"]),
            border_style=Style(color=color),
            padding=(0, 2),
            height=FOOTER_SIZE - 1,
        )

    def refresh_layout(self):
        """更新所有区域内容"""
        self.layout["header"].update(self._render_header())
        self.layout["beasts"].update(self._render_beast_panel())
        self.layout["messages"].update(self._render_messages())
        self.layout["footer"].update(self._render_footer())

    # ═══ 消息操作 ═══

    def add_message(self, text: str, role: str = "user", beast: Optional[str] = None):
        """添加一条消息并刷新"""
        beast = beast or self.active_beast
        msg = Message(text=text, role=role, beast=beast)
        self.messages.append(msg)
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]

    def add_system(self, text: str):
        """添加系统消息"""
        self.add_message(text, role="system")

    def add_beast_response(self, text: str, beast: Optional[str] = None):
        """添加兽的回复"""
        self.add_message(text, role="beast", beast=beast or self.active_beast)

    # ═══ 键盘 ═══

    def _setup_keybindings(self):
        """设置 prompt_toolkit 快捷键"""
        bindings = self._bindings

        @bindings.add("c-c")
        def _(event):
            """Ctrl+C 退出"""
            event.app.exit(result=None)

        @bindings.add("c-d")
        def _(event):
            """Ctrl+D 在空行时退出"""
            if not event.app.current_buffer.text:
                event.app.exit(result=None)

        # 1-7 切换兽 (需要 ctrl)
        for num, beast in BEAST_KEYS.items():
            @bindings.add(f"c-{num}")
            def _(event, b=beast):
                self.active_beast = b
                # 更新提示样式 (下一次渲染生效)

    # ═══ 主循环 ═══

    def _make_prompt_style(self) -> PTKStyle:
        """生成 prompt_toolkit 样式，匹配暗夜工坊"""
        C = COLORS
        b = BEASTS[self.active_beast]
        return PTKStyle.from_dict({
            # 提示符
            "prompt": f"bold {b['color']}",
            # 输入文本
            "": C["text"],
            # 光标
            "cursor": f"{b['color']}",
            # 底部工具栏
            "bottom-toolbar": f"bg:{C['surface']} {C['text_secondary']}",
        })

    def _get_prompt_message(self) -> FormattedText:
        """生成 Rich 风格的提示符"""
        b = BEASTS[self.active_beast]
        return FormattedText([
            ("class:prompt", f"  {b['icon']} {b['name']} "),
            ("", "› "),
        ])

    def _get_bottom_toolbar(self) -> FormattedText:
        """底部上下文栏"""
        b = BEASTS[self.active_beast]
        return FormattedText([
            ("class:bottom-toolbar",
             f" {b['icon']} {b['name']}·{b['role']}  "
             f"│  Enter 发送  │  Ctrl+1~7 切换  │  Ctrl+C 退出  │  "
             f"{len(self.messages)} msgs"),
        ])

    def run(self):
        """启动第二屏主循环。

        渲染策略: console.print(layout) 一次性输出全屏 → prompt_toolkit 获取输入 → 循环。
        避免 Live 与 prompt_toolkit 争夺终端控制权。
        """
        self.running = True
        self.add_system("CRUX Studio v6 · 七兽融合就绪 · 第二屏已激活")
        self.add_system("MCP 全互联 · 第一屏终端运行中")
        self.refresh_layout()

        console = self.console
        self._prompt_session = PromptSession(
            history=self._history,
            key_bindings=self._bindings,
            enable_history_search=True,
            multiline=False,
        )

        # ── 清除屏幕 ──
        console.clear()

        # 进入主循环
        while self.running:
            self.refresh_layout()

            # 移动光标到顶部并重绘全屏
            console.clear()
            console.print(self.layout, markup=False, crop=False)

            # ── 获取用户输入 ──
            try:
                b = BEASTS[self.active_beast]
                prompt_style = PTKStyle.from_dict({
                    "prompt": f"bold {b['color']}",
                    "": COLORS["text"],
                    "cursor": b["color"],
                    "bottom-toolbar": f"bg:{COLORS['surface']} {COLORS['text_secondary']}",
                })

                # 重建 session 以应用新样式
                session = PromptSession(
                    history=self._history,
                    key_bindings=self._bindings,
                    style=prompt_style,
                    enable_history_search=True,
                    multiline=False,
                )

                user_input = session.prompt(
                    self._get_prompt_message,
                    bottom_toolbar=self._get_bottom_toolbar,
                )

                if user_input is None:
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue

                # 处理特殊命令
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # 正常消息
                self.add_message(user_input, role="user")

                # 如果有回调，获取响应
                if self.on_send:
                    response = self.on_send(user_input, self.active_beast)
                    if response:
                        self.add_beast_response(response)
                else:
                    self.add_beast_response(f"收到: {user_input[:80]}")

            except KeyboardInterrupt:
                break
            except EOFError:
                break

        self.shutdown()
        console.clear()

    def _handle_command(self, cmd: str):
        """处理 / 命令"""
        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if action == "/help":
            self.add_system("命令: /help /clear /beast <name> /status /quit")
        elif action == "/clear":
            self.messages.clear()
            self.add_system("消息已清除")
        elif action == "/beast" and arg:
            if arg in BEASTS:
                self.active_beast = arg
                self.add_system(f"已切换到 {BEASTS[arg]['name']}·{BEASTS[arg]['role']}")
            else:
                self.add_system(f"未知兽: {arg}. 可用: {', '.join(BEAST_ORDER)}")
        elif action == "/status":
            for k in BEAST_ORDER:
                b = BEASTS[k]
                st = self.beast_statuses.get(k, "idle")
                self.add_system(f"  {b['icon']} {b['name']}: {st}")
        elif action == "/quit":
            self.running = False
        else:
            self.add_system(f"未知命令: {action}. 输入 /help 查看帮助")

    def shutdown(self):
        """清理退出"""
        self.running = False
        self.add_system("第二屏已关闭")
        # 最后一次渲染
        self.refresh_layout()
        try:
            self.console.print(self.layout, markup=False)
        except Exception:
            pass

    def send_beast_message(self, text: str, beast: str = ""):
        """外部调用: 向指定兽发送消息并显示回复"""
        beast = beast or self.active_beast
        self.add_message(text, role="user", beast=beast)
        self.add_beast_response(f"[{BEASTS[beast]['name']}] 处理中: {text[:100]}", beast)

    def update_beast_status(self, beast: str, status: str):
        """更新兽状态: online | idle | busy | error"""
        if beast in self.beast_statuses:
            self.beast_statuses[beast] = status


# ═══════════════════════════════════════════════
# 独立运行入口
# ═══════════════════════════════════════════════


def main():
    """独立启动第二屏"""
    screen = BeastScreen()
    try:
        screen.run()
    except KeyboardInterrupt:
        pass
    finally:
        screen.shutdown()
    print("\n第二屏已退出。第一屏继续运行中。")


if __name__ == "__main__":
    main()
