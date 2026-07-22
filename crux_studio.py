#!/usr/bin/env python3
"""CRUX Studio main entry point"""

import logging
import sys
from pathlib import Path

import core.encoding as _enc
from core.workspace_guard import resolve_workspace

_enc.setup()

# ── Rich theme (fallback after UI removal) ────────────────────────
from rich.console import Console as _RC2

console = _RC2()
COLORS = {
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "primary": "blue",
    "muted": "dim white",
    "info": "cyan",
    # ── 分区独立配色 ──
    "thinking": "magenta",
    "status": "cyan bold",
    "tool": "bright_yellow",
    "comfyui": "green bold",
    "system": "blue bold",
}

# ── 必须在任何异步操作之前应用 nest_asyncio ──
# 解决 prompt_toolkit / Playwright / edge-tts 等库
# asyncio.run() 在已有运行事件循环时抛出 RuntimeError 的问题
try:
    import nest_asyncio

    nest_asyncio.apply()
except (ImportError, OSError, RuntimeError):
    # nest_asyncio 缺失或损坏（如 .so 与 Python 版本不兼容）时降级，
    # 后续 async 调用仍能通过 asyncio.run() / asyncio.new_event_loop() 工作
    import logging

    logging.getLogger("crux").debug("nest_asyncio unavailable, continuing")

# ── Global crash guard — install BEFORE any other imports ──
# Ensures every unhandled exception leaves a trace in the incident store,
# even during startup. Pattern: Claude Code's "always know why it broke".
from core.crash_guard import install as _install_crash_guard

_install_crash_guard()

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import contextlib
import re

from core.bootstrap import (
    run_startup_health as _run_startup_health,
)

# ── Phase 1 extraction: utilities moved to core/bootstrap.py ──
from core.bootstrap import (
    safe_rich_print as _safe_rich_print,
)
from core.colors import ANSI as _ANSI
from core.config import SETTINGS

# Clean up stale error file from previous crashed sessions
_stale_err = ROOT / "output" / "last_error.txt"
if _stale_err.exists():
    _stale_err.unlink()


