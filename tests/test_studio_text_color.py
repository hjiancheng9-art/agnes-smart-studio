"""Test that crux_studio.py wraps AI text output with ANSI color codes."""


def test_text_output_has_ansi_color():
    """Verify the 'text' kind handler in crux_studio.py uses ANSI color codes."""
    with open("crux_studio.py", encoding="utf-8") as f:
        content = f.read()

    text_handler_found = False
    has_ansi_color = False

    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'if kind == "text":':
            text_handler_found = True
            for j in range(i + 1, min(i + 5, len(lines))):
                next_line = lines[j].strip()
                if "ansi" in next_line.lower() or "c[" in next_line or "color" in next_line.lower():
                    has_ansi_color = True

    assert text_handler_found, "Could not find text handler"
    assert has_ansi_color, "Text output missing ANSI color codes"
