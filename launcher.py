#!/usr/bin/env python3
"""Agnes Smart Studio 图形启动器 - 环境检测 + 模式选择 + 一键启动"""

import os
import sys
import subprocess
from pathlib import Path

# Windows UTF-8 兼容
if os.name == "nt":
    os.system("chcp 65001 >nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── 颜色常量 ──────────────────────────────────────────────
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"

BANNER = f"""
{C_CYAN}{C_BOLD}
  ___                     _   ____ _               _
 / _ \\ _ __   ___ _ __  (_) / ___| |__   ___  ___| | __
| | | | '_ \\ / _ \\ '_ \\ | || |   | '_ \\ / _ \\/ __| |/ /
| |_| | | | |  __/ | | || || |___| | | |  __/ (__|   <
 \\___/|_| |_|\\___|_| |_||_| \\____|_| |_|\\___|\\___|_|\\_\\{C_RESET}{C_DIM} v2.0{C_RESET}
"""


def print_step(msg: str):
    print(f"  {C_CYAN}➜{C_RESET} {msg}")


def print_ok(msg: str):
    print(f"  {C_GREEN}✔{C_RESET} {msg}")


def print_warn(msg: str):
    print(f"  {C_YELLOW}⚠{C_RESET} {msg}")


def print_err(msg: str):
    print(f"  {C_RED}✖{C_RESET} {msg}")


def run_cmd(cmd: str) -> tuple[int, str]:
    """运行命令并返回 (returncode, output)"""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
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
        answer = input(f"  {C_YELLOW}是否创建 .env 文件？(y/n):{C_RESET} ").strip().lower()
        if answer == "y":
            api_key = input(f"  {C_CYAN}请输入 AGNES_API_KEY:{C_RESET} ").strip()
            env_file.write_text(
                f"# Agnes AI API 配置\n"
                f"AGNES_API_KEY={api_key}\n"
                f"AGNES_BASE_URL=https://apihub.agnes-ai.com/v1\n",
                encoding="utf-8",
            )
            print_ok(".env 已创建")
            return True
        print_err("跳过 .env 创建，部分功能不可用")
        return False

    # 检查 API Key 是否已填写
    content = env_file.read_text(encoding="utf-8")
    if "sk-your-api-key-here" in content or "AGNES_API_KEY=\n" in content or "AGNES_API_KEY=" not in content:
        print_warn("API Key 未配置")
        api_key = input(f"  {C_CYAN}请输入 AGNES_API_KEY (留空跳过):{C_RESET} ").strip()
        if api_key:
            lines = []
            for line in content.splitlines():
                if line.startswith("AGNES_API_KEY="):
                    lines.append(f"AGNES_API_KEY={api_key}")
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
    "1": ("🖥️  交互菜单",     "文生图/图生图/视频/历史/模板"),
    "2": ("💬  聊天+智能体",  "36技能 + Alt+Enter换行 + 一键制片/作图/炼丹"),
    "3": ("⚡  快速生成",     "输入描述 → 选类型 → 选视频时长 → 一键生成"),
    "4": ("🖼️  图生图",      "图片编辑/风格迁移 → 进入交互菜单操作"),
    "5": ("🎬  图生视频",    "图片→视频，可选3s~18s时长"),
    "6": ("📋  查询视频",    "video_id 查进度（不要用 task_id）"),
    "7": ("🔗  一站式流水线","文本→图片→视频 全自动"),
    "8": ("📖  查看FAQ",     "常见问题/APIKey/视频时长/thinking/programming"),
    "0": ("退出", ""),
}


def show_menu():
    print(f"\n{C_BOLD}  选择模式:{C_RESET}")
    print(f"  {C_DIM}{'─' * 55}{C_RESET}")
    for key, (label, desc) in MODES.items():
        if desc:
            print(f"  {C_CYAN}{key}{C_RESET}  {label:<10} {C_DIM}{desc}{C_RESET}")
        else:
            print(f"  {C_CYAN}{key}{C_RESET}  {label}")
    print(f"  {C_DIM}{'─' * 55}{C_RESET}")


def ask_video_id() -> str | None:
    video_id = input(f"  {C_CYAN}请输入 video_id:{C_RESET} ").strip()
    return video_id or None


