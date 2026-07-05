#!/usr/bin/env python3
"""
DEPRECATED — Use ui/tui_v2.py instead.

This file is kept only for fallback/reference and must not receive new features.
"""
"""
DeepSeek V4 Flash · TUI Dashboard
==================================
Terminal identity interface — engine specs, tools, methodology, activity.
Keys: 1-5 tabs · q quit · ↑↓ scroll · r refresh
"""

import os
import sys
import time
from collections import deque
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.output import create_output
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.box import HEAVY, MINIMAL, ROUNDED
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ─── Theme ───────────────────────────────────────────────────────────────
C = {
    "bg": "#0a0e14",
    "bg2": "#121820",
    "card": "#1a2430",
    "border": "#2a3a4a",
    "accent": "#00d4aa",
    "text": "#e8edf2",
    "dim": "#8899aa",
    "muted": "#556677",
    "blue": "#54a0ff",
    "orange": "#ff9f43",
    "purple": "#a29bfe",
    "pink": "#ff6b9d",
    "red": "#ff5c5c",
    "yellow": "#feca57",
}

S_ACCENT = Style(color=C["accent"], bold=True)
S_DIM = Style(color=C["dim"])
S_MUTED = Style(color=C["muted"])
S_TEXT = Style(color=C["text"])
S_BLUE = Style(color=C["blue"], bold=True)
S_ORANGE = Style(color=C["orange"], bold=True)
S_PURPLE = Style(color=C["purple"], bold=True)
S_PINK = Style(color=C["pink"], bold=True)

# ─── Data ────────────────────────────────────────────────────────────────

SPECS = [
    ("模型", "DeepSeek V4 Flash"),
    ("上下文", "1,000,000 tokens"),
    ("平台", "CRUX Engine"),
    ("语言支持", "Python / JS/TS / Go / Rust / Java / C/C++"),
    ("技能包", "50 安装 · 743 市场可用"),
    ("工具数", "42 个集成工具"),
    ("方法论", "ZCode Protocol v5.1 · Superpowers"),
    ("运行时", "CRUX Studio"),
]

TOOLS = [
    ("⌘ code", "code_review", "代码审查"),
    ("⌘ code", "code_analyze", "源码分析"),
    ("⌘ code", "search_files", "代码搜索"),
    ("⌘ code", "run_python", "Python 执行"),
    ("⌘ code", "run_test", "测试运行"),
    ("⌘ code", "run_format", "格式化"),
    ("⌘ code", "run_lint", "静态分析"),
    ("⌘ code", "debug_inspect", "调试探查"),
    ("🌐 web", "web_search", "互联网搜索"),
    ("🌐 web", "web_fetch", "网页获取"),
    ("🌐 web", "http_request", "HTTP 请求"),
    ("🌐 web", "browser_screenshot", "网页截图"),
    ("🎨 image", "generate_image", "图像生成"),
    ("🎨 image", "view_image", "图像查看"),
    ("🎨 image", "imagegen", "独立图像通道"),
    ("🎬 video", "generate_video", "视频生成"),
    ("🎬 video", "transcribe_audio", "音频转写"),
    ("🎬 video", "text_to_speech", "文本转语音"),
    ("📁 file", "read_file", "读文件"),
    ("📁 file", "write_file", "写文件"),
    ("📁 file", "edit_file", "编辑文件"),
    ("📁 file", "patch_file", "结构化补丁"),
    ("📁 file", "glob_files", "文件搜索"),
    ("📁 file", "download_file", "下载文件"),
    ("⚡ sys", "run_bash", "Shell 执行"),
    ("⚡ sys", "env_check", "环境检查"),
    ("⚡ sys", "task_launch", "后台任务"),
    ("⚡ sys", "deploy_vercel", "Vercel 部署"),
    ("🔬 diag", "self_heal", "自愈审计"),
    ("🔬 diag", "security_review", "安全审查"),
    ("🧠 ai", "multi_agent", "多智能体"),
    ("🧠 ai", "agent_swarm", "智能体群"),
    ("🧠 ai", "execute_plan", "自主执行"),
    ("🧠 ai", "create_goal", "目标模式"),
    ("🧠 ai", "tdd_start", "TDD 会话"),
    ("🧠 ai", "quest_create", "任务链"),
    ("📊 docs", "report_create", "报告生成"),
    ("📊 docs", "wiki_create", "Wiki 创建"),
    ("📊 docs", "adr_create", "ADR 记录"),
    ("📊 docs", "create_markdown", "Markdown"),
    ("📊 docs", "create_html", "HTML 生成"),
    ("📊 docs", "create_pdf", "PDF 生成"),
]

