#!/usr/bin/env python3
"""CRUX Studio launcher - environment check + mode select + quick start"""

import os
import sys
import subprocess
from pathlib import Path

# Windows UTF-8 兼容
if os.name == "nt":
    os.system("chcp 65001 >nul 2>&1")
    # reconfigure 在 Python 3.7+ 的 TextIOWrapper 上存在，但 stubs 将 stdout 类型标注为 TextIO
    _reconfigure = getattr(sys.stdout, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8", errors="replace")
    _reconfigure_err = getattr(sys.stderr, "reconfigure", None)
    if _reconfigure_err is not None:
        _reconfigure_err(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Rich theme (single source of truth) ──────────────────────────
from ui.theme import COLORS, ICONS, LAYOUT, console


def _show_banner():
    """Display the Organic convergence-diamond logo banner."""
    from ui.terminal_logo import show as _show_logo
    _show_logo()


def print_step(msg: str):
    console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] {msg}")


def print_ok(msg: str):
    console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] {msg}")


def print_warn(msg: str):
    console.print(f"  [{COLORS['warning']}]{ICONS['warning']}[/] {msg}")


def print_err(msg: str):
    console.print(f"  [{COLORS['error']}]{ICONS['error']}[/] {msg}")


def run_cmd(cmd: str) -> tuple[int, str]:
    """运行命令并返回 (returncode, output)。

    安全：用 shlex.split 拆成参数 list 后以 shell=False 执行，
    避免 shell=True 带来的注入面。调用方仍传字符串命令即可。

    注：posix=True 会正确剥离 -c "..." 的引号；本函数调用方均为
    字面量命令（无 Windows 反斜杠路径），故 posix 模式安全。
    """
    import shlex
    try:
        args = shlex.split(cmd, posix=True)
        r = subprocess.run(
            args, shell=False, capture_output=True, text=True,
            cwd=str(ROOT), timeout=30,
        )
        return r.returncode, (r.stdout or r.stderr).strip()
    except Exception as e:
        return 1, str(e)


# ── 环境检测 ──────────────────────────────────────────────

def check_python() -> bool:
    code, out = run_cmd("python --version")
    if code == 0:
        print_ok(f"Python: {out}")
        return True
    code, out = run_cmd("python3 --version")
    if code == 0:
        print_ok(f"Python3: {out}")
        return True
    print_err("未找到 Python，请安装 Python 3.10+")
    return False


def check_env() -> bool:
    env_file = ROOT / ".env"
    if not env_file.exists():
        print_warn(".env 文件不存在")
        console.print(f"  [{COLORS['warning']}]{ICONS['warning']}[/] 是否创建 .env 文件？(y/n): ", end="")
        answer = input().strip().lower()
        if answer == "y":
            console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 请输入 CRUX_API_KEY: ", end="")
            api_key = input().strip()
            env_file.write_text(
                f"# CRUX AI API 配置\n"
                f"CRUX_API_KEY={api_key}\n"
                f"CRUX_BASE_URL=https://apihub.agnes-ai.com/v1\n",
                encoding="utf-8",
            )
            print_ok(".env 已创建")
            return True
        print_err("跳过 .env 创建，部分功能不可用")
        return False

    # 检查 API Key 是否已填写（兼容 AGNES_API_KEY 旧格式）
    content = env_file.read_text(encoding="utf-8")
    if "sk-your-api-key-here" in content or "CRUX_API_KEY=\n" in content or ("CRUX_API_KEY=" not in content and "AGNES_API_KEY=" not in content):
        print_warn("API Key 未配置")
        console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 请输入 CRUX_API_KEY (留空跳过): ", end="")
        api_key = input().strip()
        if api_key:
            lines = []
            for line in content.splitlines():
                if line.startswith("CRUX_API_KEY=") or line.startswith("AGNES_API_KEY="):
                    lines.append(f"CRUX_API_KEY={api_key}")
                else:
                    lines.append(line)
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print_ok("API Key 已保存")
        else:
            print_warn("跳过，部分功能不可用")
            return False
    else:
        print_ok(".env 配置已就绪")
    return True


