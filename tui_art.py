"""
╔══════════════════════════════════════════════════════╗
║       CRUX TUI ART v3 — 终端美学·动态艺术引擎       ║
║  动画帧 · 渐变文本 · Badge 系统 · 粒子特效         ║
║  呼吸边框 · 打字机 · 欢迎屏 · 七兽图腾             ║
╚══════════════════════════════════════════════════════╝

七兽美学注入终端 — 白虎(骨)·青龙(脉)·朱雀(眼)·玄武(甲)·麒麟(手)·螣蛇(忆)·应龙(令)
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from enum import Enum

# ══════════════════════════════════════════════════════════════
#  色彩系统 — 七兽调色板
# ══════════════════════════════════════════════════════════════

class C:
    """七兽色彩常量 — 24-bit ANSI 真彩色"""
    # 七兽主色
    CRUX_R = "\033[38;2;255;85;85m"     # 白虎 · 赤
    CRUX_G = "\033[38;2;0;255;170m"      # 青龙 · 翠
    CRUX_B = "\033[38;2;0;170;255m"      # 朱雀 · 青
    CRUX_Y = "\033[38;2;255;213;0m"      # 玄武 · 金
    CRUX_O = "\033[38;2;255;128;0m"      # 麒麟 · 橙
    CRUX_P = "\033[38;2;200;100;255m"    # 螣蛇 · 紫
    CRUX_C = "\033[38;2;0;255;200m"      # 应龙 · 青绿

    # 灰阶 & 修饰
    GRAY   = "\033[38;2;140;140;160m"
    DIM    = "\033[38;2;90;90;110m"
    WHITE  = "\033[38;2;220;220;240m"
    BOLD   = "\033[1m"
    DIM_C  = "\033[2m"
    ITALIC = "\033[3m"
    RESET  = "\033[0m"

    # 背景色
    BG_DARK   = "\033[48;2;15;15;25m"
    BG_MID    = "\033[48;2;25;25;40m"
    BG_R      = "\033[48;2;40;10;10m"
    BG_G      = "\033[48;2;10;35;20m"
    BG_B      = "\033[48;2;10;20;40m"
    BG_Y      = "\033[48;2;35;30;10m"

    # 快捷映射
    BEAST_COLORS = {
        "虎": CRUX_R, "龙": CRUX_G, "雀": CRUX_B,
        "武": CRUX_Y, "麟": CRUX_O, "蛇": CRUX_P, "翼": CRUX_C,
    }

    @classmethod
    def beast(cls, name: str) -> str:
        return cls.BEAST_COLORS.get(name, cls.WHITE)

    @classmethod
    def hex(cls, color: str) -> str:
        """从 #RRGGBB 生成 ANSI 前景色"""
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"\033[38;2;{r};{g};{b}m"


# ══════════════════════════════════════════════════════════════
#  动画帧系统 — 帧序列生成器
# ══════════════════════════════════════════════════════════════

class AnimationSet(Enum):
    """预定义动画帧集合"""
    BRAILLE    = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    BLOCK_PULSE = "▁▃▄▅▆▇██▇▆▅▄▃▁"
    ARROW_CYCLE = "←↖↑↗→↘↓↙"
    DOT_PULSE   = "⡀⡄⡆⡇⣇⣧⣷⣿⣷⣧⣇⡇⡆⡄⡀"
    BRACKET     = "┤┴├┬"
    STAR        = "✧★✧★"
    MOON        = "○◔◐◕●◕◐◔"
    HEART       = "♡♡♡❤❤❤♡♡♡"
    PULSE_RING  = "○◌◯◌"
    WAVE        = "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁"
    FADE_BLOCK  = "▓▒░ "
    TRIANGLE    = "◢◣◤◥"
    CROSSHAIR   = "┼┽╀╁╂╁╀┽"
    ZIGZAG      = "╱─╲─"
    BEAST_EYE   = "◉◎◉◎◉"


