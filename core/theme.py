"""CRUX Studio — Catppuccin Mocha theme colors.

Shared palette used by launcher, skin, and CLI.
No dependencies on any UI framework.
"""

# ── Color Palette ──────────────────────────────────────────────

COLORS = {
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
    "accent": "#89B4FA",
    "accent2": "#A6E3A1",
    "accent3": "#94E2D5",
    "error": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "info": "#89B4FA",
    "user_name": "#89B4FA",
    "crux_name": "#CBA6F7",
    "system": "#585B70",
    "blue": "#89B4FA",
    "purple": "#CBA6F7",
    "green": "#A6E3A1",
    "red": "#F38BA8",
    "yellow": "#F9E2AF",
    "teal": "#94E2D5",
    "baihu": "#CDD6F4",
    "qinglong": "#89B4FA",
    "zhuque": "#F38BA8",
    "xuanwu": "#A6E3A1",
    "qilin": "#F9E2AF",
    "tengshe": "#CBA6F7",
    "yinglong": "#FAB387",
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
