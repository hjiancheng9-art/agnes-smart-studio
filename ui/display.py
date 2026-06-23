"""展示工具 - 结果表格、Markdown渲染、颜色主题 + 文件预览"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import os
import subprocess
import platform

__all__ = [
    'COLORS', 'console', 'get_recent_outputs', 'open_file', 'show_error', 'show_history_table', 'show_image_result', 'show_info', 'show_pipeline_result', 'show_result', 'show_success', 'show_templates_list', 'show_video_result', 'show_warning', 'track_output',
]


console = Console(force_terminal=True)

# ── 最近生成的文件追踪（用于 /open 和 /outputs）──
_recent_outputs: list[dict] = []  # [{"type": "image"/"video", "path": ..., "prompt": ..., "data": {...}}, ...]
_MAX_RECENT = 50


def track_output(output_type: str, data: dict):
    """记录生成结果到最近列表"""
    path = data.get("local_path", "") or data.get("url", "")
    if path:
        _recent_outputs.insert(0, {
            "type": output_type,
            "path": path,
            "prompt": data.get("prompt", "")[:60],
            "data": data,
        })
        if len(_recent_outputs) > _MAX_RECENT:
            _recent_outputs.pop()


def get_recent_outputs(n: int = 10) -> list[dict]:
    """获取最近 N 个生成结果"""
    return _recent_outputs[:n]


def open_file(path: str) -> bool:
    """用系统默认程序打开文件"""
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
    table = Table(title=f"[cyan]◈ {title}[/]", show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="white")

    for key, val in result.items():
        if key == "error":
            table.add_row(key, f"[{COLORS['error']}]✖ {val}[/]")
        elif isinstance(val, str) and len(val) > 80:
            table.add_row(key, val[:77] + "...")
        elif isinstance(val, list):
            table.add_row(key, ", ".join(str(v) for v in val[:3]))
        else:
            table.add_row(key, str(val))

    console.print(table)


def show_image_result(data: dict):
    """展示图片生成结果（含预览提示）"""
    track_output("image", data)

    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold][cyan]◈[/] 文件:[/] {path}")
    if data.get("url"):
        items.append(f"[bold][cyan]◈[/] URL:[/] {data['url'][:60]}...")
    if data.get("model"):
        items.append(f"[bold][cyan]◈[/] 模型:[/] {data['model']}")
    if data.get("prompt"):
        items.append(f"[bold][cyan]◈[/] 提示词:[/] {data['prompt'][:80]}...")
    if path:
        items.append("\n[dim]  /open 打开 | /outputs 查看全部 | 说\"改xxx\"重新生成[/]")

    console.print(Panel(
        "\n".join(items),
        title=f"[{COLORS['success']}]◆ 图片生成完成[/]",
        border_style=COLORS["success"],
    ))
    # 自动尝试打开
    if path:
        try:
            open_file(path)
            console.print("[dim]  已自动打开预览[/]")
        except (OSError, subprocess.SubprocessError):
            pass


def show_video_result(data: dict):
    """展示视频生成结果（含预览提示）"""
    track_output("video", data)

    path = data.get("local_path", "")
    items = []
    if path:
        items.append(f"[bold][cyan]◈[/] 文件:[/] {path}")
    if data.get("url"):
        items.append(f"[bold][cyan]◈[/] URL:[/] {data['url'][:60]}...")
    if data.get("video_id"):
        items.append(f"[bold][cyan]◈[/] 视频ID:[/] {data['video_id']}")
    if data.get("task_id"):
        items.append(f"[dim]◈ 任务ID: {data['task_id']}[/]")
    if path:
        items.append("\n[dim]  /open 打开 | /outputs 查看全部 | 说\"改xxx\"重新生成[/]")

    console.print(Panel(
        "\n".join(items),
        title=f"[{COLORS['accent']}]▷ 视频生成完成[/]",
        border_style=COLORS["accent"],
    ))
    # 不自动打开视频（可能很大）
    if path:
        console.print("[dim]  输入 /open 打开预览[/]")


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
        title="[bold red]✖ 错误[/]",
        border_style=COLORS["error"],
    ))


def show_warning(message: str):
    """展示警告信息"""
    console.print(f"[{COLORS['warning']}]◈ {message}[/]")


def show_success(message: str):
    """展示成功信息"""
    console.print(f"[{COLORS['success']}]◆ {message}[/]")


def show_info(message: str):
    """展示提示信息"""
    console.print(f"[{COLORS['primary']}]⬡ {message}[/]")


def show_history_table(records: list[dict]):
    """展示历史记录表格"""
    if not records:
        console.print("[muted]◇ 暂无生成记录[/]")
        return

    table = Table(title="[cyan]◈ 生成历史[/]", show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("类型", style="cyan")
    table.add_column("提示词", max_width=40)
    table.add_column("模型", style="magenta")
    table.add_column("收藏", justify="center")
    table.add_column("时间", style="dim")

    for r in records[:20]:
        fav = "★" if r.get("favorited") else ""
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

    table = Table(title="[cyan]◈ Prompt 风格模板[/]", show_header=True, header_style=f"bold {COLORS['primary']}")
    table.add_column("模板名", style="cyan")
    table.add_column("图片风格关键词", max_width=50)
    table.add_column("负向提示词", max_width=30)

    for name, tpl in PROMPT_TEMPLATES.items():
        img_kw = tpl.get("image", "")[:47] + "..." if len(tpl.get("image", "")) > 50 else tpl.get("image", "")
        neg = tpl.get("negative", "")[:27] + "..." if len(tpl.get("negative", "")) > 30 else tpl.get("negative", "")
        table.add_row(name, img_kw, neg)

    console.print(table)
