"""CRUX TUI v2 — Seven Beasts enhanced theme for prompt_toolkit.

Extends the Night Atelier palette with beast-color semantics and
richer visual hierarchy for the redesigned TUI layout.
"""

from prompt_toolkit.styles import Style

from ui.theme_atelier import NIGHT_ATELIER as C


def build_style_v2() -> Style:
    """Build the v2 prompt_toolkit Style with beast-color semantics."""
    return Style.from_dict(
        {
            # ── Status bar layout ──
            "status-bar": f"bg:{C['surface']} fg:{C['primary']}",
            "status-bar.version": f"fg:{C['secondary']}",
            "status-bar.beast-baihu": f"fg:{C['baihu']}",
            "status-bar.beast-qinglong": f"fg:{C['qinglong']}",
            "status-bar.beast-zhuque": f"fg:{C['zhuque']}",
            "status-bar.beast-xuanwu": f"fg:{C['xuanwu']}",
            "status-bar.beast-qilin": f"fg:{C['qilin']}",
            "status-bar.beast-tengshe": f"fg:{C['tengshe']}",
            "status-bar.beast-yinglong": f"fg:{C['yinglong']}",
            "status-bar.sep": f"fg:{C['border']}",
            "status-bar.pulse": f"fg:{C['zhuque']}",
            "status-bar.git": f"fg:{C['qilin']}",
            "status-bar.ctx-bg": f"bg:{C['surface_alt']}",
            "status-bar.ctx-fg": f"fg:{C['primary']}",
            "status-bar.label": f"fg:{C['secondary']}",
            # ── Header ──
            "header": f"bg:{C['surface']} fg:{C['primary']}",
            "header-sep": f"fg:{C['border']}",
            "header-crux": f"fg:{C['qinglong']} bold",
            "header-model": f"bg:{C['surface_alt']} fg:{C['secondary']}",
            "header-latency": f"fg:{C['zhuque']}",
            "header-error": f"fg:{C['zhuque']} bold",
            "header-success": f"fg:{C['baihu']} bold",
            # ── Input bar ──
            "input-bar": f"bg:{C['surface']}",
            "input-border": f"fg:{C['border']}",
            "input-prompt": f"fg:{C['baihu']} bold",
            "input-cursor": f"bg:{C['border_active']} fg:{C['surface']} bold",
            "hint-bar": f"bg:{C['surface_alt']} fg:{C['muted']}",
            # ── Message area ──
            "message-area": f"bg:{C['bg']} fg:{C['primary']}",
            "message-user": f"fg:{C['qinglong']} bold",
            "message-crux": f"fg:{C['baihu']}",
            "message-info": f"fg:{C['secondary']} italic",
            "message-error": f"fg:{C['zhuque']} bold",
            "message-tool": f"fg:{C['tengshe']}",
            "message-streaming": f"fg:{C['yinglong']} italic",
            # ── Activity area ──
            "activity-running": f"fg:{C['zhuque']}",
            "activity-done": f"fg:{C['baihu']}",
            "activity-fail": f"fg:{C['zhuque']} bold",
            "activity-warn": f"fg:{C['qilin']}",
            "activity-info": f"fg:{C['secondary']}",
            # ── Thinking panel ──
            "thinking": f"bg:{C['surface_alt']} fg:{C['primary']} italic",
            # ── Screens ──
            "screen": f"bg:{C['bg']} fg:{C['primary']}",
            "screen-title": f"fg:{C['baihu']} bold",
            "screen-sep": f"fg:{C['border']}",
            # ── Scrollbar / cursor ──
            "scrollbar.background": "",
            "scrollbar.button": "",
            "scrollbar.arrow": "",
            # ── Completions ──
            "completion-menu": f"bg:{C['surface']} fg:{C['primary']}",
            "completion-menu.completion": f"bg:{C['surface_alt']} fg:{C['secondary']}",
            "completion-menu.completion.current": f"bg:{C['border_active']} fg:{C['qilin']} bold",
            # ── Panel styles ──
            "panel_title": "bold",
            "muted": "ansibrightblack",
            "incident-p0": "ansired bold",
            "incident-p1": "ansiyellow",
            "incident-p2": "ansiblue",
            "run-success": "ansigreen",
            "run-warn": "ansiyellow",
            "run-error": "ansired bold",
            "route-success": "ansigreen",
            "route-fail": "ansired",
            "route-skip": "ansibrightblack",
        
            "provider-ok": "ansigreen",
            "provider-warn": "ansiyellow",
            "provider-open": "ansired bold",
            "provider-half-open": "ansimagenta",
    }
    )
