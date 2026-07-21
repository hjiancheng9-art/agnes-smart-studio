"""聊天会话 - 多轮对话 + 混合生成调度（命令式 + AI 自动 tool calling）+ 多模态理解

三条轨道：
- 命令式：上层识别 /img /video 后直接调 engine（在 CLI 层处理，不过本模块）
- AI 自动调度：仅 pro 模型，通过 tool_calls 触发生成，结果喂回模型总结
- 纯聊天/多模态：流式或整块输出，维护多轮历史

agent 模式：通过 tools.json 加载外部工具（shell/http/python），作为智能体主脑

yield 协议（send_stream）：
    ("text", str)            文本增量
    ("info", str)            中间提示（如"生成图片: ..."）
    ("image", dict)          图片生成结果（含 local_path）
    ("video", dict)          视频生成结果
    ("confirm", dict)        高风险工具确认（需 UI 层处理）
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.client import CruxClient
    from core.cognitive_orchestrator import CognitiveOrchestrator
    from core.memory_bridge import MemoryBridge
    from core.reflection_loop import ReflectionLoop

logger = logging.getLogger(__name__)


from core.agent import ContextManager
from core.chat_prompt import (
    CHAT_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    build_system_prompt,
)
from core.chat_toggle_mixin import ChatToggleMixin
from core.chat_tool_dispatch import _dispatch_tool_impl

# Tools eligible for auto-retry on error (idempotent or safe to retry)
_AUTO_RETRY_TOOLS = frozenset(
    {
        "run_bash",
        "run_test",
        "pip_install",
        "run_python",
        "run_lint",
        "run_format",
    }
)

from core.chat_tool_helpers import merge_tool_calls, sanitize_tool_call_history
from core.chat_tool_retry import _PipelineToolbus, auto_retry_tool, format_tool_error  # noqa: F401
from core.chat_vision import _vision_fallback
from core.config import get_crux_vision_model
from core.provider import (
    get_provider_manager,
    get_provider_name,
    get_tool_calling_models,
)
from core.session_config import SessionConfig
from core.skills import SkillManager, get_manager
from core.tools import AGENT_SYSTEM_PROMPT, ToolRegistry, get_registry

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CODE_SYSTEM_PROMPT",
    "MAX_TOOL_LOOPS",
    "MODEL_ALIASES",
    "MODEL_INFO",
    "MODEL_PROVIDER_MAP",
    "TOOL_CALLING_MODELS",
    "ChatSession",
    "merge_tool_calls",
]

# CHAT/CODE prompts from chat_prompt.py (single source of truth)
# _cached_prompt replaced by chat_prompt.PromptCache

# ── 模型别名 / 信息从 MODEL_REGISTRY 动态派生 ──
#   resolve_model_alias(name)      → 别名/名 → 模型ID
#   get_tool_calling_models()       → set[str] 支持 tool calling 的模型 ID
#   get_model_description(id)       → str 模型能力描述
#   get_provider_name(id)           → str 供应商名称
#   model_supports_tools(id)        → bool
#
# MODEL_ALIASES / MODEL_INFO 现在惰性从 MODEL_REGISTRY + models.json 构建，
# 不再硬编码，跟随 active provider 自动刷新。


# ── 模型别名构建委托给 chat_model_helpers.py（消除重复）──
from core.chat_model_helpers import build_model_aliases, build_model_info


def _refresh_aliases_and_info() -> tuple[dict[str, str], dict[str, str]]:
    """惰性初始化 MODEL_ALIASES 和 MODEL_INFO（委托 chat_model_helpers）。"""
    global MODEL_ALIASES, MODEL_INFO
    if not MODEL_ALIASES:
        MODEL_ALIASES = build_model_aliases()
    if not MODEL_INFO:
        MODEL_INFO = build_model_info()
    return MODEL_ALIASES, MODEL_INFO


MODEL_ALIASES: dict[str, str] = {}
MODEL_INFO: dict[str, str] = {}

# 模块加载时初始化（provider.py 已先加载，无循环导入风险）
_refresh_aliases_and_info()

# 以下两个现在从 provider 动态计算，不再硬编码
TOOL_CALLING_MODELS = get_tool_calling_models()
MODEL_PROVIDER_MAP = {}  # 已由 get_provider_name() 替代

# tool calling 循环最大轮次（防止死循环）
# agent 模式 / /self 命令会经 unlimited_tools 自动翻倍
# v6.1: 40 → 60 — 40 对复杂任务偏紧，160 会导致失控 (50+ tools/turn)
MAX_TOOL_LOOPS = 60

# 429/503 过载自动降级阈值：连续多少次限流/过载就强制切换供应商
RATE_LIMIT_FALLBACK_THRESHOLD = 2
# 429/503 重试最大等待秒数上限（超过立即降级，不阻塞）
MAX_RATE_LIMIT_WAIT_SECONDS = 10


class ChatSession(ChatToggleMixin):
    """多轮聊天会话，维护历史 + 混合调度

    vision_client: 独立视觉客户端（始终指向 CRUX API），与主对话供应商解耦。
                   为 None 时退化为 self.client，向后兼容原有行为。
    vision_model:  视觉理解专用模型 ID。
    """

    # ── 类型 stub（运行时由模块级函数注入，见文件末尾）──
    _merge_tool_calls: staticmethod  # type: ignore[assignment]
    _dispatch_tool: Callable[..., tuple[str, list[tuple]]]  # type: ignore[assignment]

    def __init__(
        self,
        client: CruxClient,
        default_model: str = "",
        vision_client: CruxClient | None = None,
        vision_model: str = "",
    ) -> None:
        """初始化 ChatManager — 绑定 CruxClient、配置模型/视觉/工具/技能等子系统。"""
        self.client = client
        self.vision_client = vision_client or client  # 未指定时退化为主客户端（向后兼容）
        self.vision_model = vision_model or get_crux_vision_model()
        self._brain = None  # lazy: SmartBrain (~2.5s import, only needed for image/video gen)
        self._t2i = None  # lazy: created on first image generation
        self._vid = None  # lazy: created on first video generation
        self.media_client = client  # unified media client for tool-calling generation
        self.cfg = SessionConfig(model=default_model or self._resolve_default_model())
        self._ctx_mgr: ContextManager | None = None  # lazy: built from model's actual context window
        self._model_router = None  # lazy init
        self.tools: ToolRegistry = get_registry()
        self.skills: SkillManager = get_manager()
        self.active_skill: str = ""
        self._reflection: ReflectionLoop | None = None  # ReflectionLoop, lazy init
        self._memory: MemoryBridge | None = None  # MemoryBridge, lazy init
        self._cog: CognitiveOrchestrator | None = None  # CognitiveOrchestrator, lazy init
        self._temp_input_files: set[str] = set()  # Track long-input temp files for cleanup
        self._vote_enabled: bool = False  # /vote toggle (off by default to save tokens)
        self.messages: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]
        # Token budget monitor — warns at 80% context usage.  Silently ignores
        # all errors (tests may not have the module or may mock chat internals).
        self._budget = None
        try:
            from core.token_budget import TokenBudget

            self._budget = TokenBudget()
            self._budget.count(self.messages)
        except Exception:
            logging.getLogger(__name__).debug("silent except", exc_info=True)
        # ── Dynamic attrs set by mixins/hooks — declared here for type checking ──
        self.vision_ctx: Any = None
        self._vision_fallback: Any = None
        self._intelligence_hook: Any = None
        self._methodology_state: Any = None
        self.tvl: Any = None
        self._dispatch_tool_impl: Any = None
        self._dispatch_tool_async: Any = None
        # ── Session-scoped routing (extracted from global ProviderManager) ──
        from core.routing_state import RoutingState

        self.routing: RoutingState = RoutingState(active_provider="deepseek", active_model=self.model)
        # ── Hook wiring (Phase 1-14 + subsystem activation) ──
        from core.chat_hooks_setup import wire_session_hooks

        wire_session_hooks(self)

        # Post-init validation: ensure session is in a usable state regardless
        # of which optional subsystems failed to initialize.
        self._validate_init()

    def _validate_init(self) -> None:
        """Post-init sanity check.  Logs warnings for missing critical attrs."""
        critical = {
            "tools": "tool registry",
            "cfg": "session config",
            "messages": "message history",
            "routing": "model routing state",
        }
        missing = []
        for attr, label in critical.items():
            if not hasattr(self, attr) or getattr(self, attr, None) is None:
                missing.append(f"{attr} ({label})")
        if missing:
            logger.warning("ChatSession init incomplete — missing: %s", ", ".join(missing))

    # ── Lazy engine properties (deferred import, ~5s saved on startup) ──

    @property
    def brain(self):
        """Lazy init: SmartBrain (~2.5s import, only needed for image/video gen)."""
        if self._brain is None:
            from core.brain import SmartBrain

            self._brain = SmartBrain(self.media_client)
        return self._brain

    @property
    def t2i(self):
        """Lazy init: TextToImageEngine (~1s import, only needed for image gen)."""
        if self._t2i is None:
            from engines.text_to_image import TextToImageEngine

            self._t2i = TextToImageEngine(self.media_client)
        return self._t2i

    @property
    def vid(self):
        """Lazy init: VideoEngine (~0.8s import, only needed for video gen)."""
        if self._vid is None:
            from engines.video import VideoEngine

            self._vid = VideoEngine(self.media_client)
        return self._vid

    # ── Property aliases → SessionConfig (GPT v6.2: centralized state) ──
    @property
    def model(self):
        """当前模型名称（getter/setter → SessionConfig）。"""
        return self.cfg.model

    @model.setter
    def model(self, v):
        """设置当前模型名称。"""
        self.cfg.model = v

    @property
    def auto_model(self):
        """是否启用自动模型选择。"""
        return self.cfg.auto_model

    @auto_model.setter
    def auto_model(self, v):
        """设置自动模型选择开关。"""
        self.cfg.auto_model = v

    @property
    def enable_thinking(self):
        """是否启用深度思考模式。"""
        return self.cfg.enable_thinking

    @enable_thinking.setter
    def enable_thinking(self, v):
        """设置深度思考模式开关。"""
        self.cfg.enable_thinking = v

    @property
    def code_mode(self):
        """是否启用代码模式。"""
        return self.cfg.code_mode

    @code_mode.setter
    def code_mode(self, v):
        """设置代码模式开关。"""
        self.cfg.code_mode = v

    @property
    def mode(self):
        """当前会话模式。"""
        return self.cfg.mode

    @mode.setter
    def mode(self, v):
        """设置会话模式。"""
        self.cfg.mode = v

    @property
    def unlimited_tools(self):
        """是否无限制工具调用。"""
        return self.cfg.unlimited_tools

    @unlimited_tools.setter
    def unlimited_tools(self, v):
        """设置无限制工具调用开关。"""
        self.cfg.unlimited_tools = v

    @property
    def agent_mode(self):
        """是否启用 Agent 模式。"""
        return self.cfg.agent_mode

    @agent_mode.setter
    def agent_mode(self, v):
        """设置 Agent 模式开关。"""
        self.cfg.agent_mode = v

    @property
    def browser_enabled(self):
        """浏览器控制是否启用。"""
        return self.cfg.browser_enabled

    @browser_enabled.setter
    def browser_enabled(self, v):
        """设置浏览器控制开关。"""
        self.cfg.browser_enabled = v

    @property
    def notebook_enabled(self):
        """Jupyter Notebook 是否启用。"""
        return self.cfg.notebook_enabled

    @notebook_enabled.setter
    def notebook_enabled(self, v):
        """设置 Notebook 开关。"""
        self.cfg.notebook_enabled = v

    @property
    def audio_enabled(self):
        """音频功能是否启用。"""
        return self.cfg.audio_enabled

    @audio_enabled.setter
    def audio_enabled(self, v):
        """设置音频功能开关。"""
        self.cfg.audio_enabled = v

    @property
    def _auto_tier_order(self):
        return self.cfg.auto_tier_order

    @_auto_tier_order.setter
    def _auto_tier_order(self, v):
        self.cfg.auto_tier_order = v

    @property
    def _consecutive_skips(self):
        return self.cfg.consecutive_skips

    @_consecutive_skips.setter
    def _consecutive_skips(self, v):
        self.cfg.consecutive_skips = v

    def __del__(self) -> None:
        """Cleanup temp files and client on garbage collection (fallback to atexit)."""
        try:
            self._cleanup_temp_input_files()
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
        try:
            if hasattr(self, "client") and self.client is not None:
                self.client.close()
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

    def _cleanup_temp_input_files(self) -> None:
        """Remove all tracked long-input temp files. Safe to call multiple times."""
        import os as _os

        for fp in tuple(self._temp_input_files):
            try:
                if _os.path.exists(fp):
                    _os.remove(fp)
            except OSError:
                pass
            finally:
                self._temp_input_files.discard(fp)

    def _record_trace_failure(self, error: str, step_name: str = "tool_execution", mode: str = "") -> None:
        """Record a failure trace for the adaptive learner (best-effort, never raises)."""
        try:
            import time

            from core.intelligence_trace import TraceRecord, TraceStep, get_trace_store

            trace = TraceRecord(
                user_request=getattr(self, "_last_user_text", "")[:500],
                mode=mode or getattr(self, "_intel_mode", "BALANCED"),
                status="fail",
                steps=[TraceStep(name=step_name, status="fail", error=str(error)[:500])],
                started_at=time.time() - 1,
                ended_at=time.time(),
            )
            get_trace_store().record(trace)
        except Exception:
            logger.debug("trace record failed", exc_info=True)

    def _get_schema_for_tool(self, name: str) -> dict | None:
        """Provide JSON Schema for a tool, used by the validator."""
        try:
            from core.tool_router import get_tool_schema

            return get_tool_schema(name)
        except Exception:
            return None

    def _build_session_context(self) -> str:
        """Build session context string — git branch + status + recent commits.

        异步收集（后台线程），避免阻塞 ChatSession 构造。非关键信息，
        缺失不报错。
        """
        ctx_parts: list[str] = []

        def _collect_git():
            import os as _os
            import subprocess

            cwd = _os.environ.get("CRUX_WORKSPACE", str(Path.cwd()))
            try:
                r = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=cwd,
                )
                branch = r.stdout.strip()
                if branch:
                    ctx_parts.append(f"branch: {branch}")
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug("git rev-parse failed: %s", e)

            try:
                r = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=cwd,
                )
                changed = [line.strip() for line in r.stdout.splitlines()[:20] if line.strip()]
                if changed:
                    ctx_parts.append(f"changes ({len(changed)}): " + ", ".join(changed[:10]))
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug("git status failed: %s", e)

            try:
                r = subprocess.run(
                    ["git", "log", "--oneline", "-5"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=cwd,
                )
                commits = [line.strip() for line in r.stdout.splitlines() if line.strip()]
                if commits:
                    ctx_parts.append("recent: " + "; ".join(commits[:5]))
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug("git log failed: %s", e)

        import threading

        t = threading.Thread(target=_collect_git, daemon=True)
        t.start()
        t.join(timeout=2.0)  # 最多等 2s，超时就放弃

        if ctx_parts:
            return "\n\n[Session Context]\n" + "\n".join(ctx_parts)
        return ""

    @property
    def ctx_mgr(self) -> ContextManager:
        """上下文管理器 — 根据当前模型的实际上下文窗口动态计算压缩阈值。

        使用模型上下文窗口的 80% 作为压缩上限：
        - deepseek-v4-pro: 1M → 800K tokens
        - agnes-2.0-flash: 128K → 102K tokens
        - agnes-2.0-flash: 128K → 102K tokens

        首次访问时创建，模型切换时可通过 _rebuild_ctx_mgr() 重建。
        """
        if self._ctx_mgr is None:
            self._rebuild_ctx_mgr()
        return self._ctx_mgr  # type: ignore[return-value]

    def _rebuild_ctx_mgr(self) -> None:
        """根据当前模型 rebuild ContextManager（模型切换/初始化时调用）。"""
        from core.provider import get_context_window

        ctx = get_context_window(self.model)
        # 压缩阈值：用 25% 上下文窗口（平衡上下文利用与 token 节省）。
        # 最低 30K（保证小窗口模型也有合理缓冲），留 75% 给输出 + 工具定义 + 新消息。
        limit = max(30000, int(ctx * 0.25))
        self._ctx_mgr = ContextManager(max_tokens=limit)

    @staticmethod
    def _resolve_default_model() -> str:
        """从 active provider 派生默认模型。启动用 light（快速响应），复杂任务自动升 pro。"""
        try:
            mgr = get_provider_manager()
            model = mgr.get_model("light")
            if not model or model == "unknown":
                return "deepseek-v4-flash"
            return model
        except Exception as e:
            logger.debug("unexpected error: %s", e, exc_info=True)

            return "deepseek-v4-flash"

    @property
    def model_router(self):
        """Get or create the unified ModelRouter instance (shared with sub-agents)."""
        if self._model_router is None:
            from core.agent import ModelRouter

            self._model_router = ModelRouter()
        return self._model_router

    def _auto_route(self, prompt: str) -> dict | None:
        """Simple two-tier routing: flash for light chat, pro for real work."""
        if not self.auto_model:
            return None

        # Use flash for short conversational messages, pro for real tasks
        _is_light = len(prompt) < 120 and not any(
            kw in prompt
            for kw in (
                "修复",
                "实现",
                "重构",
                "设计",
                "审查",
                "部署",
                "fix",
                "implement",
                "refactor",
                "design",
                "deploy",
            )
        )
        target_model = "deepseek-v4-flash" if _is_light else "deepseek-v4-pro"
        if target_model == self.model:
            return None  # already on the right model

        self.model = target_model
        self._rebuild_ctx_mgr()
        self.messages[0] = {"role": "system", "content": self._build_system_prompt()}
        return {"tier": "light" if _is_light else "pro", "provider": "deepseek", "model": target_model}

    @property
    def supports_tools(self) -> bool:
        """支持 tool calling 自动调度的模型（含第三方兼容 OpenAI tools 的模型）"""
        from core.provider import model_supports_tools

        return model_supports_tools(self.model)

    def _reload_tools(self):
        """重新加载工具注册表，传入当前所有 toggle 状态。

        agent 模式: load(browser=..., notebook=..., audio=...)
        普通模式: 也传入 browser/notebook/audio（这些 toggle 独立于 agent 模式）。
        """
        pipeline = False  # showrunner 已移除
        comfyui = False  # ComfyUI 已移除
        self.tools = get_registry()
        self.tools.load(
            pipeline=pipeline,
            comfyui=comfyui,
            browser=self.browser_enabled,
            notebook=self.notebook_enabled,
            audio=self.audio_enabled,
            mcp=True,
        )

    def load_skill(self, name: str) -> str | None:
        """加载技能包，返回技能名称或 None。

        showrunner:  已移除（由 Agnes 替代）
        comfyui-bridge: 已移除
        （Showrunner 和 ComfyUI 均已移除）
        """
        self.skills.discover()
        skill = self.skills.load(name)
        if skill:
            self.active_skill = name
            # Skill 反馈: 记录触发加载的任务上下文
            self._skill_loaded_for_task = getattr(self, "_last_user_text", "")
            self._skill_loaded_at_turn = getattr(self, "_turn_count", 0)
            # Thinking only for code-heavy skills; browser/media skills don't need it
            thinking_skills = {"caliber", "debug-master"}
            self.enable_thinking = name in thinking_skills

            # ── 根据技能类型启用对应工具集 ──
            pipeline = False  # showrunner 已移除
            comfyui = False  # ComfyUI 已移除

            if pipeline or comfyui:
                self.tools = get_registry()
                self.tools.load(
                    pipeline=pipeline,
                    comfyui=comfyui,
                    browser=self.browser_enabled,
                    notebook=self.notebook_enabled,
                    audio=self.audio_enabled,
                    mcp=True,
                )

            # 重建 system prompt
            base = self._current_base_prompt()
            prompt = self.skills.get_system_prompt(base)
            self.messages[0] = {"role": "system", "content": prompt}
            for msg in self.messages[1:]:
                c = msg.get("content", "")
                if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                    msg["content"] = c[:2000] + "\n...[trimmed]"
            # 注入技能的额外工具
            for t in self.skills.get_extra_tools():
                from core.skills import resolve_skill_executor

                self.tools.register(
                    t["name"], t.get("description", ""), t.get("parameters", {}), resolve_skill_executor(t["name"], t)
                )
            return name
        return None

    def unload_skill(self):
        """卸载当前技能。管道工具集同时清理。"""
        self.active_skill = ""
        self.skills.unload()
        # 重新加载纯净工具集（只含内置 + 外部 tools.json）
        self.tools = get_registry()
        self.tools.load(
            pipeline=False,
            comfyui=False,
            browser=self.browser_enabled,
            notebook=self.notebook_enabled,
            audio=self.audio_enabled,
            mcp=True,
        )
        base = self._current_base_prompt()
        self.messages[0] = {"role": "system", "content": base}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"

    def _current_base_prompt(self) -> str:
        """获取当前模式的基础提示词（动态注入供应商和模型名）"""
        if self.code_mode:
            return self._build_system_prompt()
        if self.agent_mode:
            return AGENT_SYSTEM_PROMPT + self._render_tool_categories()
        return self._build_system_prompt()

    def _render_tool_categories(self, *, focused: bool = True) -> str:
        """Render tool categories for system prompt. Progressive disclosure.

        When focused=True (default), only core tools are shown (~20 tools,
        ~500 tokens).  All 190+ tools remain available — the LLM can discover
        them via search_files or by asking.  This matches Claude Code's
        progressive tool disclosure model.

        When focused=False (agent mode / explicit full-list request), all
        tools are shown.
        """
        cats = self.tools.tool_categories
        if not cats:
            return f"\n当前可用工具: {self.tools.tool_names}"

        if focused and not getattr(self, "agent_mode", False):
            # Core coding tools — always shown
            _CORE = frozenset(
                {
                    "read_file",
                    "write_file",
                    "edit_file",
                    "patch_file",
                    "search_files",
                    "glob_files",
                    "list_files",
                    "tree_dir",
                    "run_bash",
                    "run_python",
                    "run_test",
                    "git_add_commit",
                    "git_status",
                    "git_diff",
                    "git_branch",
                    "git_push",
                    "git_pull",
                    "run_lint",
                    "run_format",
                    "code_review",
                    "debug_inspect",
                    "web_search",
                    "web_fetch",
                }
            )
            lines = ["\n\n## 核心工具"]
            for cat_name, tools in cats.items():
                filtered = [t for t in tools if t in _CORE]
                if filtered:
                    lines.append(f"- **{cat_name}**: {', '.join(filtered)}")
            total = sum(len(v) for v in cats.values())
            lines.append(
                f"\n(以上为 {len(_CORE)} 个核心工具。共 {total} 个工具可用 — 使用 search_files 或直接询问获取更多)"
            )
            return "\n".join(lines)

        # Full listing (agent mode)
        lines = ["\n\n## 当前可用工具（按分类）"]
        for cat_name, tools in cats.items():
            lines.append(f"- **{cat_name}**: {', '.join(tools)}")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        """构建动态系统提示词，注入当前供应商和模型名 + 已启用规则。

        委托 core.chat_prompt.build_system_prompt() 处理 20 层谱系注入。
        使用模块级缓存：只有在 provider/model/mode/rules 变化时才重建。
        """
        # 规则 hash（纳入缓存 key 以保证规则变更时刷新）
        rules_hash = ""
        try:
            from core.rules import get_rules

            rules_hash = str(hash(str([r.name for r in get_rules().active_rules])))
        except (ImportError, OSError) as e:
            logger.debug("optional module skipped: %s", e)

            pass

        prompt = build_system_prompt(
            model=self.model,
            provider_name=get_provider_name(self.model),
            code_mode=self.code_mode,
            browser_enabled=self.browser_enabled,
            notebook_enabled=self.notebook_enabled,
            audio_enabled=self.audio_enabled,
            active_skill_rules_hash=rules_hash,
            skills_auto_prompt_manager=self.skills.auto_skills_prompt,
            chat_light=not self.code_mode,  # 日常聊天跳过大段编程方法论
        )
        # Inject budget warning if conversation is long (safe for tests)
        try:
            if self._budget and self._budget.should_warn():
                prompt += "\n\n" + self._budget.system_prompt_footer()
        except (AttributeError, Exception):
            pass
        # Inject repo map for code mode — LLM sees project structure
        if self.code_mode:
            try:
                from core.edit_orchestrator import repo_context

                rc = repo_context()
                if rc:
                    prompt += rc
            except (ImportError, Exception):
                pass
        # Inject methodology constraints — LLM sees current task level
        prompt += self._build_methodology_hint()
        return prompt

    @staticmethod
    def _build_methodology_hint() -> str:
        """Inject current task level and constraints into the system prompt.

        Lets the LLM know BEFORE proposing tools what restrictions apply,
        reducing confusing "blocked" tool failures.
        """
        try:
            from core.methodology import TaskLevel, get_methodology_state

            state = get_methodology_state()
            level = state.task_level
            if level == TaskLevel.A:
                return ""  # No restrictions for micro-tasks

            lines = ["\n\n## 当前任务约束 (Methodology)"]
            lines.append(f"- 任务级别: **{level.value.upper()}**")

            if state.requires_plan and not state.plan_exists:
                lines.append("- ⚠️ 必须先写 Plan 确认后才能执行写操作")
            if state.requires_test_baseline and not state.test_baseline_recorded:
                lines.append("- ⚠️ 必须先记录测试基线")
            if state.requires_worktree and not state.worktree_created:
                lines.append("- ⚠️ 必须在隔离 worktree 中操作")

            if state._tdd_phase:
                lines.append(f"- TDD 阶段: {state._tdd_phase}")
            lines.append(f"- 工作流: 步骤 {state.workflow_step}/7")
            return "\n".join(lines)
        except (ImportError, AttributeError):
            return ""

        # Prompt cache managed by chat_prompt.PromptCache (single source of truth)

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]
        if self._budget:
            self._budget.count(self.messages)

    def _check_budget(self) -> None:
        """Check token budget and print warning if needed."""
        if not self._budget:
            return
        try:
            self._budget.count(self.messages)
            if self._budget.should_warn():
                print(self._budget.warning(), flush=True)
        except Exception:
            logging.getLogger(__name__).debug("silent except", exc_info=True)

    def _vision_model_chain(self, complexity: str = "light") -> list[str]:
        """Vision model chain — single model after zhipu removal."""
        return [self.vision_model or "agnes-2.0-flash"]

    @staticmethod
    def _classify_vision_complexity(text: str) -> tuple[str, int]:
        """Classify vision request complexity. See core.chat_routing."""
        from core.chat_routing import classify_vision_complexity

        return classify_vision_complexity(text)

    def _text_fallback_chain(self) -> list[tuple[str, CruxClient]]:
        """构建主对话 fallback 链（模型 + client 对）。

        顺序：当前 (model, client) → fallback provider 的 (model, client)。
        对标 Claude 的 fallbackModel 数组：主模型挂了自动降级到备选。
        同供应商不同模型（如 deepseek-v4-pro → deepseek-v4-flash）也作为备选。
        """
        chain: list[tuple[str, CruxClient]] = [(self.model, self.client)]
        try:
            mgr = get_provider_manager()
            # ── 健康预检: 跳过已死的 fallback provider ──
            for pid in mgr.fallback_priority:
                if mgr.state.is_down(pid) or not mgr.state.circuit_can_try(pid):
                    continue
                provider = mgr.providers.get(pid, {})
                mid = provider.get("models", {}).get("pro")
                if mid and mid != self.model:
                    try:
                        fallback_client = mgr.create_client(pid)
                        chain.append((mid, fallback_client))
                    except (OSError, RuntimeError) as e:
                        logger.debug("op failed: %s", e)

                        pass
            # 同供应商轻量档兜底（如 deepseek-v4-pro → deepseek-v4-flash）
            try:
                current_pid = ""
                for _pid, pdata in mgr.providers.items():
                    if self.model in pdata.get("models", {}).values():
                        current_pid = _pid
                        break
                if current_pid:
                    light_mid = mgr.providers[current_pid].get("models", {}).get("light")
                    if light_mid and light_mid != self.model:
                        chain.append((light_mid, self.client))  # 同 client，不另建
            except (OSError, RuntimeError) as e:
                logger.debug("op failed: %s", e)

                pass
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("fallback skipped: %s", e)

            pass
        return chain

    def _is_stream_error(self, buffer: str) -> bool:
        """Whether a streamed buffer is a transport/API error. See core.chat_routing."""
        from core.chat_routing import is_stream_error

        return is_stream_error(buffer)

    def send_stream(self, user_text: str, image_url: str | None = None):
        """发送用户消息，流式 yield (kind, payload) 元组。

        Pipeline stages: accepted → plan → context → model → tools → finalize

        核心实现已提取至 core.chat_stream._send_stream_impl。
        """
        from core.chat_stream import _send_stream_impl

        yield from _send_stream_impl(self, user_text, image_url)

    # ── send_stream 的拆分子方法（行为不变，仅降低单方法复杂度）──
    # 以下三个方法由 send_stream 调用，分别处理：吃 delta / 执行工具 / 收尾计费。
    # 提取动机：原 send_stream 170 行三层嵌套（while fallback × for tool_loop × for delta），
    # 认知负荷极高（CodeBuddy/Claude/Codex 三方评分一致点名）。拆分后 send_stream 只剩控制流骨架。

    # 写操作类工具不参与跨轮去重缓存（避免吞掉用户对同一文件的连续修改意图）
    from core.constraints import WRITE_TOOLS

    _WRITE_TOOLS = WRITE_TOOLS

    def _consume_stream_delta(self, client: CruxClient, model: str, tools, *, _retry_empty: bool = False):
        """Direct stream iteration — simplest reliable path."""
        from core.provider_adapter import get_max_tokens, get_thinking_params

        max_tok = get_max_tokens(model, is_tool_call=bool(tools))
        kwargs = {}
        if self.enable_thinking:
            kwargs = get_thinking_params(model)
        # 空响应重试: 提高 temperature 增加模型输出多样性
        if _retry_empty:
            kwargs["temperature"] = kwargs.get("temperature", 0.7) + 0.2

        buffer, tool_calls = "", []
        stream_error = False
        last_usage = None

        for delta in client.chat_stream(
            model=model,
            messages=sanitize_tool_call_history(self.messages),
            tools=tools,
            max_tokens=max_tok,
            **kwargs,
        ):
            # reasoning_content (DeepSeek thinking) — yield as text too
            rc = delta.get("reasoning_content") or delta.get("think") or ""
            if rc:
                buffer += rc
                yield ("text", rc)
            if delta.get("content"):
                chunk = delta["content"]
                buffer += chunk
                if not delta.get("_error"):
                    yield ("text", chunk)
            if delta.get("tool_calls"):
                tool_calls.extend(delta["tool_calls"])
            if delta.get("_finish") == "error":
                stream_error = True
            if "_usage" in delta:
                last_usage = delta["_usage"]

        if not tool_calls and buffer:
            try:
                from core.tool_call_parser import extract_tool_calls

                xml_tools, _ = extract_tool_calls(buffer)
                if xml_tools:
                    tool_calls.extend(xml_tools)
            except ImportError:
                pass
        return buffer, tool_calls, stream_error, last_usage

    def _append_assistant_with_tools(self, buffer: str, tool_calls: list[dict]) -> str:
        """把 assistant 回复（含 tool_calls）追加到 messages。返回 buffer 供后续使用。"""
        merged = merge_tool_calls(tool_calls)
        self.messages.append(
            {
                "role": "assistant",
                "content": buffer,
                "tool_calls": merged,
            }
        )
        self._last_merged_tool_calls = merged
        return buffer

    def _run_tool_calls(self, tool_calls, executed_sigs, executed_cache, loop_idx=0):
        """执行并喂回一轮工具调用，yield 副作用。

        核心实现已提取至 core.chat_stream_tools._run_tool_calls_impl。
        """
        from core.chat_stream_tools import _run_tool_calls_impl

        yield from _run_tool_calls_impl(self, tool_calls, executed_sigs, executed_cache, loop_idx)

    def _finalize_outcome(self, model: str, last_usage) -> None:
        """正常收尾：成本追踪 + Prompt Lab outcome + 方法论工作流推进 + 会话快照。"""
        try:
            from core.cost_tracker import record_usage

            record_usage(model=model, kind="text", usage=last_usage, label="text_stream")
        except (ImportError, OSError) as e:
            logger.debug("cost_tracker.record_usage(text_stream) failed: %s: %s", type(e).__name__, e)
        self._record_outcome_promptlab()
        # ── 方法论: 自动推进至"验证+diff审查"步骤 ──
        try:
            from core.methodology import get_methodology_state

            get_methodology_state().advance_workflow("verified")
        except (ImportError, OSError) as e:
            logger.debug("optional module skipped: %s", e)

            pass
        # ── 自适应学习: 每 5 轮触发一次学习循环 ──
        self._turn_count = getattr(self, "_turn_count", 0) + 1
        if self._turn_count % 5 == 0:
            try:
                learner = getattr(self, "_adaptive_learner", None)
                if learner and learner._learning_enabled:
                    records = learner.run_learning_cycle(limit=5)
                    if records:
                        logger.info("Adaptive learner: %d new insights from %d traces", len(records), len(records))
            except Exception as e:
                logger.debug("Adaptive learner cycle skipped: %s", e)

        # ── Agent mode 统计消费: 每 5 轮读取各模式成功率 ──
        if self._turn_count % 5 == 0:
            try:
                from core.multi_agent import get_mode_statistics

                _stats = get_mode_statistics()
                if _stats:
                    _swarm = _stats.get("swarm", {})
                    _plan = _stats.get("plan_execute", {})
                    _total = _swarm.get("total", 0) + _plan.get("total", 0)
                    if _total >= 3:
                        logger.info(
                            "agent mode stats: swarm=%.0f%%(n=%d) plan=%.0f%%(n=%d) total=%d",
                            _swarm.get("success_rate", 0) * 100,
                            _swarm.get("total", 0),
                            _plan.get("success_rate", 0) * 100,
                            _plan.get("total", 0),
                            _total,
                        )
            except (ImportError, OSError):
                pass

        # ── Skill 反馈: 评估当前技能效果 ──
        _skill_name = getattr(self, "active_skill", "")
        _skill_loaded_at = getattr(self, "_skill_loaded_at_turn", 0)
        if _skill_name and _skill_loaded_at == self._turn_count - 1:
            try:
                from core.skills import get_manager as _gm

                _sm = _gm()
                if hasattr(_sm, "_skill_usage_log") and _sm._skill_usage_log:
                    _last = _sm._skill_usage_log[-1]
                    _had_tool_errors = getattr(self, "_last_turn_had_errors", False)
                    _last["turn_completed"] = True
                    _last["tool_errors"] = _had_tool_errors
                    _last["task"] = getattr(self, "_skill_loaded_for_task", "")[:200]
            except Exception:
                logger.debug("Exception in chat", exc_info=True)

        # ── TRM Growth Engine 自动调优: 每 20 轮优化工具路由 ──
        if self._turn_count % 20 == 0:
            try:
                from core.growth_engine import get_growth_engine

                _ge = get_growth_engine()
                _changes = _ge.auto_tune(apply=True)
                if _changes.get("applied"):
                    logger.info(
                        "TRM auto-tune: %d optimizations applied (%d tools reordered/demoted)",
                        len(_changes["applied"]),
                        _changes.get("_total_calls", 0),
                    )
            except (ImportError, OSError):
                pass

        # ── 会话快照: 每 5 轮保存一次，崩溃可恢复 ──
        self._maybe_snapshot()

    # ── 会话快照 ────────────────────────────────────────────

    _SNAPSHOT_INTERVAL = 5  # 每 N 轮保存一次
    _SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "output" / "sessions"

    def _maybe_snapshot(self) -> None:
        """Snapshot every N turns (best-effort). Delegates to core.chat_history.
        _turn_count is managed by _finalize_outcome; read-only here.

        Also persists methodology state so task level, workflow step, and
        compliance gates survive session restarts.
        """
        turn = getattr(self, "_turn_count", 0)
        if turn % self._SNAPSHOT_INTERVAL != 0:
            return
        from core.chat_history import save_snapshot

        save_snapshot(self._SNAPSHOT_DIR, self.model, turn, self.messages)

        # Persist methodology state alongside chat snapshots
        try:
            from core.methodology import save_methodology_state

            save_methodology_state()
        except ImportError:
            pass

    @staticmethod
    def sanitize_messages(messages: list[dict]) -> list[dict]:
        """Strip trailing incomplete tool-call sequences. See core.chat_history."""
        from core.chat_history import sanitize_messages as _sanitize

        return _sanitize(messages)

    @classmethod
    def restore_latest_snapshot(cls) -> dict | None:
        """Load an unrestored session snapshot, if any. See core.chat_history."""
        from core.chat_history import restore_latest_snapshot as _restore

        return _restore(cls._SNAPSHOT_DIR)

    def _trigger_reflection(self) -> None:
        """Post-turn reflection: disabled — extra API call per message, output invisible."""
        pass

    def _inject_memory(self, user_input: str) -> None:
        """Inject relevant past memories as system context."""
        if self._memory is None:
            try:
                from core.memory_bridge import MemoryBridge

                self._memory = MemoryBridge()
            except (ImportError, OSError) as e:
                logger.debug("MemoryBridge init failed: %s", e)
                return
        try:
            self._memory.inject_context(self.messages, user_input)
        except Exception as e:
            logger.debug("memory inject failed: %s", e)

    def _try_adversarial_bypass(self, buffer: str, user_text: str, client, model: str, tools):  # generator
        """检测模型拒绝并触发对抗样本 bypass。返回 True 表示已 yield 替代结果。

        对抗链层级 1→10：轻同形字→重编码→payload 拆分，逐级升级。
        最多 3 级尝试，成功即停。
        """
        try:
            from core.adversarial_bypass import apply_technique, is_model_refusal, record_attempt
        except ImportError:
            return False

        if not is_model_refusal(buffer):
            return False

        # 移除刚才的拒绝消息
        self.messages.pop()
        logger.info("Model refusal detected, activating adversarial bypass for: %s", user_text[:80])

        for level in (3, 6, 9):
            try:
                modified = apply_technique(user_text, level=level)
            except Exception as e:
                logger.debug("unexpected error: %s", e, exc_info=True)

                continue

            if isinstance(modified, list):
                # Split payload: inject multi-message sequence
                for msg in modified:
                    self.messages.append(msg)
            else:
                # Single message: replace user message content
                self.messages.append({"role": "user", "content": modified})

            # Retry with modified prompt — use same threaded stream pattern
            retry_buffer = ""
            try:
                import queue as _rq
                import threading as _rt

                _rq_q: _rq.Queue = _rq.Queue()
                _rq_done = _rt.Event()
                _rq_err: list[Exception | None] = [None]

                def _rq_reader(
                    _q=_rq_q,
                    _err=_rq_err,
                    _done=_rq_done,
                ):
                    try:
                        for k, p in self._consume_stream_delta(client, model, tools):
                            _q.put((k, p))
                    except Exception as e:
                        _err[0] = e
                    finally:
                        _done.set()

                _rq_t = _rt.Thread(target=_rq_reader, daemon=True)
                _rq_t.start()
                _last_rq = time.monotonic()
                while not _rq_done.is_set():
                    try:
                        kind, payload = _rq_q.get(timeout=2.0)
                        _last_rq = time.monotonic()
                    except _rq.Empty:
                        if time.monotonic() - _last_rq > 30.0:
                            _rq_err[0] = RuntimeError("Bypass stream timeout")
                            break
                        continue
                    if isinstance(payload, str) and kind == "text":
                        retry_buffer += payload
                    yield (kind, payload)
                _rq_t.join(timeout=5)
                if _rq_err[0]:
                    raise _rq_err[0]
                if retry_buffer and not is_model_refusal(retry_buffer):
                    self.messages.append({"role": "assistant", "content": retry_buffer})
                    self._finalize_outcome(model, None)
                    record_attempt(level, True)
                    logger.info("Adversarial bypass succeeded at level %d", level)
                    return True
                # Still refused — pop the adversarial messages and try next level
                if isinstance(modified, list):
                    for _ in modified:
                        self.messages.pop()
                else:
                    self.messages.pop()
            except Exception:
                logger.debug("adversarial bypass cleanup failed", exc_info=True)
                if isinstance(modified, list):
                    for _ in modified:
                        self.messages.pop()
                else:
                    self.messages.pop()
                continue

        # All levels exhausted — restore refusal so user sees what happened
        self.messages.append({"role": "assistant", "content": buffer})
        yield ("text", buffer)
        record_attempt(10, False)
        return True

    def _auto_remember(self) -> None:
        """Auto-extract and store key facts from the conversation."""
        if self._memory is None:
            return
        try:
            facts = self._memory.extract_key_facts(self.messages)
            for fact in facts:
                self._memory.remember(fact)
            self._memory.flush()
        except Exception as e:
            logger.debug("auto remember failed: %s", e)

    def _deliberate(self, prompt: str) -> dict | None:
        """Multi-model deliberation for complex questions."""
        if self._cog is None:
            try:
                from core.cognitive_orchestrator import CognitiveOrchestrator

                self._cog = CognitiveOrchestrator()
            except (ImportError, OSError) as e:
                logger.debug("CognitiveOrchestrator init failed: %s", e)
                return None
        try:
            return self._cog.deliberate(prompt)
        except Exception as e:
            logger.debug("deliberation failed: %s", e)
            return None

    def get_intel_yields(self) -> list[tuple[str, str]]:
        """V2: 获取 Intelligence 状态 yield 列表，不破坏 send_stream 协议"""
        if not hasattr(self, "_intelligence_hook"):
            return []
        return self._intelligence_hook.get_status_yield()

    def _record_outcome_promptlab(self) -> None:
        """记录会话 outcome 到 Prompt Lab（可选模块，失败静默降级）。"""
        try:
            from core.prompt_lab import get_prompt_lab

            get_prompt_lab().record_outcome()
        except (ImportError, OSError):
            logger.debug("spectrum module not available")


# ═══════════════════════════════════════════════════════════════
# 消息历史安全网 — 清洗孤儿 tool_calls
# ═══════════════════════════════════════════════════════════════


# ── sanitize_tool_call_history 增量缓存 ──


# ═══════════════════════════════════════════════════════════════
# ChatSession._dispatch_tool — 放在 merge_tool_calls 之后（模块级函数下）
# 实际上这是 ChatSession 的方法，放回类内更清晰，但当前结构为
# merge_tool_calls 把 _dispatch_tool 包进去了。修复：将其作为独立函数
# 重新定义并注入类。为避免大范围缩进重排，直接在 merge_tool_calls 后
# 重新定义类方法并用赋值注入。
# ═══════════════════════════════════════════════════════════════


ChatSession._dispatch_tool = _dispatch_tool_impl
ChatSession._dispatch_tool_impl = _dispatch_tool_impl


# ── Async dispatch bridge (Phase 1 tool chain refactoring) ──
def _dispatch_tool_async(self, tool_name: str, tool_args: str | dict):
    """Async wrapper around sync _dispatch_tool_impl with timeout and ToolOutcome.
    Use this from async code paths (browser, pipelines, sub-agents).
    Existing sync callers continue to use _dispatch_tool unchanged.
    """
    import json as _json

    from core.tool_executor import ToolExecutor

    args_dict = _json.loads(tool_args) if isinstance(tool_args, str) else (tool_args or {})
    executor = ToolExecutor(self._dispatch_tool)
    return executor.execute(tool_name, args_dict)


ChatSession._dispatch_tool_async = _dispatch_tool_async

ChatSession._vision_fallback = _vision_fallback
