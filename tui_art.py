"""
╔══════════════════════════════════════════════════════╗
║       CRUX TUI ART — 终端美学升级引擎               ║
║  字体 · Badge · 欢迎屏 · 装饰 · 终端艺术一体化     ║
╚══════════════════════════════════════════════════════╝
"""

import shutil
import sys
import time
from datetime import datetime
from typing import Optional

import pyfiglet

# ─── ANSI 颜色 ───────────────────────────────────────────
# 兼容 Windows 经典终端 + 现代终端
class C:
    """CRUX 调色板 — 深色系赛博美学"""
    RESET    = "\033[0m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"
    ITALIC   = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK    = "\033[5m"
    REVERSE  = "\033[7m"

    # 前景
    RED      = "\033[38;2;255;80;80m"
    GREEN    = "\033[38;2;80;255;180m"
    YELLOW   = "\033[38;2;255;220;80m"
    BLUE     = "\033[38;2;80;180;255m"
    MAGENTA  = "\033[38;2;200;120;255m"
    CYAN     = "\033[38;2;80;255;240m"
    WHITE    = "\033[38;2;220;220;220m"
    ORANGE   = "\033[38;2;255;160;60m"
    PINK     = "\033[38;2;255;100;180m"
    GRAY     = "\033[38;2;120;120;120m"
    LIME     = "\033[38;2;160;255;80m"

    # 背景
    BG_RED   = "\033[48;2;180;30;30m"
    BG_GREEN = "\033[48;2;30;120;60m"
    BG_BLUE  = "\033[48;2;20;60;120m"
    BG_DARK  = "\033[48;2;20;20;30m"
    BG_GRAY  = "\033[48;2;40;40;50m"

    # 特殊
    CRUX_R   = "\033[38;2;255;80;80m"   # 朱雀红
    CRUX_G   = "\033[38;2;80;255;180m"  # 青龙绿
    CRUX_B   = "\033[38;2;80;180;255m"  # 白虎蓝
    CRUX_P   = "\033[38;2;200;120;255m" # 麒麟紫
    CRUX_Y   = "\033[38;2;255;220;80m"  # 螣蛇金
    CRUX_C   = "\033[38;2;80;255;240m"  # 玄武青
    CRUX_O   = "\033[38;2;255;160;60m"  # 应龙橙


# ─── 终端尺寸 ────────────────────────────────────────────
def term_width() -> int:
    return shutil.get_terminal_size().columns

def term_height() -> int:
    return shutil.get_terminal_size().lines


# ─── 七兽字体表 ──────────────────────────────────────────
# 不同场景使用不同字体
FONT_BEASTS = {
    "hero":    "big",            # 大标题
    "sub":     "slant",          # 副标题
    "badge":   "digital",        # 徽章紧凑
    "cyber":   "cyberlarge",     # 赛博风
    "chunk":   "banner3-D",      # 3D 块
    "future":  "doom",           # DOOM 启示录
    "minimal": "ascii_new_roman", # 极简罗马
}

# ─── 文本渲染引擎 ────────────────────────────────────────
def render(text: str, font: str = "big", color: str = C.CRUX_R) -> str:
    """用 pyfiglet 渲染 + 着色"""
    try:
        art = pyfiglet.figlet_format(text, font=font)
    except Exception:
        art = text
    lines = art.split("\n")
    colored = "\n".join(f"{color}{l}{C.RESET}" for l in lines)
    return colored


def echo(text: str, font: str = "big", color: str = C.CRUX_R):
    """直接打印渲染文本"""
    print(render(text, font, color))


# ─── Badge 徽章系统 ──────────────────────────────────────
class Badge:
    """艺术风格徽章生成器"""

    STYLES = {
        "info":    (C.CRUX_B, " ◆ "),
        "ok":      (C.CRUX_G, " ✓ "),
        "warn":    (C.CRUX_Y, " ⚡"),
        "error":   (C.CRUX_R, " ✗ "),
        "done":    (C.CRUX_G, " ✔ "),
        "fire":    (C.CRUX_R, " 🔥"),
        "star":    (C.CRUX_Y, " ★ "),
        "heart":   (C.CRUX_P, " ♥ "),
        "bolt":    (C.CRUX_O, " ⚡"),
        "skull":   (C.RED,    " ☠ "),
        "crown":   (C.CRUX_Y, " ♛ "),
        "moon":    (C.CRUX_C, " ☽ "),
        "cross":   (C.CRUX_R, " † "),
        "crux":    (C.MAGENTA," ⚶ "),
    }

    @classmethod
    def make(cls, label: str, style: str = "info",
             bracket: str = "[]", pad: bool = True) -> str:
        """生成 Badge: [● INFO]"""
        clr, icon = cls.STYLES.get(style, (C.WHITE, " · "))
        lb = bracket[0]
        rb = bracket[1]
        spacing = " " if pad else ""
        return (f"{C.BOLD}{clr}{lb}{C.RESET}"
                f"{clr}{icon}{C.RESET}"
                f"{C.BOLD}{clr}{label}{C.RESET}"
                f"{C.BOLD}{clr}{rb}{C.RESET}")

    @classmethod
    def line(cls, label: str, style: str = "info") -> str:
        """生成一行完整 Badge 标签行"""
        return f" {cls.make(label, style)}"

    @classmethod
    def inline(cls, label: str, style: str = "info") -> str:
        """紧凑行内 Badge"""
        clr, icon = cls.STYLES.get(style, (C.WHITE, " · "))
        return f"{C.DIM}[{C.RESET}{clr}{icon}{label}{C.RESET}{C.DIM}]{C.RESET}"


