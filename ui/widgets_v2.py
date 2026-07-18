"""CRUX TUI v2 — Reusable widgets.

Components:
  Spinner      — animated braille spinner for activity indication
  Panel        — box-drawing border helpers
  WelcomeScreen — pixel-art welcome display (integrated in message area)
  ThinkingPanel — collapsible chain-of-thought display
"""

from __future__ import annotations

import contextlib
import threading
import time
import unicodedata
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples

if TYPE_CHECKING:
    from collections.abc import Callable

# ══════════════════════════════════════════════════════════════════
#  Spinner — animated braille spinner
# ══════════════════════════════════════════════════════════════════

BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Animated braille spinner for activity indication.

    Runs a background thread that advances the frame every 80ms.
    Callers provide an `on_tick` callback that triggers UI repaint.
    """

    def __init__(self, on_tick: Callable[[], None]) -> None:
        self._frame = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._on_tick = on_tick
        self._lock = threading.Lock()

    @property
    def current(self) -> str:
        with self._lock:
            return BRAILLE_FRAMES[self._frame % len(BRAILLE_FRAMES)]

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _spin(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    break
            self._frame += 1
            with contextlib.suppress(Exception):
                self._on_tick()
            time.sleep(0.08)


# ══════════════════════════════════════════════════════════════════
#  Box-drawing constants
# ══════════════════════════════════════════════════════════════════

# Single-line
_SL_TL, _SL_TR, _SL_BL, _SL_BR = "┌", "┐", "└", "┘"
_SL_H, _SL_V = "─", "│"
_SL_LEFT_T = "├"
_SL_RIGHT_T = "┤"
_SL_BOT_T = "┴"
_SL_TOP_T = "┬"
_SL_CROSS = "┼"

# Double-line
_DL_TL, _DL_TR, _DL_BL, _DL_BR = "╔", "╗", "╚", "╝"
_DL_H, _DL_V = "═", "║"
_DL_LEFT_T = "╠"
_DL_RIGHT_T = "╣"
_DL_BOT_T = "╩"
_DL_TOP_T = "╦"
_DL_CROSS = "╬"


def _vw(s: str) -> int:
    """Visual width — CJK chars = 2 cells."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _cjk_trunc(txt: str, mw: int) -> str:
    """Truncate string to fit max visual width."""
    if _vw(txt) <= mw:
        return txt
    acc = ""
    aw = 0
    for c in txt:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if aw + cw > mw:
            break
        acc += c
        aw += cw
    return acc


def panel_top(title: str, width: int, double: bool = False) -> str:
    """Top border of a panel with title: ┌─ Title ──────────┐"""
    if double:
        h, tl, tr = _DL_H, _DL_TL, _DL_TR
    else:
        h, tl, tr = _SL_H, _SL_TL, _SL_TR
    inner = width - 2
    if inner >= _vw(title) + 4:
        left_pad = 2
        right_pad = inner - _vw(title) - left_pad - 2
        return f"{tl}{h * left_pad} {title} {h * right_pad}{tr}"
    if inner >= 2:
        return f"{tl}{_cjk_trunc(title, inner - 2):^{inner}}{tr}"
    return f"{tl}{tr}"


def panel_bottom(width: int, double: bool = False) -> str:
    """Bottom border: └────────────────────┘"""
    if double:
        return f"{_DL_BL}{_DL_H * (width - 2)}{_DL_BR}"
    return f"{_SL_BL}{_SL_H * (width - 2)}{_SL_BR}"


def panel_line(text: str, width: int, double: bool = False) -> str:
    """A content line with side borders: │ text               │"""
    v = _DL_V if double else _SL_V
    content = _cjk_trunc(text, width - 4)
    return f"{v} {content}{' ' * max(0, width - _vw(content) - 4)} {v}"


def h_line(width: int, double: bool = False) -> str:
    """Horizontal separator line."""
    return (_DL_H if double else _SL_H) * width


# ══════════════════════════════════════════════════════════════════
#  Welcome Screen — CRUX pixel-art welcome (FormattedText)
# ══════════════════════════════════════════════════════════════════