SKILLS = [
    ("Debug / 根因分析", 97, C["red"]),
    ("Python", 96, C["blue"]),
    ("Fullstack 开发", 95, C["accent"]),
    ("系统架构设计", 90, C["pink"]),
    ("JavaScript / TS", 93, C["yellow"]),
    ("Go", 82, C["purple"]),
    ("Rust", 75, C["orange"]),
    ("数据库 / SQL", 88, C["blue"]),
    ("DevOps / CI/CD", 80, C["orange"]),
]

METHODOLOGY_STEPS = [
    ("头脑风暴", "探索意图 · 2-3 方案 · 设计确认门禁"),
    ("Git 隔离", "新分支/Worktree · 干净基线"),
    ("编写计划", "2-5分钟小任务 · 精确路径 · 验证步骤"),
    ("TDD 驱动", "RED 测试 → GREEN 实现 → REFACTOR"),
    ("Review 审计", "风格/逻辑/性能/安全 · 完整闭环"),
    ("提交闭环", "修改摘要 · 文件列表 · 验证结果 · 风险点"),
]

PRINCIPLES = [
    ("🔍", "探索优先 — 先读源码再写代码，不确定的 API 查文档不编造"),
    ("🎯", "最小改动 — 只改必须改的行，不顺手重构无关代码"),
    ("🔄", "补丁优先 — patch_file 优于裸写，失败自动回滚"),
    ("🧪", "先测后码 — 新行为先写失败测试，不跳过 TDD 门禁"),
    ("⛔", "2 次上限 — 同一问题试 2 次还不对，回退重读源码"),
    ("📝", "完整闭环 — 实现 + 测试 + 验证 + 输出摘要才算完成"),
]

ACTIVITY_LOG = deque(maxlen=8)


def log(tag, msg):
    now = datetime.now().strftime("%H:%M:%S")
    ACTIVITY_LOG.appendleft((now, tag, msg))


log("boot", "TUI 引擎启动 · v4.0")
log("init", "方法论已注入 · ZCode Protocol 活跃")
log("done", "42 工具就绪 · 等待指令")

TAB_NAMES = ["📊 仪表盘", "🛠️ 工具", "📈 能力", "📐 方法论", "📋 活动"]

# ─── Render Functions ────────────────────────────────────────────────────


def render_header():
    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"bold {C['accent']}", justify="left")
    table.add_column(style=f"bold {C['text']}")
    table.add_column(style=S_DIM, justify="right")
    table.add_row(
        "◇  CRUX Studio · 七兽引擎",
        "1M 上下文  ·  ZCode Protocol  ·  Fullstack Engine",
        "⚡ 就绪  ●",
    )
    p = Panel(
        table,
        style=Style(bgcolor=C["bg2"]),
        border_style=Style(color=C["accent"]),
        box=HEAVY,
        padding=(1, 2),
        subtitle=Style(color=C["muted"]).render("CRUX Studio"),
    )
    return p


def render_tab_bar(active):
    parts = []
    for i, name in enumerate(TAB_NAMES):
        if i == active:
            parts.append(f" [bold {C['accent']}]■ {name}[/] ")
        else:
            parts.append(f" [{C['dim']}]  {i + 1}.{name[2:]}[/] ")
    text = "".join(parts)
    return Panel(
        text,
        style=Style(bgcolor=C["bg2"]),
        border_style=Style(color=C["border"]),
        box=MINIMAL,
        padding=(0, 1),
    )


