"""CRUX screen system — BootScreen 启动动画。

v6 后 WelcomeScreen / ChatScreen 已废弃，欢迎页统一走 terminal_logo.render_welcome()。
BootScreen 保留供测试和特殊场景使用。
"""

from __future__ import annotations

import time

from ui.theme import COLORS, console

__all__ = ["BootScreen", "render_boot"]


def _banner_line(v="v5.0", t="84", s="734"):
    """紧凑单行横幅 — CRUX 单色清晰。"""
    P = COLORS["primary"]
    A = COLORS["accent"]
    M = COLORS["muted"]
    H = COLORS["highlight"]
    S = COLORS["success"]
    return (
        f"  [{P}]◈ CRUX Studio {v}[/] [{M}]·[/] [{A}]{t} tools[/] [{M}]·[/] [{H}]{s} skills[/] [{M}]·[/] [{S}]●[/]"
    )


class BootScreen:
    """启动动画 — 扫描线 → Logo行 → 就绪闪烁"""

    @staticmethod
    def render(v="v5.0", t="84", s="734", animate=True):
        if animate:
            with console.capture() as capture:
                BootScreen._scanlines()
                BootScreen._logo(v, t, s)
                BootScreen._ready(v, t, s)
            console.clear()
            console.print(capture.get())
        else:
            BootScreen._static(v, t, s)

    @staticmethod
    def _scanlines():
        console.print()
        for _ in range(6):
            console.print(f"  [dim {COLORS['muted']}]" + chr(0x25ac) * 32 + "[/]")
            time.sleep(0.06)
        time.sleep(0.15)

    @staticmethod
    def _logo(v, t, s):
        console.print()
        console.print(_banner_line(v, t, s))
        console.print()
        time.sleep(0.2)

    @staticmethod
    def _ready(v, t, s):
        S = COLORS["success"]
        P = COLORS["primary"]
        for _ in range(2):
            console.clear()
            console.print()
            console.print(_banner_line(v, t, s))
            console.print()
            console.print(f"  [{S}]{chr(0x25cf)} 系统就绪[/]")
            console.print()
            time.sleep(0.2)
            console.clear()
            time.sleep(0.1)

    @staticmethod
    def _static(v, t, s):
        console.print()
        console.print(_banner_line(v, t, s))
        console.print()
        console.print(f"  [{COLORS['success']}]{chr(0x25cf)} 系统就绪[/]")
        console.print()


def render_boot(v="v5.0", t="84", s="734", animate=True):
    BootScreen.render(v=v, t=t, s=s, animate=animate)