def main():
    # ── 子命令预处理 ──────────────────────────────────────
    # 支持 crux gen|video|chat|query|check|version 子命令，
    # 同时完全保留 -q/-v/-c/-p/--video-id 等短选项（向后兼容所有 bat/sh 脚本）。
    # 子命令会被翻译成等价的 argv flags，然后走下面的 argparse 流程。
    _SUBCOMMANDS = {
        "gen": lambda rest: ["-q", *rest],  # crux gen "猫" → -q "猫"
        "image": lambda rest: ["-q", *rest],  # 别名
        "video": lambda rest: ["-q", *rest, "-v"],  # crux video "海边" → -q "海边" -v
        "serve": lambda rest: ["--serve", *rest],  # crux serve → --serve
        "chat": lambda rest: ["-c", *rest],
        "pipeline": lambda rest: ["-q" if rest else "", "-p", *rest] if rest else ["-p", *rest],
        "query": lambda rest: ["--video-id", *rest],  # crux query <id> → --video-id <id>
        "check": lambda rest: ["--check", *rest],
    }

    if len(sys.argv) >= 2 and sys.argv[1] in _SUBCOMMANDS:
        sub = sys.argv[1]
        rest = sys.argv[2:]
        if sub == "pipeline" and rest:
            sys.argv = [sys.argv[0], "-q", rest[0], "-p", *rest[1:]]
        else:
            sys.argv = [sys.argv[0], *_SUBCOMMANDS[sub](rest)]
    elif len(sys.argv) >= 2 and sys.argv[1] in ("version", "--version", "-V"):
        # crux version — 不需要 API Key，直接打印并退出
        from core.version import __version__

        print(f"CRUX Studio v{__version__}")
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] in ("init", "login"):
        _run_init()
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] in ("doctor", "health"):
        _run_doctor()
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == "mcp-serve":
        # crux mcp-serve — 启动 MCP server（stdio JSON-RPC），让 CRUX 作为
        # 与 codex/claude/codebuddy 对等的第四象被调用。绕过 API Key 强制校验
        # （server 自己从 config / auth.json 读取，与 init/version 同为早退分支）。
        # 程序化调用，不进 REPL，不出现在 launcher 菜单里。
        from core.mcp_server import run_mcp_server

        run_mcp_server(sys.argv[2:])
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == "mcp-bridge":
        # crux mcp-bridge — 启动 Claude Code MCP Bridge（让 CRUX 获得软件工程工具）
        from core.claude_mcp_bridge import main as bridge_main

        bridge_main()
        sys.exit(0)

    if not SETTINGS.api_key:
        print("Welcome to CRUX Studio!")
        print("No API key found. Let's set one up.\n")
        print("You need a DeepSeek API key (https://platform.deepseek.com/api_keys)")
        print("or a CRUX API key.\n")
        try:
            key = input("Paste your API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled. Run 'crux init' later to configure.")
            sys.exit(0)
        if key:
            import json
            import os

            auth_dir = os.path.expanduser("~/.crux")
            os.makedirs(auth_dir, exist_ok=True)
            auth_file = os.path.join(auth_dir, "auth.json")
            existing = {}
            if os.path.exists(auth_file):
                with open(auth_file) as f:
                    existing = json.load(f)
            existing["api_key"] = key
            with open(auth_file, "w") as f:
                json.dump(existing, f, indent=2)
            SETTINGS.api_key = key
            print("API key saved to ~/.crux/auth.json. Starting CRUX...\n")
        else:
            print("No key entered. Run 'crux init' later to configure.")
            sys.exit(0)

    import argparse

    p = argparse.ArgumentParser(description="CRUX Studio — code/create/deploy")
    p.add_argument("--check", action="store_true", help="启动前运行健康检查并退出")
    p.add_argument("--serve", action="store_true", help="启动 OpenAI 兼容 API 网关")
    p.add_argument("--host", type=str, default="127.0.0.1", help="网关监听地址 (配合 --serve, 默认 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="网关监听端口 (配合 --serve, 默认 8000)")
    p.add_argument("-c", "--chat", action="store_true", help="进入 CRUX 编程助手（支持 /制片 切换视频模式）")
    p.add_argument("--tui-v3", action="store_true", help="启动 TUI v3 界面（事件驱动新架构）")
    p.add_argument("-q", "--quick", type=str, help="快速模式描述")
    p.add_argument("-v", "--video", action="store_true", help="生成视频")
    p.add_argument("-p", "--pipeline", action="store_true", help="一站式流水线")
    p.add_argument("--no-enhance", action="store_true", help="禁用Prompt增强")
    p.add_argument("--size", type=str, default="1024x768")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--submit-only", action="store_true", help="仅提交任务，不等待结果（返回video_id）")
    p.add_argument("--video-id", type=str, default=None, help="查询指定视频状态（必须使用 video_id）")
    p.add_argument("--timeout", type=float, default=None, help="视频轮询超时秒数（默认120）")
    p.add_argument("--steps", type=int, default=40, help="视频推理步数(20-50，默认40，越高质量越好)")
    p.add_argument("--num-frames", type=int, default=None, help="视频帧数(8n+1, 如81/121/161/241/441)")
    p.add_argument("--frame-rate", type=int, default=None, help="视频帧率(默认24)")
    p.add_argument(
        "--creative", "--leap", action="store_true", help="启用创意飞跃模式（运用超越常人的思维方法生成突破性创意）"
    )
    p.add_argument(
        "--methods", type=str, default=None, help="指定创意方法（逗号分隔），如：cross_domain_graft,anti_pattern"
    )
    args = p.parse_args()

    # ── 健康检查 ──
    if args.check:
        from core.startup_checks import print_report, run_all

        results = run_all()
        print_report(results, show_ok=True)
        failures = [msg for _, ok, msg in results if not ok]
        if failures:
            print(f"\n  {len(failures)} check(s) failed")
            sys.exit(1)
        else:
            print("\n  所有检查通过")
            sys.exit(0)

    if args.video_id:
        # 清洗 litellm 包装的 video_id
        from engines.video import _clean_video_id

        args.video_id = _clean_video_id(args.video_id)
        _check_task(args)
    elif args.chat:
        # ── 根目录自动整理 ──
        try:
            from core.tidy_up import tidy_on_startup

            tidy_on_startup()
        except Exception as _e:
            console.print(f"  [dim]tidy_on_startup skipped: {_e}[/dim]")

        # ── 快速启动检查（仅本地，不阻塞网络）──
        try:
            import core.startup_checks as _sc
            from core.startup_checks import critical_failures, print_report, run_all

            # 跳过慢速网络检查（chat 模式不需要等 API 响应）
            _sc._check_api_connectivity = lambda: None
            results = run_all()
            crit = critical_failures(results)
            if crit:
                console.print("\n  [bold {}]=== Startup check found issues ===[/]".format(COLORS["error"]))
                print_report(results, show_ok=False)
                console.print("  [{}]Run: crux check[/]\n".format(COLORS["warning"]))
            else:
                # 只在有 warning 时才输出
                warnings = [(c, m) for c, ok, m in results if not ok]
                if warnings:
                    for _cat, msg in warnings:
                        console.print("  [{}]![/] {}".format(COLORS["warning"], msg))
        except (ImportError, AttributeError, OSError):
            pass

        # Launch chat
        if getattr(args, "tui_v3", False):
            _chat_repl_v3(args)
        else:
            _chat_repl(args)
    elif args.serve:
        from core.gateway.server import run_server

        run_server(host=args.host, port=args.port)
    elif args.quick:
        _quick(args)
    else:
        # 默认入口：聊天
        if getattr(args, "tui_v3", False):
            _chat_repl_v3(args)
        else:
            _chat_repl(args)


def _make_chat_client():
    """Create a CruxClient whose base_url/api_key match the active provider.

    Previously the chat entry points passed a bare ``CruxClient()`` which
    defaulted to the CRUX API URL, while ``ChatSession`` derived its default
    model from the active provider (e.g. deepseek).  That model↔URL mismatch
    sent deepseek model IDs to the CRUX server, yielding HTTP 503
    ``model_not_found``.
    """
    from core.provider import get_provider_manager

    try:
        return get_provider_manager().create_client()
    except Exception as _e:
        console.print(f"  [yellow]Provider client init failed, using default: {_e}[/yellow]")
        from core.client import CruxClient

        return CruxClient()


def _chat_repl(args=None):
    """Chat REPL entry point — plain text by default."""
    _chat_plain()


def _chat_repl_v3(args=None):
    """Launch the v3 event-driven TUI (experimental)."""
    cwd = resolve_workspace()
    client = _make_chat_client()

    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI
    from core.version import __version__

    session = ChatSession(client)
    cli = CruxCLI(session)

    # ── Banner ──
    geom = [
        "           /\\          /\\            ",
        "  +-------/  \\--------/  \\-------+   ",
        "  |      / /\\ \\  CRUX  / /\\ \\      |",
        "  |     / /  \\ \\      / /  \\ \\     |",
        "  |     \\ \\  / /      \\ \\  / /     |",
        "  |      \\ \\/ / STUDIO \\ \\/ /      |",
        "  +-------\\  /--------\\  /-------+   ",
        "           \\/          \\/            ",
    ]
    for line in geom:
        print(f"  {line}")
        print(f"  CRUX Studio v{__version__}  ·  v3 event-driven TUI")
        print()

        import shutil

        if shutil.get_terminal_size().lines < 10:
            print("Terminal too small (need >=10 rows).", file=sys.stderr)
            sys.exit(1)

        from ui.v3.app import V3App

    v3 = V3App(session=session, cli=cli, cwd=cwd)
    v3.run()


def _chat_plain():
    """Plain text REPL."""
    import uuid

    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI
    from core.version import __version__

    _rprint = _safe_rich_print()
    _p = print
    cwd = resolve_workspace()

    session_id = f"session_{uuid.uuid4().hex[:8]}"
    try:
        from core.session_wire import SessionWire

        wire = SessionWire(cwd)
        wire.start_session(session_id=session_id)
    except (ImportError, OSError):
        wire = None

    try:
        session = ChatSession(_make_chat_client())
        # ── 会话恢复 ──
        snapshot = ChatSession.restore_latest_snapshot()
        if snapshot and snapshot.get("messages"):
            turn = snapshot.get("turn", "?")
            msgs = snapshot["messages"]
            msg_count = len(msgs)
            _p(f"  ⚡ 检测到未完成的会话 (第 {turn} 轮, {msg_count} 条消息)")
            recent = [m for m in msgs[-6:] if m.get("role") in ("user", "assistant")]
            for m in recent[-4:]:
                role = "You" if m["role"] == "user" else "CRUX"
                content = str(m.get("content", ""))[:100].replace("\n", " ")
                _p(f"    [{role}] {content}...")
            try:
                ans = input("  是否恢复? [Y/n] ").strip().lower()
                if ans in ("", "y", "yes"):
                    session.messages = msgs
                    session.model = snapshot.get("model", session.model)
                    _p(f"  已恢复 {msg_count} 条消息到上下文，模型: {session.model}")
            except (EOFError, KeyboardInterrupt):
                _p("  自动跳过（非交互模式）")
    except Exception as e:
        _p(f"初始化失败: {e}", file=sys.stderr)
        sys.exit(1)

    cli = CruxCLI(session)

    # ── Startup banner ──
    W = _ANSI.get("bright_white", "")
    C = _ANSI.get("bright_cyan", "")
    G = _ANSI.get("bright_green", "")
    D = _ANSI.get("dim", "")
    R = _ANSI.get("reset", "")

    # ── Banner: ASCII geometric CRUX logo ──
    geom = [
        "           /\\          /\\            ",
        "  +-------/  \\--------/  \\-------+   ",
        "  |      / /\\ \\  CRUX  / /\\ \\      |",
        "  |     / /  \\ \\      / /  \\ \\     |",
        "  |     \\ \\  / /      \\ \\  / /     |",
        "  |      \\ \\/ / STUDIO \\ \\/ /      |",
        "  +-------\\  /--------\\  /-------+   ",
        "           \\/          \\/            ",
    ]
    print()
    for line in geom:
        print(f"  {C}{line}{R}")
    print()
    print(f"  {W}CRUX Studio{R}  {C}v{__version__}{R}  ·  {G}DeepSeek V4 Pro{R}  ·  1M 上下文")
    print(f"  {D}极简内核 · 百器待命 · 七兽按需 · Multi-Agent{R}")
    print(f"  {D}平时如刀，出事成阵 —— Sharp by default. A swarm when needed.{R}")
    print()
    print(f"  {C}/ask{R}   开始 AI 编程    {C}/agent{R}  选择专业智能体")
    print(f"  {C}/swarm{R}  并行编排        {C}/skills{R} 浏览技能")
    print(f"  {C}/help{R}   查看全部命令    {C}Ctrl+V{R}  粘贴  {C}Enter{R}  发送")
    print()

    _chat_plain_session(session, cli, wire, session_id)


def _md_colorize(text: str, c: dict) -> str:
    """Apply markdown syntax highlighting with ANSI colors.

    Colorizes: **bold**, *italic*, `code`, [links](url),
    ```code blocks```, # headers, > blockquotes, - lists.
    Base color restored after each highlight.
    """
    base = c.get("ai", "")
    G = c.get("bright_green", c.get("green", ""))
    Y = c.get("bright_yellow", c.get("yellow", ""))
    B = c.get("bright_blue", c.get("blue", ""))
    C = c.get("bright_cyan", c.get("cyan", ""))

    # Code blocks: ``` ... ```
    text = re.sub(
        r"```(\w*)\n(.*?)```",
        lambda m: f"{c['reset']}{c['bold']}{G}{m.group(2).strip()}{c['reset']}{base}",
        text,
        flags=re.DOTALL,
    )
    # Inline code: `code`
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"{c['reset']}{c['bold']}{Y}{m.group(1)}{c['reset']}{base}",
        text,
    )
    # Headers: # ## ###
    text = re.sub(
        r"^(#{1,3})\s+(.+)$",
        lambda m: f"{c['reset']}{c['bold']}{C}{m.group(1)} {m.group(2)}{c['reset']}{base}",
        text,
        flags=re.MULTILINE,
    )
    # Bold: **text**
    text = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: f"{c['reset']}{c['bold']}{base}{m.group(1)}{c['reset']}{base}",
        text,
    )
    # Italic: *text*
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        lambda m: f"{c['reset']}{c['italic']}{base}{m.group(1)}{c['reset']}{base}",
        text,
    )
    # Links: [text](url)
    text = re.sub(
        r"(?<!\x1b)\[([^\]]+)\]\([^)]+\)",
        lambda m: f"{c['reset']}{c['underline']}{B}{m.group(1)}{c['reset']}{base}",
        text,
    )
    # Blockquotes: > text
    text = re.sub(
        r"^(>\s?)(.+)$",
        lambda m: f"{c['reset']}{c['dim']}▎ {m.group(2)}{c['reset']}{base}",
        text,
        flags=re.MULTILINE,
    )
    return text


