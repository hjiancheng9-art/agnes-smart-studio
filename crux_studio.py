#!/usr/bin/env python3
"""CRUX Studio main entry point"""

import sys
from pathlib import Path

import core.encoding as _enc

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

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import contextlib

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
        # crux init / crux login — 写全局 ~/.crux/auth.json，对标 codex 首次引导。
        # 不需要 API Key（这就是配置它的命令），独立处理直接退出。
        _run_init()
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
        print("错误: 未设置 CRUX_API_KEY（兼容 AGNES_API_KEY）")
        print("  解决: 运行  crux init    写入全局配置（一次配置，任意目录可用）")
        print("  或:   在当前目录建 .env 文件，加 CRUX_API_KEY=你的key")
        print("  或:   设系统环境变量 CRUX_API_KEY")
        sys.exit(1)

    import argparse

    p = argparse.ArgumentParser(description="CRUX Studio — code/create/deploy")
    p.add_argument("--check", action="store_true", help="启动前运行健康检查并退出")
    p.add_argument("-c", "--chat", action="store_true", help="进入 CRUX 编程助手（支持 /制片 切换视频模式）")
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
        _chat_repl()
    elif args.quick:
        _quick(args)
    else:
        # 默认入口：聊天
        _chat_repl()


def _run_startup_health() -> None:
    """每次进入 REPL 前自动执行轻量健康检查。

    安静模式：只日志，不打印到屏幕，避免打断启动流程。
    """
    import logging

    logger = logging.getLogger("crux.bootstrap")
    try:
        # 1. 确保 MCP 配置文件存在（首次启动时写入默认 4 桥接）
        from core.mcp_client import _mcp_client, ensure_mcp_servers

        ensure_mcp_servers()

        # 2. 如果 MCP 单例还在但配置已更新（如 >5 条幽灵），自动重载
        if _mcp_client is not None and len(_mcp_client._servers) > 5:
            old = len(_mcp_client._servers)
            n = _mcp_client.reload_config()
            logger.info("bootstrap: MCP config reloaded (%d → %d)", old, n)

        # 3. DNA identity check — warn via logger only, never a screen
        try:
            from core.startup_checks import _check_dna_identity
            _check_dna_identity()
        except Exception:
            logger.debug("bootstrap: DNA check skipped", exc_info=True)

        logger.debug("bootstrap health check complete")
    except Exception:
        logger.debug("bootstrap health check skipped", exc_info=True)


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
    except Exception:
        from core.client import CruxClient

        return CruxClient()


def _chat_repl():
    """Chat REPL entry point — routes to TUI or plain text mode."""
    if sys.stdout.isatty():
        _chat_tui()
    else:
        _chat_plain()


