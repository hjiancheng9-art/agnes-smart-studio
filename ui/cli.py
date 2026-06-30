"""Rich CLI 交互界面 — CruxCLI 主壳。

本文件只保留 CruxCLI 的核心生命周期（__init__/close/run/_chat 主循环），
所有命令处理器已按职责拆分到 ui/mixins/ 下的 7 个 Mixin：

    SharedMixin           — 输入/渲染/选择/分发（基础层）
    InlineCommandsMixin   — /clear /thinking /code /agent /tools /help /img /video
    CreativeCommandsMixin — /showrun /vision /skill + _chat_generate
    EngineeringCommandsMixin — /plan /sub /project /team /deploy /todo /refactor
    GitCommandsMixin      — /commit /changelog
    DiagCommandsMixin     — /self /audit /rules /provider /evolve /know /model
    GeneratorsMenuMixin   — 菜单生成组 _t2i/_i2i/_t2v/_i2v/_pipeline

核心约束：getattr(self, handler_name) 反射依赖 self 始终是 CruxCLI 实例，
因此采用多重继承 Mixin 而非组合。core/commands.py 的 dispatch 表零改动。
"""

import os
import sys
import threading

from rich.panel import Panel
from rich.prompt import Prompt

from core.brain import SmartBrain
from core.client import ContentPolicyError, CruxClient
from core.config import CRUX_VISION_BASE_URL, get_crux_vision_model, SETTINGS
from core.version import __version__  # 单一版本真源
from engines.image_to_image import ImageToImageEngine
from engines.text_to_image import TextToImageEngine
from engines.video import VideoEngine
from engines.pipeline.workflows import PipelineOrchestrator
from ui.beautify import splash_full
from ui.display import show_error, show_info, show_warning
from ui.mixins import (
    CreativeCommandsMixin,
    DiagCommandsMixin,
    EngineeringCommandsMixin,
    GeneratorsMenuMixin,
    GitCommandsMixin,
    InlineCommandsMixin,
    SharedMixin,
)
from ui.terminal_logo import render_rich
from ui.theme import COLORS, ICONS, LAYOUT, console
from utils import memory

__all__ = ["CruxCLI", "LOGO"]

# Dynamic logo — built on first access
LOGO = None


def _get_logo():
    global LOGO
    if LOGO is None:
        LOGO = render_rich(v=f"v{__version__}")
    return LOGO