def render_dashboard():
    # Spec table
    spec_table = Table.grid(padding=(0, 3))
    spec_table.add_column(style=S_DIM)
    spec_table.add_column(style=S_TEXT)
    for label, val in SPECS:
        spec_table.add_row(f"{label}:", val)

    # Activity mini
    act_table = Table.grid(padding=(0, 2))
    act_table.add_column(style=S_MUTED, width=7)
    act_table.add_column(style=S_DIM)
    for ts, tag, msg in list(ACTIVITY_LOG)[:5]:
        act_table.add_row(ts, f"[{tag}] {msg}")

    left = Panel(
        Group(
            Text("\n⚙️  引擎规格\n", style=f"bold {C['accent']}"),
            spec_table,
            Text("\n"),
        ),
        style=Style(bgcolor=C["card"]),
        border_style=Style(color=C["border"]),
        box=ROUNDED,
        padding=(1, 2),
    )

    right = Panel(
        Group(
            Text("\n📋  最近活动\n", style=f"bold {C['accent']}"),
            act_table,
            Text("\n"),
        ),
        style=Style(bgcolor=C["card"]),
        border_style=Style(color=C["border"]),
        box=ROUNDED,
        padding=(1, 2),
    )

    # Context capacity bar
    ctx_table = Table.grid(padding=(1, 2))
    ctx_table.add_column(justify="center")
    ctx_table.add_column(justify="center")
    ctx_table.add_column(justify="center")
    ctx_table.add_row(
        f"[bold {C['accent']}]1,000,000[/]\n[{C['dim']}]tokens",
        f"[bold {C['blue']}]750,000[/]\n[{C['dim']}]英文单词",
        f"[bold {C['orange']}]500,000[/]\n[{C['dim']}]中文字符",
    )

    bottom = Panel(
        Group(
            Text("\n🧠  上下文容量\n", style=f"bold {C['accent']}"),
            ctx_table,
            Text(
                f"\n[{C['muted']}]可一次性处理 4 套完整代码库  ·  3 部《三体》体量  ·  30 分钟对话历史[/]",
                justify="center",
            ),
        ),
        style=Style(bgcolor=C["card"]),
        border_style=Style(color=C["border"]),
        box=ROUNDED,
        padding=(1, 2),
    )

    return Group(left, right, bottom)


def render_tools():
    # Group by category
    cats = {}
    for icon, name, desc in TOOLS:
        cat = icon.split()[1] if " " in icon else icon
        cats.setdefault(cat, []).append((icon, name, desc))

    renderers = []
    colors = {
        "code": C["blue"],
        "web": C["accent"],
        "image": C["orange"],
        "video": C["pink"],
        "file": C["purple"],
        "sys": C["yellow"],
        "diag": C["red"],
        "ai": C["accent"],
        "docs": C["purple"],
    }
    emojis = {
        "code": "⌘",
        "web": "🌐",
        "image": "🎨",
        "video": "🎬",
        "file": "📁",
        "sys": "⚡",
        "diag": "🔬",
        "ai": "🧠",
        "docs": "📊",
    }

    for cat_name in sorted(cats.keys()):
        t = Table.grid(padding=(0, 1))
        t.add_column(width=3)
        t.add_column(width=18, style=S_TEXT)
        t.add_column(style=S_DIM)
        col = colors.get(cat_name, C["dim"])
        emj = emojis.get(cat_name, "?")
        for _icon, name, desc in cats[cat_name]:
            t.add_row(f"[{col}]{emj}[/]", name, desc)

        renderers.append(
            Panel(
                t,
                title=f"[bold {col}]  {cat_name.upper()}[/]",
                title_align="left",
                style=Style(bgcolor=C["card"]),
                border_style=Style(color=C["border"]),
                box=ROUNDED,
                padding=(0, 1),
            )
        )

    return Columns(renderers, padding=(0, 1), equal=False, expand=True)