def _chat_plain_session(session, cli, wire, session_id: str = "") -> None:
    """Core plain-text REPL loop — shared by _chat_plain() and TUI fallback."""
    _rprint = _safe_rich_print()
    _setup_readline_completion(cli)

    # ── ANSI color check ──
    try:
        test = f"{_ANSI['green']}✓{_ANSI['reset']} ANSI colors enabled"
        print(test, flush=True)
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)

    # ── 启动自愈 + 自优化 ──────────────────────────────────
    _run_startup_health()

    while True:
        try:
            # Bright green prompt + input text
            line = input(f"{_ANSI['bright_green']}> {_ANSI['reset']}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if wire:
            with contextlib.suppress(Exception):
                wire.record_turn("user", line)
        if line in ("/q", "/quit", "/exit"):
            break
        if line == "/h":
            cli._chat_help_inline("")
            print()
            continue
        if cli.dispatch(line):
            print()
            continue
        try:
            for kind, payload in session.send_stream(line):
                try:
                    if kind == "text":
                        text = _md_colorize(str(payload), _ANSI)
                        colored = f"{_ANSI['ai']}{text}{_ANSI['reset']}"
                        sys.stdout.write(colored)
                        sys.stdout.flush()
                    elif kind == "info":
                        msg = str(payload)[:200]
                        print(f"  {_ANSI['bright_yellow']}{msg}{_ANSI['reset']}")
                    elif kind == "error":
                        msg = str(payload)[:200]
                        print(f"\n  {_ANSI['bright_red']}✗ {msg}{_ANSI['reset']}", file=sys.stderr)
                    elif kind == "tool_result":
                        name = payload.get("name", "") if isinstance(payload, dict) else ""
                        result = payload.get("result", str(payload)) if isinstance(payload, dict) else str(payload)
                        print(f"  {_ANSI['bright_blue']}  {name}: {result[:120]}{_ANSI['reset']}")
                    elif kind in ("image", "video"):
                        data = payload if isinstance(payload, dict) else {}
                        local = data.get("local_path", "")
                        if local:
                            print(f"  已保存: {local}")
                except Exception:
                    import logging

                    logging.getLogger(__name__).debug("silent except", exc_info=True)
            if wire:
                with contextlib.suppress(Exception):
                    wire.record_turn("assistant", "[streamed response]")
        except Exception as e:
            print(f"错误: {e}")
        print()


def _setup_readline_completion(cli) -> None:
    """Set up tab completion for slash commands using readline."""
    try:
        import readline

        commands = cli.get_commands_for_completion()

        def completer(text: str, state: int) -> str | None:
            if text.startswith("/"):
                matches = [c for c in commands if c.startswith(text)]
                if state < len(matches):
                    return matches[state]
            return None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    except (ImportError, OSError):
        pass  # readline not available (e.g. Windows without pyreadline)


def _check_task(args):
    """查询视频任务状态"""
    from core.client import CruxClient

    # UI display stubs (TUI removed)
    def show_info(*_a, **_kw):
        pass

    def show_success(*_a, **_kw):
        pass

    def show_video_result(*_a, **_kw):
        pass

    def show_warning(*_a, **_kw):
        pass

    with CruxClient() as client:
        video_id = args.video_id
        if not video_id:
            show_warning("必须提供 --video-id 查询视频状态，不要使用 task_id")
            return
        show_info(f"查询视频ID {video_id}...")
        data = client.check_video(video_id=video_id)
        status = data.get("status", "unknown")
        progress = data.get("progress", 0)

        if status == "completed":
            show_success("视频已完成!")
            video_url = data.get("video_url") or data.get("remixed_from_video_id", "")
            local_path = ""
            if video_url and video_url.startswith("http"):
                from datetime import datetime

                from core.config import OUTPUT_DIR

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_path = str(OUTPUT_DIR / "videos" / f"vid_{ts}.mp4")
                try:
                    client.download_video(video_url, local_path)
                    show_success(f"已下载: {local_path}")
                except RuntimeError as e:
                    show_warning(f"下载失败: {e}")
            show_video_result({"url": video_url, "local_path": local_path, "video_id": video_id})
        elif status == "failed":
            # show_error stub (TUI removed)
            logging.getLogger(__name__).error("视频生成失败: %s", data.get("error", "未知错误"))
        else:
            show_info(f"状态: {status} | 进度: {progress:.0f}%")
            if status in ("processing", "in_progress", "pending", "queued"):
                show_info(f"使用 --video-id {video_id} 可再次查询，或加 --timeout 等待完成")


def _quick(args):
    from core.brain import SmartBrain
    from core.client import ContentPolicyError, CruxClient
    from engines.pipeline.workflows import PipelineOrchestrator
    from engines.text_to_image import TextToImageEngine
    from engines.video import VideoEngine

    # UI display stubs (TUI removed)
    def show_image_result(*_a, **_kw):
        pass

    def show_info(*_a, **_kw):
        pass

    def show_pipeline_result(*_a, **_kw):
        pass

    def show_video_result(*_a, **_kw):
        pass

    def show_warning(*_a, **_kw):
        pass

    # History stub
    class _HistoryStub:
        @staticmethod
        def add_record(*_a, **_kw):
            pass

    history = _HistoryStub()

    with CruxClient() as client:
        prompt = args.quick
        enhance = not args.no_enhance
        creative = args.creative
        creative_methods = [m.strip() for m in args.methods.split(",")] if args.methods else None
        timeout = args.timeout or 120.0
        nf = args.num_frames or 121
        fps = args.frame_rate or 24

        brain = SmartBrain(client) if (enhance or creative) else None

        if args.pipeline:
            show_info("一站式流水线...")
            try:
                result = PipelineOrchestrator(client).text_to_image_to_video(
                    args.quick,
                    enhance=enhance,
                    submit_only=args.submit_only,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                    timeout=timeout,
                )
            except ContentPolicyError as e:
                show_warning(str(e))
                sys.exit(0)
            if args.submit_only:
                vid_result = result.get("video", {})
                display_id = vid_result.get("video_id", "N/A")
                show_info(f"视频任务已提交! ID: {display_id}")
                query_id = vid_result.get("video_id", "")
                if query_id:
                    show_info(f"使用以下命令查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，请检查任务响应")
            else:
                show_pipeline_result(result)
            history.add_record("pipeline", args.quick, "multi", result)
        elif args.video:
            vid_prompt = prompt
            neg = ""
            if brain:
                if creative:
                    show_info("创意飞跃模式（视频）：运用超越常人的思维方法...")
                    r = brain.creative_leap(args.quick, methods=creative_methods)
                    leaps = r.get("creative_leaps", [])
                    idx = r.get("recommended_leap_index", 0)
                    if leaps and idx < len(leaps):
                        # 创意飞跃生成的是图片概念，需进一步增强为视频
                        leap_prompt = leaps[idx].get("optimized_prompt", prompt)
                        vid_r = brain.enhance_video_prompt(leap_prompt)
                        vid_prompt = vid_r.get("optimized_prompt", leap_prompt)
                        neg = vid_r.get("negative_prompt", "")
                        show_info(f"创意方法: {r.get('methods_used', [])}")
                        if r.get("guardrail_warning"):
                            show_warning(r["guardrail_warning"])
                    else:
                        show_warning("创意飞跃未产生有效方案，回退到普通增强")
                        r = brain.enhance_video_prompt(args.quick)
                        vid_prompt = r.get("optimized_prompt", prompt)
                        neg = r.get("negative_prompt", "")
                elif enhance:
                    show_info("优化视频提示词...")
                    r = brain.enhance_video_prompt(args.quick)
                    vid_prompt = r.get("optimized_prompt", prompt)
                    neg = r.get("negative_prompt", "")

            if args.submit_only:
                show_info("提交视频任务（仅提交，不等待）...")
                data = VideoEngine(client).submit_only(
                    prompt=vid_prompt,
                    seed=args.seed,
                    negative_prompt=neg or None,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                )
                display_id = data.get("video_id", "N/A")
                show_info(f"任务已提交! ID: {display_id}")
                query_id = data.get("video_id", "")
                if query_id:
                    show_info(f"使用以下命令查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，请检查任务响应")
                history.add_record("text_to_video", args.quick, "agnes-video-v2.0", data)
            else:
                show_info("生成视频...")

                def on_p(status, progress, data):
                    print(f"\r  [{status}] {progress:.0f}%", end="", flush=True)

                data = VideoEngine(client).text_to_video(
                    prompt=vid_prompt,
                    negative_prompt=neg or None,
                    seed=args.seed,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                    on_progress=on_p,
                    timeout=timeout,
                )
                print()
                if data.get("status") == "timeout":
                    show_warning(f"超时({timeout}s)，当前进度 {data.get('progress', 0):.0f}%")
                    query_id = data.get("video_id", "")
                    if query_id:
                        show_info(f"使用以下命令继续等待: crux query {query_id} --watch")
                    else:
                        show_warning("未返回 video_id，无法自动查询")
                else:
                    show_video_result(data)
                history.add_record("text_to_video", args.quick, "agnes-video-v2.0", data)
        else:
            img_prompt = prompt
            neg = ""
            if brain:
                if creative:
                    show_info("创意飞跃模式：运用超越常人的思维方法...")
                    r = brain.creative_leap(args.quick, methods=creative_methods)
                    leaps = r.get("creative_leaps", [])
                    idx = r.get("recommended_leap_index", 0)
                    if leaps and idx < len(leaps):
                        img_prompt = leaps[idx].get("optimized_prompt", prompt)
                        neg = leaps[idx].get("negative_prompt", "")
                        show_info(f"创意方法: {r.get('methods_used', [])}")
                        for i, leap in enumerate(leaps):
                            marker = "★" if i == idx else " "
                            show_info(f"  {marker} [{leap.get('method', '?')}] {leap.get('leap_description', '')[:60]}")
                        if r.get("guardrail_warning"):
                            show_warning(r["guardrail_warning"])
                    else:
                        show_warning("创意飞跃未产生有效方案，回退到普通增强")
                        r = brain.enhance_image_prompt(args.quick)
                        img_prompt = r.get("optimized_prompt", prompt)
                        neg = r.get("negative_prompt", "")
                elif enhance:
                    show_info("优化图片提示词...")
                    r = brain.enhance_image_prompt(args.quick)
                    img_prompt = r.get("optimized_prompt", prompt)
                    neg = r.get("negative_prompt", "")

            show_info("生成图片...")
            data = TextToImageEngine(client).generate(
                prompt=img_prompt, size=args.size, seed=args.seed, negative_prompt=neg or None
            )
            show_image_result(data)
            history.add_record("text_to_image", args.quick, data.get("model", ""), data)


def _run_init():
    """crux init / crux login — 写全局 ~/.crux/auth.json。

    对标 codex 首次运行引导：一次配置，任意目录敲 crux 都能用。
    交互式读取 API Key（不在命令行明文回显，避免 shell history 泄露）。
    """
    from core.config import AUTH_FILE, SETTINGS, save_global_auth

    print()
    print("  CRUX 全局配置初始化")
    print(f"  将写入: {AUTH_FILE}")
    print("  (此文件存 API Key，仅本机可读，配置后任意目录均可启动 crux)")
    print()

    # 预填：已有 key 时显示尾号，回车保留
    existing = SETTINGS.api_key
    if existing:
        print(f"  当前已配置 key: ...{existing[-8:]}")
        key = input("  输入新 CRUX_API_KEY (回车保留现有): ").strip()
        if not key:
            key = existing
    else:
        key = input("  请输入 CRUX_API_KEY: ").strip()

    if not key:
        print("  未输入 key，已取消。")
        return

    base_url = input("  CRUX_BASE_URL (回车用默认 https://apihub.agnes-ai.com/v1): ").strip()
    base_url = base_url or "https://apihub.agnes-ai.com/v1"

    try:
        path = save_global_auth(key, base_url)
    except OSError as e:
        print(f"  写入失败: {e}")
        return

    print()
    print(f"  ✓ 已保存到 {path}")
    print("  ✓ 现在在任意目录敲 crux 都能用。")
    print()


def _run_doctor():
    """crux doctor — 系统健康诊断。"""
    import os
    import sys
    from pathlib import Path

    from core.version import __version__

    print(f"  CRUX Studio v{__version__}")
    print(f"  Python: {sys.version}")
    print(f"  Platform: {sys.platform}")
    print()

    checks = []
    # Python version
    py_ok = sys.version_info >= (3, 11)
    checks.append(("Python >= 3.11", py_ok, "Install Python 3.11+ from python.org"))
    # API key
    env_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("CRUX_API_KEY")
    from core.config import SETTINGS

    config_key = SETTINGS.api_key
    checks.append(("API key configured", bool(env_key or config_key), "Run: crux init"))
    # Git
    try:
        import subprocess

        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        checks.append(("Git installed", r.returncode == 0, "Install git from https://git-scm.com"))
    except Exception:
        checks.append(("Git installed", False, "Install git from https://git-scm.com"))
    # pip packages
    try:
        from importlib.util import find_spec

        for pkg in ("httpx", "PIL", "rich", "yaml"):
            if find_spec(pkg) is None:
                raise ImportError(pkg)
        checks.append(("Core dependencies", True, None))
    except ImportError as e:
        checks.append(("Core dependencies", False, f"Run: pip install -r requirements.txt ({e})"))
    # CRUX root
    crux_root = Path(__file__).resolve().parent
    checks.append(("CRUX install dir exists", crux_root.is_dir(), "Reinstall: pip install -e ."))
    # models.json
    checks.append(("models.json exists", (crux_root / "models.json").is_file(), "Restore from git or template"))
    # output dir writable
    out = crux_root / "output"
    out_ok = (
        out.is_dir() and os.access(out, os.W_OK)
        if out.exists()
        else out.parent.is_dir() and os.access(out.parent, os.W_OK)
    )
    checks.append(("Output directory writable", out_ok, "Check disk space and permissions"))

    all_ok = True
    for name, ok, fix in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok and fix:
            print(f"         Fix: {fix}")
            all_ok = False
    print()
    if all_ok:
        print("  All checks passed. CRUX is ready.")
    else:
        print("  Some checks failed. Fix the issues above and try again.")


def main_doctor():
    """CLI entry: crux doctor"""
    _run_doctor()


def main_chat():
    """命令行入口：直接进入 CRUX 编程助手"""
    import sys

    sys.argv = [sys.argv[0], "-c"]
    main()


def main_query():
    """命令行入口：查询未完成视频"""
    from query import main as qmain

    qmain()


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        import datetime
        import traceback

        crash_log = Path(__file__).parent / "output" / "crash.log"
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
