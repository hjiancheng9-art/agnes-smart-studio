"""展示工具 - 结果表格、Markdown渲染、颜色主题"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import os
# Windows 兼容：强制UTF-8输出
if os.name == "nt":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

console = Console(force_terminal=True)

# 终端配色
COLORS = {
    "primary": "#00BCD4",
    "accent": "#E040FB",
    "success": "#4CAF50",
    "warning": "#FFC107",
    "error": "#F44336",
    "muted": "#9E9E9E",
}


def show_result(result: dict, title: str = "生成结果"):
    """展示单个生成结果"""
    table = Table(title=title, show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="white")

    for key, val in result.items():
        if key == "error":
            table.add_row(key, f"[{COLORS['error']}]{val}[/]")
        elif isinstance(val, str) and len(val) > 80:
            table.add_row(key, val[:77] + "...")
        elif isinstance(val, list):
            table.add_row(key, ", ".join(str(v) for v in val[:3]))
        else:
            table.add_row(key, str(val))

    console.print(table)


def show_image_result(data: dict):
    """展示图片生成结果"""
    items = []
    if data.get("local_path"):
        items.append(f"[bold]本地路径:[/] {data['local_path']}")
    if data.get("url"):
        items.append(f"[bold]在线URL:[/] {data['url'][:60]}...")
    if data.get("model"):
        items.append(f"[bold]模型:[/] {data['model']}")
    if data.get("prompt"):
        items.append(f"[bold]提示词:[/] {data['prompt'][:80]}...")

    console.print(Panel(
        "\n".join(items),
        title=f"[{COLORS['success']}]图片生成完成[/]",
        border_style=COLORS["success"],
    ))


def show_video_result(data: dict):
    """展示视频生成结果"""
    items = []
    if data.get("local_path"):
        items.append(f"[bold]本地路径:[/] {data['local_path']}")
    if data.get("url"):
        items.append(f"[bold]在线URL:[/] {data['url'][:60]}...")
    if data.get("video_id"):
        items.append(f"[bold]视频ID:[/] {data['video_id']}")
    if data.get("task_id"):
        items.append(f"[dim]任务ID: {data['task_id']}[/]")

    console.print(Panel(
        "\n".join(items),
        title=f"[{COLORS['accent']}]视频生成完成[/]",
        border_style=COLORS["accent"],
    ))


def show_pipeline_result(data: dict):
    """展示流水线结果"""
    img = data.get("image", {})
    vid = data.get("video", {})

    console.print()
    if img:
        show_image_result(img)
    if vid:
        show_video_result(vid)


def show_error(message: str):
    """展示错误信息"""
    console.print(Panel(
        message,
        title="[bold red]错误[/]",
        border_style=COLORS["error"],
    ))


def show_warning(message: str):
    """展示警告信息"""
    console.print(f"[{COLORS['warning']}][!] {message}[/]")


def show_success(message: str):
    """展示成功信息"""
    console.print(f"[{COLORS['success']}][OK] {message}[/]")


def show_info(message: str):
    """展示提示信息"""
    console.print(f"[{COLORS['primary']}][i] {message}[/]")


def show_history_table(records: list[dict]):
    """展示历史记录表格"""
    if not records:
        console.print("[muted]暂无生成记录[/]")
        return

    table = Table(title="生成历史", show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("类型", style="cyan")
    table.add_column("提示词", max_width=40)
    table.add_column("模型", style="magenta")
    table.add_column("收藏", justify="center")
    table.add_column("时间", style="dim")

    for r in records[:20]:
        fav = "*" if r.get("favorited") else ""
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
    """展示可用模板列表"""
    from core.config import PROMPT_TEMPLATES

    table = Table(title="Prompt 风格模板", show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("模板名", style="cyan")
    table.add_column("图片风格关键词", max_width=50)
    table.add_column("负向提示词", max_width=30)

    for name, tpl in PROMPT_TEMPLATES.items():
        img_kw = tpl.get("image", "")[:47] + "..." if len(tpl.get("image", "")) > 50 else tpl.get("image", "")
        neg = tpl.get("negative", "")[:27] + "..." if len(tpl.get("negative", "")) > 30 else tpl.get("negative", "")
        table.add_row(name, img_kw, neg)

    console.print(table)
