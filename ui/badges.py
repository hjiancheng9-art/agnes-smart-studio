"""CRUX Badge system v2 — 盒式徽章 + 状态条 + 模式横幅。
v2 升级: 盒式徽章(彩色边框+图标+标签) · 状态条 · 模式切换横幅 · 路由提示
Style: Box-style badges with colored borders, icons and labels.
All "what mode am I in" terminal display goes through here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.theme import BADGE_ICONS, COLORS, ICONS, LAYOUT, console

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
]


class Badge:
    __slots__ = ("icon", "text", "color")

    def __init__(self, icon: str, text: str, color: str):
        self.icon = icon
        self.text = text
        self.color = color

    def render(self, *, dim: bool = False) -> str:
        style = self.color if not dim else f"dim {self.color}"
        return f"[{style}]{self.icon} {self.text}[/]"

    def render_box(self) -> str:
        """盒式徽章: [icon LABEL] 带彩色边框."""
        c = self.color
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
    color = COLORS["muted"] if model in ("agnes-1.5-flash",) else "#26A69A"
    # 动态从 MODEL_REGISTRY 判定：light tier → 柔和色，pro tier → 强调色
    try:
        from core.provider import get_model_info
        info = get_model_info(model)
        if info:
            color = COLORS["muted"] if info.tier == "light" else "#26A69A"
    except Exception:
        pass
    return label, color


def session_badges(session: ChatSession | None) -> list[Badge]:
    if session is None:
        return []
    badges: list[Badge] = []
    if getattr(session, "code_mode", False):
        badges.append(Badge(BADGE_ICONS["code"], "Code", COLORS["badge_code"]))
    if getattr(session, "agent_mode", False):
        badges.append(Badge(BADGE_ICONS["agent"], "Agent", COLORS["badge_agent"]))
    if getattr(session, "enable_thinking", False):
        badges.append(Badge(BADGE_ICONS["think"], "Think", COLORS["badge_think"]))
    skill = getattr(session, "active_skill", "")
    if skill:
        icon = BADGE_ICONS.get("skill", "🎬")
        try:
            mgr = getattr(session, "skills", None)
            if mgr is not None:
                s = mgr._available.get(skill) if hasattr(mgr, "_available") else None
                if s and getattr(s, "icon", ""):
                    icon = s.icon
        except Exception:
            pass
        badges.append(Badge(icon, skill, COLORS["badge_skill"]))
    model_text, model_color = _model_label(session)
    badges.append(Badge(BADGE_ICONS["model"], model_text, model_color))
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
