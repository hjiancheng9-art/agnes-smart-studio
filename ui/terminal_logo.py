"""Agnes terminal ASCII logo — pixel art + ANSI color for CLI display."""


__all__ = [
    'CYAN', 'CYAN_DIM', 'GRAY', 'RESET', 'render_line', 'show',
]



# ── ANSI colors ──────────────────────────────
CYAN = '\033[96m'
CYAN_DIM = '\033[36m'
GRAY = '\033[90m'
RESET = '\033[0m'

# ── Pixel "A" icon (12x14 grid) ──────────────
# # = cyan fill  @ = bright core  . = empty
_ICON = [
    '....####....',
    '...##..##...',
    '..##....##..',
    '.##......##.',
    '##..@@....##',
    '##..@@....##',
    '##........##',
    '##........##',
    '############',
    '##........##',
    '##........##',
    '##........##',
    '##........##',
    '##........##',
]


def render_line(icon_line: str) -> str:
    """Render one icon row as ANSI-colored string."""
    out = ''
    for ch in icon_line:
        if ch == '#':
            out += CYAN + '\u2588' + RESET
        elif ch == '@':
            out += CYAN_DIM + '\u2588' + RESET
        else:
            out += ' '
    return out


def show(version: str = 'v5.0', tools: int = 107, skills: int = 62) -> None:
    """Display the full Agnes terminal logo."""
    sep = GRAY + '\u2550' * 28 + RESET

    texts = [
        (2, f'{CYAN}AGNES{RESET} {GRAY}Smart Studio{RESET}'),
        (4, sep),
        (6, f'{GRAY}{version}  \u00b7  {tools} tools  \u00b7  {skills} skills{RESET}'),
        (8, f'{GRAY}Codex parity  \u00b7  \u81ea\u7531\u521b\u4f5c  \u00b7  \u65e0\u9650\u5236{RESET}'),
    ]
    text_map = dict(texts)

    print()
    for i, line in enumerate(_ICON):
        rendered = render_line(line)
        extra = text_map.get(i, '')
        print(f'  {rendered}  {extra}')

    print(f'  {GRAY}/self audit \u00b7 /team review \u00b7 /agent \u00b7 /deploy vercel{RESET}')
    print()


if __name__ == '__main__':
    import sys
    _reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if _reconfigure is not None:
        _reconfigure(encoding='utf-8')
    show()