def _chat_tui():
    """Kimi-style TUI chat — prompt_toolkit three-zone interface."""
    import uuid
    from pathlib import Path

    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI

    cwd = Path.cwd()
    _rprint = _safe_rich_print()

    # ── Session wire init ──
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    try:
        from core.session_wire import SessionWire

        wire = SessionWire(cwd)
        wire.start_session(session_id=session_id)
    except (ImportError, OSError):
        wire = None

    # ── Init chat session ──
    try:
        session = ChatSession(_make_chat_client())
    except Exception as e:
        print(f"初始化失败: {e}", file=sys.stderr)
        sys.exit(1)

    cli = CruxCLI(session)

    # ── Startup banner (minimal, TUI handles the welcome screen) ──
    import shutil

    from core.provider import get_provider_manager
    from core.version import __version__

    mgr = get_provider_manager()
    model_name = mgr.get_model("light") or session.model

    # Banner text for TUI message pane (not printed to terminal —
    # the TUI welcome screen in build_welcome_formatted handles UI)
    import unicodedata

    def _vwidth(s: str) -> int:
        """Visual width — CJK chars count as 2 cells."""
        w = 0
        for c in s:
            w += 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        return w

    TARGET_BOX_W = 50
    INNER_W = TARGET_BOX_W - 4  # strip "  ╔…╗" frame (2 leading spaces + corners)

    # ── top: ═══ text ═══ centred ──
    tag = f" CRUX Studio v{__version__} · 平时如刀，出事成阵 "
    tag_w = _vwidth(tag)
    pad_total = max(0, INNER_W - tag_w)
    left = pad_total // 2
    right = pad_total - left
    top_line = f"  ╔{'═' * left}{tag}{'═' * right}╗"

    # ── content lines ──
    content = [
        "极简内核 · 97+ 工具 · 按需治理",
        "热路径 <1K · 冷路径按需展开",
        "七兽不坐副驾驶 · 出事才上场",
    ]
    content_lines = []
    for line in content:
        pad = INNER_W - _vwidth(f"  {line}")  # "  " prefix inside box
        content_lines.append(f"  ║  {line}{' ' * max(0, pad)}║")

    # ── bottom ──
    bottom_line = f"  ╚{'═' * INNER_W}╝"

    banner = (
        top_line + "\n"
        + "\n".join(content_lines) + "\n"
        + bottom_line + "\n"
        + "\n"
        + f"  ◈ {model_name} · 主人: 黄建程\n"
        + f"  ◈ 根因优先 → 最小复现 → 一次修对\n"
        f"\n"
        f"  试试这些:\n"
        f"    /status  查看状态    /health  系统健康\n"
        f"    /help    命令列表    /skill   技能市场\n"
        f"    Ctrl+V 粘贴   Enter 发送\n"
    )
    # ── Terminal height guard ──
    if shutil.get_terminal_size().lines < 10:
        print("Terminal too small (need >=10 rows). Falling back to plain text mode.")
        _chat_plain_session(session, cli, wire, session_id)
        return

    # ── Hide Windows console scrollbar (native, not ptk) ──
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE

            class _COORD(ctypes.Structure):
                _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

            class _SMALL_RECT(ctypes.Structure):
                _fields_ = [
                    ("Left", ctypes.c_short),
                    ("Top", ctypes.c_short),
                    ("Right", ctypes.c_short),
                    ("Bottom", ctypes.c_short),
                ]

            class _CSBI(ctypes.Structure):
                _fields_ = [
                    ("dwSize", _COORD),
                    ("dwCursorPosition", _COORD),
                    ("wAttributes", ctypes.c_ushort),
                    ("srWindow", _SMALL_RECT),
                    ("dwMaximumWindowSize", _COORD),
                ]

            csbi = _CSBI()
            if kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi)):
                cols = csbi.srWindow.Right - csbi.srWindow.Left + 1
                rows = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                if cols < csbi.dwSize.X or rows < csbi.dwSize.Y:
                    kernel32.SetConsoleScreenBufferSize(handle, _COORD(cols, rows))
        except Exception:
            pass

    # ── Launch TUI (v2) ──
    # prompt_toolkit handles full terminal management — no pre-escapes needed.
    try:
        from ui.tui_v2 import TuiAppV2

        app = TuiAppV2(session, cli, session_wire=wire, startup_banner=banner)
        app.run()
    except ImportError as e:
        print(f"TUI 模块加载失败: {e}", file=sys.stderr)
        print("回退到纯文本模式。")
        _chat_plain_session(session, cli, wire, session_id)
    except Exception as e:
        msg = str(e)
        if any(kw in msg for kw in ("NoConsoleScreenBufferError", "winpty", "xterm", "expecting a Windows console")):
            print("此终端不支持全屏 TUI。请使用 Windows Terminal 或 cmd.exe 启动。")
        else:
            import traceback

            traceback.print_exc()
            print(f"\nTUI 启动失败: {e}", file=sys.stderr)
        print("回退到纯文本模式...")
        _chat_plain_session(session, cli, wire, session_id)

    # ── Cleanup ──
    if wire:
        with contextlib.suppress(OSError):
            wire.end_session()


def _chat_plain():
    """Plain text REPL — fallback when no TTY or TUI unavailable."""
    import uuid
    from pathlib import Path

    from core.chat import ChatSession
    from core.cli_handlers import CruxCLI
    from core.version import __version__

    _rprint = _safe_rich_print()
    _p = print
    cwd = Path.cwd()

    session_id = f"session_{uuid.uuid4().hex[:8]}"
    try:
        from core.session_wire import SessionWire

        wire = SessionWire(cwd)
        wire.start_session(session_id=session_id)
    except (ImportError, OSError):
        wire = None

    try:
        session = ChatSession(_make_chat_client())
    except Exception as e:
        _p(f"初始化失败: {e}", file=sys.stderr)
        sys.exit(1)

    CruxCLI(session)

    # ── Startup banner ──
    _rprint()
    _rprint(f"[bold cyan]◆  CRUX Studio  v{__version__}[/] — [dim]平时如刀，出事成阵[/]")
    _rprint()
    _rprint(f"[bold]Working Directory:[/] [cyan]{cwd}[/]")
    _print_kimi_tree(cwd)
    _rprint()
    agents_path = cwd / "AGENTS.md"
    if agents_path.exists():
        try:
            agents_content = agents_path.read_text(encoding="utf-8")
            first_line = agents_content.strip().split("\n")[0]
            _rprint(f"[bold]AGENTS.md:[/] {first_line}")
            for line in agents_content.split("\n"):
                line = line.strip()
                if line.startswith("- Entry:") or line.startswith("- Core:") or line.startswith("- Engines:"):
                    _rprint(f"  {line}")
        except OSError:
            pass
    _rprint()
    _rprint("[bold]Skills:[/]")
    _print_skills_summary()
    _rprint()
    if wire:
        _rprint(f"[dim]Session: {session_id}[/]")
    _rprint("[dim]Type /help for all commands, /q to quit[/]")
    _rprint()


