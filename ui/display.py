"""Display utilities v2 — 美化面板 · 彩色表格 · 文件预览。
v2 升级: beautify 面板集成 · 交替行色 · 原生图片/视频面板 · 分隔线
"""

import os
import platform
import subprocess

from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table

from ui.theme import COLORS, ICONS, LAYOUT, console

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

_recent_outputs: list[dict] = []
_MAX_RECENT = 50


def track_output(output_type: str, data: dict):
    path = data.get("local_path", "") or data.get("url", "")
    if path:
        _recent_outputs.insert(
            0, {"type": output_type, "path": path, "prompt": data.get("prompt", "")[:60], "data": data}
        )
    while len(_recent_outputs) > _MAX_RECENT:
        _recent_outputs.pop()


def get_recent_outputs(n: int = 10) -> list[dict]:
    return _recent_outputs[:n]


def open_file(path: str) -> bool:
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


def show_error(message: str):
    console.print(
        Panel(
            message,
            title=f"[bold {COLORS['error']}]{ICONS['error']} Error[/]",
            border_style=COLORS["error"],
            padding=LAYOUT["panel_padding"],
        )
    )


def show_warning(message: str):
    console.print(f"  [{COLORS['warning']}]{ICONS['warning']} {message}[/]")


def show_success(message: str):
    console.print(f"  [{COLORS['success']}]{ICONS['success']} {message}[/]")


def show_info(message: str):
    console.print(f"  [{COLORS['primary']}]{ICONS['info']} {message}[/]")


def show_result(result: dict, title: str = "Results"):
    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} {title}[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        row_styles=["", f"on {COLORS['surface']}"],
    )
    table.add_column("Property", style=COLORS["primary"])
    table.add_column("Value", style="white")
    for key, val in result.items():
        if key == "error":
            table.add_row(key, f"[{COLORS['error']}]{ICONS['error']} {val}[/]")
        elif isinstance(val, str) and len(val) > 80:
            table.add_row(key, val[:77] + "...")
        elif isinstance(val, list):
            table.add_row(key, ", ".join(str(v) for v in val[:3]))
        else:
            table.add_row(key, str(val))
    console.print(table)


def show_image_result(data: dict):
    track_output("image", data)
    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} File:[/] {path}")
    if data.get("url"):
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} URL:[/] {data['url'][:60]}...")
    if data.get("model"):
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} Model:[/] {data['model']}")
    if data.get("prompt"):
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} Prompt:[/] {data['prompt'][:80]}...")
    if path:
        items.append('\n[dim]  /open preview  |  say "modify xxx" to regenerate[/]')
    console.print(
        Panel(
            "\n".join(items),
            title=f"[bold {COLORS['success']}]{ICONS['success']} Image Generated[/]",
            border_style=COLORS["success"],
            padding=LAYOUT["panel_padding"],
        )
    )
    if path:
        try:
            open_file(path)
            console.print("[dim]  Auto-opened preview[/]")
        except Exception:
            pass


def show_video_result(data: dict):
    track_output("video", data)
    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} File:[/] {path}")
    if data.get("url"):
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} URL:[/] {data['url'][:60]}...")
    if data.get("video_id"):
        items.append(f"[bold {COLORS['primary']}]{ICONS['primary']} ID:[/] {data['video_id']}")
    if path:
        items.append("\n[dim]  /open preview  |  /outputs all[/]")
    console.print(
        Panel(
            "\n".join(items),
            title=f"[bold {COLORS['accent']}]{ICONS['video']} Video Generated[/]",
            border_style=COLORS["accent"],
            padding=LAYOUT["panel_padding"],
        )
    )
    if path:
        console.print("[dim]  Enter /open to preview[/]")


def show_pipeline_result(data: dict):
    img = data.get("image", {})
    vid = data.get("video", {})
    console.print()
    if img:
        show_image_result(img)
    if vid:
        show_video_result(vid)


def show_history_table(records: list[dict]):
    if not records:
        console.print(f"  [{COLORS['muted']}]{ICONS['empty']} No records[/]")
        return
    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} History[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        row_styles=["", f"on {COLORS['surface']}"],
    )
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("Type", style=COLORS["primary"])
    table.add_column("Prompt", max_width=40)
    table.add_column("Model", style=COLORS["accent"])
    table.add_column("★", justify="center")
    table.add_column("Time", style="dim")
    for r in records[:20]:
        fav = ICONS["star"] if r.get("favorited") else ""
        prompt = r.get("prompt", "")[:37] + "..." if len(r.get("prompt", "")) > 40 else r.get("prompt", "")
        table.add_row(
            r.get("id", "")[:20], r.get("type", ""), prompt, r.get("model", ""), fav, r.get("created_at", "")[:16]
        )
    console.print(table)


def show_templates_list():
    from core.config import PROMPT_TEMPLATES

    table = Table(
        title=f"[{COLORS['primary']}]{ICONS['primary']} Templates[/]",
        show_header=True,
        header_style=f"bold {COLORS['primary']}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        row_styles=["", f"on {COLORS['surface']}"],
    )
    table.add_column("Template", style=COLORS["primary"])
    table.add_column("Keywords", max_width=50)
    table.add_column("Negative", max_width=30)
    for name, tpl in PROMPT_TEMPLATES.items():
        img_kw = tpl.get("image", "")[:47] + "..." if len(tpl.get("image", "")) > 50 else tpl.get("image", "")
        neg = tpl.get("negative", "")[:27] + "..." if len(tpl.get("negative", "")) > 30 else tpl.get("negative", "")
        table.add_row(name, img_kw, neg)
    console.print(table)