@dataclass
class AnimatedFrames:
    """动画帧迭代器 — 支持循环和单次播放"""
    frames: Sequence[str]
    interval: float = 0.12
    repeat: int = -1  # -1 = infinite

    def __post_init__(self):
        self._idx = 0
        self._count = 0

    def next(self) -> str:
        """获取下一帧"""
        f = self.frames[self._idx]
        self._idx += 1
        if self._idx >= len(self.frames):
            self._idx = 0
            self._count += 1
        return f

    def reset(self):
        self._idx = 0
        self._count = 0

    @property
    def done(self) -> bool:
        return 0 <= self.repeat <= self._count

    @classmethod
    def from_set(cls, anim: AnimationSet, interval: float = 0.12) -> AnimatedFrames:
        return cls(frames=list(anim.value), interval=interval)

    # ── 常用预设 ──
    @classmethod
    def spinner(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.BRAILLE, 0.10)

    @classmethod
    def block_pulse(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.BLOCK_PULSE, 0.08)

    @classmethod
    def dot_pulse(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.DOT_PULSE, 0.12)

    @classmethod
    def wave(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.WAVE, 0.10)

    @classmethod
    def heart(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.HEART, 0.20)

    @classmethod
    def beast_eye(cls) -> AnimatedFrames:
        return cls.from_set(AnimationSet.BEAST_EYE, 0.30)


# ══════════════════════════════════════════════════════════════
#  渐变文本 — 24-bit 真彩色渐变
# ══════════════════════════════════════════════════════════════

def gradient_text(
    text: str,
    colors: list[tuple[int, int, int]] = None,
    bold: bool = False,
) -> str:
    """将文本渲染为从左到右的渐变。

    Args:
        text: 要渲染的文本
        colors: RGB 元组列表，定义渐变节点（默认: 青→紫→粉）
        bold: 是否加粗

    Returns:
        带 ANSI 转义码的渐变文本
    """
    if not text:
        return ""

    if colors is None:
        colors = [(0, 170, 255), (200, 100, 255), (255, 85, 170)]

    n = len(text)
    if n == 0:
        return ""

    result = []
    bold_seq = C.BOLD if bold else ""

    for i, ch in enumerate(text):
        # 计算在颜色渐变中的位置
        pos = i / max(n - 1, 1) * (len(colors) - 1)
        idx = int(pos)
        t = pos - idx

        if idx >= len(colors) - 1:
            r, g, b = colors[-1]
        else:
            c1, c2 = colors[idx], colors[idx + 1]
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)

        result.append(f"\033[38;2;{r};{g};{b}m{bold_seq}{ch}{C.RESET}")

    return "".join(result)


def gradient_block(
    width: int,
    colors: list[tuple[int, int, int]] = None,
    char: str = "█",
) -> str:
    """渐变色块 — 用字符填充的渐变条"""
    if colors is None:
        colors = [(255, 85, 85), (255, 213, 0), (0, 255, 170)]
    return gradient_text(char * width, colors=colors)


# ══════════════════════════════════════════════════════════════
#  Badge 系统 — 5 种风格
# ══════════════════════════════════════════════════════════════

class BadgeStyle(Enum):
    GLOW     = "glow"      # 发光边框
    PULSE    = "pulse"     # 脉冲动画 (需配合 AnimatedBadge)
    BORDERED = "bordered"  # 精致边框
    ICON     = "icon"      # 图标 + 标签
    MINIMAL  = "minimal"   # 纯色简洁
    TAGGED   = "tagged"    # 标签式 #[]


