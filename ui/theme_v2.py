"""CRUX TUI v2 — Seven Beasts enhanced theme for prompt_toolkit.

Extends the Catppuccin Mocha palette with beast-color semantics and
richer visual hierarchy for the redesigned TUI layout.

Theme modes (per 3-platform debate):
    normal         -- Full Catppuccin Mocha + Seven Beasts semantic colors
    high_contrast  -- High contrast for color-blind accessibility
    mono           -- Monochrome/ASCII-safe for SSH/minimal terminals
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

# ── Main entry point ──────────────────────────────────────

def build_style_v2(mode: str = "normal") -> Style:
    """Build CRUX TUI style for the given mode."""
    if mode == "mono":
        return _MONO
    if mode == "high_contrast":
        return _HIGH_CONTRAST
    return _build_normal_style()


# ── Normal: Catppuccin Mocha + Seven Beasts ───────────────

def _build_normal_style() -> Style:
    """Full Catppuccin Mocha with Seven Beasts semantic colors."""
    from prompt_toolkit.styles import merge_styles

    beast_style = Style([
        # ── Message area ──
        ("msg-user",         "fg:#f2cdcd bold"),           # 虎 Tiger
        ("msg-assistant",    "fg:#89b4fa"),                 # 龙 Dragon
        ("msg-system",       "fg:#fab387"),                 # 雀 Phoenix
        ("msg-error",        "fg:#f5c2e7 bold"),            # 翼 Wing
        ("msg-success",      "fg:#a6e3a1"),                 # 武 Warrior
        ("msg-thinking",     "fg:#cba6f7 italic"),          # 麟 Qilin
        ("msg-info",         "fg:#94e2d5"),                 # 蛇 Snake

        # ── Header bar ──
        ("header-bar",       "fg:#89b4fa bg:#181825 bold"),
        ("header-bar bold",  "fg:#89b4fa bg:#181825 bold"),

        # ── Separator ──
        ("separator",        "fg:#313244"),

        # ── Status bar ──
        ("status-bar",       "fg:#a6adc8 bg:#181825"),
        ("status-bar.key",   "fg:#89b4fa bold"),
        ("status-bar.val",   "fg:#cdd6f4"),

        # ── Thinking panel ──
        ("thinking",         "fg:#cba6f7 bg:#1e1e2e italic"),
        ("thinking-header",  "fg:#cba6f7 bg:#1e1e2e bold"),

        # ── Activity / progress ──
        ("activity-info",    "fg:#89b4fa"),
        ("activity-warn",    "fg:#fab387"),
        ("activity-error",   "fg:#f38ba8 bold"),
        ("activity-success", "fg:#a6e3a1"),

        # ── Dashboard ──
        ("dashboard",        "fg:#cdd6f4 bg:#1e1e2e"),
        ("dashboard.key",    "fg:#89b4fa"),
        ("dashboard.val",    "fg:#cdd6f4"),
        ("dashboard.ok",     "fg:#a6e3a1"),
        ("dashboard.warn",   "fg:#fab387"),
        ("dashboard.error",  "fg:#f38ba8 bold"),

        # ── Input area ──
        ("input",            "fg:#cdd6f4 bg:#1e1e2e"),
        ("input.prefix",     "fg:#89b4fa"),

        # ── Completions ──
        ("command-completion", "fg:#cba6f7 bg:#1e1e2e bold"),
        ("file-completion",    "fg:#89b4fa bg:#1e1e2e"),
        ("dir-completion",     "fg:#a6e3a1 bg:#1e1e2e bold"),
        ("history-completion", "fg:#a6adc8 bg:#1e1e2e"),

        # ── Generic states ──
        (" ok",              "fg:#a6e3a1"),
        (" warn",            "fg:#fab387"),
        (" error",           "fg:#f38ba8 bold"),
        (" dim",             "fg:#585b70"),
        (" info",            "fg:#89b4fa"),
        (" bold",            "bold"),

        # ── Chrome ──
        ("chrome",           "fg:#313244"),
        ("chrome.hl",        "fg:#585b70"),
    ])

    # Catppuccin Mocha base
    mocha_style = Style([
        ("window",           "bg:#1e1e2e"),
        ("dialog",           "bg:#1e1e2e border:#313244"),
        ("dialog.body",      "bg:#181825"),
        ("dialog.title",     "bg:#313244 fg:#cdd6f4 bold"),
        ("scrollbar.area",   "bg:#1e1e2e"),
        ("scrollbar.button", "bg:#585b70"),
        ("line",             "fg:#313244"),
        ("button",           "fg:#cdd6f4 bg:#313244"),
        ("button.focused",   "fg:#1e1e2e bg:#89b4fa"),
        ("text-area",        "bg:#1e1e2e fg:#cdd6f4"),
        ("text-area.prompt", "fg:#89b4fa"),
    ])

    return merge_styles([beast_style, mocha_style])


# ── High Contrast ─────────────────────────────────────────

def _build_high_contrast_style() -> Style:
    """High-contrast theme for color-blind accessibility."""
    return Style([
        ("msg-user",         "bg:#444444 bold fg:#ffffff"),
        ("msg-assistant",    "bg:#222266 bold fg:#88ccff"),
        ("msg-system",       "bg:#444400 fg:#ffff00"),
        ("msg-error",        "bg:#660000 bold fg:#ff6666"),
        ("msg-success",      "bg:#006600 bold fg:#66ff66"),
        ("msg-thinking",     "bg:#330066 fg:#cc88ff"),
        ("msg-info",         "fg:#aaaaaa"),
        ("header-bar",       "bg:#333333 bold fg:#ffffff"),
        ("status-bar",       "bg:#222222 fg:#ffffff"),
        ("command-completion", "bg:#444400 fg:#ffffff bold"),
        ("file-completion",  "bg:#004444 fg:#ffffff"),
        ("dir-completion",   "bg:#444444 fg:#ffffff bold"),
        (" ok",              "fg:#00ff00 bold"),
        (" warn",            "fg:#ffff00 bold"),
        (" error",           "fg:#ff0000 bold"),
    ])


# ── Mono ──────────────────────────────────────────────────

def _build_mono_style() -> Style:
    """Monochrome theme for SSH / minimal terminals."""
    return Style([
        ("msg-user",         "bold"),
        ("msg-assistant",    "noreverse"),
        ("msg-system",       "bold underline"),
        ("msg-error",        "bold reverse"),
        ("msg-success",      "bold"),
        ("msg-thinking",     "italic"),
        ("msg-info",         ""),
        ("header-bar",       "bold"),
        ("status-bar",       "reverse"),
        (" ok",              "bold"),
        (" warn",            "bold"),
        (" error",           "bold reverse"),
    ])


# ── Pre-computed instances ────────────────────────────────

_HIGH_CONTRAST = _build_high_contrast_style()
_MONO = _build_mono_style()
