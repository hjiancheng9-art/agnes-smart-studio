"""CRUX TUI — Night Atelier theme for prompt_toolkit."""

from prompt_toolkit.styles import Style

C = {
    "bg": "#1E1E2E",
    "surface": "#181825",
    "input_bg": "#11111B",
    "border": "#313244",
    "primary": "#CDD6F4",
    "secondary": "#BAC2DE",
    "muted": "#7F849C",
    "dim": "#585B70",
    "accent": "#89B4FA",
    "accent2": "#A6E3A1",
    "error": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "info": "#89B4FA",
    "user": "#89B4FA",
    "crux": "#CBA6F7",
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
        "success": f"fg:{C['success']}",
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