def check_deps() -> bool:
    """检查并安装依赖"""
    code, _ = run_cmd("python -c \"import httpx, rich, PIL, dotenv\"")
    if code == 0:
        print_ok("依赖已安装")
        return True

    print_warn("检测到缺少依赖，正在安装...")
    pip = "pip"
    code, _ = run_cmd("pip --version")
    if code != 0:
        pip = "pip3"
    code, out = run_cmd(f"{pip} install -r requirements.txt")
    if code == 0:
        print_ok("依赖安装完成")
        return True
    print_err(f"依赖安装失败: {out[:100]}")
    print_warn(f"请手动运行: {pip} install -r requirements.txt")
    return False


def check_output_dir():
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    (out / "videos").mkdir(exist_ok=True)
    print_ok(f"输出目录: {out}")


# ── 模式选择 ──────────────────────────────────────────────

MODES = {
    "1": (f"{ICONS['primary']} 交互菜单",     "文生图/图生图/视频/历史/模板"),
    "2": (f"{ICONS['primary']} 聊天+智能体",  "45技能 + Alt+Enter换行 + 一键制片/作图/炼丹"),
    "3": (f"{ICONS['primary']} 快速生成",     "输入描述 → 选类型 → 选视频时长 → 一键生成"),
    "4": (f"{ICONS['primary']} 图生图",       "图片编辑/风格迁移 → 进入交互菜单操作"),
    "5": (f"{ICONS['primary']} 图生视频",     "图片→视频，可选3s~18s时长"),
    "6": (f"{ICONS['primary']} 查询视频",     "video_id 查进度（不要用 task_id）"),
    "7": (f"{ICONS['primary']} 一站式流水线", "文本→图片→视频 全自动"),
    "8": (f"{ICONS['primary']} 查看FAQ",      "常见问题/APIKey/视频时长/thinking/programming"),
    "0": (f"{ICONS['primary']} 退出", ""),
}


def show_menu():
    from rich.table import Table
    console.print()
    console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [bold]选择模式[/]")
    console.print(f"  [{COLORS['muted']}{'─' * 55}[/]")
    table = Table(show_header=False, box=None, padding=(0, 2), collapse=True)
    table.add_column(style=f"bold {COLORS['accent']}", width=2)
    table.add_column(width=14)
    table.add_column(style=COLORS['muted'])
    for key, (label, desc) in MODES.items():
        if desc:
            table.add_row(key, label, desc)
        else:
            table.add_row(key, label, "")
    console.print(table)
    console.print(f"  [{COLORS['muted']}{'─' * 55}[/]")


def ask_video_id() -> str | None:
    console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 请输入 video_id: ", end="")
    video_id = input().strip()
    return video_id or None


def ask_video_duration() -> tuple[int, int]:
    """选择视频时长，返回 (num_frames, frame_rate)"""
    # 帧数列表 (8n+1, <=441)
    frames_list = [81, 121, 161, 241, 441]
    dur_map = {81: "3s", 121: "5s", 161: "7s", 241: "10s", 441: "18s"}
    console.print()
    console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] [{COLORS['muted']}]选择视频时长 (fps=24):[/]")
    for i, nf in enumerate(frames_list, 1):
        console.print(f"  [{COLORS['accent']}]{i}[/] {nf}帧≈{dur_map[nf]}")
    console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 选择 (1-5, 默认2=5s): ", end="")
    ch = input().strip() or "2"
    idx = max(0, min(4, int(ch) - 1)) if ch.isdigit() else 1
    return frames_list[idx], 24


def ask_quick_prompt(kind: str = "image") -> tuple[str, list[str]] | None:
    """快速生成：输入描述，视频/流水线可选时长

    kind: "image" / "video" / "pipeline"
    """
    console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 请输入描述: ", end="")
    prompt = input().strip()
    if not prompt:
        return None

    args = []
    if kind == "video":
        args = ["-v"]
    elif kind == "pipeline":
        args = ["-p"]

    # 视频/流水线模式：询问时长
    if kind in ("video", "pipeline"):
        nf, fps = ask_video_duration()
        args += ["--num-frames", str(nf), "--frame-rate", str(fps)]

    return prompt, args