def ask_video_duration() -> tuple[int, int]:
    """选择视频时长，返回 (num_frames, frame_rate)"""
    # 帧数列表 (8n+1, <=441)
    frames_list = [81, 121, 161, 241, 441]
    dur_map = {81: "3s", 121: "5s", 161: "7s", 241: "10s", 441: "18s"}
    print(f"\n  {C_DIM}选择视频时长 (fps=24):{C_RESET}")
    for i, nf in enumerate(frames_list, 1):
        print(f"  {C_CYAN}{i}{C_RESET} {nf}帧≈{dur_map[nf]}")
    ch = input(f"  {C_CYAN}选择 (1-5, 默认2=5s):{C_RESET} ").strip() or "2"
    idx = max(0, min(4, int(ch) - 1)) if ch.isdigit() else 1
    return frames_list[idx], 24


def ask_quick_prompt(kind: str = "image") -> tuple[str, list[str]] | None:
    """快速生成：输入描述，视频/流水线可选时长

    kind: "image" / "video" / "pipeline"
    """
    prompt = input(f"  {C_CYAN}请输入描述:{C_RESET} ").strip()
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


def launch(cmd_parts: list[str]):
    """启动主程序，失败时提示错误并暂停"""
    cmd = " ".join(cmd_parts)
    print(f"\n  {C_DIM}执行: {cmd}{C_RESET}\n")
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(ROOT))
        if r.returncode != 0:
            print(f"\n  {C_YELLOW}程序异常退出 (code={r.returncode}){C_RESET}")
            input(f"  {C_DIM}按 Enter 返回菜单...{C_RESET}")
    except KeyboardInterrupt:
        print(f"\n  {C_YELLOW}已中断{C_RESET}")
    except Exception as e:
        print(f"\n  {C_RED}启动失败: {e}{C_RESET}")
        input(f"  {C_DIM}按 Enter 返回菜单...{C_RESET}")


# ── 主流程 ──────────────────────────────────────────────

