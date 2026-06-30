"""暗夜工坊 Dark Atelier — CRUX Studio v6 现代开发者主题。

基于 GitHub Dark 骨架，融入七兽色作为功能区分色。层次感取代扁平，
信息密度优先，终端原生表现力最大化。

设计原则:
- bg 三层: base(底色) → surface(卡片) → elevated(悬停)
- text 三层: primary(主文字) → secondary(次要) → tertiary(极淡)
- 七兽色: 降饱和做功能色，非装饰
- 边框: 极淡，不抢内容

All colors, icons, layout parameters, and the Rich Theme are defined here.
Every UI module must import from this file (never define colors/logos locally).
"""

from rich.console import Console
from rich.theme import Theme

__all__ = [
    "COLORS",
    "RETRO_THEME",
    "ICONS",
    "BADGE_ICONS",
    "BADGE_STYLES",
    "LAYOUT",
    "INPUT_STYLE",
    "DIVIDER_STYLE",
    "PANEL_STYLE",
    "CHAT_SEPARATOR_STYLE",
    "CONTEXT_BAR_STYLE",
    "create_console",
    "console",
]

# ═══════════════════════════════════════════════
#  Color palette — 暗夜工坊 v3
# ═══════════════════════════════════════════════
COLORS = {
    # ── 背景层次 (darkest → lightest) ──
    "base": "#0D1117",         # GitHub dark 底色
    "surface": "#161B22",      # 卡片/面板底色
    "elevated": "#1C2128",     # 悬停/聚焦层
    "overlay": "#30363D44",    # 半透明叠加

    # ── 文字层次 ──
    "text": "#E6EDF3",         # 主文字 · 暖白
    "text_secondary": "#8B949E",  # 次要文字 · 钢灰
    "text_tertiary": "#6E7681",   # 极淡文字

    # ── 边框 ──
    "border": "#21262D",       # 极淡边框
    "border_focus": "#30363D", # 聚焦边框
    "border_bright": "#484F58",# 高亮边框

    # ── 七兽色 — 功能区分 · 低饱和专业 ──
    "baihu": "#E3B341",        # 白虎·金 → 权威/警告
    "qinglong": "#58A6FF",     # 青龙·青 → 信息/链接
    "zhuque": "#F78166",       # 朱雀·赤 → 创意/洞察
    "xuanwu": "#7B85D6",       # 玄武·靛 → 系统/守卫
    "qilin": "#3FB950",        # 麒麟·翠 → 成功/创造
    "tengshe": "#DB8A3A",      # 螣蛇·琥珀 → 记忆/历史
    "yinglong": "#A5C8E4",     # 应龙·银蓝 → 规划/调度

    # ── 语义色 ──
    "success": "#3FB950",      # 成功 · 麒麟绿
    "warning": "#D29922",      # 警告 · 暖金
    "error": "#F85149",        # 错误 · 暖红
    "info": "#58A6FF",         # 信息 · 青龙蓝

    # ── 兼容别名 (旧代码不报错) ──
    "primary": "#58A6FF",
    "accent": "#E3B341",
    "muted": "#8B949E",
    "highlight": "#F78166",
    "transition": "#A5C8E4",

    # ── Badge 色 ──
    "badge_code": "#58A6FF",
    "badge_agent": "#E3B341",
    "badge_think": "#F78166",
    "badge_skill": "#3FB950",
    "badge_model": "#7B85D6",

    # ── 输入/交互 ──
    "input_prompt": "#58A6FF",
    "input_border": "#21262D",
    "input_text": "#E6EDF3",
    "input_placeholder": "#6E7681",
    "input_frame_top": "#30363D",
    "input_frame_bottom": "#21262D",
    "input_hint": "#8B949E",
    "input_cursor": "#58A6FF",

    # ── 组件色 ──
    "divider_primary": "#21262D",
    "card_border": "#21262D",
    "card_hover": "#58A6FF",
    "status_ok": "#3FB950",
    "status_warn": "#D29922",
    "status_err": "#F85149",
    "status_idle": "#6E7681",

    # ── 聊天分隔符 ──
    "chat_separator": "#21262D",
    "chat_separator_accent": "#30363D",
}

