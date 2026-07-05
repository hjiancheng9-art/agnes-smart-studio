"""CRUX TUI v2 — Seven Beasts enhanced theme for prompt_toolkit.

Extends the Night Atelier palette with beast-color semantics and
richer visual hierarchy for the redesigned TUI layout.
"""

from prompt_toolkit.styles import Style

# ── Catppuccin Mocha palette ───────────────────────────────────
C = {
    "bg": "#1E1E2E",
    "surface": "#181825",
    "surface_alt": "#1f1f2f",
    "input_bg": "#11111B",
    "border": "#313244",
    "border_dim": "#45475A",
    "border_active": "#89B4FA",
    "border_focus": "#CBA6F7",
    "primary": "#CDD6F4",
    "secondary": "#BAC2DE",
    "muted": "#7F849C",
    "dim": "#585B70",
    # ── Semantic accents ──
    "accent": "#89B4FA",        # blue — commands
    "accent2": "#A6E3A1",       # green — success
    "accent3": "#94E2D5",       # teal — creative
    "error": "#F38BA8",         # red — quit/error
    "warning": "#FAB387",       # peach — warning
    "success": "#A6E3A1",       # green
    "info": "#89B4FA",          # blue
    "user": "#89B4FA",          # blue
    "crux": "#CBA6F7",          # lavender
    # ── Four-primary system ──
    "blue": "#89B4FA",
    "purple": "#CBA6F7",
    "green": "#A6E3A1",
    "red": "#F38BA8",
    "yellow": "#F9E2AF",
    "teal": "#94E2D5",
    # ── Legacy beast aliases (mapped to new palette) ──
    "baihu": "#CDD6F4",
    "qinglong": "#89B4FA",
    "zhuque": "#F38BA8",
    "xuanwu": "#A6E3A1",
    "qilin": "#F9E2AF",
    "tengshe": "#CBA6F7",
    "yinglong": "#FAB387",
}


def build_style_v2() -> Style:
    """Build the v2 prompt_toolkit Style with beast-color semantics."""
    return Style.from_dict(
        {
            # ── Base ──
            "": f"fg:{C['primary']} bg:{C['bg']}",
            # ── Header bar ──
            "header-bar": f"fg:{C['primary']} bg:{C['surface']}",
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
            "message-thinking": f"fg:{C['info']} italic",
            "message-tool": f"fg:{C['xuanwu']} italic",
            "message-image": f"fg:{C['yinglong']}",
            # ── Thinking panel ──
            "thinking-panel-border": f"fg:{C['border']}",
            "thinking-panel-title": f"fg:{C['tengshe']} bold",
            "thinking-panel-text": f"fg:{C['info']} italic",
            # ── Activity bar ──
            "activity-spinner": f"fg:{C['qinglong']} bold",
            "activity-running": f"fg:{C['qinglong']}",
            "activity-done": f"fg:{C['xuanwu']}",
            "activity-fail": f"fg:{C['zhuque']}",
            "activity-info": f"fg:{C['muted']}",
            "activity-warn": f"fg:{C['warning']}",
            # ── Input area ──
            "input-border": f"fg:{C['border']} bg:{C['bg']}",
            "input-border-active": f"fg:{C['border_focus']}",
            "input-field": f"fg:{C['primary']} bg:{C['input_bg']}",
            "input-prompt": f"fg:{C['qilin']} bold bg:{C['input_bg']}",
            "input-prompt-busy": f"fg:{C['tengshe']} bold bg:{C['input_bg']}",
            "input-cursor": f"fg:{C['accent']}",
            # ── Status bar ──
            "status-bar": f"fg:{C['muted']} bg:{C['surface']}",
            "status-bar-model": f"fg:{C['qilin']} bold bg:{C['surface']}",
            "status-bar-path": f"fg:{C['muted']} bg:{C['surface']}",
            "status-bar-git": f"fg:{C['info']} bg:{C['surface']}",
            "status-bar-context": f"fg:{C['dim']} bg:{C['surface']}",

        # ── Seven beast status bar badges ──
            "status-bar-beast-baihu":    f"fg:{C['baihu']} bold bg:{C['surface']}",
            "status-bar-beast-qinglong": f"fg:{C['qinglong']} bold bg:{C['surface']}",
            "status-bar-beast-zhuque":   f"fg:{C['zhuque']} bold bg:{C['surface']}",
            "status-bar-beast-xuanwu":   f"fg:{C['xuanwu']} bold bg:{C['surface']}",
            "status-bar-beast-qilin":    f"fg:{C['qilin']} bold bg:{C['surface']}",
            "status-bar-beast-tengshe":  f"fg:{C['tengshe']} bold bg:{C['surface']}",
            "status-bar-beast-yinglong": f"fg:{C['yinglong']} bold bg:{C['surface']}",
            "status-bar-level-a": f"fg:{C['xuanwu']} bold bg:{C['surface']}",
            "status-bar-level-b": f"fg:{C['qinglong']} bold bg:{C['surface']}",
            "status-bar-level-c": f"fg:{C['yinglong']} bold bg:{C['surface']}",
            "status-bar-level-d": f"fg:{C['zhuque']} bold bg:{C['surface']}",
            "status-bar-bar-full": f"fg:{C['xuanwu']} bg:{C['surface']}",
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