# ─── 欢迎屏 ──────────────────────────────────────────────
def welcome_screen(version: str = "v5.0",
                   model: str = "DeepSeek V4 Flash",
                   project: str = "agnes-smart-studio"):
    """全屏欢迎界面"""

    tw = term_width()

    # 顶部间隔
    print("\n" * 1)

    # ── 大 Banner ──
    art = pyfiglet.figlet_format("CRUX", font="big")
    art2 = pyfiglet.figlet_format("STUDIO", font="ascii_new_roman")

    # 渐变色：从左到右 红→橙→黄→绿→青→蓝→紫
    colors_cycle = [C.CRUX_R, C.CRUX_O, C.CRUX_Y, C.CRUX_G, C.CRUX_C, C.CRUX_B, C.CRUX_P]
    lines = art.split("\n")
    for i, line in enumerate(lines):
        c = colors_cycle[i % len(colors_cycle)]
        print(f"{c}{line}{C.RESET}")

    lines2 = art2.split("\n")
    for i, line in enumerate(lines2):
        c = colors_cycle[(i + 3) % len(colors_cycle)]
        print(f"  {c}{line}{C.RESET}")

    # ── 装饰彩虹线 ──
    rainbow = "━" * min(60, tw - 4)
    print(f"\n  {C.CRUX_R}╭{C.RESET}{rainbow}{C.CRUX_P}╮{C.RESET}")

    # ── 状态信息面板 ──
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info_items = [
        f"{C.CRUX_B}●{C.RESET} {C.BOLD}版本{C.RESET}  {C.CRUX_G}{version}{C.RESET}",
        f"{C.CRUX_P}●{C.RESET} {C.BOLD}引擎{C.RESET}  {C.CRUX_C}{model}{C.RESET}",
        f"{C.CRUX_Y}●{C.RESET} {C.BOLD}项目{C.RESET}  {C.CRUX_O}{project}{C.RESET}",
        f"{C.CRUX_R}●{C.RESET} {C.BOLD}时间{C.RESET}  {C.GRAY}{now}{C.RESET}",
    ]
    for item in info_items:
        print(f"  {item}")

    # ── 七兽图腾 ──
    beasts = [
        ("白虎", C.CRUX_B, "骨"),
        ("青龙", C.CRUX_G, "脉"),
        ("朱雀", C.CRUX_R, "眼"),
        ("玄武", C.CRUX_C, "甲"),
        ("麒麟", C.CRUX_P, "手"),
        ("螣蛇", C.CRUX_Y, "忆"),
        ("应龙", C.CRUX_O, "令"),
    ]
    print(f"\n  {C.BOLD}{C.GRAY}七兽觉醒 · 魂魄交融{C.RESET}")
    beasts_line = "  "
    for name, clr, role in beasts:
        beasts_line += f"{clr}■{C.RESET}{C.BOLD}{clr}{name}{C.RESET}({C.DIM}{role}{C.RESET}) "
    print(beasts_line)

    # ── 底部 ──
    print(f"\n  {C.CRUX_R}╰{C.RESET}{rainbow}{C.CRUX_P}╯{C.RESET}")
    print(f"\n  {C.BOLD}{C.GRAY}>>> 就绪 · 随时号令 <<<{C.RESET}")
    print()


