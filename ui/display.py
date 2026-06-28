"""Display utilities v3 — 暗夜工坊风格 · 层次感面板 · 紧凑专业。

v3 升级: 适配暗夜工坊色板 · 边框减淡 · 信息密度提升 · 类型化面板
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


# ═══════════════════════════════════════════════
#  v3 消息函数 — 紧凑 · 层次感
# ═══════════════════════════════════════════════


def show_error(message: str):
    console.print(
        Panel(
            message,
            title=f"[bold {COLORS['error']}]● Error[/]",
            border_style=COLORS["error"],
            padding=LAYOUT["panel_padding"],
        )
    )


def show_warning(message: str):
    console.print(f"  [{COLORS['warning']}]▲ {message}[/]")


def show_success(message: str):
    console.print(f"  [{COLORS['success']}]● {message}[/]")


def show_info(message: str):
    console.print(f"  [{COLORS['text_secondary']}]○ {message}[/]")


def show_result(result: dict, title: str = "Results"):
    P = COLORS["primary"]
    M = COLORS["text_secondary"]
    E = COLORS["error"]
    S = COLORS["surface"]

    table = Table(
        title=f"[bold {P}]{title}[/]",
        show_header=True,
        header_style=f"bold {P}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        border_style=COLORS["border_focus"],
        row_styles=["", f"on {S}"],
    )
    table.add_column("Property", style=P)
    table.add_column("Value", style=COLORS["text"])
    for key, val in result.items():
        if key == "error":
            table.add_row(key, f"[{E}]● {val}[/]")
        elif isinstance(val, str) and len(val) > 80:
            table.add_row(key, val[:77] + "...")
        elif isinstance(val, list):
            table.add_row(key, ", ".join(str(v) for v in val[:3]))
        else:
            table.add_row(key, str(val))
    console.print(table)


def show_image_result(data: dict):
    """图片生成结果面板 — 紧凑专业。"""
    track_output("image", data)
    P = COLORS["primary"]
    S = COLORS["success"]
    M = COLORS["text_secondary"]
    T = COLORS["text_tertiary"]

    path = data.get("local_path", "")
    lines = []
    if path:
        lines.append(f"[{P}]File[/]  {path}")
    if data.get("url"):
        lines.append(f"[{P}]URL[/]   {data['url'][:60]}...")
    if data.get("model"):
        lines.append(f"[{P}]Model[/] {data['model']}")
    if data.get("prompt"):
        lines.append(f"[{P}]Prompt[/] {data['prompt'][:80]}")
    if path:
        lines.append(f"\n[{T}]/open 预览  ·  输入修改意见重新生成[/]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold {S}]● Image Generated[/]",
            border_style=COLORS["border_focus"],
            padding=LAYOUT["panel_padding"],
        )
    )
    if path:
        try:
            open_file(path)
            console.print(f"  [{T}]已自动打开预览[/]")
        except Exception:
            pass


def show_video_result(data: dict):
    """视频生成结果面板 — 紧凑专业。"""
    track_output("video", data)
    P = COLORS["primary"]
    A = COLORS["accent"]
    M = COLORS["text_secondary"]
    T = COLORS["text_tertiary"]

    path = data.get("local_path", "")
    lines = []
    if path:
        lines.append(f"[{P}]File[/]  {path}")
    if data.get("url"):
        lines.append(f"[{P}]URL[/]   {data['url'][:60]}...")
    if data.get("video_id"):
        lines.append(f"[{P}]ID[/]    {data['video_id']}")
    if path:
        lines.append(f"\n[{T}]输入 /open 预览 · /outputs 查看所有[/]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold {A}]▶ Video Generated[/]",
            border_style=COLORS["border_focus"],
            padding=LAYOUT["panel_padding"],
        )
    )


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
        console.print(f"  [{COLORS['text_tertiary']}]○ No records[/]")
        return
    P = COLORS["primary"]
    M = COLORS["text_secondary"]
    T = COLORS["text_tertiary"]
    S = COLORS["surface"]

    table = Table(
        title=f"[bold {P}]History[/]",
        show_header=True,
        header_style=f"bold {P}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        border_style=COLORS["border_focus"],
        row_styles=["", f"on {S}"],
    )
    table.add_column("ID", style=T, max_width=20)
    table.add_column("Type", style=P)
    table.add_column("Prompt", max_width=40)
    table.add_column("Model", style=M)
    table.add_column("★", justify="center")
    table.add_column("Time", style=T)
    for r in records[:20]:
        fav = "★" if r.get("favorited") else ""
        prompt = r.get("prompt", "")[:37] + "..." if len(r.get("prompt", "")) > 40 else r.get("prompt", "")
        table.add_row(
            r.get("id", "")[:20], r.get("type", ""), prompt, r.get("model", ""), fav, r.get("created_at", "")[:16]
        )
    console.print(table)


def show_templates_list():
    from core.config import PROMPT_TEMPLATES

    P = COLORS["primary"]
    S = COLORS["surface"]

    table = Table(
        title=f"[bold {P}]Templates[/]",
        show_header=True,
        header_style=f"bold {P}",
        box=ROUNDED,
        show_lines=LAYOUT["table_show_lines"],
        border_style=COLORS["border_focus"],
        row_styles=["", f"on {S}"],
    )
    table.add_column("Template", style=P)
    table.add_column("Keywords", max_width=50)
    table.add_column("Negative", max_width=30)
    for name, tpl in PROMPT_TEMPLATES.items():
        img_kw = tpl.get("image", "")[:47] + "..." if len(tpl.get("image", "")) > 50 else tpl.get("image", "")
        neg = tpl.get("negative", "")[:27] + "..." if len(tpl.get("negative", "")) > 30 else tpl.get("negative", "")
        table.add_row(name, img_kw, neg)
    console.print(table)
