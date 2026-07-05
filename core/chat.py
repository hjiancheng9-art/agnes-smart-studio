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
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.cognitive_orchestrator import CognitiveOrchestrator
    from core.memory_bridge import MemoryBridge
    from core.reflection_loop import ReflectionLoop

logger = logging.getLogger("crux.chat")

from core.agent import ContextManager
from core.brain import SmartBrain
from core.chat_prompt import (
    CHAT_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    build_system_prompt,
)
from core.chat_toggle_mixin import ChatToggleMixin
from core.chat_tool_dispatch import _dispatch_tool_impl
from core.chat_tool_helpers import merge_tool_calls, sanitize_tool_call_history
from core.chat_tool_helpers import normalize_tool_args as _normalize_tool_args
from core.chat_vision import _vision_fallback
from core.client import CruxClient
from core.config import get_crux_vision_model
from core.observability import TraceContext, metrics
from core.provider import (
    get_provider_name,
    get_tool_calling_models,
    get_vision_models,
)
from core.skills import SkillManager, get_manager
from core.tools import AGENT_SYSTEM_PROMPT, ToolRegistry, get_registry
from core.vision_context import VisionContext
from engines.text_to_image import TextToImageEngine
from engines.video import VideoEngine

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "CODE_SYSTEM_PROMPT",
    "ChatSession",
    "MAX_TOOL_LOOPS",
    "merge_tool_calls",
    "MODEL_ALIASES",
    "MODEL_INFO",
    "MODEL_PROVIDER_MAP",
    "TOOL_CALLING_MODELS",
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
        from core.provider import get_provider_manager

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
# 从 30 → 50：复杂任务（如批量生成）需要多轮工具调度
MAX_TOOL_LOOPS = 100

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
        self.brain = SmartBrain(client)  # pyright: ignore[reportArgumentType]
        self.t2i = TextToImageEngine(client)
        self.vid = VideoEngine(client)
        self.media_client = client  # unified media client for tool-calling generation
        self.model = default_model or self._resolve_default_model()
        self._ctx_mgr: ContextManager | None = None  # lazy: built from model's actual context window
        self.auto_model = True  # auto-select model per prompt
        self._model_router = None  # lazy init
        self._auto_tier_order = ["reasoner", "pro", "light"]  # preferred tier order
        self.enable_thinking = False
        self.code_mode = False
        self.mode = "chat"
        self.unlimited_tools = False
        self.agent_mode = False
        self.browser_enabled = False
        self.notebook_enabled = False
        self.audio_enabled = False
        self.tools: ToolRegistry = get_registry()
        self.skills: SkillManager = get_manager()
        self.active_skill: str = ""
        self._reflection: ReflectionLoop | None = None  # ReflectionLoop, lazy init
        self._memory: MemoryBridge | None = None  # MemoryBridge, lazy init
        self._cog: CognitiveOrchestrator | None = None  # CognitiveOrchestrator, lazy init
        self._vote_enabled: bool = False  # /vote toggle (off by default to save tokens)
        self.messages: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]
        # 七兽躯体激活
        try:
            from core.beast_wiring import wire_all

            wire_all()
        except (ImportError, OSError):
            logger.debug('spectrum module not available')
        # 激活学习钩子（agent 从工具成败中学习）
        try:
            from core.hooks import register_learning_hooks
            register_learning_hooks()
        except (ImportError, OSError) as e:

            logger.debug("optional module skipped: %s", e)

            pass
        # 激活工具拦截器（PreToolUse 安全守卫）
        try:
            from core.tool_interceptor import register_tool_interceptor
            register_tool_interceptor()
        except (ImportError, OSError) as e:

            logger.debug("optional module skipped: %s", e)

            pass
        # 启动配置热重载（models.json + tools.json 变更自动生效）
        try:
            from core.settings_watcher import start_watcher
            start_watcher()
        except (ImportError, OSError) as e:

            logger.debug("optional module skipped: %s", e)

            pass
        # 激活三层防御（PreCheck + CircuitBreaker + PostValidate + AutoRollback）
        try:
            from core.defense import register_defense_hooks
            register_defense_hooks()
        except (ImportError, OSError) as e:

            logger.debug("optional module skipped: %s", e)

            pass
        # 注入会话上下文（git 分支/状态/最近提交）— 仅在代码/Agent 模式下
        if self.code_mode or self.agent_mode:
            try:
                ctx = self._build_session_context()
                if ctx:
                    self.messages[0]["content"] += ctx
            except (OSError, RuntimeError):
                logger.debug("session context injection failed", exc_info=True)
        # 视觉上下文管理器（图片持久化 + 按需重查）
        self.vision_ctx = VisionContext()

    def _build_session_context(self) -> str:
        """Build session context string — git branch + status + recent commits.

        异步收集（后台线程），避免阻塞 ChatSession 构造。非关键信息，
        缺失不报错。
        """
        ctx_parts: list[str] = []

        def _collect_git():
            import subprocess
            cwd = str(Path(__file__).resolve().parent.parent)
            try:
                r = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=3, cwd=cwd,
                )
                branch = r.stdout.strip()
                if branch:
                    ctx_parts.append(f"branch: {branch}")
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug("git rev-parse failed: %s", e)

            try:
                r = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True, text=True, timeout=3, cwd=cwd,
                )
                changed = [line.strip() for line in r.stdout.splitlines()[:20] if line.strip()]
                if changed:
                    ctx_parts.append(f"changes ({len(changed)}): " + ", ".join(changed[:10]))
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug("git status failed: %s", e)

            try:
                r = subprocess.run(
                    ["git", "log", "--oneline", "-5"],
                    capture_output=True, text=True, timeout=3, cwd=cwd,
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
        # 用 80% 作为压缩阈值，留 20% 给输出
        limit = max(60000, int(ctx * 0.8))
        self._ctx_mgr = ContextManager(max_tokens=limit)

    @staticmethod
    def _resolve_default_model() -> str:
        """从 active provider 派生默认 light 模型。"""
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("light") or "deepseek-v4-flash"
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

    def _auto_route(self, prompt: str) -> str | None:
        """Analyze prompt and switch model if auto_model is enabled.

        Returns the selected tier string ('light'/'pro'/'reasoner') or None if
        auto_model is disabled.  Caller should check the return value and show
        a brief indicator if the model changed.
        """
        if not self.auto_model:
            return None

        router = self.model_router
        tier = router.classify_and_track(prompt)

        # Resolve tier → model ID from current provider, fallback across providers
        target_model = None
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            mgr.load()

            current_pid = mgr.state.active
            pdata = mgr.providers.get(current_pid, {})
            provider_models = pdata.get("models", {})

            target_model = router.resolve_model(tier, provider_models)

            # If current provider doesn't have this tier, search other providers
            # by latency (fastest first) to minimize response time
            if target_model not in provider_models.values() or target_model == "unknown":
                # Sort providers by policy routing: task_type, budget, circuit-state
                all_pids = list(mgr.providers.keys())
                try:
                    from core.provider_policy import select_candidates
                    circuit_states = {p: mgr.state.circuit_state(p) for p in all_pids}
                    request = {"task_type": "text", "require_code": True, "budget_remaining": 100}
                    ordered_pids = select_candidates(request, all_pids, circuit_states)
                    try:
                        from core.policy_regression import record_route_decision
                        record_route_decision(request, ordered_pids, circuit_states)
                    except ImportError:
                        pass
                except ImportError:
                    ordered_pids = mgr.state.available_by_latency(all_pids)
                for pid in ordered_pids:
                    pd = mgr.providers.get(pid, {})
                    pm = pd.get("models", {})
                    candidate = router.resolve_model(tier, pm)
                    if candidate != "unknown" and candidate in pm.values():
                        target_model = candidate
                        # Switch provider if needed
                        if pid != current_pid:
                            new_client = mgr.create_client(pid)
                            expected_url = pd.get("base_url", "")
                            if new_client.base_url.rstrip("/") == expected_url.rstrip("/"):
                                self.client = new_client
                        break
        except Exception as e:

            logger.debug("unexpected error: %s", e, exc_info=True)

            return tier  # routing failed silently, keep current model

        # Switch if different
        if target_model and target_model != self.model and target_model != "unknown":
            self.model = target_model
            self._rebuild_ctx_mgr()
            self.messages[0] = {"role": "system", "content": self._build_system_prompt()}

        return tier

    @property
    def supports_tools(self) -> bool:
        """支持 tool calling 自动调度的模型（含第三方兼容 OpenAI tools 的模型）"""
        from core.provider import model_supports_tools

        return model_supports_tools(self.model)

    def _reload_tools(self):
        """重新加载工具注册表，传入当前所有 toggle 状态。

        agent 模式: load(pipeline=..., comfyui=..., browser=..., notebook=..., audio=...)
        普通模式: 也传入 browser/notebook/audio（这些 toggle 独立于 agent 模式）。
        """
        pipeline = self.active_skill in ("showrunner", "core-showrunner")
        comfyui = self.active_skill in ("comfyui-bridge",)
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

        showrunner:  启用管道工具链（视频生产）
        comfyui-bridge: 启用 ComfyUI 桥接工具（本地生图/生视频）
        两者可同时加载（Showrunner 策划 + ComfyUI 执行）
        """
        self.skills.discover()
        skill = self.skills.load(name)
        if skill:
            self.active_skill = name
            # 不强制切模型：保留 self.model，由路由层/用户决定使用哪个支持 tools 的模型
            self.enable_thinking = True

            # ── 根据技能类型启用对应工具集 ──
            pipeline = self.active_skill == "showrunner"
            comfyui = self.active_skill == "comfyui-bridge"

            if pipeline or comfyui:
                self.tools = get_registry()
                self.tools.load(pipeline=pipeline, comfyui=comfyui,
                                browser=self.browser_enabled,
                                notebook=self.notebook_enabled,
                                audio=self.audio_enabled, mcp=True)

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
                    t["name"], t.get("description", ""), t.get("parameters", {}),
                    resolve_skill_executor(t["name"], t)
                )
            return name
        return None

    def unload_skill(self):
        """卸载当前技能。管道/ComfyUI 工具集同时清理。"""
        self.active_skill = ""
        self.skills.unload()
        # 重新加载纯净工具集（只含内置 + 外部 tools.json）
        self.tools = get_registry()
        self.tools.load(pipeline=False, comfyui=False,
                        browser=self.browser_enabled,
                        notebook=self.notebook_enabled,
                        audio=self.audio_enabled, mcp=True)
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

    def _render_tool_categories(self) -> str:
        """渲染工具分类为 system prompt 片段（分组显示，零过滤）。

        所有工具仍全量发给 LLM API（definitions 不动），此处仅做文字分组，
        降低 LLM 在 tool call 时的选择噪声。
        """
        cats = self.tools.tool_categories
        if not cats:
            return f"\n当前可用工具: {self.tools.tool_names}"
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

        # Prompt cache managed by chat_prompt.PromptCache (single source of truth)
        return prompt

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    def _vision_model_chain(self, complexity: str = "light") -> list[str]:
        """构建视觉模型 fallback 链（供应商优先于 tier，CRUX 质量 > 智谱）。

        - CRUX (agnes): 视觉质量最优，计数/OCR/细节识别精准，优先使用
        - 智谱 (zhipu): 免费兜底，CRUX 不可用时启用

        同一供应商内按思考能力 + tier 排序。
        self.vision_model 仅在 tier 匹配时提到链首。
        """
        from core.provider import get_model_info

        vision_models = get_vision_models()
        if not vision_models:
            return [self.vision_model] if self.vision_model else []

        def _info_of(mid: str):
            info = get_model_info(mid)
            if info is None:
                raise KeyError(f"model {mid} not found in registry")
            return info

        # 按供应商分组：CRUX 在前，智谱在后（质量优先）
        crux_models = [m for m in vision_models if _info_of(m).provider_id == "crux"]
        zhipu_models = [m for m in vision_models if _info_of(m).provider_id == "zhipu"]
        other_models = [m for m in vision_models if _info_of(m).provider_id not in ("zhipu", "crux")]

        def _sort_within_provider(models: list[str], pro_first: bool) -> list[str]:
            """组内排序：thinking 优先 → tier 次之。"""
            thinking = [m for m in models if _info_of(m).supports_thinking]
            no_thinking = [m for m in models if not _info_of(m).supports_thinking]

            def _by_tier(ms):
                light = [m for m in ms if _info_of(m).tier == "light"]
                pro = [m for m in ms if _info_of(m).tier != "light"]
                return (pro + light) if pro_first else (light + pro)

            return _by_tier(thinking) + _by_tier(no_thinking)

        pro_first = complexity == "complex"
        ordered: list[str] = []
        ordered.extend(_sort_within_provider(crux_models, pro_first))
        ordered.extend(_sort_within_provider(zhipu_models, pro_first))
        ordered.extend(_sort_within_provider(other_models, pro_first))

        # self.vision_model 仅在 tier 匹配时提到链首（用户偏好尊重 tier 路由）
        if self.vision_model and self.vision_model in ordered:
            vm_tier = _info_of(self.vision_model).tier
            target_tier = "light" if not pro_first else "pro"
            if vm_tier == target_tier:
                ordered.remove(self.vision_model)
                ordered.insert(0, self.vision_model)
        return ordered

    @staticmethod
    def _classify_vision_complexity(text: str) -> tuple[str, int]:
        """视觉任务复杂度启发式分类（零 LLM 消耗，对标 Claude vision tier）。

        Returns:
            ("light"|"complex", max_tokens)
        - light: OCR/描述/简单问答 → max_tokens=2048（快省）
        - complex: 计数/读代码/图表推理/对比/几何/多步分析 → max_tokens=4096
        """
        # 复杂视觉任务关键词（中文 + 英文）
        _COMPLEX_RE = re.compile(
            r"(数一数|多少个|计数|count|how many)|"
            r"(代码|code|函数|function|class |import |def )|"
            r"(图表|graph|chart|柱状|饼图|折线|scatter|bar chart)|"
            r"(对比|区别|差异|difference|compare|diff)|"
            r"(计算|算一算|calculate|compute|面积|周长|角度)|"
            r"(推理|推断|infer|deduce|逻辑|logical)|"
            r"(流程|flowchart|架构|architecture|拓扑|topology)|"
            r"(详细分析|深入|逐步|step.by.step|explain in detail)|"
            r"(公式|equation|math|数学)",
            re.IGNORECASE,
        )
        if _COMPLEX_RE.search(text):
            return ("complex", 4096)
        return ("light", 2048)

    def _text_fallback_chain(self) -> list[tuple[str, CruxClient]]:
        """构建主对话 fallback 链（模型 + client 对）。

        顺序：当前 (model, client) → fallback provider 的 (model, client)。
        对标 Claude 的 fallbackModel 数组：主模型挂了自动降级到备选。
        同供应商不同模型（如 deepseek-v4-pro → deepseek-v4-flash）也作为备选。
        """
        from core.provider import get_provider_manager

        chain: list[tuple[str, CruxClient]] = [(self.model, self.client)]
        try:
            mgr = get_provider_manager()
            for pid in mgr.fallback_priority:
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
        """检测流式输出是否因网络/API 错误而中断。

        用明确的错误标记前缀匹配，避免用户对话中恰好包含这些字符串时误触发。
        只有在 buffer 非空且以错误标记开头时才判定为流错误。
        """
        if not buffer:
            return False
        return buffer.startswith("[流中断") or buffer.startswith("[HTTP ")

    def send_stream(self, user_text: str, image_url: str | None = None):
        """发送用户消息，流式 yield (kind, payload) 元组。

        - 多模态（有 image_url）：走 vision_client 整块输出，与主模型供应商解耦
        - tool 调度（pro）：流式累积 → 检测 tool_calls → 执行 engine → 喂回 → 二次流式
        - 纯文本：流式 yield ('text', 增量)
        """
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
            user_text = f"[图片分析] {vision_raw}\n\n用户提问: {user_text}"
            # 不 return，继续走正常 LLM 流式推理

        # ── 纯文本分支：加 user message ──
        self.messages.append({"role": "user", "content": user_text})

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
                content = (
                    f"{result['answer']}\n\n"
                    f"[{result['models_used']} models, confidence: {result['confidence']}]"
                )
                if result.get("dissenting") and result["dissenting"] != "none":
                    content += f"\n[dim]Dissent: {result['dissenting']}[/]"
                self.messages.append({"role": "assistant", "content": content})
                yield ("text", content)
                return

        # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
        if self.ctx_mgr.needs_compression(self.messages):
            self.messages = self.ctx_mgr.compress(self.messages, self.client, self.model)

        tools = self.tools.get_filtered_definitions(user_text) if self.supports_tools else None

        # ── 模型级 fallback 链（对标 Claude fallbackModel）──
        # 主对话流式调用失败时自动降级到下一个供应商/模型。
        # 只在首轮（无 tool_calls）时 fallback，避免重复 tool 副作用。
        fallback_chain = self._text_fallback_chain()
        fallback_tried = 0

        # tool calling 循环（有上限，防止死循环）
        _effective_max = MAX_TOOL_LOOPS * 2 if getattr(self, "unlimited_tools", False) else MAX_TOOL_LOOPS
        buffer = ""  # 循环外预绑定，保证超出最大轮次时引用安全
        # 跨轮工具去重状态（见 _run_tool_calls 的注释）
        _executed_signatures: set[tuple[str, str]] = set()
        _executed_cache: dict[tuple[str, str], str] = {}
        _stream_error_break = False
        _tools_expanded = False  # 工具调用后自动展开全量工具

        while fallback_tried < len(fallback_chain):
            _use_model, _use_client = fallback_chain[fallback_tried]
            fallback_tried += 1
            _stream_error_break = False  # 标记 for 循环是否因流错误 break

            for _loop in range(_effective_max):
                buffer, tool_calls = "", []
                _stream_error = False
                _last_usage = None
                # _consume_stream_delta 是生成器：yield text chunks + return (buffer, tool_calls, error, usage)
                try:
                    delta_result = yield from self._consume_stream_delta(
                        _use_client,
                        _use_model,
                        tools,
                    )
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
                        )
                    except Exception as e:
                        logger.exception("_run_tool_calls 异常")
                        yield ("error", f"工具执行中断: {type(e).__name__}: {e}")
                        _stream_error_break = True
                        break
                    # 一旦模型开始调用工具，后续轮次展开全量工具定义
                    if not _tools_expanded:
                        tools = self.tools.definitions if self.supports_tools else None
                        _tools_expanded = True
                    continue  # 进入下一轮 tool loop

                # 无 tool_calls：检查是否流错误（需 fallback）还是正常收尾
                if _stream_error or self._is_stream_error(buffer):
                    if _loop == 0 and fallback_tried < len(fallback_chain):
                        # 通知 ProviderManager 标记当前供应商为 down
                        try:
                            from core.provider import get_provider_manager
                            mgr = get_provider_manager()
                            # 先尝试自动 failover（handle_failure 会选一个可用 provider）
                            new_client, new_pid = mgr.handle_failure(mgr.state.active, 500)
                            if new_client:
                                self.client = new_client
                                mgr.state.record_success(new_pid)
                                logger.info("failover: -> %s (auto)", new_pid)
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
                self._trigger_reflection()
                self._auto_remember()
                return

        # for _loop 结束：区分两种情况
        # 1. _stream_error_break=True → 流错误 fallback，回到 while 尝试下一档
        # 2. _stream_error_break=False → tool loop 溢出（模型正常工作但死循环），不 fallback
        if not _stream_error_break:
            yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
            self.messages.append({"role": "assistant", "content": buffer})
            self._record_outcome_promptlab()
            return

        # All fallback models exhausted — tell the user something went wrong.
        tried = ", ".join(m for m, _ in fallback_chain)
        yield ("error", f"所有模型均不可用（已尝试: {tried}），请稍后重试或 /provider 切换")

    # ── send_stream 的拆分子方法（行为不变，仅降低单方法复杂度）──
    # 以下三个方法由 send_stream 调用，分别处理：吃 delta / 执行工具 / 收尾计费。
    # 提取动机：原 send_stream 170 行三层嵌套（while fallback × for tool_loop × for delta），
    # 认知负荷极高（CodeBuddy/Claude/Codex 三方评分一致点名）。拆分后 send_stream 只剩控制流骨架。

    # 写操作类工具不参与跨轮去重缓存（避免吞掉用户对同一文件的连续修改意图）
    from core.constraints import WRITE_TOOLS

    _WRITE_TOOLS = WRITE_TOOLS

    def _consume_stream_delta(self, client: CruxClient, model: str, tools):
        """吃一轮流式 delta，yield text chunks，return (buffer, tool_calls, stream_error, last_usage)。

        本方法是纯消费者：把 chat_stream 的增量帧累积成 buffer + tool_calls，
        并捕获最后一帧的 usage（用于计费）和 _finish="error" 标记。
        不修改 self.messages（写入由调用方负责）。

        yield from 此生成器时，返回值通过 StopIteration.value 传递。

        max_tokens 自适应：纯文本 16384（覆盖长文案/脚本/分析），工具 8192，
        """
        buffer, tool_calls = "", []
        stream_error = False
        last_usage = None
        # 从统一适配层读取模型实际能力
        from core.provider_adapter import get_max_tokens, get_thinking_params
        max_tok = get_max_tokens(model, is_tool_call=bool(tools))
        kwargs = {}
        if self.enable_thinking:
            kwargs = get_thinking_params(model)
        for delta in client.chat_stream(
            model=model,
            messages=sanitize_tool_call_history(self.messages),
            tools=tools,
            max_tokens=max_tok,
            **kwargs,
        ):
            # 供应商感知的 thinking token 提取
            from core.provider_adapter import get_adapter, get_capability
            cap = get_capability(model)
            adapter = get_adapter(cap.provider_id if cap else "deepseek")
            think_field = adapter.thinking_response_field
            if think_field in delta and delta[think_field]:
                yield ("thinking", delta[think_field])  # type: ignore[misc]
            if "content" in delta and delta["content"]:
                chunk = delta["content"]
                buffer += chunk
                # Don't render HTTP error bodies as assistant text.
                if not delta.get("_error"):
                    yield ("text", chunk)  # type: ignore[misc]
            if "tool_calls" in delta and delta["tool_calls"]:
                tool_calls.extend(delta["tool_calls"])
            if delta.get("_finish") == "error":
                stream_error = True
            if "_usage" in delta:
                last_usage = delta["_usage"]
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

    def _run_tool_calls(self, tool_calls, executed_sigs, executed_cache):
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

        merged = getattr(self, "_last_merged_tool_calls", merge_tool_calls(tool_calls))
        for tc in merged:
            fname = tc["function"]["name"]
            fargs = tc["function"].get("arguments", "{}")
            sig = (fname, _normalize_tool_args(fargs))
            # 跨轮去重：非写工具且本会话已执行过 → 复用缓存，不重复 dispatch
            if fname not in self._WRITE_TOOLS and sig in executed_sigs:
                tool_result = executed_cache.get(sig, "")
                # 不 yield 副作用（用户已见过一次）
                append_tool_result = True
            else:
                with TraceContext("tool_call", tool_name=fname, call_id=tc.get("id", "")) as span:
                    try:
                        tool_result, side_effects = self._dispatch_tool(fname, fargs)
                    except Exception as e:
                        logger.exception("工具 %s 执行异常", fname)
                        tool_result = f"[错误] 工具 {fname} 执行失败: {type(e).__name__}: {e}"
                        side_effects = [("info", tool_result)]
                        metrics.increment("tool_errors")
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
        """正常收尾：成本追踪 + Prompt Lab outcome + 方法论工作流推进。"""
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

            # Retry with modified prompt
            retry_buffer = ""
            try:
                for kind, payload in self._consume_stream_delta(client, model, tools):
                    if isinstance(payload, str) and kind == "text":
                        retry_buffer += payload
                        yield ("text", payload)
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

    def _record_outcome_promptlab(self) -> None:
        """记录会话 outcome 到 Prompt Lab（可选模块，失败静默降级）。"""
        try:
            from core.prompt_lab import get_prompt_lab

            get_prompt_lab().record_outcome()
        except (ImportError, OSError):
            logger.debug('spectrum module not available')


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

ChatSession._vision_fallback = _vision_fallback