def _crux_cmd(args: list[str]) -> list[str]:
    """Return best available crux command: 'crux' if on PATH, else 'python crux_studio.py'."""
    import shutil
    if shutil.which("crux"):
        return ["crux"] + args
    return ["python", "crux_studio.py"] + args


def launch(cmd_parts: list[str]):
    """启动主程序，失败时提示错误并暂停。

    安全：直接以 list 形式传给 subprocess（shell=False），避免 shell 注入，
    也无需调用方手动给参数加引号转义。
    """
    # 仅用于日志展示，不参与实际执行
    console.print(f"\n  [{COLORS['muted']}]执行: {' '.join(cmd_parts)}[/]\n")
    try:
        r = subprocess.run(cmd_parts, cwd=str(ROOT))
        if r.returncode != 0:
            console.print(f"\n  [{COLORS['warning']}]程序异常退出 (code={r.returncode})[/]")
            input("  按 Enter 返回菜单...")
    except KeyboardInterrupt:
        console.print(f"\n  [{COLORS['warning']}]已中断[/]")
    except Exception as e:
        console.print(f"\n  [{COLORS['error']}]启动失败: {e}[/]")
        input("  按 Enter 返回菜单...")


# ── 主流程 ──────────────────────────────────────────────

def main():
    """默认入口：环境检测后直接启动聊天模式。用 --menu 回到旧版图形菜单。"""
    import argparse
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--menu", action="store_true", help="显示图形菜单（旧版启动器）")
    ap.add_argument("--no-check", action="store_true", help="跳过环境检测")
    a, _ = ap.parse_known_args()

    if a.menu:
        _main_menu()
        return

    _show_banner()
    if not a.no_check:
        console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [bold]环境检测[/]")
        console.print(f"  [{COLORS['muted']}{'─' * 40}[/]")
        if not check_python():
            input("\n按 Enter 退出...")
            sys.exit(1)
        check_env()
        check_deps()
        check_output_dir()
    console.print(f"\n  [{COLORS['muted']}]直接进入 CRUX Chat 模式...[/]")
    console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [{COLORS['primary']}]命令[/]  /code /agent /plan /team /deploy /showrun /help")
    console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [{COLORS['primary']}]换行[/]  Alt+Enter / Ctrl+J  ·  图片: 直接粘贴路径")
    launch(_crux_cmd(["-c"]))