def render_skills():
    bars = []
    for name, pct, color in SKILLS:
        # Build a visual bar with unicode blocks
        filled = pct // 2
        empty = 50 - filled
        bar_str = f"[{color}]{'█' * filled}{'░' * empty}[/]"
        t = Table.grid(padding=(0, 2))
        t.add_column(width=22, style=S_TEXT)
        t.add_column(width=52)
        t.add_column(width=6, justify="right", style=S_DIM)
        t.add_row(name, bar_str, f"{pct}%")
        bars.append(t)

    # ZCode Protocol flow
    flow_parts = []
    for label, color in [
        ("A. 读 Traceback", C["blue"]),
        ("读源码", C["blue"]),
        ("最小复现", C["blue"]),
        ("B. 找根因", C["accent"]),
        ("设计方案", C["accent"]),
        ("C. 一次修对", C["orange"]),
        ("回归验证", C["pink"]),
    ]:
        flow_parts.append(f"[bold {color}]■ {label}[/]")
    flow_text = "  →  ".join(flow_parts)

    flow_panel = Panel(
        Text.from_markup(f"\n{flow_text}\n"),
        title=f"[bold {C['accent']}]  ZCode Protocol — 根因优先[/]",
        title_align="left",
        style=Style(bgcolor=C["card"]),
        border_style=Style(color=C["accent"]),
        box=ROUNDED,
        padding=(1, 2),
    )

    return Group(
        Panel(
            Group(*bars),
            title=f"[bold {C['accent']}]  核心能力[/]",
            title_align="left",
            style=Style(bgcolor=C["card"]),
            border_style=Style(color=C["border"]),
            box=ROUNDED,
            padding=(1, 2),
        ),
        flow_panel,
    )


def render_methodology():
    # Steps
    steps = Table.grid(padding=(0, 2))
    steps.add_column(width=3, justify="center")
    steps.add_column(width=16, style=S_TEXT)
    steps.add_column(style=S_DIM)
    for i, (name, desc) in enumerate(METHODOLOGY_STEPS, 1):
        steps.add_row(
            f"[bold {C['accent']}]{i}[/]",
            f"[bold]{name}[/]",
            desc,
        )

    # Principles
    princ = Table.grid(padding=(0, 2))
    princ.add_column(width=3)
    princ.add_column(style=S_DIM)
    for icon, text in PRINCIPLES:
        princ.add_row(f"{icon}", text)

    return Group(
        Panel(
            Group(
                Text("\n工作流\n", style=f"bold {C['accent']}"),
                steps,
            ),
            style=Style(bgcolor=C["card"]),
            border_style=Style(color=C["border"]),
            box=ROUNDED,
            padding=(1, 2),
        ),
        Panel(
            Group(
                Text("\n编码纪律\n", style=f"bold {C['accent']}"),
                princ,
            ),
            style=Style(bgcolor=C["card"]),
            border_style=Style(color=C["border"]),
            box=ROUNDED,
            padding=(1, 2),
        ),
    )


def render_activity():
    t = Table(box=MINIMAL, header_style=S_DIM)
    t.add_column("时间", width=8, style=S_MUTED)
    t.add_column("类型", width=8)
    t.add_column("事件", style=S_TEXT)

    tag_colors = {
        "boot": C["blue"],
        "init": C["accent"],
        "done": C["accent"],
        "code": C["blue"],
        "debug": C["red"],
        "test": C["orange"],
        "docs": C["purple"],
        "image": C["orange"],
        "web": C["accent"],
        "file": C["purple"],
        "sys": C["yellow"],
    }

    for ts, tag, msg in ACTIVITY_LOG:
        col = tag_colors.get(tag, C["dim"])
        t.add_row(ts, f"[{col}]■ {tag}[/]", msg)

    # Stats summary
    stats = Table.grid(padding=(1, 3))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_row(
        f"[bold {C['accent']}]42[/]\n[{C['dim']}]工具",
        f"[bold {C['blue']}]50[/]\n[{C['dim']}]技能包",
        f"[bold {C['orange']}]743[/]\n[{C['dim']}]市场可用",
        f"[bold {C['purple']}]10+[/]\n[{C['dim']}]语言",
    )

    return Group(
        Panel(
            stats,
            style=Style(bgcolor=C["card"]),
            border_style=Style(color=C["border"]),
            box=ROUNDED,
            padding=(1, 2),
        ),
        Panel(
            Group(Text("\n事件日志\n", style=f"bold {C['accent']}"), t),
            style=Style(bgcolor=C["card"]),
            border_style=Style(color=C["border"]),
            box=ROUNDED,
            padding=(1, 2),
        ),
    )


