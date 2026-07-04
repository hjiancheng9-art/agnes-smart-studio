"""CRUX TUI v2 — Seven Beasts enhanced theme for prompt_toolkit.

Extends the Night Atelier palette with beast-color semantics and
richer visual hierarchy for the redesigned TUI layout.
"""

from prompt_toolkit.styles import Style

# ── Base palette (from core/theme.py) ──────────────────────────
C = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "surface_alt": "#1f2b47",
    "input_bg": "#0f1629",
    "border": "#3a3a5c",
    "border_active": "#6b5d3e",
    "border_focus": "#d4a853",
    "primary": "#e8e4dd",
    "secondary": "#b8b4ad",
    "muted": "#6b6560",
    "dim": "#4a4640",
    "accent": "#d4a853",       # gold / qilin
    "accent2": "#7a9a6b",      # sage green / xuanwu
    "accent3": "#5b8a9a",      # teal / info
    "error": "#c4554a",
    "warning": "#c4944a",
    "success": "#7a9a6b",
    "info": "#5b8a9a",
    "user": "#8fb8d4",         # soft blue
    "crux": "#d4a853",         # gold
    # ── Seven Beasts ──
    "baihu": "#e0e0e0",       # 白虎 — white/silver (recovery)
    "qinglong": "#5ba3d4",    # 青龙 — azure blue (flow)
    "zhuque": "#d45b5b",      # 朱雀 — vermilion red (watch)
    "xuanwu": "#5b8a6b",      # 玄武 — dark green (defense)
    "qilin": "#d4a853",       # 麒麟 — gold (memory)
    "tengshe": "#9a6bd4",     # 螣蛇 — purple (knowledge)
    "yinglong": "#d49a5b",    # 应龙 — amber (orchestration)
}


def build_style_v2() -> Style:
    """Build the v2 prompt_toolkit Style with beast-color semantics."""
    return Style.from_dict(
        {
            # ── Base ──
            "": f"fg:{C['primary']} bg:{C['bg']}",
            # ── Header bar ──
            "header-bar": f"fg:{C['primary']} bg:{C['surface']}",
            "header-logo": f"fg:{C['qilin']} bold bg:{C['surface']}",
            "header-model": f"fg:{C['qinglong']} italic bg:{C['surface']}",
            "header-latency": f"fg:{C['tengshe']} bg:{C['surface']}",
            "header-sep": f"fg:{C['border_active']} bg:{C['surface']}",
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
            "input-border": f"fg:{C['border']}",
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
            "status-bar-level-a": f"fg:{C['xuanwu']} bold bg:{C['surface']}",
            "status-bar-level-b": f"fg:{C['qinglong']} bold bg:{C['surface']}",
            "status-bar-level-c": f"fg:{C['yinglong']} bold bg:{C['surface']}",
            "status-bar-level-d": f"fg:{C['zhuque']} bold bg:{C['surface']}",
            "status-bar-bar-full": f"fg:{C['xuanwu']} bg:{C['surface']}",
            "status-bar-bar-empty": f"fg:{C['dim']} bg:{C['surface']}",
            # ── Scrollbar ──
            "scrollbar": f"fg:{C['border']} bg:{C['bg']}",
            "scrollbar.arrow": f"fg:{C['muted']} bg:{C['bg']}",
            # ── Completions ──
            "completion-menu": f"bg:{C['surface']} fg:{C['primary']}",
            "completion-menu.completion": f"bg:{C['surface_alt']} fg:{C['secondary']}",
            "completion-menu.completion.current": f"bg:{C['border_active']} fg:{C['qilin']} bold",
        }
    )