def render_badge(
    label: str,
    style: BadgeStyle | str = BadgeStyle.MINIMAL,
    color: str = C.CRUX_B,
    icon: str = "",
    width: int | None = None,
) -> str:
    """渲染一个终端 Badge。

    Args:
        label: Badge 文本
        style: Badge 风格
        color: ANSI 颜色码
        icon: 可选图标字符
        width: 最小宽度（用空格填充）

    Returns:
        带 ANSI 样式格式化的 Badge 字符串
    """
    if isinstance(style, str):
        try:
            style = BadgeStyle(style)
        except ValueError:
            style = BadgeStyle.MINIMAL

    display = f"{icon} {label}" if icon else label
    if width and len(display) < width:
        display = display.ljust(width)

    reset = C.RESET
    dim = C.DIM

    if style == BadgeStyle.MINIMAL:
        return f"{color}{C.BOLD}[{display}]{reset}"

    elif style == BadgeStyle.GLOW:
        # 模拟发光：加粗 + 颜色 + 周围 dim 边框
        padding = " " * 2
        inner = f"{color}{C.BOLD}{display}{reset}"
        dim_edge = f"{dim}"

        # 上边框
        top = f"{dim}┌{'─' * (len(display) + 4)}┐{reset}"
        mid = f"{dim}│{reset}  {inner}  {dim}│{reset}"
        bot = f"{dim}└{'─' * (len(display) + 4)}┘{reset}"
        return f"\n{top}\n{mid}\n{bot}\n"

    elif style == BadgeStyle.BORDERED:
        pad = 1
        inner_w = len(display) + pad * 2
        top = f"{color}┌{'─' * inner_w}┐{reset}"
        mid = f"{color}│{' ' * pad}{C.BOLD}{display}{reset}{color}{' ' * pad}│{reset}"
        bot = f"{color}└{'─' * inner_w}┘{reset}"
        return f"\n{top}\n{mid}\n{bot}\n"

    elif style == BadgeStyle.TAGGED:
        bg = "\033[48;2;30;30;50m"
        return f"{dim}#[{bg}{color}{C.BOLD}{display}{reset}{dim}]{reset}"

    elif style == BadgeStyle.ICON:
        icon_str = f"{icon} " if icon else ""
        return f"{dim}[{reset}{color}{C.BOLD}{icon_str}{label}{reset}{dim}]{reset}"

    # fallback
    return f"{color}{C.BOLD}[{display}]{reset}"


# ══════════════════════════════════════════════════════════════
#  粒子特效
# ══════════════════════════════════════════════════════════════

def particle_line(
    width: int = 40,
    density: float = 0.3,
    colors: list[str] | None = None,
    seed: int | None = None,
) -> str:
    """生成一条粒子线 — 随机分布的点阵带颜色。

    适合用作装饰分隔线。
    """
    import random as _random
    if seed is not None:
        _random.seed(seed)

    if colors is None:
        colors = [C.CRUX_R, C.CRUX_G, C.CRUX_B, C.CRUX_Y, C.CRUX_P]

    chars = [" "] * width
    for i in range(width):
        if _random.random() < density:
            c = _random.choice(colors)
            ch = _random.choice(["·", "∙", "•", "∗", "✧", "✦", "⋆"])
            chars[i] = f"{c}{ch}{C.RESET}"

    return "".join(chars)


def sparkle_line(width: int = 40) -> str:
    """闪烁星线 — 高密度粒子装饰线"""
    colors = [C.CRUX_Y, C.CRUX_C, C.WHITE, C.CRUX_P]
    chars = []
    for i in range(width):
        ch = " ✧★⋆· "[i % 5]
        c = colors[i % len(colors)]
        chars.append(f"{c}{C.BOLD}{ch}{C.RESET}")
    return "".join(chars)


def dot_separator(char: str = "·", color: str = C.DIM, count: int = 3) -> str:
    """点状分隔符，如 ···"""
    return f" {color}{char * count}{C.RESET} "


# ══════════════════════════════════════════════════════════════
#  呼吸边框 — 动态箱体边框
# ══════════════════════════════════════════════════════════════

