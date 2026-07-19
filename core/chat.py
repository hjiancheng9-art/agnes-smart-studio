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

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.client import CruxClient
    from core.cognitive_orchestrator import CognitiveOrchestrator
    from core.memory_bridge import MemoryBridge
    from core.reflection_loop import ReflectionLoop

logger = logging.getLogger("crux.chat")


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
from core.chat_tool_helpers import normalize_tool_args as _normalize_tool_args
from core.chat_tool_retry import _PipelineToolbus, auto_retry_tool, format_tool_error


def _summarize_tool_output(raw: str, tool_name: str = "") -> str:
    """Smart truncation for large tool outputs — keep useful info, drop noise."""
    if not raw or len(raw) <= 2000:
        return raw
    lines = raw.split("\n")
    # Prioritize error/fail/assert lines
    err_lines = [
        l
        for l in lines
        if any(kw in l.lower() for kw in ("error", "fail", "traceback", "assert", "exception", "warning"))
    ]
    if err_lines:
        head = "\n".join(lines[:5])
        errs = "\n".join(err_lines[:8])
        return f"{head}\n\n... [{len(lines)} lines, {len(err_lines)} flagged]\n\n{errs}"
    head = "\n".join(lines[:6])
    tail = "\n".join(lines[-3:]) if len(lines) > 15 else ""
    return f"{head}\n... [{len(lines) - 9} lines omitted]...\n{tail}" if tail else head


from core.chat_vision import _vision_fallback
from core.config import get_crux_vision_model
from core.observability import TraceContext, metrics
from core.provider import (
    get_provider_manager,
    get_provider_name,
    get_tool_calling_models,
)
from core.session_config import SessionConfig
from core.skills import SkillManager, get_manager
from core.tools import AGENT_SYSTEM_PROMPT, ToolRegistry, get_registry
from utils.unicode_safety import InvalidUnicodePayloadError

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


def _build_model_aliases() -> dict[str, str]:
    """从 models.json active provider 的 models 字段动态构建别名映射。
    "light" → active 供应商的 light 模型, "pro" → pro 模型。
    """
    try:
        mgr = get_provider_manager()
        mgr.load()
        pmap = mgr.get_active_models()
        return {k: v for k, v in pmap.items() if k in ("light", "pro")}
    except Exception as e:
        logger.debug("unexpected error: %s", e, exc_info=True)

        return {}


def _build_model_info() -> dict[str, str]:
    """从 MODEL_REGISTRY 构建模型 ID → 描述 映射。"""
    try:
        from core.provider import MODEL_REGISTRY

        return {mid: info.description for mid, info in MODEL_REGISTRY.items() if info.description}
    except Exception as e:
        logger.debug("unexpected error: %s", e, exc_info=True)

        return {}


