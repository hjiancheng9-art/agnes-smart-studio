"""CRUX TUI v2 — Seven Beasts enhanced theme for prompt_toolkit.

Extends the Catppuccin Mocha palette with beast-color semantics and
richer visual hierarchy for the redesigned TUI layout.
"""

from prompt_toolkit.styles import Style
from ui.theme_atelier import NIGHT_ATELIER as C


def build_style_v2() -> Style:
    """Build the v2 prompt_toolkit Style with beast-color semantics."""
    return Style.from_dict(
        {
            # ── Base ──
            "": f"fg:{C['primary']} bg:{C['bg']}",
            # ── Header bar ──
            "header-bar": f"fg:{C['primary']} bg:{C['surface']}",
            "header-error": "bg:#1e1e2e fg:#f38ba8 bold",
            "dashboard": "bg:#1e1e2e fg:#cdd6f4",
            "header-logo": f"fg:{C['yellow']} bold bg:{C['surface']}",
            "header-model": f"fg:{C['blue']} italic bg:{C['surface']}",
            "header-latency": f"fg:{C['purple']} bg:{C['surface']}",
            "header-sep": f"fg:{C['border_dim']} bg:{C['surface']}",
            # ── Welcome screen ──
            "welcome-border": f"fg:{C['border']}",
            "welcome-title": f"fg:{C['qilin']} bold",
            "welcome-text": f"fg:{C['dim']} italic",
            "welcome-tagline": f"fg:{C['yinglong']} bold",
            "welcome-key": f"fg:{C['qinglong']}",
            "welcome-desc": f"fg:{C['muted']} italic",
            "welcome-session": f"fg:{C['dim']}",
            # ── Pixel logo ──
            "pixel-bright": f"fg:{C['qilin']} bold",
            "pixel-dim": f"fg:{C['border_active']}",
            # ── Message area ──
            "message-area": f"bg:{C['bg']}",
            "message-user": f"fg:{C['user']} bold",
            "message-crux": f"fg:{C['crux']}",
            "message-crux-border": f"fg:{C['accent']}",
            "message-info": f"fg:{C['muted']} italic",
            "message-error": f"fg:{C['zhuque']}",
            "message-thinking": f"fg:{C['teal']} italic",
            "message-tool": f"fg:{C['green']} italic",
            "message-timestamp": f"fg:{C['dim']} italic",
            # ── Activity bar ──
            "activity-bar": f"bg:{C['surface']}",
            "activity-bar-label": f"fg:{C['dim']} bold italic bg:{C['surface']}",
            "activity-working": f"fg:{C['blue']} bg:{C['surface']}",
            "activity-ok": f"fg:{C['green']} bg:{C['surface']}",
            "activity-fail": f"fg:{C['zhuque']}",
            "activity-info": f"fg:{C['muted']}",
            "activity-warn": f"fg:{C['warning']}",
            # ── Input area ──
            "input-area": f"bg:{C['surface']}",
            "input-prompt": f"fg:{C['qilin']} bold bg:{C['surface']}",
            "input-text": f"fg:{C['primary']} bg:{C['surface']}",
            # ── Status bar ──
            "status-bar": f"bg:{C['surface']}",
            "status-bar-model": f"fg:{C['blue']} italic bg:{C['surface']}",
            "status-bar-mode": f"fg:{C['purple']} bold bg:{C['surface']}",
            "status-bar-tokens": f"fg:{C['dim']} bg:{C['surface']}",
            "status-bar-time": f"fg:{C['dim']} italic bg:{C['surface']}",
            "status-bar-context": f"fg:{C['dim']} bg:{C['surface']}",
            # ── Seven beast status bar badges ──
            "status-bar-beast-baihu":    f"fg:{C['baihu']} bold bg:{C['surface']}",
            "status-bar-beast-qinglong": f"fg:{C['qinglong']} bold bg:{C['surface']}",
            "status-bar-beast-zhuque":   f"fg:{C['zhuque']} bold bg:{C['surface']}",
            "status-bar-beast-xuanwu":   f"fg:{C['xuanwu']} bold bg:{C['surface']}",
            "status-bar-beast-qilin":    f"fg:{C['qilin']} bold bg:{C['surface']}",
            "status-bar-beast-tengshe":  f"fg:{C['tengshe']} bold bg:{C['surface']}",
            "status-bar-beast-yinglong": f"fg:{C['yinglong']} bold bg:{C['surface']}",
            # ── Status bar gauges ──
            "status-bar-bar-full": f"fg:{C['success']} bg:{C['surface']}",
            "status-bar-bar-empty": f"fg:{C['dim']} bg:{C['surface']}",
            # ── Scrollbar — hidden ──
            "scrollbar": "",
            "scrollbar.background": "",
            "scrollbar.button": "",
            "scrollbar.arrow": "",
            # ── Completions ──
            "completion-menu": f"bg:{C['surface']} fg:{C['primary']}",
            "completion-menu.completion": f"bg:{C['surface_alt']} fg:{C['secondary']}",
            "completion-menu.completion.current": f"bg:{C['border_active']} fg:{C['qilin']} bold",
        }
    )
