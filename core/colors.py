"""ANSI color codes for terminal output.

Usage:
    from core.colors import ANSI
    print(f"{ANSI['red']}Error!{ANSI['reset']}")

Or with Rich (for crux_studio.py):
    from core.colors import COLORS_RICH
    console.print(f"[{COLORS_RICH['info']}]Hello[/]")
"""

# ── ANSI escape codes ──
ANSI: dict[str, str] = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    # Standard foreground
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    # Bright foreground
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
    # Semantic aliases
    "ai": "\033[36m",  # cyan for AI text
    "tool": "\033[93m",  # bright yellow for tool output
    "error": "\033[91m",  # bright red for errors
    "warning": "\033[93m",  # bright yellow for warnings
    "success": "\033[92m",  # bright green for success
    "info": "\033[2;36m",  # dim cyan for info
    "status": "\033[34m",  # blue for status
    "thinking": "\033[35m",  # magenta for thinking
}

# ── Rich markup colors (for use with console.print()) ──
# Use: console.print(f"[{COLORS_RICH['error']}]error text[/]")
COLORS_RICH: dict[str, str] = {
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "primary": "blue",
    "muted": "dim white",
    "info": "cyan",
    "thinking": "magenta",
    "status": "cyan bold",
    "tool": "bright_yellow",
    "comfyui": "green bold",
    "system": "blue bold",
    "ai": "cyan",
    "bold_cyan": "bold cyan",
    "bold_white": "bold white",
}
