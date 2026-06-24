"""CRUX Badge system — unified session state visualization.

The sole legal converter from session state → colored tag stream.
All "what mode am I in" terminal display goes through here.

Style: Organic badge stream — each segment independently colored, separated by ∘
  🧬 Agent  ∘  ✨ Think  ∘  🎬 showrunner  ∘  🌊 CRUX 2.0 Flash · CRUX

Entry points:
- ui/mixins/shared.py:_mode_hint()      → prompt suffix (plain text badge)
- ui/mixins/shared.py:_stream_chat()     → per-reply dim badge header
- ui/mixins/engineering.py:_chat_plan()  → /plan standalone render path
- Various toggle handlers                 → post-switch prominent banner

Rendering contract: this module only prints plain text lines, never touching
StreamingRenderer's transient Live or single-commit-point (commit). Badge lines
are printed before renderer.start(), immune to transient preview interference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.theme import BADGE_ICONS, COLORS, ICONS, LAYOUT, console

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = [
    'Badge',
    'session_badges',
    'render_badge_line',
    'render_badge_plain',
    'print_reply_header',
    'print_mode_banner',
    'print_route_reason',
]


# ── Data model ───────────────────────────────────────────────

class Badge:
    """Single state tag: icon + text + color."""

    __slots__ = ('icon', 'text', 'color')

    def __init__(self, icon: str, text: str, color: str):
        self.icon = icon
        self.text = text
        self.color = color

    def render(self, *, dim: bool = False) -> str:
        """Return Rich markup fragment, e.g. '[magenta]🧬 Agent[/]'."""
        style = self.color if not dim else f"dim {self.color}"
        return f"[{style}]{self.icon} {self.text}[/]"


# ── Provider short-name map ──────────────────────────────

_PROVIDER_SHORT = {
    "CRUX AI": "CRUX",
    "DeepSeek": "DeepSeek",
    "SiliconFlow": "SiliconFlow",
    "Moonshot": "Kimi",
}


def _model_label(session: ChatSession) -> tuple[str, str]:
    """Return (model display text, color). Model name + provider short (dedup)."""
    model = getattr(session, 'model', '') or 'unknown'
    try:
        from core.provider import get_model_info, get_provider_name
        info = get_model_info(model)
        label = (info.name if info and info.name and info.name != model else model)
        provider = get_provider_name(model)
        short = _PROVIDER_SHORT.get(provider, "") if provider != model else ""
        if short and short.lower() not in label.lower():
            label = f"{label} · {short}"
    except Exception:
        label = model
    # Default model → muted, pro/agent model → teal (organic feel)
    color = COLORS['muted'] if model in ('agnes-1.5-flash',) else "#26A69A"
    return label, color


# ── Core: session → badge list ────────────────────────────

def session_badges(session: ChatSession | None) -> list[Badge]:
    """Generate ordered badge list from session state.

    Fixed order: mode(code/agent) → think → skill → model/provider.
    None or menu (no session) → empty list.
    """
    if session is None:
        return []

    badges: list[Badge] = []

    # Mode (mutually exclusive display: code and agent are independent toggles)
    if getattr(session, 'code_mode', False):
        badges.append(Badge(BADGE_ICONS["code"], "Code", COLORS['primary']))
    if getattr(session, 'agent_mode', False):
        badges.append(Badge(BADGE_ICONS["agent"], "Agent", COLORS['accent']))

    # Deep thinking
    if getattr(session, 'enable_thinking', False):
        badges.append(Badge(BADGE_ICONS["think"], "Think", COLORS['warning']))

    # Loaded skill (prefer skill's own icon)
    skill = getattr(session, 'active_skill', '')
    if skill:
        icon = BADGE_ICONS.get("skill", "🎬")
        try:
            mgr = getattr(session, 'skills', None)
            if mgr is not None:
                s = mgr._available.get(skill) if hasattr(mgr, '_available') else None
                if s and getattr(s, 'icon', ''):
                    icon = s.icon
        except Exception:
            pass
        badges.append(Badge(icon, skill, COLORS['success']))

    # Model / provider (always shown)
    model_text, model_color = _model_label(session)
    badges.append(Badge(BADGE_ICONS["model"], model_text, model_color))

    return badges


# ── Render entry points ───────────────────────────────────

def render_badge_line(session: ChatSession | None, *, dim: bool = True) -> str:
    """Return full badge line as Rich markup string (for console.print).

    Segments separated by badge_separator, overall optionally dimmed.
    """
    badges = session_badges(session)
    if not badges:
        return ""
    sep = f" [{COLORS['muted']}]{ICONS['info']}[/] "
    return sep.join(b.render(dim=dim) for b in badges)


def render_badge_plain(session: ChatSession | None) -> str:
    """Return plain-text badge line (for prompt_toolkit input prompt).

    prompt_toolkit doesn't parse Rich markup, giving it Rich tags would
    show '[#26A69A]🌊...' as raw text. Here we output clean
    '🧬 Agent  ∘  ✨ Think  ∘  🌊 CRUX 2.0 Flash' plain text.
    """
    badges = session_badges(session)
    if not badges:
        return ""
    sep = LAYOUT["badge_separator"]
    return sep.join(f"{b.icon} {b.text}" for b in badges)


def print_reply_header(session: ChatSession | None) -> None:
    """Print dim badge line above each AI reply.

    Called before StreamingRenderer.start() — no transient Live preview,
    plain console.print directly committed, outside rendering contract.
    """
    line = render_badge_line(session, dim=True)
    if line:
        console.print(line)


def print_mode_banner(session: ChatSession | None) -> None:
    """Print prominent badge banner on mode switch (non-dim).

    Lets user see new state immediately after toggle / load_skill / switch_model.
    """
    badges = session_badges(session)
    if not badges:
        return
    sep = f" [{COLORS['muted']}]{ICONS['info']}[/] "
    line = sep.join(b.render(dim=False) for b in badges)
    console.print(f"  {line}")


def print_route_reason(reason: str) -> None:
    """Display routing decision reason (dim, unobtrusive).

    Called after print_reply_header, so user knows why router switched model.
    Effect: '  〜 multi-file refactor → switch to DeepSeek (1M context deep reasoning)'
    """
    if reason:
        console.print(f"  [{COLORS['muted']}]{ICONS['route']} {reason}[/]")