# ═══════════════════════════════════════════════
#  Rich Theme
# ═══════════════════════════════════════════════
RETRO_THEME = Theme({
    "primary": "bold #58A6FF",
    "accent": "bold #E3B341",
    "success": "#3FB950",
    "warning": "#D29922",
    "error": "bold #F85149",
    "muted": "#8B949E",
    "surface": "on #161B22",
    "highlight": "#F78166",
    "transition": "#A5C8E4",
    "panel.title": "bold #E3B341",
    "panel.border": "#30363D",
    "table.header": "bold #58A6FF",
    "table.border": "#30363D",
    "bar.fill": "#58A6FF",
    "bar.background": "#21262D",
    "baihu": "#E3B341",
    "qinglong": "#58A6FF",
    "zhuque": "#F78166",
    "xuanwu": "#7B85D6",
    "qilin": "#3FB950",
    "tengshe": "#DB8A3A",
    "yinglong": "#A5C8E4",
    "badge.code": "bold #58A6FF",
    "badge.agent": "bold #E3B341",
    "badge.think": "bold #F78166",
    "badge.skill": "#3FB950",
    "badge.model": "#7B85D6",
    "input.prompt": "#58A6FF",
    "input.border": "#21262D",
    "input.frame": "#30363D",
    "input.hint": "#484F58",
    "divider": "#21262D",
    "chat.separator": "#21262D",
    "context.bar": "#30363D",
    # ── Markdown 渲染样式 ──
    "markdown.h1": "bold #E3B341",
    "markdown.h2": "bold #58A6FF",
    "markdown.h3": "bold #7B85D6",
    "markdown.h4": "bold #8B949E",
    "markdown.code": "#F78166 on #1C2128",
    "markdown.code_block": "on #161B22",
    "markdown.block_quote": "dim #8B949E",
    "markdown.link": "#58A6FF",
    "markdown.hr": "#21262D",
    "markdown.item.bullet": "#58A6FF",
    "markdown.item.number": "#58A6FF",
    "markdown.strong": "bold #E6EDF3",
    "markdown.em": "italic #E6EDF3",
})

# ═══════════════════════════════════════════════
#  Icons — 现代 Unicode 符号集
# ═══════════════════════════════════════════════
ICONS = {
    "primary": "●",
    "info": "○",
    "success": "●",
    "warning": "▲",
    "error": "●",
    "video": "▶",
    "route": "›",
    "on": "●",
    "off": "○",
    "enabled": "✓",
    "disabled": "✗",
    "star": "★",
    "empty": "○",
    "pipeline": "◎",
    "history": "☰",
    "template": "◇",
    "separator": " · ",
    # 七兽符号
    "baihu": "◆",
    "qinglong": "◇",
    "zhuque": "◈",
    "xuanwu": "◎",
    "qilin": "●",
    "tengshe": "◆",
    "yinglong": "◇",
    "crown": "♛",
    "shield": "⊡",
    "bolt": "⚡",
    "spark": "✦",
    "ring": "◎",
    "input": "›",
    "divider_dot": "·",
    # 新增
    "check": "✓",
    "cross": "✗",
    "arrow": "→",
    "bullet": "·",
    "dot": "·",
}

BADGE_ICONS = {
    "code": "⚡",
    "agent": "◈",
    "think": "◇",
    "model": "◎",
    "skill": "✦",
}

# ═══════════════════════════════════════════════
#  Badge 样式槽
# ═══════════════════════════════════════════════
BADGE_STYLES = {
    "code": {"icon": "⚡", "color": "badge.code", "bg": "#0D2B4A", "label": "CODE"},
    "agent": {"icon": "◈", "color": "badge.agent", "bg": "#2B2000", "label": "AGENT"},
    "think": {"icon": "◇", "color": "badge.think", "bg": "#2A1530", "label": "THINK"},
    "skill": {"icon": "✦", "color": "badge.skill", "bg": "#0D2A18", "label": "SKILL"},
    "model": {"icon": "◎", "color": "badge.model", "bg": "#1A1E35", "label": "MODEL"},
    "provider": {"icon": "●", "color": "muted", "bg": "#161B22", "label": "PROV"},
}

# ═══════════════════════════════════════════════
#  Layout
# ═══════════════════════════════════════════════
LAYOUT = {
    "panel_padding": (1, 2),
    "panel_border_style": "round",
    "table_show_lines": False,
    "table_box": "ROUNDED",
    "indent": "  ",
    "separator_len": 42,
    "separator_char": "─",
    "badge_separator": "  ·  ",
    "bar_style": "#58A6FF",
    "bar_complete_style": "#3FB950",
    "input_indent": "  ",
    "welcome_width": 68,
    "card_min_width": 22,
}

# ── 输入框样式 ──
INPUT_STYLE = {
    "prompt_symbol": "›",
    "prompt_symbol_alt": "❯",
    "prompt_color": "primary",
    "border_char": "─",
    "border_color": "muted",
    "hint_color": "muted",
    "frame_top_left": "╭",
    "frame_top_right": "╮",
    "frame_bottom_left": "╰",
    "frame_bottom_right": "╯",
    "frame_vertical": "│",
    "frame_horizontal": "─",
    "width": 72,
    "min_padding": 2,
}

