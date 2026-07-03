"""CRUX TUI — Night Atelier theme for prompt_toolkit."""

from prompt_toolkit.styles import Style

C = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "input_bg": "#0f1629",
    "border": "#3a3a5c",
    "primary": "#e8e4dd",
    "secondary": "#b8b4ad",
    "muted": "#6b6560",
    "dim": "#4a4640",
    "accent": "#d4a853",
    "accent2": "#7a9a6b",
    "error": "#c4554a",
    "warning": "#c4944a",
    "success": "#7a9a6b",
    "info": "#5b8a9a",
    "user": "#8fb8d4",
    "crux": "#d4a853",
}


def build_style() -> Style:
    return Style.from_dict({
        "": f"fg:{C['primary']} bg:{C['bg']}",
        "message-area": f"bg:{C['bg']}",
        "message-user": f"fg:{C['user']} bold",
        "message-crux": f"fg:{C['crux']}",
        "message-info": f"fg:{C['muted']} italic",
        "message-error": f"fg:{C['error']}",
        "message-thinking": f"fg:{C['info']} italic",
        "message-tool": f"fg:{C['accent2']} italic",
        "input-border": f"fg:{C['border']}",
        "input-field": f"fg:{C['primary']} bg:{C['input_bg']}",
        "status-bar": f"fg:{C['muted']} bg:{C['surface']}",
        "status-bar-model": f"fg:{C['crux']} bold bg:{C['surface']}",
        "status-bar-path": f"fg:{C['muted']} bg:{C['surface']}",
        "status-bar-git": f"fg:{C['info']} bg:{C['surface']}",
        "status-bar-context": f"fg:{C['dim']} bg:{C['surface']}",
        "status-bar-key": f"fg:{C['dim']} bg:{C['surface']}",
        "scrollbar": f"fg:{C['border']} bg:{C['bg']}",
        "scrollbar.arrow": f"fg:{C['muted']} bg:{C['bg']}",
    })