# ─── Key binding handling ────────────────────────────────────────────────


def tui_loop():
    console = Console()
    active_tab = 0

    RENDERERS = [render_dashboard, render_tools, render_skills, render_methodology, render_activity]

    # Hide cursor
    console.show_cursor(False)

    try:
        with Live(
            Group(render_header(), render_tab_bar(0), RENDERERS[0]()),
            console=console,
            screen=True,
            refresh_per_second=4,
        ) as live:
            # Use prompt_toolkit for key reading
            # On Windows with a Unix-like terminal (Git Bash, etc.), create_output()
            # defaults to Win32Output which fails. Force Vt100_Output instead.
            if sys.platform == "win32" and "TERM" in os.environ:
                output = Vt100_Output.from_pty(sys.stdout, term=os.environ.get("TERM"))
            else:
                output = create_output()
            session = PromptSession(output=output)
            kb = KeyBindings()

            @kb.add("q")
            @kb.add("Q")
            def exit_(event):
                event.app.exit()

            @kb.add("1")
            def tab1(event):
                nonlocal active_tab
                active_tab = 0

            @kb.add("2")
            def tab2(event):
                nonlocal active_tab
                active_tab = 1

            @kb.add("3")
            def tab3(event):
                nonlocal active_tab
                active_tab = 2

            @kb.add("4")
            def tab4(event):
                nonlocal active_tab
                active_tab = 3

            @kb.add("5")
            def tab5(event):
                nonlocal active_tab
                active_tab = 4

            @kb.add("r")
            @kb.add("R")
            def refresh(event):
                pass  # just re-render

            # Main loop
            while True:
                try:
                    result = session.prompt(
                        "",
                        key_bindings=kb,
                        mouse_support=False,
                    )
                    if result is None:
                        break
                    live.update(Group(render_header(), render_tab_bar(active_tab), RENDERERS[active_tab]()))
                except (EOFError, KeyboardInterrupt):
                    break
                except Exception:
                    break
    finally:
        console.show_cursor(True)
        console.clear()
        console.print("[bold green]◆ TUI 已退出[/]  — 重新运行 python agnes_tui.py 即可启动")


# ─── Entry ───────────────────────────────────────────────────────────────


def main():
    console = Console()
    try:
        # Try raw terminal mode first
        tui_loop()
    except Exception as e:
        console.clear()
        console.print(f"[bold red]✗ TUI 启动失败: {e}[/]")
        console.print("\n请确保终端支持全屏模式，或直接运行 [bold]python agnes_tui.py[/]")
        console.print("快捷键: 1-5 切换面板 · q 退出 · r 刷新")


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        import datetime
        import traceback
        from pathlib import Path

        crash_log = Path(__file__).parent / "output" / "crash_agnes_tui.log"
        crash_log.parent.mkdir(parents=True, exist_ok=True)
        with open(crash_log, "a", encoding="utf-8") as _f:
            _f.write(f"\n{'=' * 60}\n")
            _f.write(f"CRASH: {datetime.datetime.now()}\n")
            _f.write(f"Error: {type(_e).__name__}: {_e}\n")
            traceback.print_exc(file=_f)
        print(f"\nFATAL: {_e}", file=sys.stderr)
        print(f"Crash log saved to: {crash_log}", file=sys.stderr)
        import time

        time.sleep(3)
        sys.exit(1)