class CruxCLI(
    SharedMixin,
    InlineCommandsMixin,
    CreativeCommandsMixin,
    EngineeringCommandsMixin,
    GitCommandsMixin,
    DiagCommandsMixin,
    GeneratorsMenuMixin,
):
    """CRUX Studio CLI.

    通过多重继承组合 7 个 Mixin，每个 Mixin 提供一组命令处理器。
    self 始终是 CruxCLI 实例，getattr(self, handler) 反射正常工作。
    """

    def __init__(self):
        self.client = CruxClient()
        # 独立视觉客户端：始终指向 CRUX API，与主对话供应商解耦
        self.vision_client = CruxClient(
            api_key=SETTINGS.api_key,
            base_url=CRUX_VISION_BASE_URL,
        )
        self.brain = SmartBrain(self.client)
        self.t2i = TextToImageEngine(self.client)
        self.i2i = ImageToImageEngine(self.client)
        self.vid = VideoEngine(self.client)
        self.pipe = PipelineOrchestrator(self.client)

    def close(self):
        self.client.close()
        self.vision_client.close()

    def __enter__(self):
        return self

    def _select_provider_tui(self):
        """Auto-select provider for TUI mode (no interactive console menu)."""
        import json
        import os as _os
        from pathlib import Path as _Path

        cfg = self._load_models_config()
        cfg_path = _Path(__file__).parent.parent / "models.json"
        providers = cfg.get("providers", {})
        # Find first available external provider with an API key
        first_external = None
        for pid, p in providers.items():
            if pid == "crux":
                continue
            key_env = f"{pid.upper()}_API_KEY"
            api_key = p.get("api_key") or _os.getenv(key_env)
            if api_key or not p.get("auth_required", True):
                first_external = (pid, p, api_key or "")
                break
        if first_external:
            pid, p, api_key = first_external
            model = p.get("models", {}).get("pro", "unknown")
            # Actually activate the provider (reconfigures client + writes config)
            self._activate_provider(pid, p, model, api_key, cfg, str(cfg_path))
            return (pid, model)
        # Fall back to CRUX
        p = providers.get("crux", {})
        return ("crux", p.get("models", {}).get("light", "agnes-1.5-flash"))

    def __exit__(self, *_):
        self.close()

    # ── 多行输入支持 ───────────────────────────────

    _prompt_session = None  # 类级复用 prompt_toolkit session

    def run(self):
        """v6 启动流程 — 欢迎页 → 紧凑启动器 → 聊天直达。

        Chat 是默认入口（Enter 即进入）。创意工具通过 [g] 子菜单访问。
        """
        from ui.terminal_logo import render_welcome
        from ui.screen import render_boot

        # 启动动画 (~1s)
        render_boot(v=f"v{__version__}", animate=True)
        console.print()  # 分隔

        # 欢迎页
        render_welcome(v=f"v{__version__}")

        P = COLORS["primary"]
        M = COLORS["text_secondary"]
        T = COLORS["text_tertiary"]
        G = COLORS["success"]
        A = COLORS["accent"]

        while True:
            choice = Prompt.ask(
                f"\n  [{P}]Chat[/] [{T}](Enter)[/]  "
                f"[{A}]Generate[/] [{T}](g)[/]  "
                f"[{P}]History[/] [{T}](h)[/]  "
                f"[{P}]Templates[/] [{T}](t)[/]  "
                f"[{COLORS['error']}]Exit[/] [{T}](q)[/]",
                choices=["", "g", "h", "t", "q"],
                default="",
                show_choices=False,
            )
            if choice == "q":
                break
            try:
                if choice == "":
                    import asyncio
                    asyncio.run(self._chat())
                elif choice == "g":
                    self._gen_menu()
                elif choice == "h":
                    self._hist()
                elif choice == "t":
                    self._tmpl()
            except ContentPolicyError as e:
                show_warning(str(e))
            except Exception as e:
                show_error(str(e))

        # 退出时显示记忆统计
        tips = memory.get_tips()
        if tips:
            console.print(f"\n[{T}]{LAYOUT['separator_char'] * LAYOUT['separator_len']}[/]")
            for t in tips:
                console.print(f"  [{T}]·[/] [{T}]{t}[/]")

    def _gen_menu(self):
        """v6 生成子菜单 — 紧凑，替代旧 1-5 选项。"""
        P = COLORS["primary"]
        M = COLORS["text_secondary"]
        T = COLORS["text_tertiary"]
        A = COLORS["accent"]

        console.print(f"\n  [{A}]── 生成工具 ──────────────────────────────[/]")
        items = [
            ("1", "Text → Image", self._t2i),
            ("2", "Image → Image", self._i2i),
            ("3", "Text → Video", self._t2v),
            ("4", "Image → Video", self._i2v),
            ("5", "Pipeline (T→I→V)", self._pipeline),
        ]
        for key, label, _fn in items:
            console.print(f"  [{P}]{key}[/] [{M}]{label}[/]")

        ch = Prompt.ask(
            f"  [{T}]选择 (Enter=返回)[/]",
            choices=["", "1", "2", "3", "4", "5"],
            default="",
            show_choices=False,
        )
        fn_map = {k: f for k, _, f in items}
        if ch and ch in fn_map:
            try:
                fn_map[ch]()
            except ContentPolicyError as e:
                show_warning(str(e))
            except Exception as e:
                show_error(str(e))

    # ── 命令分发基础设施 ──────────────────────────────────

    # Dispatch 返回值标记
    _DISPATCH_OK = True
    _DISPATCH_UNKNOWN = None
    _DISPATCH_EXIT = "EXIT"

    # 延迟构建的 dispatch table（首次调用时初始化）
    _dispatch_table: dict | None = None

    # ── 聊天模式 ────────────────────────────────────

    async def _chat(self):
        """聊天模式：异步引擎 — AI 生成时输入框不消失，可插话排队。

        流式生成在后台线程运行，主线程立即恢复输入等待。
        """
        import asyncio
        import threading
        from core.chat import ChatSession

        active_provider, active_model = self._select_provider()
        auto_mode = active_provider == "auto"

        console.print()
        display_model = "auto" if auto_mode else active_model
        console.print(
            Panel(
                f"[bold {COLORS['primary']}]◆ Studio v{__version__}[/]  "
                f"[{COLORS['text_secondary']}]{display_model}[/]  "
                f"[{COLORS['success']}]● online[/]",
                border_style=COLORS["border_focus"],
                padding=LAYOUT["panel_padding"],
            )
        )

        session = ChatSession(self.client, vision_client=self.vision_client, vision_model=get_crux_vision_model())
        session.model = active_model
        session.auto_model = auto_mode
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}

        from ui.badges import print_context_bar, render_badge_line
        _last_badge_line = ""
        _pending: str | None = None  # 排队中的输入
        _stream_done = threading.Event()
        _stream_done.set()  # 初始状态：无流在跑

        while True:
            current = render_badge_line(session, dim=False)
            if current != _last_badge_line:
                print_context_bar(session)
                _last_badge_line = current

            # 如果上一轮排队了输入，直接处理
            if _pending is not None:
                raw = _pending
                _pending = None
            else:
                try:
                    raw = self._prompt_user(self._mode_hint(session)).strip()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    break
                except OSError as e:
                    # stdin 不可用时优雅降级（例如被重定向或终端已关闭）
                    show_error(f"输入不可用: {e}")
                    break
                except Exception as e:
                    show_error(f"输入异常: {type(e).__name__}: {e}")
                    continue
            if not raw:
                continue

            if "\\n" in raw:
                raw = raw.replace("\\n", "\n")
            if raw == '"""':
                user = self._read_multiline()
                if user is None:
                    continue
            else:
                user = raw

            # 斜杠命令
            if user.startswith("/"):
                cmd, _, arg = user[1:].partition(" ")
                arg = arg.strip()
                if cmd in ("exit", "quit", "q"):
                    break
                dispatched = self._dispatch_command(cmd, arg, session)
                if dispatched == self._DISPATCH_EXIT:
                    break
                elif dispatched == self._DISPATCH_UNKNOWN:
                    show_warning(f"未知命令 /{cmd}，输入 /help 查看")
                continue

            # 图片路由
            img_path, clean_text = self._extract_path_and_text(user)
            if img_path and img_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                try:
                    self._chat_vision(session, user)
                except Exception as e:
                    show_error(f"图片处理异常: {type(e).__name__}: {e}")
                continue

            # ── 自然语言对话：后台流式生成 ──
            if session.auto_model:
                tier = session._auto_route(user)
                if tier:
                    tier_icon = {"light": "⚡", "pro": "◆", "reasoner": "🔬"}.get(tier, "◆")
                    console.print(f"  [dim]{tier_icon} auto → {session.model}[/]")

            _stream_done.clear()

            def _run_stream():
                try:
                    self._stream_chat(session, user)
                except Exception:
                    pass
                finally:
                    _stream_done.set()

            stream_thread = threading.Thread(target=_run_stream, daemon=True)
            stream_thread.start()

            # 流式生成期间：显示可见的状态提示（不用 promp_toolkit，避免与 Live 终端冲突）
            # 不支持排队输入——简化方案保证终端状态干净，流结束后立即恢复输入框
            hint = "  [dim]⏳ AI 生成中... 请等待[/]"
            console.print(hint)
            _stream_done.wait()
            stream_thread.join(timeout=2)

    # ── Terminal 聊天模式 ─────────────────────────

    def _chat_terminal(self):
        """全屏终端聊天模式 — 固定输入框不被滚动消息打扰。

        使用 prompt_toolkit Application 构建 Claude Code 风格界面：
        - 上部消息区（可滚动，Rich 渲染）
        - 中部状态栏（模型/耗时）
        - 下部输入框（固定，始终可见可交互）
        """
        import asyncio
        import threading
        from core.chat import ChatSession
        from ui.terminal_app import CruxTerminalApp

        # In TUI mode, auto-select the first available provider to avoid
        # the interactive console menu (which blocks the event loop).
        active_provider, active_model = self._select_provider_tui()
        auto_mode = active_provider == "auto"
        display_model = "auto" if auto_mode else active_model

        session = ChatSession(
            self.client,
            vision_client=self.vision_client,
            vision_model=get_crux_vision_model(),
        )
        session.model = active_model
        session.auto_model = auto_mode
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}

        _stream_done = threading.Event()
        _stream_done.set()
        _interrupted = False

        _stream_thread_ref: list = []  # mutable ref to active stream thread

        # ── on_submit 回调：处理用户输入 ──
        def _handle_input(user: str) -> None:
            nonlocal _interrupted

            # 等待上一轮流结束
            if not _stream_done.is_set():
                _stream_done.wait()

            _interrupted = False

            try:
                # 斜杠命令
                if user.startswith("/"):
                    cmd, _, arg = user[1:].partition(" ")
                    arg = arg.strip()
                    if cmd in ("exit", "quit", "q"):
                        terminal_app.exit()
                        return
                    # ── /beast — 兽魂主题切换 ──
                    if cmd == "beast":
                        from ui.flourish import BEAST_THEMES
                        if not arg:
                            names = "  ".join(
                                f"{t.icon} {n}" for n, t in BEAST_THEMES.items()
                            )
                            terminal_app.add_message(
                                "system",
                                f"Beasts:\n{names}\n\nUsage: /beast <name>",
                            )
                        else:
                            label = terminal_app.set_beast(arg)
                            if label:
                                terminal_app.add_message(
                                    "system",
                                    f"{terminal_app.beast_theme.icon} Beast: {label}",
                                )
                                terminal_app.sparkle()
                            else:
                                terminal_app.add_message(
                                    "system",
                                    f"Unknown beast '{arg}'. Try: {', '.join(BEAST_THEMES)}",
                                )
                        return
                    dispatched = self._dispatch_command(cmd, arg, session)
                    if dispatched == self._DISPATCH_EXIT:
                        terminal_app.exit()
                        return
                    if dispatched == self._DISPATCH_UNKNOWN:
                        terminal_app.add_message("system", f"Unknown command /{cmd}, type /help")
                    return

                # 图片路由
                img_path, clean_text = self._extract_path_and_text(user)
                if img_path and img_path.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
                ):
                    try:
                        self._chat_vision(session, user)
                    except Exception as e:
                        terminal_app.add_message("system", f"Image error: {e}")
                    return

                # 自动路由
                if session.auto_model:
                    tier = session._auto_route(user)
                    if tier:
                        tier_icon = {"light": "⚡", "pro": "◆", "reasoner": "🔬"}.get(tier, "◆")
                        terminal_app.add_message("system", f"{tier_icon} auto → {session.model}")

                # ── 显示用户消息 ──
                terminal_app.add_message("user", user)

                # ── 自然语言：后台流式生成 ──
                _stream_done.clear()

                def _run_stream():
                    """Consume send_stream directly, route to terminal app."""
                    terminal_app.start_generating()
                    try:
                        stream = session.send_stream(user)
                        for kind, payload in stream:
                            if _interrupted:
                                break
                            if kind == "text":
                                terminal_app.add_stream_chunk(payload)
                            elif kind == "error":
                                terminal_app.commit_stream()
                                terminal_app.add_message("system", f"✗ {payload}")
                            elif kind == "info":
                                terminal_app.commit_stream()
                                terminal_app.add_message("system", payload)
                            elif kind in ("image", "video"):
                                terminal_app.commit_stream()
                                terminal_app.sparkle()
                                try:
                                    from core.async_render import default_side_effect_handlers
                                    handler = default_side_effect_handlers().get(kind)
                                    if handler:
                                        handler(kind, payload)
                                except Exception:
                                    pass
                            elif kind == "confirm":
                                terminal_app.commit_stream()
                                msg = payload if isinstance(payload, str) else payload.get("message", "Permission required")
                                terminal_app.add_message("system", msg)
                        terminal_app.commit_stream()
                    except Exception as _e:
                        import traceback as _tb
                        _err_msg = f"{type(_e).__name__}: {_e}"
                        terminal_app.add_message("system", f"✗ {_err_msg}")
                        terminal_app.flash_error()
                        # Write full traceback to log for debugging
                        try:
                            from pathlib import Path as _Path
                            _log = _Path(__file__).parent.parent / "output" / "last_error.txt"
                            _log.parent.mkdir(parents=True, exist_ok=True)
                            _log.write_text(_tb.format_exc(), encoding="utf-8")
                        except Exception:
                            pass
                    finally:
                        terminal_app.stop_generating()
                        terminal_app.set_status(f"● {display_model}  ·  ready")
                        _stream_done.set()

                stream_thread = threading.Thread(target=_run_stream, daemon=True)
                # Update stream thread ref for interrupt handling
                _stream_thread_ref.clear()
                _stream_thread_ref.append(stream_thread)
                stream_thread.start()

                # Update status
                terminal_app.set_status(
                    f"● {display_model}  ·  generating..."
                )

            except Exception as e:
                terminal_app.add_message("system", f"Error: {e}")
                _stream_done.set()

        # ── on_interrupt 回调 ──
        def _handle_interrupt():
            nonlocal _interrupted
            _interrupted = True
            terminal_app.commit_stream()
            terminal_app.add_message("system", "⏹ Interrupted")
            terminal_app.set_status(f"● {display_model}  ·  ready")

        # ── 轮询流完成状态，更新状态栏 ──
        def _poll_stream_done(app: CruxTerminalApp):
            """After stream completes, update status bar."""
            if _stream_done.is_set():
                app.set_status(f"● {display_model}  ·  ready")

        # ── 启动终端应用 ──
        terminal_app = CruxTerminalApp(
            on_submit=_handle_input,
            on_interrupt=_handle_interrupt,
        )
        terminal_app.set_header(f"◆ Studio v{__version__}  ·  {display_model}  ·  ● online")

        # Swap console to route Rich output → terminal app
        from ui.theme import _LayoutSink
        old_sink = console._sink
        sink = _LayoutSink(layout=terminal_app, real_console=console._real_console)
        console.set_sink(sink)

        try:
            terminal_app.run()
        except KeyboardInterrupt:
            pass
        finally:
            console.restore_real_console()

    # ── TODO 扫描 ─────────────────────────────
    # 递归遍历项目文件，用正则匹配 TODO / FIXME / HACK / XXX / OPTIMIZE / BUG 标签
    # 只扫描代码和文档文件（.py/.js/.ts/.md/.html/.css/.sh/.bat），输出文件名+行号+内容

    # ── 自动 Commit ───────────────────────────
    # 1. 读取 git diff --staged（已暂存的更改）
    # 2. 将 diff 内容发给 LLM，让它生成简洁的中文 commit 消息
    # 3. 确认后自动执行 git commit

    # ── Changelog ─────────────────────────────
    # 1. 读取 git log（默认最近 7 天，可指定时间段如 "14 days ago"）
    # 2. 发给 LLM 分类汇总（新增/修复/优化/其他）
    # 3. 可选保存为 CHANGELOG.md

    # ── 批量重构 ──────────────────────────────
    # 用 sed 在指定路径下批量替换文本（仅 .py/.js/.ts/.md 文件）
    # ⚠ 不可逆操作，执行前会确认

    # ── 依赖审计 ──────────────────────────────
    # 检查 pip 和 npm 依赖的：
    # 1. 过期版本（pip list --outdated / npm outdated）
    # 2. 已知安全漏洞（pip-audit / npm audit）
    # 支持 pip / npm / all 三种范围

    # ── Rules 系统 ────────────────────────────
    # 管理持久化编码规范，启用后自动注入到每次会话的 system prompt
    # rules/ 目录下的 .rules.md 文件即规范内容

    # ── 自动化任务 ────────────────────────────
    # 存储定时任务定义到 output/automations/tasks.json
    # cron 格式: "分 时 日 月 周"，如 "0 9 * * 1" = 每周一早 9 点
    # 实际执行需配合外部调度器（如 Windows 任务计划 / cron）

    # ── 多模型供应商 ──────────────────────────
    # 从 models.json 读取供应商配置，运行时切换 base_url + api_key
    # 支持 CRUX / DeepSeek / Kimi 等任意 OpenAI 兼容 API
    # API Key 从环境变量 {PROVIDER}_API_KEY 或手动输入
