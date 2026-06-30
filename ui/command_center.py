"""CRUX 暗夜指挥台 — 七兽共鸣 · 固定对话框 · 终端原生。

设计理念:
  终端不是聊天框，是指挥台。
  - 固定输入框 = 驾驶舱操纵杆 (Rich Layout footer size=6 硬隔离)
  - 消息区 = 战场态势图 (独立滚动，绝不干扰输入区)
  - 七兽面板 = 武器系统 (Ctrl+1~7 秒切，配色同步)

架构保证:
  Rich Layout 三区硬分割:
    root ─┬─ header  (size=3, 固定)
          ├─ body    (ratio=1, 左右分栏)
          │   ├─ beasts   (size=22)
          │   └─ messages (ratio=1, 此处滚动)
          └─ footer  (size=6, 固定, 永不滚动！)

用法:
    python -m ui.command_center                     # 独立启动
    from ui.command_center import CommandCenter
    cc = CommandCenter()
    cc.on_send = lambda txt, beast: process(txt)    # 挂回调
    cc.run()
"""

from __future__ import annotations

import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.style import Style
from rich.align import Align
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PTKStyle
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings


# ═══════════════════════════════════════════════
# 颜色牌 — 暗夜工坊 v3
# ═══════════════════════════════════════════════

C = {
    "base":        "#0D1117",
    "surface":     "#161B22",
    "elevated":    "#1C2128",
    "text":        "#E6EDF3",
    "text_sec":    "#8B949E",
    "border":      "#21262D",
    "border_brt":  "#484F58",
    "success":     "#3FB950",
    "warning":     "#D29922",
    "error":       "#F85149",
    "zhuque":      "#F78166",
    "qinglong":    "#58A6FF",
    "baihu":       "#E3B341",
    "xuanwu":      "#7B85D6",
    "qilin":       "#3FB950",
    "tengshe":     "#DB8A3A",
    "yinglong":    "#A5C8E4",
}

# ═══════════════════════════════════════════════
# 七兽档案
# ═══════════════════════════════════════════════

BEASTS: Dict[str, dict] = {
    "zhuque":   {"name": "朱雀", "role": "洞察", "color": C["zhuque"],   "icon": "◆", "key": "1",
                 "motto": "洞若观火"},
    "qinglong": {"name": "青龙", "role": "并行", "color": C["qinglong"], "icon": "〰", "key": "2",
                 "motto": "万流归宗"},
    "baihu":    {"name": "白虎", "role": "容灾", "color": C["baihu"],    "icon": "▲", "key": "3",
                 "motto": "固若金汤"},
    "xuanwu":   {"name": "玄武", "role": "存储", "color": C["xuanwu"],   "icon": "●", "key": "4",
                 "motto": "海纳百川"},
    "qilin":    {"name": "麒麟", "role": "验证", "color": C["qilin"],    "icon": "◇", "key": "5",
                 "motto": "明察秋毫"},
    "tengshe":  {"name": "螣蛇", "role": "记忆", "color": C["tengshe"],  "icon": "◎", "key": "6",
                 "motto": "过目不忘"},
    "yinglong": {"name": "应龙", "role": "号令", "color": C["yinglong"], "icon": "⬡", "key": "7",
                 "motto": "一呼百应"},
}

BEAST_ORDER = ["zhuque", "qinglong", "baihu", "xuanwu", "qilin", "tengshe", "yinglong"]

STATUS_ICONS  = {"online": "●", "idle": "○", "busy": "◉", "error": "✕"}
STATUS_COLORS = {"online": C["success"], "idle": C["text_sec"],
                 "busy": C["warning"], "error": C["error"]}

HEADER_SIZE  = 3
FOOTER_SIZE  = 6   # ← 固定高度, 永不参与滚动
BEAST_WIDTH  = 22
MAX_MESSAGES = 200


# ═══════════════════════════════════════════════
@dataclass
class Message:
    """一条消息"""
    text: str
    role: str = "user"       # user | system | beast
    beast: str = "zhuque"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


# ═══════════════════════════════════════════════
# 暗夜指挥台
# ═══════════════════════════════════════════════

