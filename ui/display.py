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


def _view_image(path: str) -> str:
    """工具入口：用系统默认查看器打开图片，返回操作结果字符串"""
    if not path:
        return "[view_image] 未提供图片路径"
    if not os.path.exists(path):
        return f"[view_image] 文件不存在: {path}"
    success = open_file(path)
    if success:
        return f"[view_image] 已打开: {path}"
    else:
        return f"[view_image] 无法打开: {path}（检查文件格式或系统默认查看器）"


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
    console.print(
        Panel(
            message,
            title=f"[bold {COLORS['warning']}]▲ Warning[/]",
            border_style=COLORS["warning"],
            padding=LAYOUT["panel_padding"],
        )
    )


def show_success(message: str):
    console.print(
        Panel(
            message,
            title=f"[bold {COLORS['success']}]● Success[/]",
            border_style=COLORS["success"],
            padding=LAYOUT["panel_padding"],
        )
    )


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
        except Exception as e:
            console.print(f"  [{COLORS['error']}]⚠ 自动打开预览失败: {e}[/]")


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


# ═══════════════════════════════════════════════
#  工具函数 — 供 ToolRegistry 调用
# ═══════════════════════════════════════════════

def _tool_search(query: str) -> str:
    """搜索可用工具，返回匹配的工具名和描述"""
    import json
    from pathlib import Path as _Path

    tf = _Path(__file__).resolve().parent.parent / "tools.json"
    if not tf.exists():
        return "[tool_search] tools.json 未找到"
    try:
        data = json.loads(tf.read_text(encoding="utf-8"))
        tools = data.get("tools", []) if isinstance(data, dict) else data
    except (json.JSONDecodeError, OSError) as e:
        return f"[tool_search] 读取 tools.json 失败: {e}"

    q = query.lower()
    matches = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name", "")
        desc = t.get("description", "")
        if q in name.lower() or q in desc.lower():
            matches.append(f"  • {name} — {desc[:80]}")

    if not matches:
        return f"[tool_search] 未找到与 '{query}' 匹配的工具"
    return f"[tool_search] 找到 {len(matches)} 个匹配:\n" + "\n".join(matches[:20])


def _request_user_input(question: str) -> str:
    """暂停并询问用户问题，返回用户文本回复"""
    try:
        from rich.prompt import Prompt

        return Prompt.ask(f"\n  [bold yellow]?[/] {question}").strip()
    except (EOFError, KeyboardInterrupt):
        return "[request_user_input] 用户取消或输入不可用"


def _update_plan(
    action: str,
    step_id: int | None = None,
    name: str | None = None,
    tool: str | None = None,
    args: dict | None = None,
    reason: str = "",
) -> str:
    """更新当前执行计划：添加/删除/修改/插入步骤"""
    try:
        from core.plan_mode import get_plan_mode_manager

        mgr = get_plan_mode_manager()
        plan = mgr.current_plan()
        if plan is None:
            return "[update_plan] 当前没有活跃的计划"
        if plan.selected_option < 0 or plan.selected_option >= len(plan.options):
            return "[update_plan] 没有选中的方案"

        option = plan.options[plan.selected_option]
        steps = option.steps  # list[dict]

        if action == "add":
            new_step = {
                "id": step_id or (len(steps) + 1),
                "name": name or "未命名步骤",
                "tool": tool or "",
                "args": args or {},
            }
            steps.append(new_step)
            return f"[update_plan] 已添加步骤: {new_step['name']}"
        elif action == "remove":
            if step_id is not None:
                option.steps = [s for s in steps if s.get("id") != step_id]
                return f"[update_plan] 已移除步骤 {step_id}"
            return "[update_plan] 需要提供 step_id"
        elif action == "modify":
            if step_id is not None:
                for s in steps:
                    if s.get("id") == step_id:
                        if name:
                            s["name"] = name
                        if tool:
                            s["tool"] = tool
                        if args:
                            s["args"] = args
                        return f"[update_plan] 已修改步骤 {step_id}"
            return f"[update_plan] 未找到步骤 {step_id}"
        elif action == "insert":
            new_step = {
                "id": step_id or (len(steps) + 1),
                "name": name or "未命名步骤",
                "tool": tool or "",
                "args": args or {},
            }
            pos = max(0, min(step_id or 0, len(steps)))
            steps.insert(pos, new_step)
            return f"[update_plan] 已插入步骤: {new_step['name']} 到位置 {pos}"
        else:
            return f"[update_plan] 未知操作: {action}，支持 add/remove/modify/insert"
    except Exception as e:
        return f"[update_plan] 操作失败: {e}"
