"""CRUX TUI v2 — Seven Beasts + Four Palette theme system for prompt_toolkit.

Modes (accessibility):
    normal         -- Full color
    high_contrast  -- High contrast for color-blind accessibility
    mono           -- Monochrome/ASCII-safe for SSH/minimal terminals

Palettes (aesthetic, from ui/theme.py):
    blade         -- 玄青底 + 紫刃青脉 · 平时如刀出事成阵 (DEFAULT)
    polar_night   -- 深黑底 + 霓虹青蓝 · 冷酷科技感
    lava          -- 炭黑底 + 橙红琥珀 · 温热高能感
    jade          -- 墨绿底 + 翠青金线 · 自然沉静感

Usage:
    build_style_v2("blade")          → palette theme
    build_style_v2("polar_night")    → palette theme
    build_style_v2("normal")         → mode (Catppuccin Mocha)
    build_style_v2("high_contrast")  → mode
    build_style_v2("mono")           → mode
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

# ══════════════════════════════════════════════════════════════
# Four Palette Definitions (from ui/theme.py)
# ══════════════════════════════════════════════════════════════

POLAR_NIGHT = {
    "name": "极夜 Polar Night",
    "desc": "极冰底 + 霓虹青蓝 · 冷酷科技感",
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#1C3038",
    "primary": "#E8F2FA",
    "secondary": "#A8C8D8",
    "muted": "#6B94A4",
    "dim": "#3D5A68",
    "accent": "#00E5FF",
    "accent2": "#06D6A0",
    "error": "#FF4068",
    "warning": "#FFC060",
    "success": "#06D6A0",
    "info": "#00D4F0",
    "user": "#70C0FF",
    "crux": "#9966FF",
    "thinking": "#B890FF",
    "tool": "#FFB070",
    "code_bg": "#11111B",
}

LAVA = {
    "name": "熔岩 Lava",
    "desc": "余烬底 + 琥珀熔金 · 温热高能感",
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#3C2E24",
    "primary": "#F2E8D8",
    "secondary": "#D4C8B0",
    "muted": "#AA9070",
    "dim": "#6B5840",
    "accent": "#FF7847",
    "accent2": "#F7C948",
    "error": "#F24D60",
    "warning": "#FFB060",
    "success": "#84D060",
    "info": "#FF9C60",
    "user": "#FFB080",
    "crux": "#D8A8FF",
    "thinking": "#D0A0FF",
    "tool": "#FFC880",
    "code_bg": "#11111B",
}

JADE = {
    "name": "翡翠 Jade",
    "desc": "密林底 + 翠青金线 · 自然沉静感",
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#24302C",
    "primary": "#DCF0E4",
    "secondary": "#A8C8B4",
    "muted": "#6B9880",
    "dim": "#3E604C",
    "accent": "#10F080",
    "accent2": "#26C6DA",
    "error": "#FF5C5C",
    "warning": "#FFD848",
    "success": "#60F0A0",
    "info": "#18E888",
    "user": "#58D8C0",
    "crux": "#C098F0",
    "thinking": "#B0A0E0",
    "tool": "#E8C878",
    "code_bg": "#11111B",
}

BLADE = {
    "name": "刀阵 Blade Formation",
    "desc": "锻钢底 + 紫刃青脉 · 平时如刀出事成阵",
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#2A2C3C",
    "primary": "#E4ECF8",
    "secondary": "#A4B4D0",
    "muted": "#8B90B0",
    "dim": "#535B6C",
    "accent": "#8C6CFC",
    "accent2": "#00D4AA",
    "error": "#FF7575",
    "warning": "#FFC048",
    "success": "#00D4AA",
    "info": "#C0A8FF",
    "user": "#B0C4F0",
    "crux": "#C0A8FF",
    "thinking": "#A8B8FF",
    "tool": "#FFB078",
    "code_bg": "#11111B",
}

NEON_GALAXY = {
    "name": "霓虹星河 Neon Galaxy",
    "desc": "星云底 + 霓虹虹彩 · 缤纷高饱和",
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#302840",
    "primary": "#ECE4F8",
    "secondary": "#C4B8E8",
    "muted": "#9488C0",
    "dim": "#5C5480",
    "accent": "#FF3D75",
    "accent2": "#00E5FF",
    "error": "#FF5575",
    "warning": "#FFE050",
    "success": "#39FFA0",
    "info": "#68C4FF",
    "user": "#FF90B0",
    "crux": "#D060FF",
    "thinking": "#B870FF",
    "tool": "#FFB060",
    "code_bg": "#11111B",
}

PALETTES = {
    "blade": BLADE,
    "polar_night": POLAR_NIGHT,
    "lava": LAVA,
    "jade": JADE,
    "neon": NEON_GALAXY,
}

_DEFAULT_PALETTE = "blade"


# ══════════════════════════════════════════════════════════════
# Style builders
# ══════════════════════════════════════════════════════════════


def _build_palette_style(palette: dict) -> Style:
    """Build a prompt_toolkit Style from a color palette dict.

    Maps all 17 semantic color slots from ui/theme.py onto the
    actual class names used by tui_v2.py FormattedText renderers.
    """
    C = palette  # shorthand

    return Style(
        [
            # ── Message area ──
            ("message-area", f"bg:{C['bg']}"),
            ("message-user", f"fg:{C['user']} bold"),
            ("message-crux", f"fg:{C['crux']}"),
            ("message-info", f"fg:{C['muted']} italic"),
            ("message-error", f"fg:{C['error']}"),
            ("message-tool", f"fg:{C['accent2']} italic"),
            # ── Header bar ──
            ("header-bar", f"fg:{C['accent']} bg:{C['surface']} bold"),
            ("header-logo", f"fg:{C['accent']} bg:{C['surface']}"),
            ("header-model", f"fg:{C['crux']} bold bg:{C['surface']}"),
            ("header-sep", f"fg:{C['dim']} bg:{C['surface']}"),
            ("header-latency", f"fg:{C['muted']} bg:{C['surface']}"),
            # ── Section headers (分区独立配色) ──
            ("header-thinking", f"fg:{C['thinking']} bg:{C['surface']} bold"),
            ("header-status", f"fg:{C['accent2']} bg:{C['surface']} bold"),
            ("header-tool", f"fg:{C['tool']} bg:{C['surface']} bold"),
            ("header-comfyui", f"fg:{C['success']} bg:{C['surface']} bold"),
            ("header-system", f"fg:{C['crux']} bg:{C['surface']} bold"),
            ("header-error", f"fg:{C['error']} bg:{C['surface']}"),
            # ── Status bar ──
            ("status-bar", f"fg:{C['muted']} bg:{C['surface']}"),
            ("status-bar-model", f"fg:{C['crux']} bold bg:{C['surface']}"),
            ("status-bar-path", f"fg:{C['muted']} bg:{C['surface']}"),
            ("status-bar-git", f"fg:{C['info']} bg:{C['surface']}"),
            ("status-bar-context", f"fg:{C['dim']} bg:{C['surface']}"),
            ("status-err", f"fg:{C['error']} bold"),
            ("status-warn", f"fg:{C['warning']}"),
            # ── Status bar: beast sigils (七兽) ──
            ("status-bar-beast-qinglong", f"fg:{C['accent']} bg:{C['surface']}"),
            ("status-bar-beast-zhuque", f"fg:{C['warning']} bg:{C['surface']}"),
            ("status-bar-beast-xuanwu", f"fg:{C['info']} bg:{C['surface']}"),
            ("status-bar-beast-baihu", f"fg:{C['success']} bg:{C['surface']}"),
            ("status-bar-beast-qilin", f"fg:{C['crux']} bg:{C['surface']}"),
            ("status-bar-beast-tengshe", f"fg:{C['accent2']} bg:{C['surface']}"),
            ("status-bar-beast-yinglong", f"fg:{C['primary']} bg:{C['surface']}"),
            # ── Status bar: level indicators ──
            ("status-bar-level-a", f"fg:{C['success']} bg:{C['surface']} bold"),
            ("status-bar-level-b", f"fg:{C['warning']} bg:{C['surface']} bold"),
            ("status-bar-level-c", f"fg:{C['error']} bg:{C['surface']} bold"),
            ("status-bar-level-d", f"fg:{C['muted']} bg:{C['surface']}"),
            # ── Input area ──
            ("input-border", f"fg:{C['border']}"),
            ("input-field", f"fg:{C['primary']} bg:{C['input_bg']}"),
            ("text-area", f"fg:{C['primary']} bg:{C['input_bg']}"),
            ("text-area.prompt", f"fg:{C['accent']} bold bg:{C['input_bg']}"),
            ("text-area.cursor", f"fg:{C['input_bg']} bg:{C['accent']}"),
            # ── Activity log ──
            ("activity-info", f"fg:{C['info']}"),
            ("activity-warn", f"fg:{C['warning']}"),
            ("activity-error", f"fg:{C['error']} bold"),
            ("activity-success", f"fg:{C['success']}"),
            ("activity-done", f"fg:{C['success']}"),
            ("activity-fail", f"fg:{C['error']} bold"),
            ("activity-running", f"fg:{C['accent2']}"),
            # ── Thinking panel ──
            ("thinking-panel-border", f"fg:{C['border']}"),
            ("thinking-panel-text", f"fg:{C['info']} italic"),
            # ── Generic states ──
            ("dim", f"fg:{C['dim']}"),
            ("info", f"fg:{C['info']}"),
            ("error", f"fg:{C['error']} bold"),
            ("line-number", f"fg:{C['dim']}"),
            # ── Code block ──
            ("code-block", f"bg:{C['code_bg']}"),
            # ── Welcome ──
            ("welcome-desc", f"fg:{C['muted']} italic"),
            # ── App root background (covers HSplit container gaps) ──
            ("app", f"bg:{C['bg']}"),
            # ── Base chrome (fallback for all unclassified elements) ──
            ("", f"fg:{C['primary']} bg:{C['bg']}"),
            ("scrollbar", f"fg:{C['border']} bg:{C['bg']}"),
            ("scrollbar.arrow", f"fg:{C['muted']} bg:{C['bg']}"),
        ]
    )


# ══════════════════════════════════════════════════════════════
# Legacy mode styles (Catppuccin Mocha — kept for fallback)
# ══════════════════════════════════════════════════════════════

_MOCHA_BASE = None


def _get_mocha_base() -> Style:
    """Lazy-init the Catppuccin Mocha base (shared across all modes)."""
    global _MOCHA_BASE
    if _MOCHA_BASE is None:
        _MOCHA_BASE = Style(
            [
                ("window", "bg:#1e1e2e"),
                ("dialog", "bg:#1e1e2e border:#313244"),
                ("dialog.body", "bg:#181825"),
                ("dialog.title", "bg:#313244 fg:#cdd6f4 bold"),
                ("scrollbar.area", "bg:#1e1e2e"),
                ("scrollbar.button", "bg:#585b70"),
                ("line", "fg:#313244"),
                ("button", "fg:#cdd6f4 bg:#313244"),
                ("button.focused", "fg:#1e1e2e bg:#89b4fa"),
                ("text-area", "bg:#1e1e2e fg:#cdd6f4"),
                ("text-area.prompt", "fg:#89b4fa"),
                ("text-area.cursor", "fg:#1e1e2e bg:#89b4fa"),
            ]
        )
    return _MOCHA_BASE


def _build_normal_style() -> Style:
    """Full Catppuccin Mocha with Seven Beasts semantic colors."""
    from prompt_toolkit.styles import merge_styles

    beast_style = Style(
        [
            ("msg-user", "fg:#f2cdcd bold"),
            ("msg-assistant", "fg:#89b4fa"),
            ("msg-system", "fg:#fab387"),
            ("msg-error", "fg:#f5c2e7 bold"),
            ("msg-success", "fg:#a6e3a1"),
            ("msg-thinking", "fg:#cba6f7 italic"),
            ("msg-info", "fg:#94e2d5"),
            # ── message_pane.py 使用的 message-* 命名 (alias) ──
            ("message-user", "fg:#f2cdcd bold"),
            ("message-crux", "fg:#89b4fa"),
            ("message-system", "fg:#fab387"),
            ("message-error", "fg:#f5c2e7 bold"),
            ("message-success", "fg:#a6e3a1"),
            ("message-thinking", "fg:#cba6f7 italic"),
            ("message-info", "fg:#94e2d5"),
            ("message-tool", "fg:#a6e3a1 italic"),
            # ── Container backgrounds ──
            ("message-area", "bg:#1e1e2e"),
            ("input-field", "fg:#cdd6f4 bg:#1e1e2e"),
            ("input-border", "fg:#313244"),
            ("header-bar", "fg:#89b4fa bg:#181825 bold"),
            ("header-bar bold", "fg:#89b4fa bg:#181825 bold"),
            # ── Section headers (分区独立配色) ──
            ("header-thinking", "fg:#cba6f7 bg:#1e1e2e bold"),
            ("header-status", "fg:#94e2d5 bg:#1e1e2e bold"),
            ("header-tool", "fg:#fab387 bg:#1e1e2e bold"),
            ("header-comfyui", "fg:#a6e3a1 bg:#1e1e2e bold"),
            ("header-system", "fg:#89b4fa bg:#1e1e2e bold"),
            ("separator", "fg:#313244"),
            ("status-bar", "fg:#a6adc8 bg:#181825"),
            ("status-bar.key", "fg:#89b4fa bold"),
            ("status-bar.val", "fg:#cdd6f4"),
            ("thinking", "fg:#cba6f7 bg:#1e1e2e italic"),
            ("thinking-header", "fg:#cba6f7 bg:#1e1e2e bold"),
            ("activity-info", "fg:#89b4fa"),
            ("activity-warn", "fg:#fab387"),
            ("activity-error", "fg:#f38ba8 bold"),
            ("activity-success", "fg:#a6e3a1"),
            ("dashboard", "fg:#cdd6f4 bg:#1e1e2e"),
            ("dashboard.key", "fg:#89b4fa"),
            ("dashboard.val", "fg:#cdd6f4"),
            ("dashboard.ok", "fg:#a6e3a1"),
            ("dashboard.warn", "fg:#fab387"),
            ("dashboard.error", "fg:#f38ba8 bold"),
            ("input", "fg:#cdd6f4 bg:#1e1e2e"),
            ("input.prefix", "fg:#89b4fa"),
            ("command-completion", "fg:#cba6f7 bg:#1e1e2e bold"),
            ("file-completion", "fg:#89b4fa bg:#1e1e2e"),
            ("dir-completion", "fg:#a6e3a1 bg:#1e1e2e bold"),
            ("history-completion", "fg:#a6adc8 bg:#1e1e2e"),
            (" ok", "fg:#a6e3a1"),
            (" warn", "fg:#fab387"),
            (" error", "fg:#f38ba8 bold"),
            (" dim", "fg:#585b70"),
            (" info", "fg:#89b4fa"),
            (" bold", "bold"),
            ("chrome", "fg:#313244"),
            ("chrome.hl", "fg:#585b70"),
            # ── Utility tokens (renderer uses class:dim not class: dim) ──
            ("dim", "fg:#585b70"),
            ("error", "fg:#f38ba8 bold"),
            ("info", "fg:#89b4fa"),
            ("ok", "fg:#a6e3a1"),
            ("warn", "fg:#fab387"),
            ("success", "fg:#a6e3a1"),
            # ── Base chrome (fallback for all unclassified elements) ──
            ("", "fg:#cdd6f4 bg:#1e1e2e"),
            ("scrollbar", "fg:#45475a bg:#1e1e2e"),
            ("scrollbar.arrow", "fg:#585b70 bg:#1e1e2e"),
            ("line-number", "fg:#585b70"),
            # ── Activity bar ──
            ("activity-done", "fg:#a6e3a1"),
            ("activity-fail", "fg:#f38ba8 bold"),
            ("activity-running", "fg:#a6e3a1"),
            ("activity-warn", "fg:#fab387"),
            # ── Welcome screen ──
            ("welcome-desc", "fg:#6c7086"),
            # ── Thinking panel ──
            ("thinking-panel-border", "fg:#313244"),
            ("thinking-panel-text", "fg:#cba6f7"),
            # ── Status bar: Seven Beasts ──
            ("status-bar-beast-baihu", "fg:#f2cdcd bg:#181825"),
            ("status-bar-beast-qinglong", "fg:#a6e3a1 bg:#181825"),
            ("status-bar-beast-zhuque", "fg:#fab387 bg:#181825"),
            ("status-bar-beast-xuanwu", "fg:#89b4fa bg:#181825"),
            ("status-bar-beast-qilin", "fg:#cba6f7 bg:#181825"),
            ("status-bar-beast-tengshe", "fg:#f9e2af bg:#181825"),
            ("status-bar-beast-yinglong", "fg:#cdd6f4 bg:#181825"),
            # ── Status bar: detail fields ──
            ("status-bar-context", "fg:#a6adc8"),
            ("status-bar-git", "fg:#a6e3a1"),
            ("status-bar-model", "fg:#89b4fa"),
            ("status-bar-path", "fg:#6c7086"),
            ("status-bar-level-a", "fg:#a6e3a1 bg:#181825 bold"),
            ("status-bar-level-b", "fg:#f9e2af bg:#181825 bold"),
            ("status-bar-level-c", "fg:#fab387 bg:#181825 bold"),
            ("status-bar-level-d", "fg:#f38ba8 bg:#181825 bold"),
            # ── Status bar: alt names ──
            ("status-err", "fg:#f38ba8 bold"),
            ("status-warn", "fg:#fab387"),
            # ── Header detail ──
            ("header", "fg:#cdd6f4 bg:#181825"),
            ("header-model", "fg:#89b4fa bold bg:#181825"),
            ("header-sep", "fg:#585b70 bg:#181825"),
            ("header-latency", "fg:#6c7086 bg:#181825"),
            ("header-error", "fg:#f38ba8 bg:#181825"),
            ("header-logo", "fg:#cba6f7 bold bg:#181825"),
            # ── Completions ──
            ("command-completion", "fg:#89b4fa"),
            ("file-completion", "fg:#a6e3a1"),
            ("dir-completion", "fg:#89b4fa bold"),
            ("history-completion", "fg:#6c7086"),
            # ── App root background ──
            ("app", "bg:#1e1e2e"),
        ]
    )

    return merge_styles([beast_style, _get_mocha_base()])


def _build_high_contrast_style() -> Style:
    """High-contrast theme for color-blind accessibility."""
    return Style(
        [
            # message-* class names (what the rendering code uses)
            ("message-user", "bg:#444444 bold fg:#ffffff"),
            ("message-crux", "bg:#222266 bold fg:#88ccff"),
            ("message-system", "bg:#444400 fg:#ffff00"),
            ("message-error", "bg:#660000 bold fg:#ff6666"),
            ("message-success", "bg:#004400 fg:#88ff88"),
            ("message-thinking", "bg:#222244 fg:#ccbbff italic"),
            ("message-info", "bg:#003344 fg:#66dddd"),
            ("message-tool", "bg:#004444 fg:#66dddd italic"),
            # msg-* aliases (for any code still using short form)
            ("msg-user", "bg:#444444 bold fg:#ffffff"),
            ("msg-assistant", "bg:#222266 bold fg:#88ccff"),
            ("msg-system", "bg:#444400 fg:#ffff00"),
            ("msg-error", "bg:#660000 bold fg:#ff6666"),
            ("msg-success", "bg:#004400 fg:#88ff88"),
            ("msg-thinking", "bg:#222244 fg:#ccbbff italic"),
            ("msg-info", "bg:#003344 fg:#66dddd"),
            ("header-bar", "bg:#222222 fg:#ffffff bold"),
            # ── Section headers (分区独立配色, high-contrast safe) ──
            ("header-thinking", "bg:#222244 fg:#ccbbff bold"),
            ("header-status", "bg:#003344 fg:#66dddd bold"),
            ("header-tool", "bg:#442200 fg:#ffcc88 bold"),
            ("header-comfyui", "bg:#004400 fg:#88ff88 bold"),
            ("header-system", "bg:#222266 fg:#88ccff bold"),
            ("status-bar", "bg:#222222 fg:#ffffff"),
            ("status-bar.key", "fg:#aaaaaa bold bg:#222222"),
            ("status-bar.val", "fg:#ffffff bg:#222222"),
            ("command-completion", "bg:#444400 fg:#ffffff bold"),
            ("file-completion", "bg:#004444 fg:#ffffff"),
            ("dir-completion", "bg:#444444 fg:#ffffff bold"),
            ("thinking", "bg:#222244 fg:#ccbbff italic"),
            ("input-field", "fg:#ffffff bg:#222222"),
            ("text-area", "fg:#ffffff bg:#222222"),
            ("text-area.prompt", "fg:#88ccff bold bg:#222222"),
            ("text-area.cursor", "fg:#222222 bg:#ffffff"),
            (" ok", "fg:#00ff00 bold"),
            (" warn", "fg:#ffff00 bold"),
            (" error", "fg:#ff0000 bold"),
            ("", "fg:#ffffff bg:#111111"),
        ]
    )


def _build_mono_style() -> Style:
    """Monochrome theme for SSH / minimal terminals — uses basic ANSI colors."""
    return Style(
        [
            # message-* class names (primary — what rendering code uses)
            ("message-user", "bold fg:ansiwhite"),
            ("message-crux", "fg:ansibrightblue"),
            ("message-system", "fg:ansiyellow bold"),
            ("message-error", "bold fg:ansired"),
            ("message-success", "fg:ansigreen bold"),
            ("message-thinking", "italic fg:ansimagenta"),
            ("message-info", "fg:ansicyan"),
            ("message-tool", "italic fg:ansigreen"),
            # msg-* aliases (for any code still using short form)
            ("msg-user", "bold fg:ansiwhite"),
            ("msg-assistant", "fg:ansibrightblue"),
            ("msg-system", "fg:ansiyellow bold"),
            ("msg-error", "bold fg:ansired"),
            ("msg-success", "fg:ansigreen bold"),
            ("msg-thinking", "italic fg:ansimagenta"),
            ("msg-info", "fg:ansicyan"),
            # chrome
            ("header-bar", "bold reverse"),
            # ── Section headers (分区独立配色, mono-safe via ANSI) ──
            ("header-thinking", "bold fg:ansimagenta"),
            ("header-status", "bold fg:ansicyan"),
            ("header-tool", "bold fg:ansiyellow"),
            ("header-comfyui", "bold fg:ansigreen"),
            ("header-system", "bold fg:ansiblue"),
            ("status-bar", "reverse"),
            ("status-bar.key", "bold"),
            ("status-bar.val", ""),
            ("thinking", "italic"),
            ("input-field", ""),
            ("text-area", ""),
            ("text-area.prompt", "bold"),
            (" ok", "bold fg:ansigreen"),
            (" warn", "bold fg:ansiyellow"),
            (" error", "bold fg:ansired reverse"),
            ("", ""),
        ]
    )


# Pre-computed mode instances
_HIGH_CONTRAST = _build_high_contrast_style()
_MONO = _build_mono_style()

# Cache for palette styles (built lazily)
_PALETTE_STYLE_CACHE: dict[str, Style] = {}


# ══════════════════════════════════════════════════════════════
# Main entry point
# ══════════════════════════════════════════════════════════════


def build_style_v2(mode_or_theme: str = "blade") -> Style:
    """Build CRUX TUI style.

    Accepts:
        - A palette name:  "blade" | "polar_night" | "lava" | "jade"
        - A mode name:     "normal" | "high_contrast" | "mono"

    Default: "blade" (刀阵 — 玄青底 + 紫刃青脉).
    """
    from prompt_toolkit.styles import merge_styles

    # ── Palette themes ──
    if mode_or_theme in PALETTES:
        if mode_or_theme not in _PALETTE_STYLE_CACHE:
            _PALETTE_STYLE_CACHE[mode_or_theme] = _build_palette_style(PALETTES[mode_or_theme])
        return _PALETTE_STYLE_CACHE[mode_or_theme]

    # ── Legacy modes ──
    base = _get_mocha_base()
    if mode_or_theme == "mono":
        return merge_styles([_MONO, base])
    if mode_or_theme == "high_contrast":
        return merge_styles([_HIGH_CONTRAST, base])

    # Fallback: normal / unknown → Catppuccin Mocha
    return _build_normal_style()


def list_themes_v2() -> list[dict]:
    """Return all available palette themes + modes."""
    result = []
    for pid, p in PALETTES.items():
        result.append({"id": pid, "name": p["name"], "desc": p["desc"], "type": "palette"})
    result.append({"id": "normal", "name": "Normal", "desc": "Catppuccin Mocha (default)", "type": "mode"})
    result.append({"id": "high_contrast", "name": "High Contrast", "desc": "Color-blind accessible", "type": "mode"})
    result.append({"id": "mono", "name": "Mono", "desc": "SSH / minimal terminal safe", "type": "mode"})
    return result
