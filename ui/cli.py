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

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from core.client import CruxClient, ContentPolicyError
from core.brain import SmartBrain
from core.config import SETTINGS, CRUX_VISION_MODEL, CRUX_VISION_BASE_URL
from core.version import __version__  # 单一版本真源
from engines.text_to_image import TextToImageEngine
from engines.image_to_image import ImageToImageEngine
from engines.video import VideoEngine
from pipeline.workflows import PipelineOrchestrator
from utils import memory
from ui.theme import COLORS, ICONS, LAYOUT, console
from ui.display import show_error, show_warning, show_info
from ui.terminal_logo import render_rich as _render_logo_rich
from ui.mixins import (
    SharedMixin, InlineCommandsMixin, CreativeCommandsMixin,
    EngineeringCommandsMixin, GitCommandsMixin, DiagCommandsMixin,
    GeneratorsMenuMixin,
)

__all__ = ['CruxCLI', 'LOGO']


def _build_logo() -> str:
    """Build the organic pixel logo as Rich markup."""
    return _render_logo_rich(v=f'v{__version__}')


LOGO = _build_logo()


class CruxCLI(SharedMixin, InlineCommandsMixin, CreativeCommandsMixin,
               EngineeringCommandsMixin, GitCommandsMixin, DiagCommandsMixin,
               GeneratorsMenuMixin):
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
        console.print(LOGO)
        while True:
            console.print()
            menu = Table(title=f"[{COLORS['primary']}]{ICONS['primary']} Menu[/]", show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style=f"bold {COLORS['accent']}", width=4)
            menu.add_column("Name", style="white", width=16)
            menu.add_column("Desc", style="dim")
            for k, n, d in [
                ("1",f"{ICONS['primary']} Text→Image","Generate image from text"),
                ("2",f"{ICONS['empty']} Image→Image","Edit / style transfer"),
                ("3",f"{ICONS['video']} Text→Video","Generate video from text"),
                ("4",f"{ICONS['video']} Image→Video","Animate an image"),
                ("5",f"{ICONS['pipeline']} Pipeline","Text → Image → Video"),
                ("6",f"{ICONS['history']} History","View generation history"),
                ("7",f"{ICONS['template']} Templates","Browse style templates"),
                ("8",f"{ICONS['primary']} Chat","AI conversation with generation"),
                ("0",f"{ICONS['error']} Exit",""),
            ]:
                menu.add_row(k, n, d)
            console.print(menu)

            ch = Prompt.ask(f"[{COLORS['primary']}]{ICONS['primary']} Select[/]", choices=["0","1","2","3","4","5","6","7","8"], default="1")
            if ch == "0":
                break
            try:
                {"1": self._t2i, "2": self._i2i, "3": self._t2v,
                 "4": self._i2v, "5": self._pipeline, "6": self._hist, "7": self._tmpl,
                 "8": self._chat}[ch]()
            except ContentPolicyError as e:
                show_warning(str(e))
            except Exception as e:
                show_error(str(e))

        # 退出时显示记忆统计
        tips = memory.get_tips()
        if tips:
            console.print(f"\n[dim]{LAYOUT['separator_char'] * LAYOUT['separator_len']}[/]")
            for t in tips:
                console.print(f"  [{COLORS['primary']}]{ICONS['primary']}[/] [dim]{t}[/]")

    # ── 命令分发基础设施 ──────────────────────────────────

    # Dispatch 返回值标记
    _DISPATCH_OK = True
    _DISPATCH_UNKNOWN = None
    _DISPATCH_EXIT = "EXIT"

    # 延迟构建的 dispatch table（首次调用时初始化）
    _dispatch_table: dict | None = None

    # ── 聊天模式 ──────────────────────────────────────────

    def _chat(self):
        """聊天模式：多轮流式对话 + 命令式生成 + AI 自动调度（pro）
        
        按 models.json fallback.priority 自动探测可用供应商，
        主对话走优先供应商，视觉始终走 CRUX 独立通道。
        - 多行输入：首行输入 \"\"\" 进入，再输入 \"\"\" 结束
        - 中止操作：Ctrl+C 中断当前运行
        - 退出模式：/code、/agent 再次输入即切回，/exit 完全退出
        """
        from core.chat import ChatSession, MODEL_INFO

        # 自助选择供应商（多 Key 时弹出菜单，单 Key 自动激活）
        active_provider, active_model = self._select_provider()

        console.print(Panel(
            "直接输入文字即可对话（流式输出）。\n"
            "命令: /help /model /img /video /vision /clear /exit\n"
            "技能: /skill load 视频|作图|写剧本|分镜|质检...\n"
            "换行: Alt+Enter / Ctrl+J 换行，Enter 发送\n"
            "图片: 直接粘贴图片路径即可自动识别\n"
            "提示: Ctrl+C 中止运行 · Ctrl+C 再次退出\n"
            f"默认模型: {active_model}（{MODEL_INFO.get(active_model, active_provider)}）\n"
            "视觉通道: 独立 CRUX · 图片理解始终可用",
            title=f"[{COLORS['accent']}]✿ Chat mode[/]",
            border_style=COLORS["accent"],
            padding=LAYOUT["panel_padding"],
        ))

        session = ChatSession(self.client, vision_client=self.vision_client, vision_model=CRUX_VISION_MODEL)
        session.model = active_model
        # 用实际模型重建系统提示词（避免 init 用默认模型构建的过期提示词）
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        while True:
            try:
                raw = self._prompt_user(f"你 {self._mode_hint(session)}").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not raw:
                continue

            # ── 文本 \\n → 真实换行 ──
            if "\\n" in raw:
                raw = raw.replace("\\n", "\n")

            # ── 多行输入：\\\"\\\"\\\" 开头进入多行模式 ──
            if raw == '"""':
                user = self._read_multiline()
                if user is None:
                    continue
            else:
                user = raw

            # ── 斜杠命令（确定性，不过 LLM）── 表驱动分发
            if user.startswith("/"):
                cmd, _, arg = user[1:].partition(" ")
                arg = arg.strip()

                # exit 特殊处理：break 退出循环
                if cmd in ("exit", "quit", "q"):
                    break

                dispatched = self._dispatch_command(cmd, arg, session)
                if dispatched == self._DISPATCH_EXIT:
                    break
                elif dispatched == self._DISPATCH_UNKNOWN:
                    show_warning(f"未知命令 /{cmd}，输入 /help 查看")
                continue

            # ── 智能图片路由：检测到图片路径 → 自动走视觉通道 ──
            img_path, clean_text = self._extract_path_and_text(user)
            if img_path and img_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                self._chat_vision(session, user)
                continue

                    # ── 自然语言对话（流式）──
            try:
                self._stream_chat(session, user)
            except KeyboardInterrupt:
                console.print()
                show_info("已中止 · 按 Ctrl+C 退出聊天，或继续输入")
                # 回滚刚加进去的 user message
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()
            except Exception as e:
                show_error(f"对话出错: {e}")
                # 回滚刚加进去的 user message，避免历史污染
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()


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

