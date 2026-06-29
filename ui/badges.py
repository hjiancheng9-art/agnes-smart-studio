"""CRUX Badge system v3 — 盒式徽章 + 上下文栏 + 回复分隔线 + 状态条 + 模式横幅。
v3 升级: 上下文栏(输入框上方) · 回复分隔线 · 输入框底部提示 · Claude Code 风格
Style: Box-style badges with colored borders, icons and labels.
All "what mode am I in" terminal display goes through here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.theme import (
    BADGE_ICONS,
    BADGE_STYLES,
    CHAT_SEPARATOR_STYLE,
    COLORS,
    CONTEXT_BAR_STYLE,
    ICONS,
    INPUT_STYLE,
    LAYOUT,
    console,
)

if TYPE_CHECKING:
    from core.chat import ChatSession
__all__ = [
    "Badge",
    "session_badges",
    "render_badge_line",
    "render_badge_plain",
    "print_reply_header",
    "print_mode_banner",
    "print_route_reason",
    "render_box_badges",
    "render_status_bar",
    "print_welcome_banner",
    # v3 新增
    "render_context_bar",
    "print_context_bar",
    "print_chat_separator",
    "render_input_footer",
    "print_reply_separator",
]


class Badge:
    __slots__ = ("icon", "text", "color", "bg")

    def __init__(self, icon: str, text: str, color: str, bg: str = ""):
        self.icon = icon
        self.text = text
        self.color = color
        self.bg = bg

    def render(self, *, dim: bool = False) -> str:
        style = self.color if not dim else f"dim {self.color}"
        if self.bg:
            return f"[{style} on {self.bg}]{self.icon} {self.text}[/]"
        return f"[{style}]{self.icon} {self.text}[/]"

    def render_box(self) -> str:
        """盒式徽章: [icon LABEL] 带彩色边框和背景."""
        c = self.color
        if self.bg:
            return f"[{c}]┃[/][{c} on {self.bg}] {self.icon} {self.text} [/][{c}]┃[/]"
        return f"[{c}]┃[/] [{c}]{self.icon} {self.text}[/] [{c}]┃[/]"


_PROVIDER_SHORT = {"CRUX AI": "CRUX", "DeepSeek": "DeepSeek", "Zhipu GLM": "GLM"}


def _model_label(session: ChatSession) -> tuple[str, str]:
    model = getattr(session, "model", "") or "unknown"
    try:
        from core.provider import get_model_info, get_provider_name

        info = get_model_info(model)
        label = info.name if info and info.name and info.name != model else model
        provider = get_provider_name(model)
        short = _PROVIDER_SHORT.get(provider, "") if provider != model else ""
        if short and short.lower() not in label.lower():
            label = f"{label} · {short}"
    except Exception:
        label = model
    color = COLORS["muted"] if model in ("agnes-1.5-flash",) else COLORS["badge_model"]
    # 动态从 MODEL_REGISTRY 判定：light tier → 柔和色，pro tier → 强调色
    try:
        from core.provider import get_model_info
        info = get_model_info(model)
        if info:
            color = COLORS["muted"] if info.tier == "light" else COLORS["badge_model"]
    except Exception:
        pass
    return label, color


def session_badges(session: ChatSession | None) -> list[Badge]:
    if session is None:
        return []
    badges: list[Badge] = []
    styles = BADGE_STYLES
    if getattr(session, "code_mode", False):
        s = styles.get("code", {})
        badges.append(Badge(s.get("icon", BADGE_ICONS.get("code", "")), "Code", COLORS.get("badge_code", ""), s.get("bg", "")))
    if getattr(session, "agent_mode", False):
        s = styles.get("agent", {})
        badges.append(Badge(s.get("icon", BADGE_ICONS.get("agent", "")), "Agent", COLORS.get("badge_agent", ""), s.get("bg", "")))
    if getattr(session, "enable_thinking", False):
        s = styles.get("think", {})
        badges.append(Badge(s.get("icon", BADGE_ICONS.get("think", "")), "Think", COLORS.get("badge_think", ""), s.get("bg", "")))
    skill = getattr(session, "active_skill", "")
    if skill:
        icon = BADGE_ICONS.get("skill", "🎬")
        try:
            mgr = getattr(session, "skills", None)
            if mgr is not None:
                sk = mgr._available.get(skill) if hasattr(mgr, "_available") else None
                if sk and getattr(sk, "icon", ""):
                    icon = sk.icon
        except Exception:
            pass
        s = styles.get("skill", {})
        badges.append(Badge(icon, skill, COLORS.get("badge_skill", ""), s.get("bg", "")))
    model_text, model_color = _model_label(session)
    s = styles.get("model", {})
    badges.append(Badge(BADGE_ICONS["model"], model_text, model_color, s.get("bg", "")))
    return badges


def render_badge_line(session: ChatSession | None, *, dim: bool = True) -> str:
    badges = session_badges(session)
    if not badges:
        return ""
    sep = f" [{COLORS['muted']}]{ICONS['info']}[/] "
    return sep.join(b.render(dim=dim) for b in badges)


def render_badge_plain(session: ChatSession | None) -> str:
    badges = session_badges(session)
    if not badges:
        return ""
    sep = LAYOUT["badge_separator"]
    return sep.join(f"{b.icon} {b.text}" for b in badges)


def render_box_badges(session: ChatSession | None) -> str:
    """盒式徽章行 — 彩色边框包裹，更醒目."""
    badges = session_badges(session)
    if not badges:
        return ""
    return "  ".join(b.render_box() for b in badges)


def render_status_bar(session: ChatSession | None) -> str:
    """状态条: [模式徽章] ◆ 模型 · 供应商 · 工具数."""
    badges = session_badges(session)
    if not badges:
        return ""
    parts = []
    for b in badges:
        parts.append(f"[{b.color}]{b.icon}[/] [{b.color}]{b.text}[/]")
    return f"  [{COLORS['muted']}]┌─[/] " + f" [{COLORS['muted']}]◆[/] ".join(parts) + f" [{COLORS['muted']}]─┐[/]"


def print_reply_header(session: ChatSession | None) -> None:
    line = render_badge_line(session, dim=True)
    if line:
        console.print(f"  {line}")


def print_mode_banner(session: ChatSession | None) -> None:
    badges = session_badges(session)
    if not badges:
        return
    sep = f" [{COLORS['muted']}]{ICONS['info']}[/] "
    line = sep.join(b.render(dim=False) for b in badges)
    console.print(f"\n  [{COLORS['primary']}]{ICONS['primary']}[/] {line}\n")


def print_route_reason(reason: str) -> None:
    if reason:
        console.print(f"  [{COLORS['muted']}]{ICONS['route']} {reason}[/]")


def print_welcome_banner(session: ChatSession | None = None):
    """启动欢迎横幅 — 模式切换后调用."""
    from rich.panel import Panel

    badge_line = render_box_badges(session) if session else ""
    body = "  [bold]◆ Studio[/]  [dim]七兽归位 · 魂盏交汇[/]"
    if badge_line:
        body += f"\n\n  {badge_line}"
    console.print(Panel(body, border_style=COLORS["primary"], padding=(1, 2)))


# ═══════════════════════════════════════════════════════════════
#  v3 — 上下文栏 / 回复分隔线 / 输入框架
# ═══════════════════════════════════════════════════════════════


def render_context_bar(session: ChatSession | None, width: int = 60) -> str:
    """渲染输入框上方的上下文栏。

    格式: ├─ ⚡ Code · ◎ model · ✦ skill ──────────┤

    参考 Claude Code / Copilot CLI 的紧凑状态行风格。
    """
    badges = session_badges(session)
    if not badges:
        return ""

    # 构建徽章文本（纯文本，不含 Rich markup 宽度计算）
    parts = []
    for b in badges:
        parts.append(f"[{b.color}]{b.icon} {b.text}[/]")
    badge_line = f" [{COLORS['muted']}]·[/] ".join(parts)

    # 计算填充
    left = CONTEXT_BAR_STYLE["left_edge"]
    right = CONTEXT_BAR_STYLE["right_edge"]
    fill_char = CONTEXT_BAR_STYLE["fill"]
    color = CONTEXT_BAR_STYLE["color"]

    # 简化：使用固定宽度，不精确计算 Rich markup 长度
    # 让终端自然截断
    inner = f" {badge_line} "
    bar = f"[{color}]{left}{fill_char}[/] {badge_line} [{color}]{fill_char * 3}{right}[/]"

    return bar


def print_context_bar(session: ChatSession | None, width: int = 60) -> None:
    """打印输入框上方的上下文栏。"""
    bar = render_context_bar(session, width)
    if bar:
        console.print(f"  {bar}")


def print_chat_separator() -> None:
    """打印聊天分隔线 — AI 回复与下一个输入框之间的视觉断点。

    参考 Claude Code 的细线分隔风格。
    """
    c = CHAT_SEPARATOR_STYLE["char"]
    ln = CHAT_SEPARATOR_STYLE["length"]
    color = CHAT_SEPARATOR_STYLE["color"]
    console.print(f"  [{color}]{c * ln}[/]")


def print_reply_separator() -> None:
    """打印回复开始分隔线 — 输入框与 AI 回复之间的视觉断点。

    比 chat_separator 更淡，带一个小菱形装饰。
    """
    c = CHAT_SEPARATOR_STYLE["char"]
    ln = CHAT_SEPARATOR_STYLE["length"] // 3
    d = CHAT_SEPARATOR_STYLE["dot_char"]
    color = CHAT_SEPARATOR_STYLE["color"]
    accent = CHAT_SEPARATOR_STYLE["accent_color"]
    console.print(f"  [{color}]{c * ln}[/][{accent}]{d}[/][{color}]{c * ln}[/]")


def render_input_footer() -> str:
    """渲染输入框底部提示行。

    格式: ╰─ Enter 发送 · Alt+Enter 换行 · Ctrl+C 退出 ─╯
    参考 Claude Code / Copilot CLI 的底部提示栏。
    """
    left = INPUT_STYLE["frame_bottom_left"]
    right = INPUT_STYLE["frame_bottom_right"]
    fill = INPUT_STYLE["frame_horizontal"]
    color = COLORS["input_frame_bottom"]
    hint_color = COLORS["input_hint"]

    hints = (
        f"[{hint_color}]Enter[/] 发送  ·  "
        f"[{hint_color}]Alt+Enter[/] 换行  ·  "
        f"[{hint_color}]Ctrl+C[/] 退出  ·  "
        f"[{hint_color}]\"\"\"[/] 多行"
    )
    return f"[{color}]{left}{fill}[/] {hints} [{color}]{fill * 2}{right}[/]"


def print_input_footer() -> None:
    """打印输入框底部提示行。"""
    console.print(f"  {render_input_footer()}")