@dataclass
class BreathingBorder:
    """呼吸边框 — 可动画化的箱体边框

    用法:
        border = BreathingBorder("七兽觉醒")
        for frame in border.animate(steps=6):
            print(frame)
            time.sleep(0.15)
    """
    title: str = ""
    width: int = 60
    color: str = C.CRUX_C
    style: str = "rounded"  # rounded | sharp | double | heavy

    _BOX_STYLES = {
        "rounded":  ("╭", "╮", "╰", "╯", "─", "│"),
        "sharp":    ("┌", "┐", "└", "┘", "─", "│"),
        "double":   ("╔", "╗", "╚", "╝", "═", "║"),
        "heavy":    ("┏", "┓", "┗", "┛", "━", "┃"),
    }

    def _box(self) -> tuple:
        return self._BOX_STYLES.get(self.style, self._BOX_STYLES["rounded"])

    def render(self, breathe: float = 1.0) -> str:
        """渲染边框，breathe=0.0~1.0 控制呼吸强度

        breathe 影响边框颜色亮度（模拟呼吸）
        """
        tl, tr, bl, br, h, v = self._box()
        c = self.color
        dim = max(0.3, breathe)
        # 调暗颜色 — 通过 ANSI 亮度模拟
        bright = C.BOLD if breathe > 0.7 else C.DIM_C if breathe < 0.4 else ""

        title_str = ""
        if self.title:
            title_str = f" {self.title} "

        # 上边框
        left_gap = 2
        top = f"{c}{bright}{tl}{h * left_gap}{title_str}{h * (self.width - left_gap - len(title_str) - 2)}{tr}{C.RESET}"
        # 下边框
        bot = f"{c}{bright}{bl}{h * self.width}{br}{C.RESET}"
        return f"{top}\n{bot}"

    def animate(self, steps: int = 8, interval: float = 0.1) -> Generator[str, None, None]:
        """生成呼吸动画帧序列"""
        for i in range(steps):
            breathe = 0.3 + 0.7 * abs((i % steps) / (steps / 2) - 1)
            yield self.render(breathe=breathe)


def breathing_box(
    lines: list[str],
    title: str = "",
    color: str = C.CRUX_C,
    style: str = "rounded",
    padding: int = 1,
) -> str:
    """静态呼吸风格箱体 — 一次性渲染带内容的盒子"""
    border = BreathingBorder(title=title, color=color, style=style)
    tl, tr, bl, br, h, v = border._box()
    c = color
    r = C.RESET
    max_w = max((len(l) for l in lines), default=0) if lines else 20
    inner_w = max_w + padding * 2

    title_str = f" {title} " if title else ""
    top = f"{c}{tl}{h * 2}{title_str}{h * (inner_w - len(title_str) - 1)}{tr}{r}"
    mid = "\n".join(
        f"{c}{v}{r} {' ' * padding}{l}{' ' * (inner_w - len(l) - padding)}{c}{v}{r}"
        for l in lines
    )
    bot = f"{c}{bl}{h * inner_w}{br}{r}"
    return f"{top}\n{mid}\n{bot}"


# ══════════════════════════════════════════════════════════════
#  打字机效果
# ══════════════════════════════════════════════════════════════

def typewriter(
    text: str,
    color: str = C.WHITE,
    char_interval: float = 0.03,
    line_interval: float = 0.1,
    end_with_newline: bool = True,
) -> Generator[str, None, None]:
    """打字机效果生成器 — 逐字/逐行输出

    Yields:
        每步输出带 ANSI 的字符串
    """
    for i, ch in enumerate(text):
        if ch == "\n":
            if end_with_newline:
                yield "\n"
            if line_interval:
                time.sleep(line_interval)
        else:
            yield f"{color}{ch}{C.RESET}"
            if char_interval:
                time.sleep(char_interval)


# ══════════════════════════════════════════════════════════════
#  状态指示器
# ══════════════════════════════════════════════════════════════

def status_dot(status: str = "idle") -> str:
    """状态指示器小圆点

    Args:
        status: idle | busy | ok | error | warn

    Returns:
        带颜色的圆点 + 状态文字
    """
    dots = {
        "idle":  (C.GRAY,   "○"),
        "busy":  (C.CRUX_C, "◉"),
        "ok":    (C.CRUX_G, "●"),
        "error": (C.CRUX_R, "●"),
        "warn":  (C.CRUX_Y, "◉"),
        "off":   (C.DIM,    "○"),
    }
    color, dot = dots.get(status, dots["idle"])
    return f"{color}{dot}{C.RESET}"


# ══════════════════════════════════════════════════════════════
#  保留的原有功能（向下兼容）
# ══════════════════════════════════════════════════════════════

def divider(char: str = "═", color: str = C.DIM, title: str = "") -> None:
    """水平分隔线"""
    width = shutil.get_terminal_size().columns
    if title:
        title_str = f" {title} "
        mid = f"{color}{C.DIM}{char * 2}{C.RESET}{title_str}{color}{C.DIM}{char * (width - len(title_str) - 4)}{C.RESET}"
        print(mid)
    else:
        print(f"{color}{C.DIM}{char * width}{C.RESET}")


