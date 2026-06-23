"""Agnes terminal cyberpunk pixel logo — AGNES block-letter with ANSI color.

Each letter is a 5×7 pixel grid, 1-col gap between letters.
Rendered with block characters (█ U+2588) and layered ANSI colors
for a neon-tube cyberpunk aesthetic.

Color palette:
    CYAN     = bright cyan  (#00e5ff)  — main fill
    CYAN_HI  = white-cyan   (#00ffff)  — edge highlight
    MAGENTA  = neon magenta (#ff00ff)  — glow / accent
    CYAN_DIM = dark cyan    (#006688)  — inner shadow
    WHITE    = white         — text
    GRAY     = dim gray     — secondary info
    RESET    = ANSI reset

Usage:
    from ui.terminal_logo import show, render_rich
    show()                       # prints ANSI logo to stdout
    rich_str = render_rich()     # returns Rich markup string
"""

__all__ = [
    'CYAN', 'CYAN_HI', 'MAGENTA', 'CYAN_DIM', 'WHITE', 'GRAY', 'RESET',
    'GLYPHS', 'render_glyph', 'render_line', 'build_banner',
    'show', 'render_rich',
]

# ── ANSI colors ────────────────────────────────────────
CYAN     = '\033[96m'
CYAN_HI  = '\033[38;2;0;255;255m'
MAGENTA  = '\033[95m'
CYAN_DIM = '\033[36m'
WHITE    = '\033[97m'
GRAY     = '\033[90m'
DIM_GRAY = '\033[2m'
RESET    = '\033[0m'

# ── Block chars ───────────────────────────────────────
BLK  = '\u2588'   # full block  █
HALF = '\u2580'   # upper half  ▀ (for glow underline)

# ── Pixel glyph definitions (5 wide × 7 tall) ─────────
# '#' = filled cyan, '@' = bright highlight, '.' = empty
GLYPHS: dict[str, list[str]] = {
    'A': [
        '.#.@.',
        '#...#',
        '#...#',
        '#####',
        '#@.@#',
        '#...#',
        '#...#',
    ],
    'G': [
        '.####',
        '#....',
        '#....',
        '#.##@',
        '#...#',
        '#...#',
        '.####',
    ],
    'N': [
        '##..#',
        '#@.@#',
        '#@..#',
        '#...#',
        '#..@#',
        '#..@#',
        '#..@#',
    ],
    'E': [
        '#####',
        '#....',
        '#....',
        '####@',
        '#....',
        '#....',
        '#####',
    ],
    'S': [
        '.####',
        '#....',
        '#....',
        '.###@',
        '....#',
        '....#',
        '####.',
    ],
}


def render_glyph(glyph_lines: list[str]) -> list[str]:
    """Render a single glyph to ANSI-colored block strings."""
    rendered = []
    for row in glyph_lines:
        line = ''
        for ch in row:
            if ch == '#':
                line += CYAN + BLK + RESET
            elif ch == '@':
                line += CYAN_HI + BLK + RESET
            else:
                line += ' '
        rendered.append(line)
    return rendered


def render_line(letters: str, row: int) -> str:
    """Render one row across multiple letters with 1-col gaps."""
    parts = []
    for i, ch in enumerate(letters.upper()):
        glyph = GLYPHS.get(ch)
        if not glyph:
            parts.append('     ')  # 5-col placeholder for unknown chars
            continue
        glyph_row = glyph[row] if row < len(glyph) else '.....'
        for px in glyph_row:
            if px == '#':
                parts.append(CYAN + BLK + RESET)
            elif px == '@':
                parts.append(CYAN_HI + BLK + RESET)
            else:
                parts.append(' ')
        if i < len(letters) - 1:
            parts.append(' ')  # 1-col gap between letters
    return ''.join(parts)