def _refresh_aliases_and_info() -> tuple[dict[str, str], dict[str, str]]:
    """惰性初始化 MODEL_ALIASES 和 MODEL_INFO（含模块缓存）。"""
    global MODEL_ALIASES, MODEL_INFO
    if not MODEL_ALIASES:
        MODEL_ALIASES = _build_model_aliases()
    if not MODEL_INFO:
        MODEL_INFO = _build_model_info()
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
        self._pipeline_result: dict | None = None
        import threading as _t

        self._pipeline_lock = _t.Lock()
        self.messages: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]
        # Token budget monitor — warns at 80% context usage.  Silently ignores
        # all errors (tests may not have the module or may mock chat internals).
        self._budget = None
        try:
            from core.token_budget import TokenBudget

            self._budget = TokenBudget()
            self._budget.count(self.messages)
        except Exception:
            logging.getLogger("crux").debug("silent except", exc_info=True)
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
        return self.cfg.model

    @model.setter
    def model(self, v):
        self.cfg.model = v

    @property
    def auto_model(self):
        return self.cfg.auto_model

    @auto_model.setter
    def auto_model(self, v):
        self.cfg.auto_model = v

    @property
    def enable_thinking(self):
        return self.cfg.enable_thinking

    @enable_thinking.setter
    def enable_thinking(self, v):
        self.cfg.enable_thinking = v

    @property
    def code_mode(self):
        return self.cfg.code_mode

    @code_mode.setter
    def code_mode(self, v):
        self.cfg.code_mode = v

    @property
    def mode(self):
        return self.cfg.mode

    @mode.setter
    def mode(self, v):
        self.cfg.mode = v

    @property
    def unlimited_tools(self):
        return self.cfg.unlimited_tools

    @unlimited_tools.setter
    def unlimited_tools(self, v):
        self.cfg.unlimited_tools = v

    @property
    def agent_mode(self):
        return self.cfg.agent_mode

    @agent_mode.setter
    def agent_mode(self, v):
        self.cfg.agent_mode = v

    @property
    def browser_enabled(self):
        return self.cfg.browser_enabled

    @browser_enabled.setter
    def browser_enabled(self, v):
        self.cfg.browser_enabled = v

    @property
    def notebook_enabled(self):
        return self.cfg.notebook_enabled

    @notebook_enabled.setter
    def notebook_enabled(self, v):
        self.cfg.notebook_enabled = v

    @property
    def audio_enabled(self):
        return self.cfg.audio_enabled

    @audio_enabled.setter
    def audio_enabled(self, v):
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

            logging.getLogger("crux").debug("silent except", exc_info=True)
        try:
            if hasattr(self, "client") and self.client is not None:
                self.client.close()
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

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
        return prompt

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
            logging.getLogger("crux").debug("silent except", exc_info=True)

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
        """
        self._last_user_text = user_text
        self._last_turn_had_errors = False

        # ── 输入截断: 超长文本存临时文件，避免炸上下文 ──
        _MAX_INPUT_CHARS = 4000
        _input_len = len(user_text)
        if _input_len > _MAX_INPUT_CHARS:
            import tempfile

            tmp_dir = tempfile.gettempdir()
            tmp_path = f"{tmp_dir}/crux_input_{os.getpid()}.txt".replace("\\", "/")
            with open(tmp_path, "w", encoding="utf-8") as f_tmp:
                f_tmp.write(self._last_user_text)
            self._temp_input_files.add(tmp_path)
            import atexit

            atexit.register(lambda p=tmp_path: os.path.exists(p) and os.remove(p))  # final safety net
            user_text = (
                f"[大文本 {_input_len} 字符，完整内容: {tmp_path}]\n"
                f"开头:\n{user_text[: _MAX_INPUT_CHARS // 2]}\n"
                f"...\n结尾:\n{user_text[-_MAX_INPUT_CHARS // 4 :]}"
            )
            yield ("info", f"输入过长({_input_len}字符)，已截断。用 read_file 读完整内容: {tmp_path}")

        # 触发 CHAT_TURN_START 钩子
        try:
            from core.hooks import HookType
            from core.hooks import fire as _fire_hook

            _fire_hook(HookType.CHAT_TURN_START, prompt=user_text)
        except (ImportError, OSError) as e:
            logger.debug("optional module skipped: %s", e)

            pass

        # #6 预算守卫：会话开始时检查今日花费，超限/接近上限仅提示不阻断
        try:
            from core.cost_tracker import check_budget

            warning = check_budget()
            if warning:
                yield ("info", warning)
        except (ImportError, OSError) as e:
            logger.debug("cost_tracker.check_budget failed: %s: %s", type(e).__name__, e)
        except Exception as e:
            logger.debug("cost_tracker.check_budget unexpected error: %s: %s", type(e).__name__, e)

        # ── 方法论分级：根据意图自动判定 A/B/C/D 任务等级 ──
        try:
            from core.methodology import get_methodology_state

            state = get_methodology_state()
            state.classify(user_text, [])
            state.record_step()
            if state.task_level.value in ("complex", "critical"):
                yield ("info", f"[方法] 任务等级 {state.task_level.name} — {state.summary()}")
        except (ImportError, OSError) as e:
            logger.debug("optional module skipped: %s", e)

            pass

        # ── 多模态分支：有图片 → vision 模型理解 + LLM 推理 ──
        if image_url:
            try:
                vision_raw = self._vision_fallback(user_text, image_url)
            except Exception as e:
                logger.exception("Vision fallback crashed unexpectedly")
                vision_raw = f"(视觉理解异常: {type(e).__name__}: {e})"
            # 注册到视觉上下文（持久化图片 + 原始描述，供后续追问重查）
            self.vision_ctx.register(image_url, vision_raw)
            # 将 vision 输出作为"系统视觉情报"注入用户消息，替换原始图片 URL
            # Truncate to prevent context window waste (complex mode: 4096 tokens max)
            _MAX_VISION_CHARS = 2000
            _clean = vision_raw[: _MAX_VISION_CHARS * 2]  # ~4000 chars ≈ 1000 tokens
            # Strip magic tokens that could confuse the downstream LLM
            for _tok in ("<|im_end|>", "<|im_start|>", "<|user|>", "<|assistant|>", "<|system|>"):
                _clean = _clean.replace(_tok, "")
            user_text = f"[图片分析] {_clean}\n\n用户提问: {user_text}"
            # 不 return，继续走正常 LLM 流式推理

        # ── Unified execution plan ──
        try:
            from core.runtime_types import ExecutionMode, plan_from_policy

            _plan = plan_from_policy(user_text)

            # For orchestrate/swarm: trigger directly instead of asking the model
            # to produce a tool call. This is NOT a workaround — it's the correct
            # architecture for deterministic workflows. Two reasons:
            # 1. DeepSeek thinking mode: model completes thinking then goes silent,
            #    never producing the tool call (122s idle timeout).
            # 2. Even without thinking mode, asking an LLM to "call orchestrate"
            #    adds latency + failure surface for a deterministic trigger.
            # Direct orchestration bypasses the model entirely for the trigger.
            # Skip orchestration for short conversational queries — models over-trigger
            # orchestrate for simple questions like "how many bugs do you have?"
            _skip_orch = len(user_text) < 60 and ("?" in user_text or "？" in user_text)
            if _plan is not None and _plan.mode in (ExecutionMode.ORCHESTRATE, ExecutionMode.SWARM) and not _skip_orch:
                import time as _time

                # Append user message to history (same as normal path)
                self.messages.append({"role": "user", "content": user_text})
                yield ("stream_start", {"run_id": str(uuid.uuid4())[:12], "message": "start"})

                yield ("info", "【编排】自检自修 — 完整执行")
                _result_parts = []
                _t0 = _time.monotonic()

                # Step 1: self_heal — audit + auto-fix
                yield ("info", "[1/4] self_heal 审计 + 自动修复...")
                try:
                    _raw1, _ = self._dispatch_tool("self_heal", '{"fix":true}')
                    _result_parts.append(f"## 自愈审计\n{str(_raw1)[:2000]}")
                    yield ("info", f"  自愈完成 ({_time.monotonic() - _t0:.1f}s)")
                except Exception as e:
                    _result_parts.append(f"## 自愈失败\n{str(e)[:300]}")
                    yield ("error", f"  自愈失败: {e}")

                # Step 2: code_review on changed files
                yield ("info", "[2/4] 代码审查...")
                try:
                    _raw2, _ = self._dispatch_tool("code_review", "{}")
                    _result_parts.append(f"## 代码审查\n{str(_raw2)[:1500]}")
                    yield ("info", f"  审查完成 ({_time.monotonic() - _t0:.1f}s)")
                except Exception as e:
                    _result_parts.append(f"## 审查失败\n{str(e)[:300]}")

                # Step 3: lint fix + format
                yield ("info", "[3/4] 代码质量修复...")
                try:
                    _raw3a, _ = self._dispatch_tool("run_lint", '{"fix":true}')
                    _result_parts.append(f"## Lint\n{str(_raw3a)[:1000]}")
                except Exception as e:
                    _result_parts.append(f"## Lint 失败\n{str(e)[:300]}")
                try:
                    _raw3b, _ = self._dispatch_tool("run_format", "{}")
                    _result_parts.append(f"## 格式化\n{str(_raw3b)[:500]}")
                except Exception as e:
                    _result_parts.append(f"## 格式化失败\n{str(e)[:300]}")
                yield ("info", f"  质量修复完成 ({_time.monotonic() - _t0:.1f}s)")

                # Step 4: summary
                _elapsed = _time.monotonic() - _t0
                # Strip ANSI escape codes — prompt_toolkit TUI can't render them
                import re as _re

                _result_text = "\n\n".join(_result_parts)
                _clean = _re.sub(r"\x1b\[[0-9;]*m", "", _result_text)
                # Extract key numbers for the info bar
                _lines = [l for l in _clean.split("\n") if l.strip() and not l.startswith("══")]
                if _lines:
                    yield ("info", f"[完成] {_elapsed:.1f}s — {'; '.join(_lines[:3])}")
                if _clean.strip():
                    yield ("text", _clean)
                self.messages.append({"role": "assistant", "content": _result_text or ""})
                self._finalize_outcome(self.model, None)
                self._trigger_reflection()
                self._auto_remember()
                return  # ── skip model call entirely ──

            if _plan.mode != ExecutionMode.DIRECT:
                instruction = "[执行策略] "
                if _plan.mode == ExecutionMode.ORCHESTRATE:
                    instruction += "请调用 `orchestrate` 工具。不要用逐步思考替代编排。"
                elif _plan.mode == ExecutionMode.SWARM:
                    instruction += "请调用 `agent_swarm` 并行分派子智能体。"
                original_user = user_text
                user_text = f"{instruction}\n\n用户任务: {original_user}"

            # Auto-upgrade model for complex tasks
            if _plan.complexity >= 3 and ("flash" in self.model or "light" in self.model):
                import re as _re

                pro = _re.sub(r"\b(flash|light)\b", "pro", self.model)
                if pro != self.model:
                    self.model = pro
                    self.routing.select(self.routing.active_provider, pro)
                    yield ("info", f"自动切换模型: {self.model}")
        except ImportError:
            _plan = None

        # ── 事件协议: 生成 run_id ──
        _run_id = str(uuid.uuid4())[:12]

        # ── Prompt enhancement: use domain/prompts assembler for orchestrate/swarm. ──
        # RuntimeEngine now only does prompt prep — model flow stays in the legacy
        # _consume_stream_delta loop (proven stable). The old KNOWN-BROKEN comment
        # referred to a removed model-stage that tried to replace the full stream.
        # Opt-in via env:  export CRUX_ENABLE_NEW_RUNTIME=1
        _use_new_runtime = (
            _plan is not None
            and _plan.mode in ("orchestrate", "swarm")
            and os.environ.get("CRUX_ENABLE_NEW_RUNTIME", "0") == "1"
        )
        if _use_new_runtime:
            try:
                from runtime.engine import RuntimeEngine

                _new_engine = RuntimeEngine()
                _prepared = _new_engine.prepare_turn(old_plan=_plan)
                if _prepared and _prepared.system_prompt:
                    old_len = len(self.messages[0]["content"])
                    self.messages[0]["content"] = _prepared.system_prompt
                    yield ("info", f"系统提示词: {len(_prepared.system_prompt)} chars (旧 {old_len} chars)")
                    # Disable thinking mode for orchestrate — it stalls between think and output
                    self.enable_thinking = False
            except ImportError:
                pass  # new runtime not ready, use old prompt

        # ── 纯文本分支：加 user message ──
        # Set orchestration goal context (used by trigger_orchestrate)
        try:
            from core.runtime_orchestrator import set_orchestrate_goal

            set_orchestrate_goal(user_text)
        except ImportError:
            pass
        self.messages.append({"role": "user", "content": user_text})

        # ── 事件协议: 生成 run_id ──
        _run_id = str(uuid.uuid4())[:12]
        import time as _time

        _turn_start = _time.monotonic()  # track turn start for heartbeat timing

        # Only show planning for non-trivial messages (skip for simple greetings/chitchat)
        if len(user_text) > 30 or any(
            kw in user_text
            for kw in (
                "修复",
                "实现",
                "重构",
                "设计",
                "审查",
                "分析",
                "部署",
                "优化",
                "测试",
                "fix",
                "implement",
                "refactor",
                "design",
                "review",
                "debug",
                "deploy",
            )
        ):
            yield ("info", "【规划】分析任务 & 选择模型...")

        # Auto-route: classify prompt intent → dynamically switch model tier
        # (e.g. complex code → pro, simple Q&A → light, deep reasoning → reasoner)
        self._auto_route(user_text)

        # ── Intelligence Pipeline V2: 在流前分析，不破坏 yield 协议 ──
        # analyze() 内部捕获异常，失败自动 fallback
        intel_analysis = self._intelligence_hook.analyze(user_text)
        self._intel_mode = intel_analysis.get("mode", "BALANCED")
        self._intel_analysis = intel_analysis.get("summary", {})
        self._intel_config = intel_analysis.get("config", {})

        # ── 消费 intelligence 分析结果 ──
        # 1. Yield 状态提示（DEEP/SAFE/RESEARCH 模式）
        yield from self._intelligence_hook.get_status_yield()

        # 2. 根据模式调整推理参数
        if self._intel_mode in ("DEEP", "RESEARCH", "SAFE"):
            # DeepSeek thinking mode causes stream hang when tools are active:
            # model completes internal reasoning then goes silent without producing
            # content or tool_calls. Disable thinking when tool calling is supported.
            self.enable_thinking = not self.supports_tools
        elif self._intel_mode == "FAST":
            self.enable_thinking = False  # 快速模式关闭思考省 token

        # ── Agent mode 自动评分: 复杂任务提示 LLM 使用 agent_swarm ──
        try:
            from core.multi_agent import compute_agent_mode

            _agent_ctx = {
                "files_touched": len(
                    (
                        getattr(self, "_methodology_state", None)
                        and getattr(self._methodology_state, "files_touched", None)
                    )
                    or []
                ),
                "recent_failures": 0,
            }
            _agent_mode, _agent_score, _agent_breakdown = compute_agent_mode(user_text, _agent_ctx)
            self._last_agent_score = _agent_score
            self._last_agent_mode = _agent_mode.value
            if _agent_score >= 5:
                yield (
                    "info",
                    f"[智能体] 任务复杂度 {_agent_score:.1f} (mode={_agent_mode.value})"
                    f" — 建议使用 agent_swarm 并行分派子智能体",
                )
        except (ImportError, OSError):
            pass

        # 3. Pipeline 执行: DEEP/SAFE 模式跑 Plan→Critic→Repair 工作流
        if self._intel_mode in ("DEEP", "SAFE") and not image_url:
            try:
                import asyncio
                import threading

                toolbus = _PipelineToolbus(self._dispatch_tool, self.tools)

                # 后台运行 pipeline，不阻塞主回复
                def _run_pipeline():
                    try:
                        result = asyncio.run(
                            self._intelligence_hook.execute_pipeline(
                                user_text,
                                context={"project": str(Path(__file__).parent.parent)},
                                toolbus=toolbus,
                            )
                        )
                        self._pipeline_result = result
                    except Exception:
                        logger.debug("Exception in chat", exc_info=True)

                # Track pipeline threads — join old ones to prevent accumulation
                if not hasattr(self, "_pipeline_threads"):
                    self._pipeline_threads = []
                # Clean up finished threads
                self._pipeline_threads = [t for t in self._pipeline_threads if t.is_alive()]
                t = threading.Thread(target=_run_pipeline, daemon=True, name="crux-pipeline")
                self._pipeline_threads.append(t)
                t.start()
            except Exception as e:
                logger.debug("Pipeline execution skipped: %s", e)

        # Inject relevant past memories as context
        self._inject_memory(user_text)

        # 视觉上下文：后续追问时按需重查 vision 模型
        if not image_url and self.vision_ctx.active and self.vision_ctx.needs_lookup(user_text):
            fresh = self.vision_ctx.reask(
                user_text,
                lambda t, u: self._vision_fallback(t, u),
            )
            if fresh:
                # 用重查结果覆盖最后一条用户消息
                augmented = f"[图片局部查询] {fresh}\n\n用户提问: {user_text}"
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages[-1]["content"] = augmented
                else:
                    self.messages.append({"role": "user", "content": augmented})

        # Multi-model deliberation for complex questions
        from core.cognitive_orchestrator import is_complex

        if self._vote_enabled and is_complex(user_text) and not image_url:
            result = self._deliberate(user_text)
            if result and result.get("confidence") in ("high", "medium"):
                content = f"{result['answer']}\n\n[{result['models_used']} models, confidence: {result['confidence']}]"
                if result.get("dissenting") and result["dissenting"] != "none":
                    content += f"\n[dim]Dissent: {result['dissenting']}[/]"
                self.messages.append({"role": "assistant", "content": content})
                self._check_budget()
                yield ("text", content)
                return

        # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
        # 触发条件：token 超阈值，或消息条数超过 40（防止大量小消息堆积
        # 导致 token 估算偏低但请求体积膨胀）。
        if self.ctx_mgr.needs_compression(self.messages) or len(self.messages) > 40:
            self.messages = self.ctx_mgr.compress(self.messages, self.client, self.model)

        tools = self.tools.get_filtered_definitions(user_text) if self.supports_tools else None
        # Track the set of tool names the model is allowed to see. Starts with the
        # filtered set and grows as the model calls tools, instead of jumping to the
        # full 97-tool definition list (~14K tokens) on every subsequent loop round.
        _active_tool_names: set[str] | None = {d["function"]["name"] for d in tools} if tools else None

        # ── 模型级 fallback 链（对标 Claude fallbackModel）──
        # 主对话流式调用失败时自动降级到下一个供应商/模型。
        # 只在首轮（无 tool_calls）时 fallback，避免重复 tool 副作用。
        fallback_chain = self._text_fallback_chain()
        fallback_tried = 0

        # ── 预检: 活跃供应商挂了就立刻切 ──
        try:
            mgr = get_provider_manager()
            active_pid = mgr.state.active
            if mgr.state.is_down(active_pid) or not mgr.state.circuit_can_try(active_pid):
                # 活跃供应商不可用 → 从 fallback chain 跳过第一个（当前）直接切
                if len(fallback_chain) > 1:
                    # skip first (current) provider
                    fallback_chain = fallback_chain[1:]
                    self.model, self.client = fallback_chain[0]
                    yield ("info", f"当前供应商不可用，已切换至 {self.model}")
                    self._rebuild_ctx_mgr()
        except (ImportError, OSError) as e:
            logger.debug("provider precheck skipped: %s", e)

        # tool calling 循环（有上限，防止死循环）
        # 支持 CRUX_MAX_TOOL_LOOPS 环境变量热覆盖（免重启，设了立即生效）
        _base = MAX_TOOL_LOOPS
        _env_override = os.environ.get("CRUX_MAX_TOOL_LOOPS")
        if _env_override:
            try:
                _base = int(_env_override)
            except ValueError:
                logger.warning(
                    "CRUX_MAX_TOOL_LOOPS=%r is not a valid integer, using default %d", _env_override, MAX_TOOL_LOOPS
                )
        _effective_max = _base * 2 if getattr(self, "unlimited_tools", False) else _base
        # ── Adaptive limit: expand for plans, shrink on failures ──
        try:
            from core.skill_orchestrator import get_orchestrator

            orch = get_orchestrator()
            if hasattr(orch, "_last_plan") and orch._last_plan and orch._last_plan.steps:
                plan_steps = len(orch._last_plan.steps)
                _effective_max = max(_effective_max, plan_steps * 8)
        except (ImportError, AttributeError):
            pass
        self._consecutive_failures = 0  # adaptive: shrink limit on cascade failures
        self._consecutive_successes = 0  # adaptive: expand limit on clean runs
        self._effective_max = _effective_max  # shared with _run_tool_calls for adaptive limit
        buffer = ""  # 循环外预绑定，保证超出最大轮次时引用安全
        # 跨轮工具去重状态（见 _run_tool_calls 的注释）
        _executed_signatures: set[tuple[str, str]] = set()
        _executed_cache: dict[tuple[str, str], str] = {}
        _stream_error_break = False
        _test_run_count = 0  # detect fix-test-fail-fix runaway loops

        while fallback_tried < len(fallback_chain):
            _use_model, _use_client = fallback_chain[fallback_tried]
            fallback_tried += 1
            _stream_error_break = False  # 标记 for 循环是否因流错误 break

            for _loop in range(_effective_max):
                buffer, tool_calls = "", []
                _stream_error = False
                _last_usage = None
                # _consume_stream_delta is a generator: yields text chunks, returns result tuple.
                # stream_adapter.consume_stream() inside handles thread+queue+30s watchdog.
                # No double-wrapping needed — single threaded layer is sufficient.
                try:
                    delta_result = yield from self._consume_stream_delta(
                        _use_client,
                        _use_model,
                        tools,
                    )
                except InvalidUnicodePayloadError:
                    logger.exception(
                        "_consume_stream_delta: payload encoding error — NOT a provider failure, skipping failover"
                    )
                    yield ("error", "请求数据含非法字符（Unicode surrogate），已跳过。请重试。")
                    return
                except Exception as e:
                    logger.exception("_consume_stream_delta 异常")
                    yield ("error", f"流式接收中断: {type(e).__name__}: {e}")
                    _stream_error_break = True
                    break
                buffer, tool_calls, _stream_error, _last_usage = delta_result
                # 收完一轮 delta：有 tool_calls → 执行并喂回，进入下一轮
                if tool_calls:
                    buffer = self._append_assistant_with_tools(buffer, tool_calls)
                    try:
                        yield from self._run_tool_calls(
                            tool_calls,
                            _executed_signatures,
                            _executed_cache,
                            _loop,
                        )
                    except Exception as e:
                        logger.exception("_run_tool_calls 异常")
                        yield ("error", f"工具执行中断: {type(e).__name__}: {e}")
                        _stream_error_break = False  # tool error, NOT a provider failure
                        break
                    # Grow the visible tool set with any tools the model just called,
                    # instead of expanding to the full 97-tool list (14K tokens/round).
                    if _active_tool_names is not None and tool_calls:
                        for _tc in tool_calls:
                            _fn = _tc.get("function", {}) if isinstance(_tc, dict) else {}
                            _name = _fn.get("name")
                            if _name:
                                _active_tool_names.add(_name)
                        tools = self.tools.get_definitions_for_names(_active_tool_names)
                    # Detect fix-test-fail-fix runaway loops: break if test runner called too many times
                    _test_tools = sum(
                        1
                        for tc in tool_calls
                        if isinstance(tc, dict) and tc.get("function", {}).get("name") == "run_test"
                    )
                    if _test_tools:
                        _test_run_count += _test_tools
                    if _test_run_count > 5:
                        yield ("info", f"测试已运行 {_test_run_count} 次，疑似死循环。已自动停止。")
                        self.messages.append({"role": "assistant", "content": buffer})
                        self._finalize_outcome(_use_model, _last_usage)
                        return  # clean stop — NOT a provider failure
                    continue  # 进入下一轮 tool loop

                # 无 tool_calls：检查是否流错误（需 fallback）还是正常收尾
                if _stream_error or self._is_stream_error(buffer):
                    if _loop == 0 and fallback_tried < len(fallback_chain):
                        # 通知 ProviderManager 标记当前供应商为 down
                        try:
                            mgr = get_provider_manager()
                            # 先尝试自动 failover（handle_failure 会选一个可用 provider）
                            new_client, new_pid = mgr.handle_failure(mgr.state.active, 500)
                            if new_client:
                                # Defer closing old client — closing mid-stream corrupts httpx state
                                self.client = new_client
                                self._current_provider = new_pid
                                mgr.state.record_success(new_pid)
                                logger.info("failover: -> %s (auto)", new_pid)
                                yield ("info", f"Provider 自动切换: {new_pid}")
                            else:
                                # 无可用 provider，仅标记下线
                                mgr.state.mark_down(mgr.state.active)
                        except Exception as e:
                            logging.debug("Failed to mark provider down: %s", str(e)[:120])
                        yield ("info", f"模型 {_use_model} 连接中断，尝试 fallback...")
                        metrics.increment("fallback.text_model")
                        _stream_error_break = True
                        break  # 出 for _loop → while 继续
                    self.messages.append({"role": "assistant", "content": buffer})
                    return

                # 正常收尾 — 检测是否为模型拒绝，若是则触发对抗 bypass
                # 空响应检测：模型返回空内容时自动重试一次
                _empty_buffer = not buffer or not buffer.strip()
                if _empty_buffer and _loop == 0:
                    yield ("info", "模型返回空内容，正在重试…")
                    # 用稍高 temperature 重试，有可能唤醒模型
                    try:
                        retry_delta = yield from self._consume_stream_delta(
                            _use_client, _use_model, tools, _retry_empty=True
                        )
                        retry_buffer, _, _, retry_usage = retry_delta
                        if retry_buffer and retry_buffer.strip():
                            buffer = retry_buffer
                            if retry_usage:
                                _last_usage = retry_usage
                            _empty_buffer = False
                            yield ("info", "重试成功")
                    except Exception as e:
                        logger.debug("empty-retry failed: %s", e)
                if _empty_buffer:
                    buffer = "（模型未返回内容，请重试或换一种表述）"
                    yield ("text", buffer)
                self._finalize_outcome(_use_model, _last_usage)
                self.messages.append({"role": "assistant", "content": buffer})
                # ── 红旗警示: 检测输出中的危险短语 ──
                try:
                    from core.methodology import detect_red_flags, get_methodology_state

                    flags = detect_red_flags(buffer)
                    if flags:
                        for w in flags:
                            yield ("info", w)
                        get_methodology_state().advance_workflow("verified")
                except (ImportError, OSError) as e:
                    logger.debug("optional module skipped: %s", e)

                    pass
                if (yield from self._try_adversarial_bypass(buffer, user_text, _use_client, _use_model, tools)):
                    return  # bypass 成功，已在内部 yield 结果
                # ── Pipeline 结果: 后台运行完成后 yield ──
                _pr = getattr(self, "_pipeline_result", None)
                if _pr:
                    with self._pipeline_lock:
                        _pr = self._pipeline_result
                        if _pr:
                            if _pr.get("passed") is False:
                                yield ("info", f"[Pipeline] 审查未通过: {_pr.get('summary', '')[:200]}")
                            elif _pr.get("summary"):
                                yield ("info", f"[Pipeline] {_pr.get('summary', '')[:200]}")
                            self._pipeline_result = None
                self._trigger_reflection()
                self._auto_remember()
                return

        # for _loop 结束：区分两种情况
        # 1. _stream_error_break=True → 流错误 fallback，回到 while 尝试下一档
        # 2. _stream_error_break=False → tool loop 溢出（模型正常工作但死循环），不 fallback
        if not _stream_error_break:
            yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
            self._record_trace_failure(f"tool loop overflow: {_effective_max} rounds", step_name="tool_loop")
            self.messages.append({"role": "assistant", "content": buffer})
            self._check_budget()
            self._record_outcome_promptlab()
            return

        # All fallback models exhausted — tell the user something went wrong.
        tried = ", ".join(m for m, _ in fallback_chain)
        self._record_trace_failure(f"all models exhausted: {tried}", step_name="fallback_chain")
        yield ("error", f"所有模型均不可用（已尝试: {tried}），请稍后重试或 /provider 切换")

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
        """执行并喂回一轮工具调用，yield 副作用，return True 表示应中断流。

        契约（输出不重复 DNA · 工具副作用层）：
        - 配合 merge_tool_calls 的单轮内去重，本方法做**跨轮**去重：
          相同 (name, normalized_args) 的非写工具只执行一次，复用缓存。
        - 写操作类工具（_WRITE_TOOLS）不缓存。
        - yield 用户可见的副作用（info/image/video/confirm）。

        Returns (via StopIteration.value):
            False — confirm 不再中断流（拒绝时占位已在历史中，合法）。
        """
        from core.context_tools import compress_tool_result

        # ── Adaptive state shared with send_stream ──
        _loop = loop_idx

        # ── Phase 1: Tool call validation ──
        if getattr(self, "tvl", None) is not None:
            import json as _json
            import time as _time

            validation_issues: list[str] = []
            _merged_check = getattr(self, "_last_merged_tool_calls", merge_tool_calls(tool_calls))
            _v_start = _time.time()
            for tc_check in _merged_check:
                fname_c = self.tools.resolve_name(tc_check["function"]["name"])
                fargs_raw = tc_check["function"].get("arguments", "{}")
                if isinstance(fargs_raw, str):
                    try:
                        fargs_c = _json.loads(fargs_raw)
                    except _json.JSONDecodeError:
                        fargs_c = {}
                else:
                    fargs_c = fargs_raw
                issues = self.tvl.validate_tool_call(fname_c, fargs_c)
                if issues:
                    for iss in issues:
                        validation_issues.append(f"[{iss.code.value}] {iss.tool_name}: {iss.message}")
            _v_duration = (_time.time() - _v_start) * 1000
            if validation_issues:
                error_text = "\\n".join(validation_issues)
                logger.warning(f"Tool validation failed:\\n{error_text}")
                yield ("validation_error", error_text)
                msg = f"[ToolCall Validation Failed]\\n{error_text}\\n---\\nFix your tool calls and retry."
                self.messages.append({"role": "tool", "content": msg, "tool_call_id": "__validation__"})
                # Telemetry: validation blocked
                try:
                    self.tvl.record_telemetry("tool_validation", "p1", "", _v_duration, False, error_text[:100])
                except Exception:
                    logging.getLogger("crux").debug("silent except", exc_info=True)
                return False
            # Telemetry: validation passed
            try:
                self.tvl.record_telemetry(
                    "tool_validation", "p1", "", _v_duration, True, f"{len(_merged_check)} calls OK"
                )
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)

        merged = getattr(self, "_last_merged_tool_calls", merge_tool_calls(tool_calls))
        for tc in merged:
            fname = self.tools.resolve_name(tc["function"]["name"])
            fargs = tc["function"].get("arguments", "{}")
            sig = (fname, _normalize_tool_args(fargs))
            # 跨轮去重：非写工具且本会话已执行过 → 复用缓存，不重复 dispatch
            if fname not in self._WRITE_TOOLS and sig in executed_sigs:
                tool_result = executed_cache.get(sig, "")
                # 不 yield 副作用（用户已见过一次）
                append_tool_result = True
            else:
                # Surface tool activity into message pane — compact one-line format
                _desc = {
                    "read_file": "读取",
                    "write_file": "写入",
                    "edit_file": "编辑",
                    "run_bash": "执行",
                    "run_python": "Python",
                    "run_test": "测试",
                    "search_files": "搜索",
                    "search_symbols": "查符号",
                    "git_diff": "diff",
                    "git_status": "状态",
                    "git_add_commit": "提交",
                    "agent_swarm": "并行",
                }.get(fname, fname)
                _path = ""
                if isinstance(fargs, dict):
                    _path = str(fargs.get("path", fargs.get("command", "")))[:50]
                elif isinstance(fargs, str):
                    _path = fargs[:50]
                _line = f"\n> {_desc} {_path}" if _path else f"\n> {_desc}"
                yield ("text", _line + "\n")
                with TraceContext("tool_call", tool_name=fname, call_id=tc.get("id", "")) as span:
                    try:
                        # ── Phase 2c: Diff guard snapshot before write ──
                        if fname in ("write_file", "edit_file", "patch_file"):
                            try:
                                import json as _json2

                                _args2 = _json2.loads(fargs) if isinstance(fargs, str) else (fargs or {})
                                _path2 = _args2.get("path", "")
                                if _path2:
                                    getattr(self, "tvl", None) and self.tvl.snapshot_before_write(_path2)
                            except Exception:
                                logging.getLogger("crux").debug("silent except", exc_info=True)

                        # Dispatch (sync, same as HEAD — ThreadPoolExecutor timeout guard
                        # removed because it masked fast-fail errors in mock/test environments
                        # and introduced 120s hangs in fallback paths).
                        raw = self._dispatch_tool(fname, fargs)
                        from core.runtime_result import ToolResult

                        normalized = ToolResult.from_raw(raw)
                        if not normalized.ok:
                            tool_result = format_tool_error(fname, normalized.content)
                        else:
                            content = normalized.content
                            tool_result = _summarize_tool_output(content, fname) if len(content) > 2000 else content
                        side_effects = list(normalized.side_effects)

                        # ── 自动重试: 仅对幂等/可重试工具，且错误表明可修正时才重试 ──
                        _can_retry = not normalized.ok and fname in _AUTO_RETRY_TOOLS
                        if _can_retry:
                            tool_result, side_effects = auto_retry_tool(self, fname, fargs, tool_result)

                        # ── 工具结果缓存: 缓存成功的只读工具结果 ──
                        try:
                            from core.tool_cache import CACHEABLE_TOOLS, get_tool_cache

                            if fname in CACHEABLE_TOOLS and normalized.ok:
                                get_tool_cache().set(fname, fargs, str(tool_result))
                        except ImportError:
                            pass

                        # ── Phase 2a+b: Validate result + track history ──
                        try:
                            tvl = getattr(self, "tvl", None)
                            if tvl:
                                vr = tvl.validate_result(fname, str(tool_result)[:2000], success=True)
                                if not vr.is_valid:
                                    logger.warning(f"Result validation: {fname} -> {len(vr.notes)} issues")
                                tvl.track_tool_use_v2(fname, fargs, str(tool_result)[:2000], success=True)
                        except Exception:
                            logging.getLogger("crux").debug("silent except", exc_info=True)
                    except Exception as e:
                        logger.exception("工具 %s 执行异常", fname)
                        tool_result = f"[错误] 工具 {fname} 执行失败: {type(e).__name__}: {e}"
                        self._record_trace_failure(str(e), step_name=fname)

                        # ── Phase 2a: Track failed execution ──
                        try:
                            tvl = getattr(self, "tvl", None)
                            if tvl:
                                vr = tvl.validate_result(fname, tool_result, success=False)
                                tvl.track_tool_use_v2(fname, fargs, tool_result, success=False)
                        except Exception:
                            logging.getLogger("crux").debug("silent except", exc_info=True)
                        side_effects = [("info", tool_result)]
                        metrics.increment("tool_errors")
                        self._last_turn_had_errors = True
                    # ── Agent mode 反馈: 记录 agent_swarm / multi_agent 执行结果 ──
                    if fname in ("agent_swarm", "multi_agent"):
                        try:
                            from core.multi_agent import AgentMode, AgentModeResult, record_agent_mode_result

                            _is_ok = (
                                not str(tool_result).startswith("[错误]")
                                and "error" not in str(tool_result).lower()[:200]
                            )
                            _mode = AgentMode.SWARM if fname == "agent_swarm" else AgentMode.PLAN_EXECUTE
                            _latency = (span.end_time - span.start_time) if hasattr(span, "end_time") else 0.0
                            record_agent_mode_result(
                                AgentModeResult(
                                    mode=_mode,
                                    task_type="tool_call",
                                    success=_is_ok,
                                    latency=_latency,
                                )
                            )
                        except (ImportError, AttributeError):
                            pass
                    # ── 方法论追踪: 自动记录文件操作 + 触发升级 ──
                    try:
                        from core.methodology import get_methodology_state

                        m_state = get_methodology_state()
                        m_state.record_tool(fname)
                        # 追踪写入文件
                        if fname in self._WRITE_TOOLS:
                            path = json.loads(fargs).get("path") or json.loads(fargs).get("file_path", "")
                            if path:
                                m_state.files_touched.append(path)
                                # 文件数超阈值 → 自动升级
                                n = len(set(m_state.files_touched))
                                if n > 3 and m_state.task_level.value in ("micro", "normal"):
                                    m_state.escalate(f"files>{n}")
                                elif n > 1 and m_state.task_level.value == "micro":
                                    m_state.escalate("files>1")
                    except (ImportError, json.JSONDecodeError, OSError):
                        pass
                    # Fold oversized tool results for cleaner display
                    if isinstance(tool_result, str) and len(tool_result) > 800:
                        preview = "\n".join(tool_result.split("\n")[:5])
                        tool_result = f"{preview}\n... [{len(tool_result)} chars folded, result sent to model]"
                    span.set_attribute("result_chars", len(tool_result) if isinstance(tool_result, str) else -1)
                    metrics.increment("tool_calls")
                    metrics.timing("tool_call_ms", span.duration_ms())
                    # #5 Prompt Lab: 记录工具调用和错误
                    try:
                        from core.prompt_lab import get_prompt_lab

                        get_prompt_lab().record_tool_call()
                        if "[错误]" in str(tool_result) or "error" in str(tool_result).lower():
                            get_prompt_lab().record_tool_error()
                    except (ImportError, OSError) as e:
                        logger.debug("optional module skipped: %s", e)

                        pass
                # ── Adaptive loop limit: expand on success, shrink on cascade failures ──
                _tool_ok = not str(tool_result).startswith("[错误]") and not str(tool_result).startswith("[自愈失败]")
                if _tool_ok:
                    self._consecutive_failures = 0
                    self._consecutive_successes += 1
                    if self._consecutive_successes > 10:
                        self._effective_max = max(self._effective_max, int(self._effective_max * 1.5))
                        self._consecutive_successes = 0
                else:
                    self._consecutive_failures += 1
                    self._consecutive_successes = 0
                    if self._consecutive_failures >= 3:
                        self._effective_max = min(self._effective_max, _loop + 5)
                        yield ("info", f"连续 {self._consecutive_failures} 次失败 — 剩余最多 5 次重试")
                # ── 高风险工具确认：同意即执行，拒绝则占位跳过 ──
                is_confirm = any(k == "confirm" for k, _ in side_effects)
                if is_confirm:
                    # a. 预追加占位 tool 结果（保证消息历史始终合法）。
                    #    后续 yield from side_effects 会触发 UI 的 Confirm.ask（同步阻塞）。
                    #    若用户拒绝: PermissionError 从 yield from 抛出 → generator 关闭
                    #      → 占位安全留在历史中 → 下一轮 API 不会报 orphan 错误 ✓
                    #    若用户同意: yield from 正常返回 → 进入步骤 b
                    placeholder = f"[高风险工具 {fname}: 等待用户确认]"
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": placeholder,
                        }
                    )
                    yield from side_effects  # ← Confirm.ask 阻塞点
                    # b. 用户同意 → 用 confirmed=True 重新执行，跳过 confirm 检查
                    tool_result, exec_side_effects = self._dispatch_tool(fname, fargs, confirmed=True)
                    yield from exec_side_effects
                    # c. 用真实结果替换占位
                    self.messages[-1] = {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": compress_tool_result(tool_result, self.client, self.model),
                    }
                    append_tool_result = False  # 已在 confirm 分支内追加
                else:
                    yield from side_effects
                    append_tool_result = True
                # 把 tool 执行结果 yield 给 UI，实现闭环展示
                result_text = tool_result if isinstance(tool_result, str) else str(tool_result)
                if len(result_text) > 2000:
                    result_text = result_text[:2000] + "\n...[folded]"
                yield ("tool_result", {"name": fname, "result": result_text})
                if fname not in self._WRITE_TOOLS:
                    executed_sigs.add(sig)
                    executed_cache[sig] = tool_result
            # 上下文窗口防护：智能压缩（抽取→LLM→截断三级路由），
            # 防止大文件/长输出撑爆 LLM 上下文。原始结果仍在 cache 中。
            # confirm 分支已在上面追加 tool 结果，跳过此处追加。
            if append_tool_result:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": compress_tool_result(tool_result, self.client, self.model),
                    }
                )
        return False

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
        _turn_count is managed by _finalize_outcome; read-only here."""
        turn = getattr(self, "_turn_count", 0)
        if turn % self._SNAPSHOT_INTERVAL != 0:
            return
        from core.chat_history import save_snapshot

        save_snapshot(self._SNAPSHOT_DIR, self.model, turn, self.messages)

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
        """Post-turn reflection: light model reviews output quality."""
        if self._reflection is None:
            try:
                from core.reflection_loop import ReflectionLoop

                self._reflection = ReflectionLoop()
            except (ImportError, OSError) as e:
                logger.debug("ReflectionLoop init failed: %s", e)
                return
        try:
            self._reflection.review(self)
        except Exception as e:
            logger.debug("reflection review failed: %s", e)

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
