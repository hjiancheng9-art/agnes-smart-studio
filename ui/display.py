"""Display utilities — result tables, Markdown rendering, status messages + file preview.

All colors, icons, and layout params are imported from ui.theme (single source of truth).
This module provides the show_* function API that the rest of the codebase consumes.
"""

import os
import platform
import subprocess

from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table

from ui.theme import COLORS, ICONS, LAYOUT, console  # noqa: F401 — re-exported

__all__ = [
    "COLORS",
    "console",
    "get_recent_outputs",
    "open_file",
    "show_error",
    "show_history_table",
    "show_image_result",
    "show_info",
    "show_pipeline_result",
    "show_result",
    "show_success",
    "show_templates_list",
    "show_video_result",
    "show_warning",
    "track_output",
]

# ── Recent output tracking (for /open and /outputs) ──────────────

_recent_outputs: list[dict] = []
_MAX_RECENT = 50


def track_output(output_type: str, data: dict):
    """Record a generation result to the recent list."""
    path = data.get("local_path", "") or data.get("url", "")
    if path:
        _recent_outputs.insert(
            0,
            {
                "type": output_type,
                "path": path,
                "prompt": data.get("prompt", "")[:60],
                "data": data,
            },
        )
        if len(_recent_outputs) > _MAX_RECENT:
            _recent_outputs.pop()


def get_recent_outputs(n: int = 10) -> list[dict]:
    """Get the most recent N generation results."""
    return _recent_outputs[:n]


def open_file(path: str) -> bool:
    """Open a file with the system default application."""
    if not path or not os.path.exists(path):
        return False
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# ── Status message functions ──────────────────────────────────────


def show_error(message: str):
    """Display error message in a rounded Panel."""
    console.print(
        Panel(
            message,
            title=f"[bold {COLORS['error']}]⊗ Error[/]",
            border_style=COLORS["error"],
            padding=LAYOUT["panel_padding"],
        )
    )


def show_warning(message: str):
    """Display warning message inline."""
    console.print(f"[{COLORS['warning']}]⠶ {message}[/]")


def show_success(message: str):
    """Display success message inline."""
    console.print(f"[{COLORS['success']}]✿ {message}[/]")


def show_info(message: str):
    """Display info message inline."""
    console.print(f"[{COLORS['primary']}]∘ {message}[/]")


# ── Result display functions ──────────────────────────────────────


def show_result(result: dict, title: str = "Results"):
    """Display a single generation result as a table."""
    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} {title}[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
    )
    table.add_column("Property", style=COLORS["primary"])
    table.add_column("Value", style="white")

    for key, val in result.items():
        if key == "error":
            table.add_row(key, f"[{COLORS['error']}]⊗ {val}[/]")
        elif isinstance(val, str) and len(val) > 80:
            table.add_row(key, val[:77] + "...")
        elif isinstance(val, list):
            table.add_row(key, ", ".join(str(v) for v in val[:3]))
        else:
            table.add_row(key, str(val))

    console.print(table)


def show_image_result(data: dict):
    """Display image generation result with preview hint."""
    track_output("image", data)

    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] File:[/] {path}")
    if data.get("url"):
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] URL:[/] {data['url'][:60]}...")
    if data.get("model"):
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] Model:[/] {data['model']}")
    if data.get("prompt"):
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] Prompt:[/] {data['prompt'][:80]}...")
    if path:
        items.append('\n[dim]  /open preview | /outputs all | say "modify xxx" to regenerate[/]')

    console.print(
        Panel(
            "\n".join(items),
            title=f"[{COLORS['success']}]✿ Image generated[/]",
            border_style=COLORS["success"],
            padding=LAYOUT["panel_padding"],
        )
    )
    # Auto-open preview
    if path:
        try:
            open_file(path)
            console.print("[dim]  Auto-opened preview[/]")
        except (OSError, subprocess.SubprocessError):
            pass


def show_video_result(data: dict):
    """Display video generation result with preview hint."""
    track_output("video", data)

    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] File:[/] {path}")
    if data.get("url"):
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] URL:[/] {data['url'][:60]}...")
    if data.get("video_id"):
        items.append(f"[bold][{COLORS['primary']}]{ICONS['primary']}[/] Video ID:[/] {data['video_id']}")
    if data.get("task_id"):
        items.append(f"[dim]{ICONS['primary']} Task ID: {data['task_id']}[/]")
    if path:
        items.append('\n[dim]  /open preview | /outputs all | say "modify xxx" to regenerate[/]')

    console.print(
        Panel(
            "\n".join(items),
            title=f"[{COLORS['accent']}]↝ Video generated[/]",
            border_style=COLORS["accent"],
            padding=LAYOUT["panel_padding"],
        )
    )
    # Don't auto-open videos (may be large)
    if path:
        console.print("[dim]  Enter /open to preview[/]")


def show_pipeline_result(data: dict):
    """Display pipeline result."""
    img = data.get("image", {})
    vid = data.get("video", {})

    console.print()
    if img:
        show_image_result(img)
    if vid:
        show_video_result(vid)


# ── History / Template tables ─────────────────────────────────────


def show_history_table(records: list[dict]):
    """Display generation history as a table."""
    if not records:
        console.print(f"[{COLORS['muted']}]{ICONS['empty']} No generation records[/]")
        return

    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} Generation history[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
    )
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("Type", style=COLORS["primary"])
    table.add_column("Prompt", max_width=40)
    table.add_column("Model", style=COLORS["accent"])
    table.add_column("Fav", justify="center")
    table.add_column("Time", style="dim")

    for r in records[:20]:
        fav = ICONS["star"] if r.get("favorited") else ""
        prompt = r.get("prompt", "")[:37] + "..." if len(r.get("prompt", "")) > 40 else r.get("prompt", "")
        table.add_row(
            r.get("id", "")[:20],
            r.get("type", ""),
            prompt,
            r.get("model", ""),
            fav,
            r.get("created_at", "")[:16],
        )

    console.print(table)


def show_templates_list():
    """Display available prompt templates."""
    from core.config import PROMPT_TEMPLATES

    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} Prompt style templates[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
    )
    table.add_column("Template", style=COLORS["primary"])
    table.add_column("Image keywords", max_width=50)
    table.add_column("Negative prompt", max_width=30)

    for name, tpl in PROMPT_TEMPLATES.items():
        img_kw = tpl.get("image", "")[:47] + "..." if len(tpl.get("image", "")) > 50 else tpl.get("image", "")
        neg = tpl.get("negative", "")[:27] + "..." if len(tpl.get("negative", "")) > 30 else tpl.get("negative", "")
        table.add_row(name, img_kw, neg)

    console.print(table)
