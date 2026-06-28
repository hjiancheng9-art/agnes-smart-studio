"""CRUX screen system — v4 七兽归位启动动画。
BootScreen: 启动扫描线动画 → Logo行 → 就绪标记
WelcomeScreen: 静态欢迎页（七兽阵列 + 结界 + 命令速查）
ChatScreen: 聊天模式头部/底部渲染
"""

from __future__ import annotations

import time
from typing import Any

from rich.table import Table
from rich.text import Text

from ui.theme import COLORS, ICONS, LAYOUT, console

__all__ = ["BootScreen", "WelcomeScreen", "ChatScreen", "render_boot"]


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


class WelcomeScreen:
    """静态欢迎页 — 七兽阵列 + 结界 + 命令速查"""

    @staticmethod
    def render(v="v5.0", t="84", s="734", **kw):
        P = COLORS["primary"]
        A = COLORS["accent"]
        M = COLORS["muted"]
        H = COLORS["highlight"]
        S = COLORS["success"]
        BAI = COLORS["baihu"]
        QIN = COLORS["qinglong"]
        ZHU = COLORS["zhuque"]
        XUA = COLORS["xuanwu"]
        QIL = COLORS["qilin"]
        TEN = COLORS["tengshe"]
        YIN = COLORS["yinglong"]

        console.print()
        console.print(_banner_line(v, t, s))
        console.print()

        # 工具分类网格（2行 x 5列）
        cat_table = Table(show_header=False, box=None, padding=(0, 1))
        for _ in range(5):
            cat_table.add_column(width=20)
        cats = [
            ("图像", "generate_image  imagegen  comfyui*", "primary"),
            ("视频", "generate_video  text_to_speech  transcribe", "accent"),
            ("代码", "code_analyze  find_*  search_*  graph_*", "highlight"),
            ("文件", "read_file  write_file  edit_file  patch_*", "success"),
            ("Git ", "branch  push  pull  pr  stash  tag  log", "baihu"),
            ("GitHub", "browse  search  api  issue  release", "qinglong"),
            ("浏览器", "web_fetch  web_search  pw_*  screenshot", "zhuque"),
            ("系统", "run_bash  run_python  env_check  test", "xuanwu"),
            ("AI  ", "multi_agent  think_deep  goal  plan", "tengshe"),
            ("部署", "deploy_vercel  html  markdown  pdf", "yinglong"),
        ]
        cat_table.add_row(
            *[f"[bold {COLORS[c[2]]}]{c[0]}[/]\n[dim {M}]{c[1]}[/]" for c in cats[:5]]
        )
        cat_table.add_row(
            *[f"[bold {COLORS[c[2]]}]{c[0]}[/]\n[dim {M}]{c[1]}[/]" for c in cats[5:]]
        )
        console.print(cat_table)
        console.print()

        # 七兽结界
        beast_tags = [
            (BAI, "白虎·自愈"), (QIN, "青龙·并行"), (ZHU, "朱雀·验证"),
            (XUA, "玄武·守卫"), (QIL, "麒麟·创造"), (TEN, "螣蛇·记忆"), (YIN, "应龙·调度"),
        ]
        console.print(
            f"  [{M}]七兽[/] "
            + "  ".join(f"[{c}]●[/] [{M}]{n}[/]" for c, n in beast_tags)
        )
        console.print()

        # 结界
        shields = "沙箱 熔断 加密 隐私 快照 校验 自愈".split()
        console.print(
            f"  [{M}]结界[/] "
            + "  ".join(f"[{S}]●[/] [{M}]{s}[/]" for s in shields)
        )
        console.print()

        # 命令
        console.print(
            f"  [{M}]命令[/]  "
            + "  ".join(f"[{M}]/{name}[/]" for name in ["model", "code", "img", "video", "skill", "plan", "team", "help"])
        )
        console.print()

        # 光标
        cursor_line = Text()
        cursor_line.append("▮ ", style=f"bold {S}")
        cursor_line.append("键入指令开始", style=f"bold {P}")
        cursor_line.append(" · ", style=M)
        cursor_line.append("Alt+Enter 换行", style=M)
        console.print(f"\n  {cursor_line}")
        console.print()


class ChatScreen:
    """聊天模式头部/底部渲染"""

    @staticmethod
    def render_header(session=None, show_detail=True):
        from ui.badges import print_reply_header

        if session:
            print_reply_header(session)

    @staticmethod
    def render_mode_switch(old_mode="", new_mode=""):
        from ui.theme import COLORS, console

        console.print(
            f"  [{COLORS['transition']}]◆[/] Switched: [{COLORS['muted']}]{old_mode}[/] → [{COLORS['primary']}]{new_mode}[/]"
        )

    @staticmethod
    def render_exit():
        from ui.theme import COLORS, console

        console.print(f"\n  [{COLORS['success']}]再见![/]\n")
