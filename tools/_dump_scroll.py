"""Dump scroll methods from tui_app.py for analysis."""

with open("ui/tui_app.py", encoding="utf-8") as f:
    lines = f.readlines()
# Write _scroll method + scroll_up/scroll_down methods to a temp file
with open("ui/_scroll_methods.txt", "w", encoding="utf-8") as out:
    in_method = False
    for idx, line in enumerate(lines):
        if (
            "def _scroll(" in line
            or "def scroll_up" in line
            or "def scroll_down" in line
            or "def scroll_page_up" in line
            or "def scroll_page_down" in line
        ):
            in_method = True
        if in_method:
            out.write(f"{idx + 1:4d}: {line}")
            # Check if next line is a new method (not indented)
            if idx + 1 < len(lines) and lines[idx + 1].strip() and not lines[idx + 1].startswith((" ", "\t")):
                if line.strip().startswith("def ") and "scroll_" in line:
                    pass  # continue, same method
                elif line.strip().startswith("def ") and idx > 0:
                    in_method = False
