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

    # ── 聊天模式 ──────────────────────────────────────────

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