# ── 聊天分隔线样式 ──
CHAT_SEPARATOR_STYLE = {
    "char": "─",
    "heavy_char": "━",
    "double_char": "═",
    "dot_char": "◆",
    "length": 50,
    "color": "chat_separator",
    "accent_color": "chat_separator_accent",
}

# ── 状态栏/上下文栏样式 ──
CONTEXT_BAR_STYLE = {
    "left_edge": "├",
    "right_edge": "┤",
    "fill": "─",
    "color": "context_bar",
}

# ── 分隔线样式 ──
DIVIDER_STYLE = {
    "char": "─",
    "dot": "·",
    "length": 50,
    "color": "muted",
    "heavy_char": "━",
    "double_char": "═",
}

# ── 面板预设 ──
PANEL_STYLE = {
    "success": {"border": "#3FB950", "title_color": "#3FB950"},
    "error": {"border": "#F85149", "title_color": "#F85149"},
    "info": {"border": "#58A6FF", "title_color": "#58A6FF"},
    "warn": {"border": "#D29922", "title_color": "#D29922"},
    "baihu": {"border": "#E3B341", "title_color": "#E3B341"},
    "qinglong": {"border": "#58A6FF", "title_color": "#58A6FF"},
    "zhuque": {"border": "#F78166", "title_color": "#F78166"},
    "xuanwu": {"border": "#7B85D6", "title_color": "#7B85D6"},
    "qilin": {"border": "#3FB950", "title_color": "#3FB950"},
    "tengshe": {"border": "#DB8A3A", "title_color": "#DB8A3A"},
    "yinglong": {"border": "#A5C8E4", "title_color": "#A5C8E4"},
}


def create_console() -> Console:
    return Console(theme=RETRO_THEME, force_terminal=True)


# ══════════════════════════════════════════════════════════════════════
# Output sink proxy — enables ChatLayout to intercept all console.print()
# ══════════════════════════════════════════════════════════════════════

import threading
import re as _re

_RICH_TAG = _re.compile(r"\[/?[^\]]*\]")


def _strip_rich(text: str) -> str:
    """Strip Rich markup tags, returning plain text."""
    return _RICH_TAG.sub("", text)


class _LayoutSink:
    """Routes console.print() calls to ChatLayout.add_message('system', ...).

    Delegates all non-print attributes (width, height, clear, etc.) to the
    real Console so that ChatLayout can still query terminal dimensions.
    """

    def __init__(self, layout=None, real_console=None):
        self._layout = layout
        self._real_console = real_console
        self._lock = threading.Lock()

    def set_layout(self, layout):
        with self._lock:
            self._layout = layout

    def print(self, *args, **kwargs):
        layout = self._layout
        if layout is None:
            return
        with self._lock:
            for arg in args:
                text = self._to_text(arg)
                if text.strip():
                    layout.add_message("system", text)

    def _to_text(self, arg) -> str:
        """Convert any print argument to plain text."""
        if hasattr(arg, "plain"):
            return arg.plain
        if isinstance(arg, str):
            return _strip_rich(arg)
        # Rich renderable without .plain (Panel, Markdown, Table, Tree, etc.)
        # Capture its terminal output via the real console
        if self._real_console is not None:
            try:
                with self._real_console.capture() as capture:
                    self._real_console.print(arg)
                return capture.get().strip()
            except Exception:
                pass
        return str(arg)

    def print_json(self, data, **kwargs):
        import json as _json
        self.print(_json.dumps(data, indent=2, ensure_ascii=False, default=str))

    def __getattr__(self, name):
        """Delegate unknown attributes (width, height, clear, log, error, etc.)
        to the real Console so terminal queries still work."""
        if self._real_console is not None:
            return getattr(self._real_console, name)
        raise AttributeError(f"_LayoutSink has no attribute '{name}'")


class _ConsoleProxy:
    """Mutable proxy: delegates .print()/.print_json() to current sink.

    Modules that do ``from ui.theme import console`` hold a reference to
    this proxy — not the underlying Console. Swapping the sink via
    :meth:`set_sink` thus affects ALL existing imports at once.
    """

    def __init__(self, console: Console):
        self._real_console = console
        self._sink = console  # default: real console

    def set_sink(self, sink):
        self._sink = sink

    def restore_real_console(self):
        self._sink = self._real_console

    # 上下文管理器协议（Live / Progress 等 Rich 组件依赖）
    def __enter__(self):
        return self._sink.__enter__()

    def __exit__(self, *args):
        return self._sink.__exit__(*args)

    # Delegate all attribute access to current sink
    def __getattr__(self, name):
        return getattr(self._sink, name)


console = _ConsoleProxy(create_console())