def progress_bar(percent: int, width: int = 30, color: str = "") -> str:
    """进度条

    Args:
        percent: 0-100
        width: 条宽度（字符数）
        color: ANSI 颜色码

    Returns:
        渲染好的进度条字符串
    """
    if not color:
        if percent < 33:
            color = C.CRUX_R
        elif percent < 66:
            color = C.CRUX_Y
        else:
            color = C.CRUX_G

    filled = int(percent / 100 * width)
    bar = f"{color}{'█' * filled}{C.DIM}{'▒' * (width - filled)}{C.RESET}"
    return f"{bar} {color}{C.BOLD}{percent:>3}%{C.RESET}"


def gradient_progress_bar(percent: int, width: int = 30) -> str:
    """渐变进度条 — 用 gradient_text 渲染"""
    filled = int(percent / 100 * width)
    empty_w = width - filled
    colors = [(255, 85, 85), (255, 213, 0), (0, 255, 170)]
    filled_part = gradient_text("█" * filled, colors=colors) if filled > 0 else ""
    empty_part = f"{C.DIM}{'▒' * empty_w}{C.RESET}" if empty_w > 0 else ""
    return f"{filled_part}{empty_part} {gradient_text(f'{percent:>3}%', colors=colors)}"


def big_banner() -> str:
    """大字 banner — 像素风格 CRUX logo"""
    return f"""\
{C.CRUX_C}{C.BOLD}
   ██████  ██████  ██    ██ ██   ██
  ██       ██   ██  ██  ██   ██ ██
  ██   ███ ██████    ████     ███
  ██    ██ ██   ██    ██     ██ ██
   ██████  ██   ██    ██    ██   ██
{C.RESET}"""


def small_banner() -> str:
    """小号 banner"""
    return f"""\
{C.CRUX_P}{C.BOLD}  ⚡ CRUX Studio — 七兽引擎 v5.0 {C.RESET}"""


def beast_art() -> str:
    """七兽图腾 ASCII art"""
    return f"""\
{C.CRUX_R}   ╔══════════════════════════════╗
{C.CRUX_R}   ║  {C.CRUX_C}⚡ 白虎 {C.CRUX_G}青龙 {C.CRUX_B}朱雀 {C.CRUX_Y}玄武{C.CRUX_R}   ║
{C.CRUX_R}   ║  {C.CRUX_O}麒麟 {C.CRUX_P}螣蛇 {C.CRUX_C}应龙{C.CRUX_R}          ║
{C.CRUX_R}   ╚══════════════════════════════╝{C.RESET}"""


def toolchain_display() -> None:
    """工具链展示"""
    tools = [
        ("py",  "Python",   C.CRUX_B),
        ("js",  "Node.js",  C.CRUX_G),
        ("sh",  "Shell",    C.CRUX_Y),
        ("go",  "Golang",   C.CRUX_C),
        ("rs",  "Rust",     C.CRUX_O),
        ("db",  "SQL",      C.CRUX_P),
    ]
    line = "  ".join(
        f"{c}{C.BOLD}[{name}]{C.RESET}" for _, name, c in tools
    )
    print(f"  {line}")


# ══════════════════════════════════════════════════════════════
#  动画演示 — 展示所有新功能
# ══════════════════════════════════════════════════════════════

def demo_animate_frames(duration: float = 3.0) -> None:
    """演示各种动画帧"""
    anims = [
        ("Braille",    AnimatedFrames.spinner()),
        ("Block",      AnimatedFrames.block_pulse()),
        ("DotPulse",   AnimatedFrames.dot_pulse()),
        ("Wave",       AnimatedFrames.wave()),
        ("BeastEye",   AnimatedFrames.beast_eye()),
    ]
    end = time.perf_counter() + duration
    while time.perf_counter() < end:
        parts = []
        for name, af in anims:
            parts.append(f"{C.DIM}{name}:{C.RESET}{af.next()}")
        print(f"\r{'  '.join(parts)}", end="", flush=True)
        time.sleep(0.08)
    print()


