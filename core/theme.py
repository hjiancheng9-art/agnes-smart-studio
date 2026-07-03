"""CRUX Studio — 暗夜工坊 (Night Atelier) theme colors.

Shared palette used by launcher, skin, and CLI.
No dependencies on any UI framework.
"""

# ── Color Palette ──────────────────────────────────────────────

COLORS = {
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
    "accent": "#d4a853",
    "accent2": "#7a9a6b",
    "accent3": "#5b8a9a",
    "error": "#c4554a",
    "warning": "#c4944a",
    "success": "#7a9a6b",
    "info": "#5b8a9a",
    "user_name": "#8fb8d4",
    "crux_name": "#d4a853",
    "system": "#6b6560",
    "baihu": "#e0e0e0",
    "qinglong": "#5ba3d4",
    "zhuque": "#d45b5b",
    "xuanwu": "#5b8a6b",
    "qilin": "#d4a853",
    "tengshe": "#9a6bd4",
    "yinglong": "#d49a5b",
}

BEAST_ORDER = ["BAIHU", "QINGLONG", "ZHUQUE", "XUANWU", "QILIN", "TENGSHE", "YINGLONG"]

BEAST_ICONS = {
    "BAIHU": "虎", "QINGLONG": "龙", "ZHUQUE": "雀",
    "XUANWU": "武", "QILIN": "麟", "TENGSHE": "蛇", "YINGLONG": "翼",
}

BEAST_PALETTE = {
    "BAIHU": COLORS["baihu"], "QINGLONG": COLORS["qinglong"],
    "ZHUQUE": COLORS["zhuque"], "XUANWU": COLORS["xuanwu"],
    "QILIN": COLORS["qilin"], "TENGSHE": COLORS["tengshe"],
    "YINGLONG": COLORS["yinglong"],
}
