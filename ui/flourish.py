"""CRUX flourish — terminal animations, themes, and decorative effects.

All effects are pure Python (no extra dependencies). Colors sourced from ui.theme.COLORS.
"""

from __future__ import annotations

import math
import time
from typing import Callable

from ui.theme import COLORS

__all__ = [
    "BeastTheme",
    "Spinner",
    "ParticleBurst",
    "DayNightPalette",
    "BEAST_THEMES",
    "BEAST_ASCII",
    "SPLASH_FRAMES",
]


# ═══════════════════════════════════════════════════════════════
# Beast themes — /beast <name> switches the accent palette
# ═══════════════════════════════════════════════════════════════

class BeastTheme:
    """A named colour scheme derived from one of the seven beasts."""

    def __init__(
        self,
        name: str,
        icon: str,
        primary: str,
        accent: str,
        glow: str,
        border: str,
        label: str,
    ):
        self.name = name
        self.icon = icon
        self.primary = primary
        self.accent = accent
        self.glow = glow
        self.border = border
        self.label = label


BEAST_THEMES: dict[str, BeastTheme] = {
    "baihu": BeastTheme(
        "baihu", "◆", COLORS["baihu"], "#C8932A",
        "#E3B341", COLORS["baihu"], "白虎 · 金 · 权威",
    ),
    "qinglong": BeastTheme(
        "qinglong", "◇", COLORS["qinglong"], "#3A7FD6",
        "#58A6FF", COLORS["qinglong"], "青龙 · 木 · 智慧",
    ),
    "zhuque": BeastTheme(
        "zhuque", "◈", COLORS["zhuque"], "#D95F3E",
        "#F78166", COLORS["zhuque"], "朱雀 · 火 · 创意",
    ),
    "xuanwu": BeastTheme(
        "xuanwu", "◎", COLORS["xuanwu"], "#5A65B6",
        "#7B85D6", COLORS["xuanwu"], "玄武 · 水 · 守护",
    ),
    "qilin": BeastTheme(
        "qilin", "●", COLORS["qilin"], "#2A8A3A",
        "#3FB950", COLORS["qilin"], "麒麟 · 土 · 创造",
    ),
    "tengshe": BeastTheme(
        "tengshe", "◆", COLORS["tengshe"], "#B06820",
        "#DB8A3A", COLORS["tengshe"], "螣蛇 · 火 · 记忆",
    ),
    "yinglong": BeastTheme(
        "yinglong", "◇", COLORS["yinglong"], "#85A8C4",
        "#A5C8E4", COLORS["yinglong"], "应龙 · 风 · 调度",
    ),
}

DEFAULT_BEAST = "qinglong"


# ═══════════════════════════════════════════════════════════════
# Beast ASCII mini-glyphs (used in splash and header)
# ═══════════════════════════════════════════════════════════════

BEAST_ASCII: dict[str, str] = {
    "baihu": r"""
    /\_/\
   ( o.o )   BAIHU
    > ^ <    White Tiger · Authority
""",
    "qinglong": r"""
    /^^^\
   <  o  >   QINGLONG
    \___/    Azure Dragon · Wisdom
""",
    "zhuque": r"""
   \|/
  --o--     ZHUQUE
   /|\      Vermilion Bird · Creation
""",
    "xuanwu": r"""
   .---.
  /  o  \   XUANWU
  \_____/   Black Tortoise · Guardian
""",
    "qilin": r"""
    /\
   (oo)      QILIN
   /""\      Kirin · Creation
""",
    "tengshe": r"""
   >--->
  ( O O )   TENGSHE
   \_-_/    Flying Serpent · Memory
""",
    "yinglong": r"""
   .,,,.
  (o   o)   YINGLONG
   '---'    Winged Dragon · Planner
""",
}


# ═══════════════════════════════════════════════════════════════
# Splash screen frame sequence
# ═══════════════════════════════════════════════════════════════

SPLASH_FRAMES = [
    r"""
         ██████╗██████╗ ██╗   ██╗██╗  ██╗
        ██╔════╝██╔══██╗██║   ██║╚██╗██╔╝
        ██║     ██████╔╝██║   ██║ ╚███╔╝
        ██║     ██╔══██╗██║   ██║ ██╔██╗
        ╚██████╗██║  ██║╚██████╔╝██╔╝ ██╗
         ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
""",
    r"""
         ██████╗██████╗ ██╗   ██╗██╗  ██╗
        ██╔════╝██╔══██╗██║   ██║╚██╗██╔╝
        ██║     ██████╔╝██║   ██║ ╚███╔╝   ◆ 七兽融合
        ██║     ██╔══██╗██║   ██║ ██╔██╗
        ╚██████╗██║  ██║╚██████╔╝██╔╝ ██╗
         ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
""",
    r"""
         ██████╗██████╗ ██╗   ██╗██╗  ██╗
        ██╔════╝██╔══██╗██║   ██║╚██╗██╔╝
        ██║     ██████╔╝██║   ██║ ╚███╔╝   ◆ 七兽融合 · AI-Native Studio
        ██║     ██╔══██╗██║   ██║ ██╔██╗
        ╚██████╗██║  ██║╚██████╔╝██╔╝ ██╗
         ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
""",
]


# ═══════════════════════════════════════════════════════════════
# Animated spinner
# ═══════════════════════════════════════════════════════════════

