"""CRUX Studio terminal logo — convergence diamond + wordmark.

A rotated rhombus with four Organic-colored arms converging at a white core,
representing the decisive point (crux). All rendering uses Rich Console.
"""

__all__ = ["show", "render_rich", "build_banner"]

# ── Logo pixel data ──────────────────────────────────────────────
# Convergence diamond — 17 cols × 11 rows
# Top/bottom arms: River blue (primary) — flowing convergence
# Inner accent ring: Lavender (accent) — creative intensity
# Convergence rows: Leaf green (success) — natural growth inward
# White core: the crux — the decisive point where all paths meet

BL = "█"

MARK = [
    #         0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
    [".", ".", ".", ".", ".", "B", "B", ".", ".", ".", ".", ".", ".", ".", ".", ".", "."],  # top apex
    [".", ".", ".", ".", "B", "B", ".", "B", "B", ".", ".", ".", ".", ".", ".", ".", "."],  # shoulders
    [".", ".", ".", "B", ".", ".", ".", ".", ".", "B", ".", ".", ".", ".", ".", ".", "."],  # spreading
    [".", ".", "B", ".", ".", "R", "R", ".", "R", "R", ".", ".", "B", ".", ".", ".", "."],  # accent ring
    [".", "B", "R", "R", ".", "G", ".", "G", ".", "R", "R", ".", "B", ".", ".", ".", "."],  # convergence
    [".", "B", "R", ".", "G", ".", "W", ".", "G", ".", "R", ".", "B", ".", ".", ".", "."],  # WHITE CORE
    [".", "B", "R", "R", ".", "G", ".", "G", ".", "R", "R", ".", "B", ".", ".", ".", "."],  # convergence
    [".", ".", "B", ".", ".", "R", "R", ".", "R", "R", ".", ".", "B", ".", ".", ".", "."],  # accent ring
    [".", ".", ".", "B", ".", ".", ".", ".", ".", "B", ".", ".", ".", ".", ".", ".", "."],  # narrowing
    [".", ".", ".", ".", "B", "B", ".", "B", "B", ".", ".", ".", ".", ".", ".", ".", "."],  # shoulders
    [".", ".", ".", ".", ".", "B", "B", ".", ".", ".", ".", ".", ".", ".", ".", ".", "."],  # bottom apex
]

# Color key → Rich markup style names (Organic palette)
_C = {
    "B": "[#5BA3CF]",  # River blue (primary) — flowing
    "R": "[#C084FC]",  # Lavender (accent) — creative
    "G": "[#7BC47F]",  # Leaf green (success) — growth
    "W": "[#FFFFFF]",  # White — the crux core
}
_C_CLOSE = {
    "B": "[/#5BA3CF]",
    "R": "[/#C084FC]",
    "G": "[/#7BC47F]",
    "W": "[/#FFFFFF]",
}


def _render_rich():
    """Render convergence diamond as Rich markup lines."""
    return ["".join((_C[c] + BL + _C_CLOSE[c]) if c in _C else " " for c in row) for row in MARK]


# CRUX wordmark glyphs — bold, decisive, terminal-native
# # → primary blue, @ → accent purple (serif/detail)

GLYPHS = {
    "C": ["..##..", ".#..@.", "#....", "#....", "#....", ".#..@.", "..##.."],
    "R": ["####..", "#..@#", "#..##", "####.", "#.@..", "#..@#", "#..##"],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#..@#", ".####."],
    "X": ["#...#", "#..@.", ".#.#.", "..@..", ".#.#.", ".@..#", "#...#"],
}


def build_banner(v="v5.0", t=None, s=None, provider=None):
    """Build full banner as Rich markup string (single source of truth).

    Args:
        v: version string
        t: tool count (None → fallback "52")
        s: skill count (None → fallback "45")
        provider: optional provider name
    """
    from ui.theme import COLORS, ICONS, LAYOUT

    rows = []
    P = "        "

    # Convergence diamond mark
    for line in _render_rich():
        rows.append(f"{P}{line}")

    rows.append("")

    # CRUX wordmark: # → primary blue, @ → accent purple
    for ri in range(7):
        parts = []
        for ch in "CRUX":
            gr = GLYPHS.get(ch, ["......"] * 7)[ri]
            for px in gr:
                if px == "#":
                    parts.append(f"[{COLORS['primary']}]{BL}[/]")
                elif px == "@":
                    parts.append(f"[{COLORS['accent']}]{BL}[/]")
                else:
                    parts.append(" ")
            parts.append(" ")
        rows.append(f"{P}    {''.join(parts)}")

    rows.append("")
    rows.append(f"{P}[dim]{LAYOUT['separator_char'] * LAYOUT['separator_len']}[/]")
    _t = t if t is not None else "52"
    _s = s if s is not None else "45"
    rows.append(f"{P}[{COLORS['success']}]{ICONS['success']}[/] [dim]{v}  ·  {_t} tools  ·  {_s} skills[/]")
    rows.append("")

    return "\n".join(rows)


def show(v=None, t=None, s=None, provider=None):
    """Print the CRUX Studio banner to terminal using Rich Console."""
    from ui.theme import console

    console.print()
    console.print(
        build_banner(
            v or "v5.0",
            t=t,
            s=s,
            provider,
        )
    )
    console.print()


def render_rich(v=None, t=None, s=None, provider=None):
    """Return the CRUX Studio banner as Rich markup string (for embedding)."""
    return build_banner(
        v or "v5.0",
        t=t,
        s=s,
        provider,
    )


if __name__ == "__main__":
    show()
