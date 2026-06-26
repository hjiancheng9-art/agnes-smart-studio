"""Organic animation and transition effects for terminal output v3.
v3: All effects fully functional with real Rich output.
Provides visual feedback for mode switches, generation completion,
thinking states. Only use in non-streaming contexts.
Effects: splash / typewriter / spin / progress_bar / pulse_border /
         sparkle_burst / divider / fade_in / success_pulse / thinking_dots
"""

import random
import sys
import time

from ui.theme import COLORS, ICONS, console

__all__ = [
    "fade_in",
    "success_pulse",
    "thinking_dots",
    "progress_bar",
    "spin",
    "typewriter",
    "splash_screen",
    "divider",
    "pulse_border",
    "sparkle_burst",
]


def fade_in(content: str, duration: float = 0.4, steps: int = 5):
    """Rich 文本淡入 — 逐次增加亮度。"""
    for i in range(1, steps + 1):
        style = "dim" if i < steps // 2 else ("default" if i < steps else "bold")
        console.print(f"[{style}]{content}[/]")
        time.sleep(duration / steps)


def success_pulse(icon: str = "★", count: int = 3, interval: float = 0.12):
    """成功脉冲闪烁。"""
    chars = ["  ", f"[{COLORS['success']}]{icon}[/]"]
    for _ in range(count * 2):
        sys.stdout.write(f"\r{chars[_ % 2]}")
        sys.stdout.flush()
        time.sleep(interval)
    sys.stdout.write(f"\r[{COLORS['success']}]{icon} Done![/]\n")
    sys.stdout.flush()


def thinking_dots(count: int = 4, interval: float = 0.3):
    """思考点动画: thinking . .. ... ...."""
    for i in range(count + 1):
        dots = "." * i
        sys.stdout.write(f"\r[{COLORS['transition']}]thinking{dots}[/]   ")
        sys.stdout.flush()
        time.sleep(interval)
    sys.stdout.write("\r" + " " * 20 + "\r")
    sys.stdout.flush()


def progress_bar(label: str, total: float, width: int = 30, color: str = "primary"):
    """返回 Rich Progress 实例 + task ID，调用方自行控制."""
    from rich.progress import BarColumn, Progress, TextColumn

    p = Progress(
        TextColumn(f"[{color}]{label}[/]"),
        BarColumn(complete_style=color, finished_style="success"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    )
    task = p.add_task("", total=total)
    return p, task


def spin(message: str, duration: float = 1.5, style: str = "primary"):
    """旋转等待指示器 — 功能完整。"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    start = time.time()
    i = 0
    while time.time() - start < duration:
        sys.stdout.write(f"\r  [{style}]{frames[i % 10]}[/] {message}  ")
        sys.stdout.flush()
        time.sleep(0.08)
        i += 1
    sys.stdout.write(f"\r  [{COLORS['success']}]✓[/] {message}  [dim]done[/]\n")
    sys.stdout.flush()


def typewriter(text: str, delay: float = 0.015, style: str = ""):
    """打字机逐字输出。"""
    for ch in text:
        if style:
            console.print(ch, end="", style=style, highlight=False)
        else:
            sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def splash_screen():
    """CRUX 启动闪屏 — 五行色条 + Logo 面板。"""
    from ui.beautify import splash_full

    splash_full()


def divider(char: str = "─", length: int = 50, style: str = "muted"):
    console.print(char * length, style=style)


def pulse_border(message: str, pulses: int = 3, style: str = "accent"):
    """脉冲边框 — 消息在发光的框中闪烁。"""
    from rich.panel import Panel

    for i in range(pulses):
        b = COLORS[style] if i == pulses - 1 else COLORS["muted"]
        console.print(Panel(message, border_style=b, padding=(0, 2)))
        if i < pulses - 1:
            time.sleep(0.2)
    console.print(f"[bold {style}]{ICONS['star']} {message} {ICONS['star']}[/]")


def sparkle_burst(message: str, count: int = 7):
    """星光爆发 — 彩色粒子向外扩散。"""
    particles = ["✦", "✧", "⋆", "✶", "⁕", "·", "•", "∘"]
    colours = ["primary", "accent", "highlight", "success", "warning", "transition"]
    for _ in range(count):
        p = random.choice(particles)
        c = random.choice(colours)
        sys.stdout.write(f"[{c}]{p} [/]")
        sys.stdout.flush()
        time.sleep(0.05)
    console.print(f"\n[bold accent]{ICONS['star']} {message} {ICONS['star']}[/]")