class CommandCenter:
    """CRUX 暗夜指挥台。

    三个不变式:
    1. footer 区 size=FOOTER_SIZE, 永远不被消息区侵占
    2. 消息区独立滚动, Rich Panel 内容自动截断适配可视高度
    3. 输入框在 footer 下方由 prompt_toolkit 接管, 不受 Rich 渲染影响
    """

    def __init__(self):
        self.console = Console()
        self.messages: List[Message] = []
        self.active_beast = "zhuque"
        self.beast_statuses = {k: "online" for k in BEAST_ORDER}
        self.beast_statuses["xuanwu"] = "idle"
        self.beast_statuses["yinglong"] = "idle"
        self.running = False
        self.on_send: Optional[Callable[[str, str], Optional[str]]] = None

        self.layout = self._build_layout()
        self._history = InMemoryHistory()
        self._bindings = self._build_keybindings()
        self._clock = datetime.now().strftime("%H:%M:%S")
        self._clock_thread: Optional[threading.Thread] = None

    # ═══ 布局 — 三区硬分割 ═══

    def _build_layout(self) -> Layout:
        root = Layout(name="root")
        root.split_column(
            Layout(name="header", size=HEADER_SIZE),
            Layout(name="body",   ratio=1),
            Layout(name="footer", size=FOOTER_SIZE),   # ← 固定, 永不滚动
        )
        root["body"].split_row(
            Layout(name="beasts",   size=BEAST_WIDTH),
            Layout(name="messages", ratio=1),
        )
        return root

    # ═══ 后台时钟 ═══

    def _clock_tick(self):
        while self.running:
            self._clock = datetime.now().strftime("%H:%M:%S")
            time.sleep(1)

    # ═══════════════════════════════════════════
    # 渲染 — 四个区
    # ═══════════════════════════════════════════

    def _render_header(self) -> Panel:
        """顶部标题栏"""
        left = Text()
        left.append("◆ ", Style(color=C["zhuque"], bold=True))
        left.append("CRUX", Style(color=C["text"], bold=True))
        left.append(" 暗夜指挥台", Style(color=C["text_sec"]))
        left.append(" · 七兽共鸣", Style(color=C["text_sec"], dim=True))

        right = Text()
        right.append(self._clock, Style(color=C["text"]))
        right.append("  ", "")
        right.append("●", Style(color=C["success"]))
        right.append(" MCP", Style(color=C["text_sec"]))

        tbl = Table(show_header=False, box=None, padding=0, expand=True)
        tbl.add_column("L", ratio=1)
        tbl.add_column("R", justify="right")
        tbl.add_row(left, right)

        return Panel(tbl, style=Style(color=C["border"]), padding=(0, 2))

    def _render_beasts(self) -> Panel:
        """左侧七兽武器库"""
        tbl = Table(show_header=False, box=None, padding=(0, 1), expand=True,
                    show_edge=False, pad_edge=False)
        tbl.add_column("sel", width=2)
        tbl.add_column("ico", width=2)
        tbl.add_column("nam", width=5)
        tbl.add_column("rol", width=5)
        tbl.add_column("dot", width=3, justify="right")

        for key in BEAST_ORDER:
            b = BEASTS[key]
            active = key == self.active_beast
            st = self.beast_statuses.get(key, "idle")

            sel = "▐" if active else " "
            sel_s = Style(color=b["color"], bold=True) if active else Style()

            tbl.add_row(
                Text(sel, style=sel_s),
                Text(b["icon"], style=Style(color=b["color"], bold=active)),
                Text(b["name"], style=Style(color=b["color"] if active else C["text"], bold=active)),
                Text(b["role"], style=Style(color=b["color"] if active else C["text_sec"], dim=not active)),
                Text(STATUS_ICONS.get(st, "○"),
                     style=Style(color=STATUS_COLORS.get(st, C["text_sec"]))),
            )

        return Panel(tbl, style=Style(color=C["border"]),
                     border_style=Style(color=C["border"]), padding=(0, 0))

    def _render_messages(self) -> Panel:
        """消息态势区 (此处可滚动)"""
        tbl = Table(show_header=False, box=None, padding=(0, 0), expand=True,
                    show_edge=False)
        tbl.add_column("gut", width=2)
        tbl.add_column("tag", width=10)
        tbl.add_column("ts",  width=9)
        tbl.add_column("txt", ratio=1)

        visible = self.messages[-60:]

        if not visible:
            empty = Text(
                "\n\n    七兽就绪 · 输入指令开始指挥\n"
                "    Ctrl+1~7 切换武器系统\n",
                style=Style(color=C["text_sec"], dim=True), justify="center")
            tbl.add_row("", "", "", empty)
        else:
            for msg in visible:
                b = BEASTS.get(msg.beast, BEASTS["zhuque"])
                color = b["color"]

                # 左侧兽色指示条
                gutter = Text("▌", style=Style(color=color, bold=True))

                # 标签
                if msg.role == "system":
                    tag = Text(f" SYSTEM ", style=Style(color=C["text_sec"], bold=False))
                elif msg.role == "beast":
                    tag = Text(f" {b['name']} ", style=Style(color=color, bold=True))
                else:
                    tag = Text(f" YOU ", style=Style(color=C["text_sec"], bold=True))

                ts = Text(msg.timestamp, style=Style(color=C["text_sec"], dim=True))
                body = Text(msg.text[:200], style=Style(color=C["text"]))

                tbl.add_row(gutter, tag, ts, body)

        return Panel(tbl, style=Style(color=C["border"]),
                     border_style=Style(color=C["border"]), padding=(0, 0))

    def _render_footer(self) -> Panel:
        """底部固定栏 — 上下文信息"""
        b = BEASTS[self.active_beast]
        color = b["color"]

        ctx = Text()
        ctx.append("◆ ", Style(color=color, bold=True))
        ctx.append(f"{b['name']}·{b['role']}模式", Style(color=C["text"], bold=True))
        ctx.append(f"  {b['motto']}  ", Style(color=C["text_sec"], dim=True))
        ctx.append("│  ", Style(color=C["border_brt"]))
        ctx.append(f"共 {len(self.messages)} 条", Style(color=C["text_sec"]))
        ctx.append("  │  ", Style(color=C["border"]))
        ctx.append("Enter 发送", Style(color=C["text_sec"]))
        ctx.append(" · ", Style(color=C["border"]))
        ctx.append("Ctrl+1~7 切换", Style(color=C["text_sec"]))
        ctx.append(" · ", Style(color=C["border"]))
        ctx.append("/help 帮助", Style(color=C["text_sec"]))

        return Panel(
            Align(ctx, align="left", vertical="middle"),
            style=Style(color=C["border"]),
            border_style=Style(color=color),
            padding=(0, 2),
        )

    def refresh_layout(self):
        self.layout["header"].update(self._render_header())
        self.layout["beasts"].update(self._render_beasts())
        self.layout["messages"].update(self._render_messages())
        self.layout["footer"].update(self._render_footer())

    # ═══════════════════════════════════════════
    # 消息操作
    # ═══════════════════════════════════════════

    def add_message(self, text: str, role: str = "user", beast: str = ""):
        msg = Message(text=text, role=role, beast=beast or self.active_beast)
        self.messages.append(msg)
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]

    def add_system(self, text: str):
        self.add_message(text, role="system")

    def add_response(self, text: str, beast: str = ""):
        self.add_message(text, role="beast", beast=beast or self.active_beast)

    # ═══════════════════════════════════════════
    # 键盘
    # ═══════════════════════════════════════════

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            event.app.exit(result=None)

        @kb.add("c-d")
        def _(event):
            if not event.app.current_buffer.text:
                event.app.exit(result=None)

        # Ctrl+1~7 秒切武器系统
        for i, key in enumerate(BEAST_ORDER, 1):
            @kb.add(f"c-{i}")
            def _(event, k=key):
                self.active_beast = k

        return kb

    # ═══════════════════════════════════════════
    # 主循环
    # ═══════════════════════════════════════════

    def run(self):
        self.running = True
        self.add_system("CRUX v6 · 暗夜指挥台已就绪 · MCP 全互联")
        self.add_system("七兽待命 — 朱雀洞察 | 青龙并行 | 白虎容灾 | 玄武存储 | 麒麟验证 | 螣蛇记忆 | 应龙号令")
        self.refresh_layout()

        # 启动后台时钟线程
        self._clock_thread = threading.Thread(target=self._clock_tick, daemon=True)
        self._clock_thread.start()

        while self.running:
            self.refresh_layout()

            # 全屏重绘 (clear + print, 不用 Live 避免和 prompt_toolkit 抢终端)
            self.console.clear()
            self.console.print(self.layout, markup=False, crop=False)

            # ── 当前兽配色 ──
            b = BEASTS[self.active_beast]
            color = b["color"]

            # 构造 prompt_toolkit 样式 (动态跟随兽色)
            ptk_style = PTKStyle.from_dict({
                "prompt":         f"bold {color}",
                "":               C["text"],
                "cursor":         color,
                "bottom-toolbar": f"bg:{C['surface']} {C['text_sec']}",
            })

            session = PromptSession(
                history=self._history,
                key_bindings=self._bindings,
                style=ptk_style,
                enable_history_search=True,
                multiline=False,
            )

            prompt_msg = FormattedText([
                ("class:prompt", f"  {b['icon']} {b['name']} "),
                ("",             ">>> "),
            ])

            toolbar = FormattedText([
                ("class:bottom-toolbar",
                 f" {b['icon']} {b['name']}·{b['role']}  │  "
                 f"Enter 发送  │  Ctrl+1~7 切换  │  /help 帮助  │  "
                 f"{len(self.messages)} 条消息"),
            ])

            # ── 获取输入 (prompt_toolkit 在 footer 下方接管) ──
            try:
                user_input = session.prompt(prompt_msg, bottom_toolbar=toolbar)
            except KeyboardInterrupt:
                break
            except EOFError:
                break

            if user_input is None:
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # ── 命令 / 消息路由 ──
            if user_input.startswith("/"):
                self._dispatch_command(user_input)
                continue

            self.add_message(user_input, role="user")

            if self.on_send:
                resp = self.on_send(user_input, self.active_beast)
                if resp:
                    self.add_response(resp)
            else:
                b2 = BEASTS[self.active_beast]
                self.add_response(f"[{b2['icon']} {b2['name']}] 收到指令: {user_input[:80]}")

        self.shutdown()

    def _dispatch_command(self, cmd: str):
        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if action == "/help":
            self.add_system("═══ 指挥台命令 ═══")
            for c, d in [
                ("/help",           "显示此帮助"),
                ("/clear",          "清空态势区"),
                ("/beast <name>",   "切换武器系统 (zhuque/qinglong/...)"),
                ("/status",         "查看七兽状态"),
                ("/watch [beast]",  "监视模式"),
                ("/broadcast <msg>","全兽广播"),
                ("/quit",           "退出指挥台"),
            ]:
                self.add_system(f"  {c:20s} — {d}")

        elif action == "/clear":
            self.messages.clear()
            self.add_system("态势区已清除")

        elif action == "/beast" and arg:
            if arg in BEASTS:
                self.active_beast = arg
                b = BEASTS[arg]
                self.add_system(f"▐ 已切换至 {b['icon']} {b['name']}·{b['role']} — {b['motto']}")
            else:
                self.add_system(f"未知武器系统: {arg}")
                self.add_system(f"可用: {', '.join(BEAST_ORDER)}")

        elif action == "/status":
            self.add_system("═══ 七兽状态 ═══")
            for k in BEAST_ORDER:
                b = BEASTS[k]
                st = self.beast_statuses.get(k, "idle")
                icon = STATUS_ICONS.get(st, "○")
                self.add_system(
                    f"  {icon} {b['icon']} {b['name']}·{b['role']}  [{st}]  {b['motto']}")

        elif action == "/watch":
            target = arg or "全部"
            self.add_system(f"监视模式启动 — 追踪 {target} 兽状态变化... (Ctrl+C 退出监视)")

        elif action == "/broadcast" and arg:
            for k in BEAST_ORDER:
                self.add_response(f"[广播] {arg}", k)
            self.add_system("全兽广播完成")

        elif action == "/quit":
            self.running = False

        else:
            self.add_system(f"未知命令: {action}，输入 /help 查看帮助")

    # ═══════════════════════════════════════════
    # 退出
    # ═══════════════════════════════════════════

    def shutdown(self):
        self.running = False
        self.add_system("暗夜指挥台已关闭 · 第一屏终端继续运行")
        self.refresh_layout()
        try:
            self.console.clear()
            self.console.print(self.layout, markup=False)
        except Exception:
            pass


# ═══════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════

def main():
    """独立启动暗夜指挥台"""
    print()
    print("  ◆ CRUX 暗夜指挥台 — 七兽共鸣")
    print("  固定输入框 · 终端原生 · 暗夜工坊")
    print("  ─" * 30)
    print()

    cc = CommandCenter()
    try:
        cc.run()
    except KeyboardInterrupt:
        pass
    finally:
        cc.shutdown()

    print("\n  暗夜指挥台已退出。第一屏终端继续运行。\n")


if __name__ == "__main__":
    main()