def _main_menu():
    """旧版图形菜单（--menu 触发）"""
    _show_banner()
    console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [bold]环境检测[/]")
    console.print(f"  [{COLORS['muted']}{'─' * 40}[/]")
    if not check_python():
        input("\n按 Enter 退出...")
        sys.exit(1)
    check_env()
    check_deps()
    check_output_dir()
    try:
        from utils import memory
        tips = memory.get_tips()
        if tips:
            console.print(f"\n  [{COLORS['muted']}]💡 使用建议:[/]")
            for t in tips:
                console.print(f"  [{COLORS['muted']}]  {t}[/]")
    except (ImportError, AttributeError, OSError):
        pass
    show_menu()
    while True:
        console.print(f"\n  [{COLORS['primary']}]{ICONS['primary']}[/] 请选择 (0-8): ", end="")
        choice = input().strip()
        if choice == "0":
            console.print(f"\n  [{COLORS['success']}]{ICONS['success']}[/] 再见！\n")
            break
        if choice == "1":
            console.print(f"\n  [{COLORS['muted']}]正在启动交互菜单...[/]")
            launch(_crux_cmd([]))
            continue
        if choice == "2":
            console.print(f"\n  [{COLORS['muted']}]正在启动聊天+智能体模式...[/]")
            console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] 技能: /skill load 视频|作图|写剧本|分镜|炼丹...")
            console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] 换行: Alt+Enter / Ctrl+J  ·  图片: 直接粘贴路径")
            console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] 命令: /code /agent /plan /team /deploy /provider /help")
            launch(_crux_cmd(["-c"]))
            continue
        if choice == "3":
            console.print(f"\n  [{COLORS['muted']}]选择生成类型:[/]")
            console.print(f"  [{COLORS['accent']}]{1}[/] 图片  [{COLORS['accent']}]{2}[/] 视频  [{COLORS['accent']}]{3}[/] 流水线")
            console.print(f"  [{COLORS['primary']}]{ICONS['info']}[/] 选择 (1-3): ", end="")
            ch = input().strip()
            kind_map = {"1": "image", "2": "video", "3": "pipeline"}
            if ch not in kind_map:
                print_warn(f"无效选择 '{ch}'，已取消")
                continue
            kind = kind_map[ch]
            kind_names = {"image": "图片", "video": "视频", "pipeline": "一站式流水线"}
            console.print(f"  [{COLORS['muted']}]已选中: {kind_names.get(kind, kind)}[/]")
            result = ask_quick_prompt(kind=kind)
            if result:
                prompt, extra_args = result
                console.print(f"  [{COLORS['muted']}]正在启动生成...[/]")
                launch(_crux_cmd(["-q", prompt] + extra_args))
            else:
                print_warn("已取消（未输入描述）")
                continue
        if choice == "4":
            console.print(f"\n  [{COLORS['warning']}]{ICONS['warning']}[/] 图生图需要传入图片文件")
            console.print(f"  [{COLORS['muted']}]进入交互菜单后选 '2-图生图'，支持拖拽图片或输入路径[/]")
            input("  按 Enter 进入...")
            launch(_crux_cmd([]))
            continue
        if choice == "5":
            console.print(f"\n  [{COLORS['warning']}]{ICONS['warning']}[/] 图生视频需要传入图片文件")
            console.print(f"  [{COLORS['muted']}]进入交互菜单后选 '4-图生视频'，支持拖拽图片或输入路径[/]")
            console.print(f"  [{COLORS['muted']}]菜单内可选视频时长（3s~18s）[/]")
            input("  按 Enter 进入...")
            launch(_crux_cmd([]))
            continue
        if choice == "6":
            video_id = ask_video_id()
            if video_id:
                console.print(f"  [{COLORS['muted']}]正在查询 video_id: {video_id} ...[/]")
                launch(_crux_cmd(["--video-id", video_id]))
            else:
                print_warn("已取消（未输入 video_id）")
            continue
        if choice == "7":
            console.print(f"\n  [{COLORS['muted']}]一站式流水线: 文本 → AI 生图 → 图转视频[/]")
            result = ask_quick_prompt(kind="pipeline")
            if result:
                prompt, extra_args = result
                console.print(f"  [{COLORS['muted']}]正在启动流水线...[/]")
                launch(_crux_cmd(["-q", prompt] + extra_args))
            else:
                print_warn("已取消（未输入描述）")
                continue
        if choice == "8":
            faq_path = ROOT / "FAQ.md"
            if faq_path.exists():
                console.print(f"\n  [{COLORS['muted']}]正在打开 FAQ.md ...[/]")
                try:
                    import os
                    os.startfile(str(faq_path))
                    console.print(f"  [{COLORS['success']}]{ICONS['success']}[/] 已打开 FAQ 文档")
                except (OSError, AttributeError) as e:
                    console.print(f"  [{COLORS['warning']}]{ICONS['warning']}[/] 自动打开失败: {e}")
                    console.print(f"  [{COLORS['muted']}]请手动打开: {faq_path}[/]")
            else:
                print_warn("FAQ.md 文件不存在，请检查项目目录")
            input("  按 Enter 返回菜单...")
            continue
        print_warn(f"无效选择 '{choice}'，请输入 0-8")



if __name__ == "__main__":
    main()