def main():
    print(BANNER)

    # 1. 环境检测
    print(f"{C_BOLD}  环境检测{C_RESET}")
    print(f"  {C_DIM}{'─' * 40}{C_RESET}")

    if not check_python():
        input("\n按 Enter 退出...")
        sys.exit(1)

    check_env()       # 不阻断，允许继续
    check_deps()      # 不阻断，允许继续
    check_output_dir()

    # 记忆统计
    try:
        from utils import memory
        tips = memory.get_tips()
        if tips:
            print(f"\n  {C_DIM}💡 使用建议:{C_RESET}")
            for t in tips:
                print(f"  {C_DIM}  {t}{C_RESET}")
    except Exception:
        pass

    # 2. 主菜单循环
    while True:
        show_menu()
        choice = input(f"\n  {C_CYAN}请选择 (0-8):{C_RESET} ").strip()

        # ── 退出 ──
        if choice == "0":
            print(f"\n  {C_GREEN}再见！{C_RESET}\n")
            break

        # ── 模式 1: 交互菜单 ──
        # 启动完整的 CLI 交互界面，包含文生图/图生图/视频/历史等全部功能
        if choice == "1":
            print(f"\n  {C_DIM}正在启动交互菜单...{C_RESET}")
            launch(["python", "agnes_studio.py"])
            continue

        # ── 模式 2: 聊天+智能体 ──
        if choice == "2":
            print(f"\n  {C_DIM}正在启动聊天+智能体模式...{C_RESET}")
            print(f"  {C_CYAN}技能: /skill load 视频|作图|写剧本|分镜|炼丹...{C_RESET}")
            print(f"  {C_CYAN}换行: Alt+Enter / Ctrl+J  ·  图片: 直接粘贴路径{C_RESET}")
            print(f"  {C_DIM}命令: /code /agent /plan /team /deploy /provider /help{C_RESET}")
            launch(["python", "agnes_studio.py", "-c"])
            continue

        # ── 模式 3: 快速生成 ──
        # 先选类型（图片/视频/流水线），再输入描述，视频和流水线会额外询问时长
        if choice == "3":
            print(f"\n  {C_DIM}选择生成类型:{C_RESET}")
            print(f"  {C_CYAN}1{C_RESET} 图片  {C_CYAN}2{C_RESET} 视频  {C_CYAN}3{C_RESET} 流水线")
            ch = input(f"  {C_CYAN}选择 (1-3):{C_RESET} ").strip()
            kind_map = {"1": "image", "2": "video", "3": "pipeline"}
            if ch not in kind_map:
                print_warn(f"无效选择 '{ch}'，已取消")
                continue
            kind = kind_map[ch]
            kind_names = {"image": "图片", "video": "视频", "pipeline": "一站式流水线"}
            print(f"  {C_DIM}已选中: {kind_names.get(kind, kind)}{C_RESET}")
            result = ask_quick_prompt(kind=kind)
            if result:
                prompt, extra_args = result
                print(f"  {C_DIM}正在启动生成...{C_RESET}")
                launch(["python", "agnes_studio.py", "-q", f'"{prompt}"'] + extra_args)
            else:
                print_warn("已取消（未输入描述）")
            continue

        # ── 模式 4: 图生图 ──
        # 图生图需要图片文件输入，启动交互菜单（菜单内选 #2）
        if choice == "4":
            print(f"\n  {C_YELLOW}⚠ 图生图需要传入图片文件{C_RESET}")
            print(f"  {C_DIM}进入交互菜单后选 '2-图生图'，支持拖拽图片或输入路径{C_RESET}")
            input(f"  {C_DIM}按 Enter 进入...{C_RESET}")
            launch(["python", "agnes_studio.py"])
            continue

        # ── 模式 5: 图生视频 ──
        # 图生视频同样需要图片文件，菜单内选 #4
        if choice == "5":
            print(f"\n  {C_YELLOW}⚠ 图生视频需要传入图片文件{C_RESET}")
            print(f"  {C_DIM}进入交互菜单后选 '4-图生视频'，支持拖拽图片或输入路径{C_RESET}")
            print(f"  {C_DIM}菜单内可选视频时长（3s~18s）{C_RESET}")
            input(f"  {C_DIM}按 Enter 进入...{C_RESET}")
            launch(["python", "agnes_studio.py"])
            continue

        # ── 模式 6: 查询视频 ──
        # 输入 video_id 查询生成进度（⚠ 必须用 video_id，不要用 task_id）
        if choice == "6":
            video_id = ask_video_id()
            if video_id:
                print(f"  {C_DIM}正在查询 video_id: {video_id} ...{C_RESET}")
                launch(["python", "agnes_studio.py", "--video-id", video_id])
            else:
                print_warn("已取消（未输入 video_id）")
            continue

        # ── 模式 7: 一站式流水线 ──
        # 输入描述 → 选时长 → 文本 → 图片 → 视频，全自动
        if choice == "7":
            print(f"\n  {C_DIM}一站式流水线: 文本 → AI 生图 → 图转视频{C_RESET}")
            result = ask_quick_prompt(kind="pipeline")
            if result:
                prompt, extra_args = result
                print(f"  {C_DIM}正在启动流水线...{C_RESET}")
                launch(["python", "agnes_studio.py", "-q", f'"{prompt}"'] + extra_args)
            else:
                print_warn("已取消（未输入描述）")
            continue

        # ── 模式 8: 查看 FAQ ──
        # 用系统默认程序打开 FAQ.md
        if choice == "8":
            faq_path = ROOT / "FAQ.md"
            if faq_path.exists():
                print(f"\n  {C_DIM}正在打开 FAQ.md ...{C_RESET}")
                try:
                    import os
                    os.startfile(str(faq_path))
                    print(f"  {C_GREEN}已打开 FAQ 文档{C_RESET}")
                except Exception as e:
                    print(f"  {C_YELLOW}自动打开失败: {e}{C_RESET}")
                    print(f"  {C_DIM}请手动打开: {faq_path}{C_RESET}")
            else:
                print_warn("FAQ.md 文件不存在，请检查项目目录")
            input(f"  {C_DIM}按 Enter 返回菜单...{C_RESET}")
            continue

        print_warn(f"无效选择 '{choice}'，请输入 0-8")


if __name__ == "__main__":
    main()