class Spinner:
    """Thread-safe spinning animation for the status bar.

    Usage::

        spin = Spinner()
        spin.start()
        # ... in UI render loop ...
        status = f"● model  {spin.frame()}  generating..."
        spin.stop()
    """

    FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    PULSE = ["●", "○", "◌", "○"]  # breathing dot

    def __init__(self, style: str = "braille"):
        self._idx = 0
        self._frames = self.FRAMES if style == "braille" else self.PULSE
        self._start = 0.0

    def start(self) -> None:
        self._start = time.time()

    def stop(self) -> None:
        self._start = 0.0

    @property
    def active(self) -> bool:
        return self._start > 0

    def frame(self) -> str:
        if not self.active:
            return ""
        # Advance based on elapsed wall-clock time (60fps feel)
        elapsed = time.time() - self._start
        idx = int(elapsed * 8) % len(self._frames)
        return self._frames[idx]

    def pulse(self) -> str:
        """Breathing dot — brighter when active."""
        if not self.active:
            return "●"
        elapsed = time.time() - self._start
        # Sine-wave opacity approximation via character choice
        phase = (math.sin(elapsed * 3.0) + 1) / 2  # 0..1
        if phase > 0.75:
            return "●"
        elif phase > 0.5:
            return "◉"
        elif phase > 0.25:
            return "○"
        return "◌"


# ═══════════════════════════════════════════════════════════════
# Particle burst (success sparkles / error flash)
# ═══════════════════════════════════════════════════════════════

class ParticleBurst:
    """Generates short-lived decorative text particles.

    Usage::

        burst = ParticleBurst.success()
        # renders as "  ✦ ✧ ♥ ✦  "

        burst = ParticleBurst.error()
        # renders as "  ╳ ╳ ╳  "
    """

    CONFETTI = ["🎉", "✨", "🌟", "💫", "⭐", "🎊", "🎆", "✨", "🌟", "💫"]

    SUCCESS_PARTICLES = ["✦", "✧", "♥", "★", "✶", "♡", "♦"]
    ERROR_PARTICLES = ["╳", "✗", "⬥", "▨"]
    SPARK_PARTICLES = ["·", "•", "✧", "·"]

    def __init__(self, particles: list[str], length: int = 7):
        self._particles = particles
        self._length = length
        self._frame = 0

    @classmethod
    def success(cls) -> ParticleBurst:
        return cls(cls.SUCCESS_PARTICLES, length=5)

    @classmethod
    def error(cls) -> ParticleBurst:
        return cls(cls.ERROR_PARTICLES, length=3)

    @classmethod
    def sparkle(cls) -> ParticleBurst:
        return cls(cls.SPARK_PARTICLES, length=5)

    @classmethod
    def confetti(cls) -> ParticleBurst:
        """Big celebration burst for major successes."""
        return cls(cls.CONFETTI, length=10)

    def render(self) -> str:
        """Return one frame of the burst animation."""
        import random
        seed = int(time.time() * 10) + self._frame
        rng = random.Random(seed)
        chars = [rng.choice(self._particles) for _ in range(self._length)]
        self._frame += 1
        return " ".join(chars)


# ═══════════════════════════════════════════════════════════════
# Day / night palette
# ═══════════════════════════════════════════════════════════════

class DayNightPalette:
    """Returns a (slightly) adjusted palette based on system hour.

    Night (18:00–06:00): deeper base, warmer accents, reduced blue light
    Day   (06:00–18:00): standard Dark Atelier
    """

    @staticmethod
    def is_night() -> bool:
        hour = time.localtime().tm_hour
        return hour >= 18 or hour < 6

    @classmethod
    def adjust(cls, colors: dict) -> dict:
        """Return a copy of *colors* with night-mode tweaks."""
        if not cls.is_night():
            return dict(colors)

        c = dict(colors)
        # Warm the base tones slightly, dim blue-heavy accents
        c["base"] = "#0A0E14"          # deeper black
        c["surface"] = "#12161D"       # warmer dark
        c["text"] = "#F0E6D3"          # slight warm tint
        c["text_secondary"] = "#9B9280"
        c["primary"] = "#D29922"       # gold instead of blue
        c["accent"] = "#C8932A"
        c["info"] = "#D29922"
        c["input_prompt"] = "#D29922"
        c["input_cursor"] = "#D29922"
        c["qinglong"] = "#6B8DBF"      # muted blue
        c["badge_code"] = "#6B8DBF"
        return c


# ═══════════════════════════════════════════════════════════════
# Prompt glow — color-cycling the input prompt character
# ═══════════════════════════════════════════════════════════════

class PromptGlow:
    """Cycles through accent colours for the › prompt hint.

    Usage::

        glow = PromptGlow()
        # In render loop:
        prompt_color = glow.current()
    """

    ACCENT_KEYS = ["primary", "accent", "zhuque", "qilin", "baihu"]

    def __init__(self, speed: float = 0.8):
        self._speed = speed
        self._start = time.time()

    def current(self) -> str:
        """Return the current glow color hex."""
        elapsed = time.time() - self._start
        idx = int(elapsed * self._speed) % len(self.ACCENT_KEYS)
        key = self.ACCENT_KEYS[idx]
        return COLORS.get(key, COLORS["primary"])