# Pixel art CRUX logo (from terminal_splash.py)
CRUX_PIXEL = [
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "  ████████████    ████████████    ████████████    ████████████  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ████░░░░████  ",
    " ████░░░░░░████  ██████████      ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ██████████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░░████     ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ██░░░░░░░░██  ",
    "  ████████████    ████████████    ████░░░░████    ██░░░░░░░░██  ",
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "                                ",
]


def build_welcome_formatted(
    model_name: str = "",
    cwd: str = "",
    branch: str = "",
    palette: dict | None = None,
) -> FormattedText:
    """Build welcome — responsive layout: TW-driven 3-column grid.

    If *palette* is given (a dict like BLADE / LAVA / JADE / POLAR_NIGHT),
    derive inline colors from it.  Otherwise fall back to Catppuccin Mocha.
    """
    import os as _os
    import shutil

    from core.version import __version__ as _ver

    _model = model_name or "deepseek-v4-flash"
    _branch = branch or "main"
    _home = _os.path.expanduser("~")
    _cwd = cwd
    if _cwd.startswith(_home):
        _cwd = "~" + _cwd[len(_home) :]
    if len(_cwd) > 28:
        _cwd = "..." + _cwd[-25:]

    TW = shutil.get_terminal_size().columns
    TW = max(60, min(120, TW))
    CW = TW - 4  # content width (2px margin each side)

    if palette:
        PX = palette  # shorthand
        B = f"bold fg:{PX['accent']}"
        P = f"bold fg:{PX['crux']}"
        G = f"bold fg:{PX['success']}"
        R = f"bold fg:{PX['error']}"
        Y = f"bold fg:{PX['warning']}"
        T = f"bold fg:{PX.get('info', PX.get('accent2', PX['accent']))}"
        M = f"fg:{PX['muted']}"
        W = f"fg:{PX['primary']}"
        S = f"fg:{PX['dim']}"
        A = f"bold fg:{PX.get('accent2', PX['warning'])}"
    else:
        B = "bold fg:#89B4FA"
        P = "bold fg:#CBA6F7"
        G = "bold fg:#A6E3A1"
        R = "bold fg:#F38BA8"
        Y = "bold fg:#F9E2AF"
        T = "bold fg:#94E2D5"
        M = "fg:#7F849C"
        W = "fg:#CDD6F4"
        S = "fg:#45475A"
        A = "bold fg:#FAB387"

    def clamp_box_width(width: int, terminal_width: int = TW, x: int = 0, margin: int = 2) -> int:
        return max(10, min(width, terminal_width - x - margin))

    lines: list[StyleAndTextTuples] = []
    L = lines.append

    def sp(n):
        return " " * max(0, n)

    def _vw(s: str) -> int:
        """Visual width — CJK = 2 cells."""
        return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)

    # ── Title ──
    L(
        [
            (Y, "  CRUX Studio"),
            (M, f"  v{_ver}"),
            (M, "  ·  "),
            (W, "工程搭档"),
            (M, "  ·  "),
            (B, "DeepSeek V4 Flash"),
            (M, "  ·  "),
            (T, "1M上下文"),
            (M, "  ·  "),
            (G, "● ready"),
        ]
    )
    L([("", "\n")])

    # ── Badge bar ──
    def _badge(sty: str, label: str, w: int = 0) -> StyleAndTextTuples:
        """Build a pill-badge:  [label]  with colored bracket."""
        return [(S, "["), (sty, label), (S, "] ")]

    _bb: StyleAndTextTuples = []
    _bb.extend(_badge(B, f" {_model} "))
    _bb.extend(_badge(P, f" {_branch} "))
    _bb.extend(_badge(G, " 1M context "))
    _bb.extend(_badge(T, f" v{_ver} "))
    _bb.extend(_badge(A, " 34 skills · 121 pkgs "))
    _bb.append((S, sp(CW - sum(len(x[1]) + 2 for x in _bb) - 2)))
    L([("", "  "), *_bb])
    L([("", "\n")])
    L([(S, "  " + "─" * (CW - 2))])
    L([("", "\n\n")])

    # ═══════ 3-column grid ═══════
    col_w = clamp_box_width((CW - 4) // 3, CW)
    c3_w = clamp_box_width(CW - col_w * 2 - 4, CW, x=col_w * 2 + 4)
    # ── safe width clamping: final check ──
    col_w = clamp_box_width(col_w, CW)
    c3_w = clamp_box_width(c3_w, CW, x=col_w * 2 + 4)
    c1_x = 2
    c2_x = c1_x + col_w + 2
    c2_x + col_w + 2

    def btop(title, w):
        w = clamp_box_width(max(14, w), CW)
        return f"╭─ {title} {'─' * max(0, w - _vw(title) - 5)}╮"

    def bbot(w):
        w = clamp_box_width(max(4, w), CW)
        return f"╰{'─' * max(0, w - 2)}╯"

    def row_at(x, sty, txt, w):
        w = clamp_box_width(max(8, w), CW, x=x)
        t = str(txt)
        # Truncate by visual width
        if _vw(t) > w - 4:
            acc = ""
            aw = 0
            for c in t:
                cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                if aw + cw > w - 4:
                    break
                acc += c
                aw += cw
            t = acc
        return (sty, f"{' ' * max(0, x)}{'│'} {t}{' ' * max(0, w - 4 - _vw(t))} │")

    def _cjkt(txt, mw):
        """Truncate string to fit max visual width (CJK=2 cells)."""
        if _vw(txt) <= mw:
            return txt
        a = ""
        aw = 0
        for c in txt:
            cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
            if aw + cw > mw:
                break
            a += c
            aw += cw
        return a

    # Box tops
    r: StyleAndTextTuples = []
    r.extend(
        [(S, btop("Commands", col_w)), ("", "  "), (S, btop("Workspace", col_w)), ("", "  "), (S, btop("System", c3_w))]
    )
    L(
        [
            ("", "  "),
            (S, btop("Commands", col_w)),
            ("", "  "),
            (S, btop("Workspace", col_w)),
            ("", "  "),
            (S, btop("System", c3_w)),
        ]
    )
    L([("", "\n")])

    _cmd = [
        ("/help    commands", B),
        ("/skill   marketplace", P),
        ("/status  overview", B),
        ("/health  diagnostics", B),
        ("/image   generate", T),
    ]
    _wsp = [
        ("/method  methodology", P),
        ("/config  settings", B),
        ("/model   switch model", P),
        ("/chat    new chat", T),
        ("/video   generate", T),
    ]
    _sys = [
        ("● ready", G),
        ("Agent Swarm 并行执行", P),
        ("34 loaded · 121 pkgs · 767 market", W),
        ("理解意图→推理→执行→验证", G),
        ("34 专业技能 · 3963 tests ✓", T),
    ]

    for i in range(5):
        cl, cs = _cmd[i]
        wl, ws = _wsp[i]
        sl, ss = _sys[i]
        cl_t = _cjkt(cl, col_w - 4)
        wl_t = _cjkt(wl, col_w - 4)
        sl_t = _cjkt(sl, c3_w - 4)
        L(
            [
                ("", "  "),
                (S, "│ "),
                (cs, cl_t),
                ("", sp(col_w - 3 - _vw(cl_t))),
                (S, "│"),
                ("", "  "),
                (S, "│ "),
                (ws, wl_t),
                ("", sp(col_w - 3 - _vw(wl_t))),
                (S, "│"),
                ("", "  "),
                (S, "│ "),
                (ss, sl_t),
                ("", sp(c3_w - 3 - _vw(sl_t))),
                (S, "│"),
            ]
        )
        L([("", "\n")])

    L([("", "  "), (S, bbot(col_w)), ("", "  "), (S, bbot(col_w)), ("", "  "), (S, bbot(c3_w))])
    L([("", "\n\n")])

    # ═══════ Welcome (2 cols) + Quick Start (1 col) ═══════
    wl_w = clamp_box_width(col_w * 2 + 2, CW)
    qs_w = clamp_box_width(c3_w, CW, x=wl_w + 2)

    # Helper: build a centered row │ pad + text + pad │ fitting visual width w
    def _wbox_row(sty, txt, w):
        tw = _vw(txt)
        lp = (w - 2 - tw) // 2
        rp = w - 2 - tw - lp
        return (sty, "│" + " " * lp + txt + " " * rp + "│")

    _wel = [
        (S, btop("CRUX Studio", wl_w)),
        _wbox_row(S, "", wl_w),
        _wbox_row(Y, "工程搭档 · 能读能写能跑代码 · 自我纠错", wl_w),
        _wbox_row(S, "", wl_w),
        _wbox_row(W, "平时如刀，出事成阵", wl_w),
        _wbox_row(W, "理解意图 → 深度推理 → 自主执行 → 验证闭环", wl_w),
        _wbox_row(G, f"v{_ver} · 3963 tests ✓ · 0 failures · 自修复", wl_w),
        _wbox_row(A, "Agent Swarm · 自修改 · A/B/C/D 任务分级", wl_w),
        _wbox_row(S, "", wl_w),
        (S, bbot(wl_w)),
    ]
    _qs_items = [
        ("1.", "/method", "load workflow"),
        ("2.", "/model", "choose model"),
        ("3.", "/chat", "start session"),
        ("4.", "/image", "generate img"),
        ("5.", "/video", "generate vid"),
    ]
    _qs = [(S, btop("Quick Start", qs_w))]
    for idx, cmd, desc in _qs_items:
        line = f"│ {idx:<3}{cmd:<8}{desc}"
        _qs.append((M, line + " " * (qs_w - 2 - len(line)) + " │"))
    _qs.append((S, "│" + " " * (qs_w - 2) + "│"))
    _qs.append((S, bbot(qs_w)))

    for i in range(8):
        ws, wt = _wel[i]
        qs, qt = _qs[i]
        L([("", "  "), (ws, wt), ("", "  " + sp(wl_w - _vw(wt))), (qs, qt)])
        L([("", "\n")])

    L([("", "\n")])

    # ═══════ Shortcuts (full width) ═══════
    L([("", "  "), (S, btop("Shortcuts", CW))])
    L([("", "\n")])
    for group in [
        [("Ctrl+V", "paste image"), ("Enter", "send"), ("PgUp/Dn", "scroll"), ("Ctrl+C", "new session")],
        [("Tab", "autocomplete"), ("Mouse", "select"), ("Alt+Enter", "newline"), ("Ctrl+L", "clear")],
    ]:
        r: StyleAndTextTuples = [("", "  "), (S, "│ ")]
        for k, d in group:
            r.extend([(A, f"{k} "), (M, f"{d}  ")])
        r.append(("", sp(CW - 4 - sum(len(k) + len(d) + 4 for k, d in group))))
        r.append((S, "│"))
        L(r)
        L([("", "\n")])
    L([("", "  "), (S, bbot(CW))])
    L([("", "\n\n")])

    # ── Footer ──
    L(
        [
            (R, "  /q quit"),
            ("", "    "),
            (P, "/method methodology"),
            ("", "    "),
            (M, "session"),
            (G, " ready"),
            ("", "    "),
            (M, "Python 3.11"),
            ("", "    "),
            (M, "skills"),
            (P, " 34 loaded"),
        ]
    )

    flat: list[tuple[str, str]] = []
    for line in lines:
        flat.extend(line)
    return FormattedText(flat)


class ThinkingPanel:
    """A collapsible panel that shows model reasoning / thinking steps.

    Features:
    - Auto-expands when thinking content arrives
    - Collapses when thinking completes (or stays open if pinned)
    - Max height capping with "..."
    """

    MAX_LINES = 8  # max visible lines before truncation

    def __init__(self) -> None:
        self._content: str = ""
        self._visible: bool = False
        self._pinned: bool = False
        self._lock = threading.Lock()

    @property
    def visible(self) -> bool:
        with self._lock:
            return self._visible

    @property
    def content(self) -> str:
        with self._lock:
            return self._content

    @property
    def has_content(self) -> bool:
        with self._lock:
            return bool(self._content)

    def toggle_pin(self) -> None:
        """Toggle whether panel stays visible after thinking completes."""
        with self._lock:
            self._pinned = not self._pinned
            if not self._pinned and not self._content:
                self._visible = False

    def append(self, text: str) -> None:
        """Append text to the thinking buffer. Auto-shows panel."""
        with self._lock:
            # Cap content to prevent memory leak on long thinking sessions
            MAX_CONTENT = 131072  # 128KB — more than enough for thinking traces
            if len(self._content) < MAX_CONTENT:
                self._content += text
            self._visible = True

    def clear(self) -> None:
        """Clear thinking content. Hides panel unless pinned."""
        with self._lock:
            self._content = ""
            if not self._pinned:
                self._visible = False

    def done(self) -> None:
        """Called when thinking is complete. Hides unless pinned."""
        with self._lock:
            if not self._pinned:
                self._visible = False

    def render(self, width: int) -> FormattedText:
        """Render the thinking panel content as FormattedText.

        Returns empty FormattedText when invisible or no content.
        """
        with self._lock:
            if not self._visible or not self._content:
                return FormattedText([])

            pieces: list[tuple[str, str]] = []

            # ── Top border with title ──
            title = " 💭 深度思考 "
            h_rem = max(0, width - len(title) - 4)
            left_w = h_rem // 2
            right_w = h_rem - left_w
            top = f"┌{'─' * left_w}{title}{'─' * right_w}┐"
            top = top[:width] if len(top) > width else top
            pieces.append(("class:thinking-panel-border", top[:width] + "\n"))

            # ── Content lines (capped at MAX_LINES) ──
            # Only render the tail of large content to avoid OOM
            content = self._content
            MAX_BYTES_RENDER = 65536  # 64KB — prevent OOM from huge thinking traces
            if len(content) > MAX_BYTES_RENDER:
                content = content[-MAX_BYTES_RENDER:]
                # Split at first newline to avoid mid-text truncation
                nl = content.find("\n")
                if nl > 0:
                    content = content[nl + 1 :]
            # Split into visual lines based on width
            visual_lines: list[str] = []
            inner = max(1, width - 4)
            for paragraph in content.split("\n"):
                if not paragraph:
                    visual_lines.append("")
                    continue
                # Simple wrap: chop at width boundaries
                while len(paragraph) > inner:
                    visual_lines.append(paragraph[:inner])
                    paragraph = paragraph[inner:]
                visual_lines.append(paragraph)

            shown = visual_lines[-self.MAX_LINES :] if len(visual_lines) > self.MAX_LINES else visual_lines
            for line in shown:
                line_w = len(line)
                pad = max(0, width - line_w - 4)
                pieces.append(("class:thinking-panel-border", "│ "))
                pieces.append(("class:thinking-panel-text", line))
                pieces.append(("class:thinking-panel-border", " " * pad + " │\n"))

            if len(visual_lines) > self.MAX_LINES:
                pieces.append(
                    ("class:thinking-panel-text", f"│ ... (+{len(visual_lines) - self.MAX_LINES} more lines) ... │\n")
                )

            # ── Bottom border ──
            bot = "└" + "─" * (width - 2) + "┘"
            pieces.append(("class:thinking-panel-border", bot[:width] + "\n"))

            return FormattedText(pieces)

    def height(self, width: int) -> int:
        """Calculate the rendered height (0 when invisible)."""
        with self._lock:
            if not self._visible or not self._content:
                return 0
            content = self._content
        inner = max(1, width - 4)
        total_lines = 0
        for paragraph in content.split("\n"):
            if not paragraph:
                total_lines += 1
            else:
                total_lines += max(1, -(-len(paragraph) // inner))  # ceil division
        line_count = min(total_lines, self.MAX_LINES)
        if total_lines > self.MAX_LINES:
            line_count += 1  # for the "...(+N more)" line
        return line_count + 2  # +2 for top/bottom borders


# ══════════════════════════════════════════════════════════════════
#  Context bar — visual progress bar
# ══════════════════════════════════════════════════════════════════


def context_bar(percentage: float, width: int = 10) -> str:
    """Build a visual context usage bar: ████░░░░░░"""
    filled = max(0, min(width, int(percentage / 100 * width)))
    empty = width - filled
    return "█" * filled + "░" * empty


# ══════════════════════════════════════════════════════════════════
#  AnimatedBadge — 动态徽章
# ══════════════════════════════════════════════════════════════════


class AnimatedBadge:
    """动态 Badge — 带帧动画的徽章组件。

    支持与 tui_art.AnimatedFrames 联动，自动渲染动画帧到徽章中。

    Usage:
        badge = AnimatedBadge("白虎", color=C.CRUX_R, icon="⚡")
        badge.render()  # 获取当前帧
        badge.next()    # 前进一帧并返回
    """

    _FRAMES = {
        "pulse": ["◉", "◎", "◉", "◎", "◉"],
        "glow": ["◆", "◇", "◆", "◇", "◆"],
        "breathe": ["⬤", "◍", "○", "◍", "⬤"],
        "scan": ["◐", "◓", "◑", "◒"],
        "blink": ["●", "○", "●", "○"],
    }

    def __init__(
        self,
        label: str,
        color: str = "",
        icon: str = "",
        anim: str = "pulse",
        width: int | None = None,
    ):
        self.label = label
        self.color = color
        self.icon = icon
        self.anim = anim
        self.width = width
        self._frames = self._FRAMES.get(anim, self._FRAMES["pulse"])
        self._idx = 0

    def next(self) -> str:
        """前进一帧并返回渲染后的 badge"""
        self._idx = (self._idx + 1) % len(self._frames)
        return self.render()

    def render(self, frame: str | None = None) -> str:
        """渲染当前帧为 ANSI 字符串"""
        from tui_art import C as _C

        c = self.color or _C.CRUX_C
        dot = frame if frame is not None else self._frames[self._idx]
        icon_str = f"{self.icon} " if self.icon else ""
        label = self.label
        if self.width and len(label) < self.width:
            label = label.ljust(self.width)
        return f"{_C.DIM}[{c}{dot}{_C.DIM}]{_C.RESET} {c}{_C.BOLD}{icon_str}{label}{_C.RESET}"

    def reset(self):
        self._idx = 0


# ══════════════════════════════════════════════════════════════════
#  PulseDot — 脉冲状态点
# ══════════════════════════════════════════════════════════════════


class PulseDot:
    """脉冲状态指示器 — 动态小圆点。

    Usage:
        dot = PulseDot("idle")
        print(dot.render())  # ● 或 ◉ 或 ○
    """

    _STATES = {
        "idle": {"frames": ["○"], "color": ""},
        "busy": {"frames": ["◉", "◎", "◉"], "color": ""},
        "think": {"frames": ["◌", "○", "◌", "○"], "color": ""},
        "ok": {"frames": ["●"], "color": ""},
        "error": {"frames": ["●", "⬤", "●", "⬤"], "color": ""},
        "warn": {"frames": ["◉", "⬤", "◉"], "color": ""},
    }

    def __init__(self, state: str = "idle"):
        self.state = state
        self._idx = 0

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str):
        self._state = value
        self._idx = 0

    def next(self) -> str:
        """前进一帧并返回"""
        return self.render()

    def render(self) -> str:
        """渲染当前帧"""
        from tui_art import C as _C

        info = self._STATES.get(self._state, self._STATES["idle"])
        frames = info["frames"]
        dot = frames[self._idx % len(frames)]
        self._idx = (self._idx + 1) % len(frames)

        color_map = {
            "idle": _C.GRAY,
            "busy": _C.CRUX_C,
            "think": _C.CRUX_B,
            "ok": _C.CRUX_G,
            "error": _C.CRUX_R,
            "warn": _C.CRUX_Y,
        }
        c = color_map.get(self._state, _C.GRAY)
        return f"{c}{dot}{_C.RESET}"


# ══════════════════════════════════════════════════════════════════
#  BreathingLabel — 呼吸文本
# ══════════════════════════════════════════════════════════════════


class BreathingLabel:
    """呼吸文本 — 文本亮度周期性变化。

    Usage:
        label = BreathingLabel("CRUX Studio 就绪")
        print(label.next())  # 每次调用亮度变化
    """

    def __init__(self, text: str, color: str = "", steps: int = 12):
        self.text = text
        self.color = color
        self.steps = steps
        self._idx = 0

    def next(self) -> str:
        """前进并返回呼吸帧"""
        from tui_art import C as _C

        c = self.color or _C.CRUX_C
        t = (self._idx % self.steps) / self.steps
        breathe = 0.3 + 0.7 * (1 - abs(2 * t - 1))
        self._idx += 1

        if breathe > 0.7:
            return f"{c}{_C.BOLD}{self.text}{_C.RESET}"
        if breathe > 0.4:
            return f"{c}{self.text}{_C.RESET}"
        return f"{_C.DIM_C}{c}{self.text}{_C.RESET}"

    def render(self) -> str:
        """渲染当前帧（不前进）"""
        return self.next()

    def reset(self):
        self._idx = 0


# ══════════════════════════════════════════════════════════════════
#  EnhancedSpinner — 增强版 Spinner，更多动画模式
# ══════════════════════════════════════════════════════════════════


class EnhancedSpinner:
    """增强版 Spinner — 支持 8 种动画模式。

    Usage:
        spin = EnhancedSpinner(mode="wave")
        spin.start()
        # ... do work ...
        spin.stop()
        print(spin.current(), end="")
    """

    _MODE_FRAMES = {
        "braille": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "blocks": ["▁", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▁"],
        "wave": ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂", "▁"],
        "arrows": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "dots": ["⡀", "⡄", "⡆", "⡇", "⣇", "⣧", "⣷", "⣿", "⣷", "⣧", "⣇", "⡇", "⡆", "⡄", "⡀"],
        "moon": ["○", "◔", "◐", "◕", "●", "◕", "◐", "◔"],
        "pulse": ["◌", "○", "◉", "●", "◉", "○", "◌"],
        "cross": ["┼", "┽", "╀", "╁", "╂", "╁", "╀", "┽"],
    }

    def __init__(self, mode: str = "braille", interval: float = 0.1):
        self._mode = mode
        self._interval = interval
        self._frames = self._MODE_FRAMES.get(mode, self._MODE_FRAMES["braille"])
        self._idx = 0
        self._running = False
        self._task_id: str | None = None
        self._lock = threading.Lock()

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        self._mode = value
        self._frames = self._MODE_FRAMES.get(value, self._MODE_FRAMES["braille"])
        self._idx = 0

    def current(self) -> str:
        """获取当前帧字符"""
        return self._frames[self._idx]

    def next(self) -> str:
        """前进一帧并返回"""
        self._idx = (self._idx + 1) % len(self._frames)
        return self._frames[self._idx]

    def start(self):
        """启动后台动画线程"""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._idx = 0

        def _spin_loop():
            while self._running:
                self._idx = (self._idx + 1) % len(self._frames)
                time.sleep(self._interval)

        import threading

        self._thread = threading.Thread(target=_spin_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止动画"""
        with self._lock:
            self._running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


# ══════════════════════════════════════════════════════════════════
#  EnhancedProgressBar — 带标签的进度组件
# ══════════════════════════════════════════════════════════════════


class EnhancedProgressBar:
    """增强进度条 — 带 label 和自动颜色。

    Usage:
        bar = EnhancedProgressBar("加载", width=20)
        print(bar.render(42))
    """

    def __init__(self, label: str = "", width: int = 20):
        self.label = label
        self.width = width

    def render(self, percent: int) -> str:
        from tui_art import C as _C
        from tui_art import gradient_progress_bar

        label_str = f"{_C.DIM}{self.label}{_C.RESET} " if self.label else ""
        bar_str = gradient_progress_bar(percent, self.width)
        return f"{label_str}{bar_str}"

    def render_line(self, percent: int) -> str:
        """打印一整行"""
        return "  " + self.render(percent)


# ══════════════════════════════════════════════════════════════════
#  render_status_line — 组合式状态行
# ══════════════════════════════════════════════════════════════════


def render_status_line(
    beast: str = "虎",
    state: str = "idle",
    model: str = "deepseek-v4-flash",
    context_pct: float = 42,
    extra: str = "",
) -> str:
    """一键渲染状态行 — 包含脉冲点 + Badge + 模型 + 进度

    Returns:
        带 ANSI 的状态行字符串
    """
    from tui_art import C as _C

    dot = PulseDot(state)
    badge_color = _C.beast(beast)
    badge = AnimatedBadge(f"七{beast}", color=badge_color, anim="pulse")

    if state == "done":
        progress = "done"
    elif state == "idle":
        progress = "ready"
    else:
        progress = context_bar(context_pct)

    parts = [
        f"{dot.render()}",
        f"{badge.render()}",
        f"{_C.DIM}model:{_C.RESET}{_C.WHITE}{model}{_C.RESET}",
        f"{_C.DIM}[{_C.RESET}{_C.GRAY}{progress}{_C.DIM}]{_C.RESET}",
    ]
    if extra:
        parts.append(f"{_C.DIM}{extra}{_C.RESET}")
    return "  ".join(parts)
