"""Preview CRUX logo as plain text (no colors) to verify shape."""

from ui.terminal_logo import _GAP, _LETTER_H, _LETTER_W, GLYPHS

letters = "CRUX"
span = _LETTER_W + _GAP

for row in range(_LETTER_H):
    line = []
    for col in range(span * len(letters) + 1):
        ch = "."
        # find which letter
        for li, letter in enumerate(letters):
            base = li * span
            local = col - base
            if 0 <= local < _LETTER_W:
                g = GLYPHS[letter]
                px = g[row][local]
                if px == "#":
                    ch = "#"
                elif px == "@":
                    ch = "@"
                elif px == "+":
                    ch = "+"
        line.append(ch)
    print("".join(line).replace("#", "█").replace("@", "◆").replace("+", "◈").replace(".", " "))

print()
print("--- with shadow ---")
# Render with shadow
canvas_w = span * len(letters) + 1
for r in range(_LETTER_H + 1):
    cells = ["."] * canvas_w
    # shadow from row r-1, col+1
    if r >= 1:
        sr = r - 1
        for li, letter in enumerate(letters):
            base = li * span
            g = GLYPHS[letter]
            for ci, px in enumerate(g[sr]):
                if px != ".":
                    target = base + ci + 1
                    if 0 <= target < canvas_w:
                        cells[target] = "░"
    # main from row r
    if r < _LETTER_H:
        for li, letter in enumerate(letters):
            base = li * span
            g = GLYPHS[letter]
            for ci, px in enumerate(g[r]):
                if px == "#":
                    cells[ci + base] = "█"
                elif px == "@":
                    cells[ci + base] = "◆"
                elif px == "+":
                    cells[ci + base] = "◈"
    print("".join(cells).replace(".", " "))