def demo_gradient() -> None:
    """演示渐变文本"""
    print()
    print(gradient_text("  七兽觉醒 · SEVEN BEASTS AWAKEN  ",
                        colors=[(255, 85, 85), (255, 213, 0), (0, 255, 170), (0, 170, 255), (200, 100, 255)],
                        bold=True))
    print(gradient_text("  白虎炼骨 · 青龙通脉 · 朱雀开眼 · 玄武披甲  ",
                        colors=[(255, 85, 85), (0, 255, 170), (0, 170, 255), (255, 213, 0)],
                        bold=False))
    print()


def demo_badges() -> None:
    """演示各种 Badge 风格"""
    print(f"  {C.DIM}// Badge 风格展示{RESET}")
    styles = [
        ("minimal",  "七兽",   C.CRUX_C),
        ("glow",     "白虎",   C.CRUX_R),
        ("tagged",   "青龙",   C.CRUX_G),
        ("bordered", "朱雀",   C.CRUX_B),
        ("icon",     "麒麟",   C.CRUX_O, "⚡"),
    ]
    for style_args in styles:
        kwargs = {"label": style_args[1], "color": style_args[2]}
        if len(style_args) > 3:
            kwargs["icon"] = style_args[3]
        badge = render_badge(style=style_args[0], **kwargs)
        for line in badge.split("\n"):
            if line.strip():
                print(f"    {line}")


def demo_particles() -> None:
    """演示粒子特效"""
    print(f"  {C.DIM}粒子线:{C.RESET}")
    print(f"    {particle_line(50, density=0.4)}")
    print(f"  {C.DIM}闪烁星线:{C.RESET}")
    print(f"    {sparkle_line(50)}")


def demo_breathing_border() -> None:
    """演示呼吸边框"""
    print(f"  {C.DIM}呼吸边框:{C.RESET}")
    box = breathing_box(
        ["  七兽引擎 · 终端美学升级  ", "  动态 · Badge · 艺术感      "],
        title=" CRUX ",
        color=C.CRUX_C,
        style="rounded",
    )
    print(f"  {box}")


def demo_progress() -> None:
    """演示渐变进度条"""
    print(f"  {C.DIM}渐变进度条:{C.RESET}")
    for pct in [15, 33, 50, 72, 100]:
        print(f"    {gradient_progress_bar(pct, 30)}")


def demo() -> None:
    """全功能演示"""
    reset = C.RESET
    width = shutil.get_terminal_size().columns

    print()
    print(" " * 6 + gradient_text("✦  七 兽 艺 术 引 擎  v3  ✦",
                                   colors=[(255,85,85), (255,213,0), (0,255,170), (0,170,255), (200,100,255)],
                                   bold=True))
    print()

    divider("═", C.DIM, "动画帧 ANIMATED FRAMES")
    demo_animate_frames(2.0)
    print()

    divider("═", C.DIM, "渐变文本 GRADIENT")
    demo_gradient()

    divider("═", C.DIM, "Badge 系统 BADGES")
    demo_badges()
    print()

    divider("═", C.DIM, "粒子特效 PARTICLES")
    demo_particles()
    print()

    divider("═", C.DIM, "呼吸边框 BREATHING BORDER")
    demo_breathing_border()
    print()

    divider("═", C.DIM, "进度条 PROGRESS")
    demo_progress()
    print()

    divider("═", C.DIM, "七兽图腾 BEAST ART")
    print()
    print(f"  {beast_art()}")
    print()

    divider("═", C.DIM)

    # 结尾 — 渐变签名
    print()
    print(" " * 4 + gradient_text("✦  CRUX Studio · 七兽引擎 · 终端美学  ✦",
                                   colors=[(200,100,255), (0,170,255), (0,255,170)],
                                   bold=True))
    print(f"  {C.DIM}  {particle_line(50, density=0.2, colors=[C.CRUX_C, C.CRUX_P, C.CRUX_G])}")
    print(f"  {C.DIM}  >> 就绪 · 随时号令 <<{C.RESET}")
    print()


if __name__ == "__main__":
    demo()