def build_banner(
    version: str | None = None,
    tools: int | str | None = None,
    skills: int | str | None = None,
    provider: str | None = None,
) -> str:
    """Build the full ANSI banner string (does not print).

    version/tools/skills 默认 None → 运行时从 core.capability.get_banner_counts()
    取真实计数（单一真源），避免本文件再硬编码会与 tools.json/skills/ 失同步的数字。
    传入显式值则覆盖（仅用于测试或离线预览）。统计失败时显示 '?' 而非 0，
    让「统计失败」与「真的没有」在视觉上可区分。

    Returns a multi-line string ready for print().
    """
    if version is None or tools is None or skills is None:
        try:
            from core.capability import get_banner_counts
            real = get_banner_counts()
        except Exception:
            real = {"version": None, "tools": None, "skills": None}
        if version is None:
            version = real.get("version") or "v?"
        if tools is None:
            tools = real.get("tools") if real.get("tools") is not None else "?"
        if skills is None:
            skills = real.get("skills") if real.get("skills") is not None else "?"

    letters = 'AGNES'
    rows = []
    gap = '    '  # 4-col gap between logo and text

    # ── Build text annotations per row ──
    # Map: logo row index → right-side text
    sep = GRAY + '\u2500' * 32 + RESET

    right_text: dict[int, str] = {
        0: f'{CYAN_HI}AGNES{RESET} {MAGENTA}S{CYAN}m{MAGENTA}a{CYAN}r{MAGENTA}t{CYAN} {GRAY}Studio{RESET}',
        1: '',
        2: sep,
        3: f'{GRAY}{version}  \u00b7  {tools} tools  \u00b7  {skills} skills{RESET}',
        4: f'{GRAY}Codex parity  \u00b7  \u81ea\u7531\u521b\u4f5c  \u00b7  \u65e0\u9650\u5236{RESET}',
        5: '',
        6: '',
    }
    if provider:
        right_text[5] = f'{CYAN_DIM}active: {provider}{RESET}'

    # ── Render pixel rows ──
    for row in range(7):
        pixel = render_line(letters, row)
        text = right_text.get(row, '')
        rows.append(f'{gap}{pixel}  {text}')

    # ── Magenta neon glow underline ──
    glow = MAGENTA + HALF * (5 * 5 + 4) + RESET  # 29 half-blocks
    rows.append(f'{gap}{glow}')

    # ── Separator ──
    rows.append('')

    # ── Command hints footer ──
    cmds = f'{GRAY}/self audit  \u00b7  /team review  \u00b7  /agent  \u00b7  /deploy vercel{RESET}'
    rows.append(f'{gap}{cmds}')

    return '\n'.join(rows)


def show(version: str | None = None, tools: int | str | None = None,
         skills: int | str | None = None, provider: str | None = None) -> None:
    """Display the full cyberpunk Agnes logo to stdout.

    默认参数留空时由 build_banner() 运行时取真实计数（见其 docstring）。
    """
    print()
    print(build_banner(version, tools, skills, provider))
    print()


def render_rich(version: str | None = None, tools: int | str | None = None,
               skills: int | str | None = None, provider: str | None = None) -> str:
    """Render the logo as Rich markup string (for console.print).

    Uses Rich color tags instead of raw ANSI codes.
    默认参数留空时取真实计数（与 build_banner 同源，见其 docstring）。
    """
    if version is None or tools is None or skills is None:
        try:
            from core.capability import get_banner_counts
            real = get_banner_counts()
        except Exception:
            real = {"version": None, "tools": None, "skills": None}
        if version is None:
            version = real.get("version") or "v?"
        if tools is None:
            tools = real.get("tools") if real.get("tools") is not None else "?"
        if skills is None:
            skills = real.get("skills") if real.get("skills") is not None else "?"

    letters = 'AGNES'
    rows = []
    gap = '    '

    sep = '[dim]\u2500' * 32 + '[/]'

    right_text: dict[int, str] = {
        0: '[bright_cyan]AGNES[/] [magenta]S[/][cyan]m[/][magenta]a[/][cyan]r[/][magenta]t[/][cyan] [dim]Studio[/]',
        1: '',
        2: sep,
        3: f'[dim]{version}  \u00b7  {tools} tools  \u00b7  {skills} skills[/]',
        4: '[dim]Codex parity  \u00b7  \u81ea\u7531\u521b\u4f5c  \u00b7  \u65e0\u9650\u5236[/]',
        5: '',
        6: '',
    }
    if provider:
        right_text[5] = f'[cyan]active: {provider}[/]'

    for row in range(7):
        parts = []
        for i, ch in enumerate(letters.upper()):
            glyph = GLYPHS.get(ch)
            if not glyph:
                parts.append('     ')
                continue
            glyph_row = glyph[row] if row < len(glyph) else '.....'
            for px in glyph_row:
                if px == '#':
                    parts.append('[cyan]\u2588[/]')
                elif px == '@':
                    parts.append('[bright_cyan]\u2588[/]')
                else:
                    parts.append(' ')
            if i < len(letters) - 1:
                parts.append(' ')
        text = right_text.get(row, '')
        rows.append(f'{gap}{"".join(parts)}  {text}')

    # Magenta glow underline
    glow_width = 5 * 5 + 4
    _glow_str = '\u2580' * glow_width
    rows.append(f'{gap}[magenta]{_glow_str}[/]')
    rows.append('')

    cmds = '[dim]/self audit  \u00b7  /team review  \u00b7  /agent  \u00b7  /deploy vercel[/]'
    rows.append(f'{gap}{cmds}')

    return '\n'.join(rows)


# ── Standalone demo ────────────────────────────────────
if __name__ == '__main__':
    import sys
    _reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if _reconfigure is not None:
        _reconfigure(encoding='utf-8')
    show()