# ─── Panel 装饰盒子 ──────────────────────────────────────
def panel(title: str, content: str, color: str = C.CRUX_B,
          width: Optional[int] = None):
    """带标题的装饰面板"""
    tw = width or min(72, term_width() - 4)
    inner_w = tw - 4

    print(f"\n  {color}╭{'─' * (tw - 2)}╮{C.RESET}")
    print(f"  {color}│{C.RESET} {C.BOLD}{color}{title:^{inner_w}}{C.RESET} {color}│{C.RESET}")

    for line in content.split("\n"):
        display = line[:inner_w]
        padding = inner_w - len(display)
        print(f"  {color}│{C.RESET} {display}{' ' * padding} {color}│{C.RESET}")

    print(f"  {color}╰{'─' * (tw - 2)}╯{C.RESET}\n")


# ─── 分隔线 ──────────────────────────────────────────────
def divider(char: str = "═", color: str = C.GRAY, label: str = ""):
    """主题分隔线"""
    tw = term_width()
    if label:
        side = (tw - len(label) - 4) // 2
        print(f"\n  {color}{char * side}  {C.BOLD}{C.WHITE}{label}{C.RESET}  {color}{char * side}{C.RESET}\n")
    else:
        print(f"\n  {color}{char * tw}{C.RESET}\n")


# ─── 状态行 ──────────────────────────────────────────────
def status_bar(items: list, sep: str = " │ "):
    """状态栏：一行多个状态项"""
    parts = []
    for label, value, style in items:
        b = Badge.inline(label, style)
        val = f"{C.BOLD}{value}{C.RESET}" if value else ""
        parts.append(f"{b} {val}")
    print("  " + sep.join(parts))


# ─── 工具链一览 ──────────────────────────────────────────
def toolchain_display():
    """显示可用工具链"""
    chains = [
        ("画图",  "generate_image",    C.CRUX_P),
        ("视频",  "generate_video",    C.CRUX_R),
        ("代码",  "run_python/bash",   C.CRUX_G),
        ("搜索",  "web_search/fetch",  C.CRUX_Y),
        ("Git",   "git_*",             C.CRUX_B),
        ("文件",  "read/write/edit",   C.CRUX_C),
        ("浏览",  "pw_navigate",       C.CRUX_O),
    ]
    line = "  "
    for name, tool, clr in chains:
        line += f"{clr}◈{C.RESET}{C.BOLD}{clr}{name}{C.RESET}{C.DIM}/{tool}{C.RESET}  "
    print(line)


# ─── 进度条 ──────────────────────────────────────────────
def progress_bar(percent: float, width: int = 40,
                 filled: str = "█", empty: str = "░",
                 color: str = C.CRUX_G) -> str:
    """艺术风格进度条"""
    p = min(100, max(0, percent))
    fw = int(p / 100 * width)
    ew = width - fw
    bar = f"{color}{filled * fw}{C.DIM}{empty * ew}{C.RESET}"
    pct = f"{C.BOLD}{color}{p:5.1f}%{C.RESET}"
    return f"{bar} {pct}"


# ─── 快速演示 ────────────────────────────────────────────
def demo():
    """演示所有功能"""
    welcome_screen()
    time.sleep(0.5)

    divider("═", C.CRUX_P, "徽章系统 BADGES")

    for style in ["info", "ok", "warn", "error", "done",
                   "fire", "star", "heart", "bolt", "crown"]:
        print(Badge.line(style.upper(), style))

    divider("═", C.CRUX_B, "状态栏 STATUS")

    status_bar([
        ("STATUS", "ACTIVE", "ok"),
        ("UPTIME", "12:34:56", "info"),
        ("TASKS", "7", "star"),
        ("TEMP", "42°C", "fire"),
    ])

    divider("═", C.CRUX_G, "面板 PANEL")

    panel("CRUX 系统状态",
          " 白虎 · 骨骼架构     ✅ 自愈\n"
          " 青龙 · 并行脉路     ✅ 开拓\n"
          " 朱雀 · 洞察之眼     ✅ 验证\n"
          " 玄武 · 守护甲盾     ✅ 校验\n"
          " 麒麟 · 创造之手     ✅ 锻造\n"
          " 螣蛇 · 传承记忆     ✅ 归档\n"
          " 应龙 · 号令八方     ✅ 协同",
          C.CRUX_C)

    divider("═", C.CRUX_Y, "进度 PROGRESS")

    print(f"  {progress_bar(42, color=C.CRUX_R)}")
    print(f"  {progress_bar(78, color=C.CRUX_G)}")
    print(f"  {progress_bar(100, color=C.CRUX_B)}")

    divider("═", C.CRUX_O, "工具链 TOOLCHAIN")
    toolchain_display()

    divider()
    print(f"\n  {C.BOLD}{C.CRUX_P}✦ 终端美学升级完成 · 七兽之力已注入 ✦{C.RESET}\n")


if __name__ == "__main__":
    demo()