def _chat_plain_session(session, cli, wire, session_id: str = "") -> None:
    """Core plain-text REPL loop — shared by _chat_plain() and TUI fallback."""
    _rprint = _safe_rich_print()
    _setup_readline_completion(cli)

    # ── 启动自愈 + 自优化 ──────────────────────────────────
    _run_startup_health()

    while True:
        try:
            line = input("> ").strip()
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
                if kind == "text":
                    sys.stdout.write(payload)
                    sys.stdout.flush()
                elif kind == "info":
                    _rprint(f"[dim]  {payload}[/]")
                elif kind == "error":
                    print(f"\n  ⚠ {payload}", file=sys.stderr)
                elif kind in ("image", "video"):
                    data = payload if isinstance(payload, dict) else {}
                    local = data.get("local_path", "")
                    url = data.get("url", data.get("video_url", ""))
                    if local:
                        _rprint(f"[green]  已保存: {local}[/]")
                    elif url:
                        _rprint(f"[green]  URL: {url}[/]")
            if wire:
                with contextlib.suppress(Exception):
                    wire.record_turn("assistant", "[streamed response]")
        except Exception as e:
            _rprint(f"[red]错误: {e}[/]")
        print()


def _safe_rich_print():
    """Return a print function that uses Rich if available, plain print otherwise."""
    try:
        from rich.console import Console

        rc = Console(highlight=False)

        def _rp(text: str = "", **kwargs) -> None:
            rc.print(text, **kwargs)

        return _rp
    except ImportError:
        return print


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


def _print_kimi_tree(root: Path, max_depth: int = 2) -> None:
    """Print a Kimi-style directory tree (first N levels, censored hidden dirs)."""

    SKIP_DIRS = {
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        "egg-info",
    }
    SKIP_FILES = {".DS_Store", "Thumbs.db", "nul", "python"}  # nul=Windows NUL artifact

    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        print("  (permission denied)")
        return

    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file() and e.name not in SKIP_FILES]

    lines: list[str] = []
    shown = 0
    FILE_CAP = 20  # max root-level files to show
    DIR_CAP = 40  # max root-level dirs

    # ── Directories first ──
    for entry in dirs:
        if shown >= DIR_CAP:
            remaining_dirs = len(dirs) - shown
            lines.append(f"  ... and {remaining_dirs} more directories")
            break
        name = entry.name
        marker = "/" if not name.startswith(".") and name not in SKIP_DIRS else "/"
        lines.append(f"  {name}{marker}")
        if max_depth > 1 and not name.startswith(".") and name not in SKIP_DIRS:
            try:
                sub_entries = sorted(entry.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                shown += 1
                continue
            for sub_idx, sub in enumerate(sub_entries):
                if sub_idx >= 15:
                    remaining = sum(1 for _ in entry.iterdir())
                    lines.append(f"    ... and {remaining - sub_idx} more")
                    break
                sname = sub.name
                if sub.is_dir():
                    lines.append(f"    {sname}/")
                elif sname not in SKIP_FILES:
                    lines.append(f"    {sname}")
        shown += 1

    # ── Files second (capped) ──
    for entry in files[:FILE_CAP]:
        lines.append(f"  {entry.name}")
    if len(files) > FILE_CAP:
        lines.append(f"  ... and {len(files) - FILE_CAP} more files")

    if not lines:
        print("  (empty)")
        return
    print("  ```")
    for line in lines:
        print(line)
    print("  ```")


def _print_skills_summary() -> None:
    """Print available skills grouped by scope (Kimi-style)."""
    from pathlib import Path

    # Built-in skills
    builtin_skills = ["update-config", "write-goal"]

    # Project skills (local skills dir)
    project_dir = Path(__file__).parent / "skills"
    project_skills: list[str] = []
    if project_dir.exists():
        for f in sorted(project_dir.glob("*.skill.json")):
            project_skills.append(f.stem.replace(".skill", ""))
        for f in sorted(project_dir.glob("*.skill.md")):
            project_skills.append(f.stem.replace(".skill", ""))

    # Marketplace count
    marketplace_count = 668  # from AGENTS.md

    print(
        f"  Scope: Built-in ({len(builtin_skills)})  |  Project ({len(project_skills)})  |  Marketplace ({marketplace_count})"
    )
    if project_skills:
        shown = project_skills[:8]
        print(f"  Project skills: {', '.join(shown)}" + ("..." if len(project_skills) > 8 else ""))
    print(f"  Built-in: {', '.join(builtin_skills)}")
    print()
    print("  Use /skill list to browse, /skill load <name> to activate.")


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
            print(f"错误: 视频生成失败: {data.get('error', '未知错误')}", file=sys.stderr)
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
