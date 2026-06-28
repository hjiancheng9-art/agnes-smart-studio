"""聊天会话 - 多轮对话 + 混合生成调度（命令式 + AI 自动 tool calling）+ 多模态理解

三条轨道：
- 命令式：上层识别 /img /video 后直接调 engine（在 ui/cli.py 处理，不过本模块）
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

import contextlib
import json
import logging
import re
from collections.abc import Callable

logger = logging.getLogger("crux.chat")

from core.agent import ContextManager
from core.brain import SmartBrain
from core.chat_prompt import (
    CHAT_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    build_system_prompt,
    get_cached_prompt,
)
from core.client import CruxClient
from core.config import get_crux_vision_model
from core.context_tools import truncate_messages
from core.observability import TraceContext, metrics
from core.provider import (
    get_provider_name,
    get_tool_calling_models,
    get_vision_models,
)
from core.skills import SkillManager, get_manager
from core.tools import AGENT_SYSTEM_PROMPT, ToolRegistry, get_registry
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

# ── System prompt 模块级缓存（委托 chat_prompt.py 管理）──
_cached_prompt: list[str] = ["", ""]  # 向后兼容旧引用


CHAT_SYSTEM_PROMPT = """你是 {provider_name} 智能助手，当前运行在 {model_name} 模型上。你擅长：
- 日常问答、创意写作、知识解释、方案讨论
- 当用户明确想生成图片时，调用 generate_image 工具
- 当用户明确想生成视频/动画时，调用 generate_video 工具
- 普通对话不要调用任何工具

重要约束：
- generate_image / generate_video 每轮对话最多调用 1 次，生成后必须立即总结结果给用户
- 不要在生成后调用对比/评估工具，更不要因评分不理想而重新生成
- 工具执行成功后，直接用文字回复用户，不要再调用任何工具

风格：简洁、中文优先、回答到位。如果用户询问你使用的模型，直接告知当前运行的是 {model_name}。"""

CODE_SYSTEM_PROMPT = """你是 {provider_name} 编程助手，当前运行在 {model_name} 模型上。
你是一位资深全栈工程师，擅长：
- Python、JavaScript/TypeScript、Go、Rust、Java、C/C++ 等主流语言
- Web 开发（React、Vue、Node.js、FastAPI、Django）
- 数据库设计、API 设计、系统架构
- 调试、性能优化、代码审查
- 所有回答附带完整可运行代码，标注语言

## 工作纪律（探索-计划-执行三段式）
回答编码任务时遵循以下顺序，简单任务可压缩，但探索段永不可省：
1. **探索**：先读相关文件理解现状，不凭记忆猜 API 签名和库行为
2. **计划**：复杂任务用 ≤5 步概述方案，每步可独立验证
3. **执行**：按计划实施，每步完成后说明"已完成 + 验证方式"

## 核心约束
- **事实优先**：不确定的 API/配置/默认值，先读代码或文档验证，绝不编造
- **最小改动**：只改必须改的行，不顺手重构无关代码，不为未来需求过度抽象
- **完整闭环**：一个任务必须含实现+测试+验证才算完成；修复 error 后必须验证
- **删除前搜索**：删除函数/变量/文件前，先 grep 全项目确认无引用
- **失败如实报**：测试失败就报失败，跳过的步骤明说跳过了

## 输出规范
- 代码块必须标注语言（```python、```javascript 等）
- 复杂问题分步骤讲解：分析 → 方案 → 代码 → 说明
- 优先给出最简实现，不过度设计
- 如需调用图片/视频工具，明确告知用户用 /img 或 /video 命令
- 如果用户询问你使用的模型，直接告知当前运行的是 {model_name}，由 {provider_name} 提供"""

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
    except Exception:
        return {}


def _build_model_info() -> dict[str, str]:
    """从 MODEL_REGISTRY 构建模型 ID → 描述 映射。"""
    try:
        from core.provider import MODEL_REGISTRY

        return {mid: info.description for mid, info in MODEL_REGISTRY.items() if info.description}
    except Exception:
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
MAX_TOOL_LOOPS = 30


def _normalize_tool_args(args_json: str) -> str:
    """归一化工具 arguments JSON 字符串，用于语义去重签名。

    解析 JSON → 按 key 排序 → 紧凑序列化，使 {"a":1,"b":2} 与 {"b":2,"a":1}
    产生相同签名。解析失败时退化为去空白原串（仍能去重明显重复）。
    """
    s = (args_json or "").strip()
    if not s:
        return ""
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    except (json.JSONDecodeError, TypeError):
        # 不完整的 JSON 分片（流式中途）：去空白作签名，仍能合并明显重复
        return "".join(s.split())


class ChatSession:
    """多轮聊天会话，维护历史 + 混合调度

    vision_client: 独立视觉客户端（始终指向 CRUX API），与主对话供应商解耦。
                   为 None 时退化为 self.client，向后兼容原有行为。
    vision_model:  视觉理解专用模型 ID，默认 agnes-1.5-flash。
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
        self.brain = SmartBrain(client)
        self.ctx_mgr = ContextManager(max_tokens=60000)
        self.t2i = TextToImageEngine(client)
        self.vid = VideoEngine(client)
        self.model = default_model or self._resolve_default_model()
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
        self.messages: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]
        # 五兽躯体激活
        try:
            from core.beast_wiring import wire_all

            wire_all()
        except (ImportError, OSError):
            logger.debug('spectrum module not available')

    @staticmethod
    def _resolve_default_model() -> str:
        """从 active provider 派生默认 light 模型。"""
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("light") or "deepseek-v4-flash"
        except Exception:
            return "deepseek-v4-flash"

    @property
    def supports_tools(self) -> bool:
        """支持 tool calling 自动调度的模型（含第三方兼容 OpenAI tools 的模型）"""
        from core.provider import model_supports_tools

        return model_supports_tools(self.model)

    def toggle_code_mode(self) -> bool:
        """切换代码助手模式，返回切换后的状态

        不再强制绑定 agnes-2.0-flash，保留当前供应商模型。
        视觉能力由 self.vision_client 独立处理，不受主模型影响。
        """
        self.code_mode = not self.code_mode
        self.enable_thinking = self.code_mode  # 代码模式自动开启 thinking（供应商支持时生效）
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.code_mode

    def toggle_agent_mode(self) -> bool:
        """切换智能体模式，加载 tools.json 中定义的外部工具

        不再强制绑定 agnes-2.0-flash，保留当前供应商模型——只要模型
        支持 tool calling（见 supports_tools / provider.model_supports_tools）
        即可参与智能体调度；若当前模型不支持，由 ui 层给出切换提示。
        视觉能力由 self.vision_client 独立处理，不受主模型影响。
        """
        self.agent_mode = not self.agent_mode
        # 不强制切模型：保留 self.model（若用户已选 deepseek 等支持 tools 的模型）
        self.enable_thinking = True
        # agent 模式自动翻倍工具轮次：复杂跨项目任务（探索+修复）需要更多回合
        self.unlimited_tools = self.agent_mode
        if self.agent_mode:
            self.tools = get_registry()  # 重新加载工具配置
            self.tools.load(
                browser=self.browser_enabled,
                notebook=self.notebook_enabled,
                audio=self.audio_enabled,
                mcp=True,
            )
            # 激活代码守卫 hook（语法验证 + smoke 测试）
            try:
                from core.hooks import register_code_hooks

                register_code_hooks()
            except (ImportError, OSError):
                pass
            # #2 激活反思 hook（定期 critique，辅助模型分析工具调用序列）
            try:
                from core.config import SETTINGS
                from core.hooks import register_reflection_hook

                register_reflection_hook(
                    client=self.client,
                    interval=SETTINGS.reflection_interval,
                    enabled=SETTINGS.reflection_enabled,
                )
            except (ImportError, OSError):
                pass
            prompt = AGENT_SYSTEM_PROMPT + self._render_tool_categories()
        else:
            prompt = self._build_system_prompt()
        prompt = self.skills.get_system_prompt(prompt)
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.agent_mode

    def toggle_browser(self) -> bool:
        """切换 Browser Companion 网页生成工具（8 个 provider：可灵/即梦/Runway/Luma/DALL-E/Gemini/Opal/Veo）。"""
        self.browser_enabled = not self.browser_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.browser_enabled

    def toggle_notebook(self) -> bool:
        """切换 Notebook (.ipynb) 工具（数据科学场景：打开/编辑/执行/保存 Jupyter notebook）。"""
        self.notebook_enabled = not self.notebook_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.notebook_enabled

    def toggle_audio(self) -> bool:
        """切换音频工具（edge-tts 旁白/BGM/SFX/混音，补齐 Showrunner 音轨缺口）。"""
        self.audio_enabled = not self.audio_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.audio_enabled

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
                self.tools.load(pipeline=pipeline, comfyui=comfyui, mcp=True)

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
        self.tools.load(pipeline=False, comfyui=False, mcp=True)
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
        except (ImportError, OSError):
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
        )

        # 同步回旧缓存（向后兼容 async_chat.py 的 _cached_prompt 引用）
        cache = get_cached_prompt()
        _cached_prompt[:] = [cache.key, cache.prompt]
        return prompt

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    def _vision_model_chain(self, complexity: str = "light") -> list[str]:
        """构建视觉模型 fallback 链（按复杂度选首选，去重保持稳定）。

        阶段 4b: 除 deepseek 外所有模型均支持视觉。按复杂度自动选首选：
        - complexity="light":  首选 light tier 模型（agnes-1.5-flash，最便宜快档）
        - complexity="complex": 首选 pro tier 模型（agnes-2.0-flash，支持推理）

        首选失败后，按 tier 升序（light → pro）补位其余视觉模型，
        保证 fallback 链稳定可预测。单一真相源 provider.get_vision_models()。

        self.vision_model 仅作为"用户显式首选偏好"：当其 tier 匹配任务复杂度时
        排首位；否则不干预自动 tier 选择（避免轻量任务强制走 pro、或复杂任务
        被钉在 light tier）。
        """
        from core.provider import get_model_info

        vision_models = get_vision_models()
        if not vision_models:
            return [self.vision_model] if self.vision_model else []

        def _tier_of(mid: str) -> str:
            info = get_model_info(mid)
            return info.tier if info else "pro"

        light_models = [m for m in vision_models if _tier_of(m) == "light"]
        pro_models = [m for m in vision_models if _tier_of(m) != "light"]

        # 复杂任务 → pro 优先；轻量任务 → light 优先
        ordered = (pro_models + light_models) if complexity == "complex" else (light_models + pro_models)

        # self.vision_model 仅在 tier 匹配时提到链首（用户偏好尊重 tier 路由）
        if self.vision_model and self.vision_model in ordered:
            vm_tier = _tier_of(self.vision_model)
            target_tier = "light" if complexity != "complex" else "pro"
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

    def _text_fallback_chain(self) -> list[tuple[str, "CruxClient"]]:
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
                    except (OSError, RuntimeError):
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
            except (OSError, RuntimeError):
                pass
        except (ImportError, OSError, RuntimeError):
            pass
        return chain

    def _is_stream_error(self, buffer: str) -> bool:
        """检测流式输出是否因网络/API 错误而中断。"""
        return "[流中断" in buffer or "[HTTP " in buffer

    def _vision_fallback(self, text: str, image_url: str) -> str:
        """视觉理解调用 + fallback 链（按复杂度自动选首选模型）。

        依次尝试 _vision_model_chain(complexity) 中的模型，首个成功即返回；
        全部失败时返回包含尝试列表的人类可读错误（不抛异常，保证流式不中断）。

        阶段 4b: 复杂度不仅决定 max_tokens，还决定首选模型 tier：
        - light: 首选 agnes-1.5-flash（便宜快档），失败再升 pro
        - complex: 首选 pro tier（agnes-2.0-flash / Kimi / Qwen），失败再降 light

        失败原因分类：
        - KeyError/IndexError: 返回 JSON 结构异常（供应商换了 schema）
        - OSError/TimeoutError: 网络/超时（最常见，触发下一档 fallback）
        - RuntimeError: 供应商上游错误
        """
        # Vision 复杂度分级：light → 2048 tokens + light tier 首选；
        #                  complex → 4096 tokens + pro tier 首选 + 推理引导
        complexity, max_tok = self._classify_vision_complexity(text)
        chain = self._vision_model_chain(complexity)
        tried: list[str] = []
        last_reason = ""
        vision_text = text
        if complexity == "complex":
            # 注入逐步推理引导（不修改用户原始文本，只影响 API 调用）
            vision_text = f"请仔细观察图片，逐步推理分析：\n{text}"
        for model_id in chain:
            tried.append(model_id)
            try:
                # Use provider-aware client: zhipu models need zhipu endpoint
                vc = self.vision_client
                if model_id.startswith("glm-") or model_id.startswith("cog"):
                    try:
                        from core.provider import get_provider_manager
                        mgr = get_provider_manager()
                        vc = mgr.create_client("zhipu")
                    except (ImportError, RuntimeError):
                        pass  # fall through to default vision_client
                r = vc.chat_multimodal(
                    text=vision_text,
                    image_url=image_url,
                    model=model_id,
                    max_tokens=max_tok,
                )
                content = r["choices"][0]["message"]["content"] or ""
                # #6 成本追踪：视觉调用按 token 计费（text kind），usage 来自 API 返回
                try:
                    from core.cost_tracker import record_usage

                    record_usage(model=model_id, kind="text", usage=r.get("usage"), label="vision")
                except (ImportError, OSError, KeyError, TypeError) as e:
                    logger.debug("cost_tracker.record_usage(vision) failed: %s: %s", type(e).__name__, e)
                return content
            except (KeyError, IndexError) as e:
                last_reason = f"返回格式异常: {e}"
                # P1-10: 请求成功但解析失败 → 尝试从响应中提取 usage 记费
                # 注意: r 可能在 chat_multimodal 本身抛异常时未赋值（side_effect）
                _r_usage = None
                with contextlib.suppress(NameError):
                    _r_usage = r.get("usage")  # type: ignore[possibly-undefined]
                if _r_usage:
                    try:
                        from core.cost_tracker import record_usage

                        record_usage(model=model_id, kind="text", usage=_r_usage, label="vision_fail")
                    except (ImportError, OSError, KeyError, TypeError) as e:
                        logger.debug("cost_tracker.record_usage(vision_fail) failed: %s: %s", type(e).__name__, e)
                continue
            except (OSError, TimeoutError) as e:
                last_reason = f"网络/超时: {e}"
                metrics.increment("fallback.vision_model")
                continue
            except RuntimeError as e:
                last_reason = f"上游错误: {e}"
                continue
            except (OSError, RuntimeError, KeyError, TypeError, ValueError) as e:  # noqa: BLE001 — 视觉通道不能让流式中断
                last_reason = f"未知错误: {e}"
                continue

        # 全部失败：返回可读错误，列出已尝试模型与最后原因
        return (
            f"(视觉理解失败 · 已尝试 {len(tried)} 个模型: {', '.join(tried)})\n"
            f"最后错误: {last_reason}\n"
            "建议：检查网络/供应商 Key，或用 /provider 切换视觉供应商后重试。"
        )

    def send_stream(self, user_text: str, image_url: str | None = None):
        """发送用户消息，流式 yield (kind, payload) 元组。

        - 多模态（有 image_url）：走 vision_client 整块输出，与主模型供应商解耦
        - tool 调度（pro）：流式累积 → 检测 tool_calls → 执行 engine → 喂回 → 二次流式
        - 纯文本：流式 yield ('text', 增量)
        """
        # #6 预算守卫：会话开始时检查今日花费，超限/接近上限仅提示不阻断
        try:
            from core.cost_tracker import check_budget

            warning = check_budget()
            if warning:
                yield ("info", warning)
        except (ImportError, OSError) as e:
            logger.debug("cost_tracker.check_budget failed: %s: %s", type(e).__name__, e)

        # ── 多模态分支：有图片 → 走独立视觉客户端 ──
        if image_url:
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            )
            content = self._vision_fallback(user_text, image_url)
            self.messages.append({"role": "assistant", "content": content})
            yield ("text", content)
            return

        # ── 纯文本分支：加 user message ──
        self.messages.append({"role": "user", "content": user_text})

        # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
        if self.ctx_mgr.needs_compression(self.messages):
            self.messages = self.ctx_mgr.compress(self.messages, self.client, self.model)

        tools = self.tools.definitions if self.supports_tools else None

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
                    continue  # 进入下一轮 tool loop

                # 无 tool_calls：检查是否流错误（需 fallback）还是正常收尾
                if _stream_error or self._is_stream_error(buffer):
                    if _loop == 0 and fallback_tried < len(fallback_chain):
                        # 通知 ProviderManager 标记当前供应商为 down
                        try:
                            from core.provider import get_provider_manager
                            mgr = get_provider_manager()
                            mgr.state.mark_down(mgr.state.active)
                        except Exception:
                            pass
                        yield ("info", f"模型 {_use_model} 连接中断，尝试 fallback...")
                        metrics.increment("fallback.text_model")
                        _stream_error_break = True
                        break  # 出 for _loop → while 继续
                    self.messages.append({"role": "assistant", "content": buffer})
                    return

                # 正常收尾
                self._finalize_outcome(_use_model, _last_usage)
                self.messages.append({"role": "assistant", "content": buffer})
                return

        # for _loop 结束：区分两种情况
        # 1. _stream_error_break=True → 流错误 fallback，回到 while 尝试下一档
        # 2. _stream_error_break=False → tool loop 溢出（模型正常工作但死循环），不 fallback
        if not _stream_error_break:
            yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
            self.messages.append({"role": "assistant", "content": buffer})
            self._record_outcome_promptlab()
            return

    # ── send_stream 的拆分子方法（行为不变，仅降低单方法复杂度）──
    # 以下三个方法由 send_stream 调用，分别处理：吃 delta / 执行工具 / 收尾计费。
    # 提取动机：原 send_stream 170 行三层嵌套（while fallback × for tool_loop × for delta），
    # 认知负荷极高（CodeBuddy/Claude/Codex 三方评分一致点名）。拆分后 send_stream 只剩控制流骨架。

    # 写操作类工具不参与跨轮去重缓存（避免吞掉用户对同一文件的连续修改意图）
    from core.constraints import WRITE_TOOLS

    _WRITE_TOOLS = WRITE_TOOLS

    def _consume_stream_delta(self, client: "CruxClient", model: str, tools):
        """吃一轮流式 delta，yield text chunks，return (buffer, tool_calls, stream_error, last_usage)。

        本方法是纯消费者：把 chat_stream 的增量帧累积成 buffer + tool_calls，
        并捕获最后一帧的 usage（用于计费）和 _finish="error" 标记。
        不修改 self.messages（写入由调用方负责）。

        yield from 此生成器时，返回值通过 StopIteration.value 传递。

        max_tokens 自适应：纯文本对话 2048 省 token；携带工具时调到 8192，
        避免 tool_call 的 arguments（如 create_html 的大段 HTML）被 max_tokens
        截断 → JSON 残缺 → write_file 写入"3字节" → agent 反复重试"中断"。
        """
        buffer, tool_calls = "", []
        stream_error = False
        last_usage = None
        kwargs = {}
        # 带工具时放大预算：tool_call arguments 计入输出 token，大文件生成需要空间
        max_tok = 8192 if tools else 2048
        if self.enable_thinking:
            kwargs["chat_template_kwargs"] = {"enable_thinking": True}
        for delta in client.chat_stream(
            model=model,
            messages=sanitize_tool_call_history(self.messages),
            tools=tools,
            max_tokens=max_tok,
            **kwargs,
        ):
            if "content" in delta and delta["content"]:
                chunk = delta["content"]
                buffer += chunk
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
                    span.set_attribute("result_chars", len(tool_result) if isinstance(tool_result, str) else -1)
                    metrics.increment("tool_calls")
                    metrics.timing("tool_call_ms", span.duration_ms())
                    # #5 Prompt Lab: 记录工具调用和错误
                    try:
                        from core.prompt_lab import get_prompt_lab

                        get_prompt_lab().record_tool_call()
                        if "[错误]" in str(tool_result) or "error" in str(tool_result).lower():
                            get_prompt_lab().record_tool_error()
                    except (ImportError, OSError):
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
        """正常收尾：成本追踪 + Prompt Lab outcome 记录。"""
        try:
            from core.cost_tracker import record_usage

            record_usage(model=model, kind="text", usage=last_usage, label="text_stream")
        except (ImportError, OSError) as e:
            logger.debug("cost_tracker.record_usage(text_stream) failed: %s: %s", type(e).__name__, e)
        self._record_outcome_promptlab()

    def _record_outcome_promptlab(self) -> None:
        """记录会话 outcome 到 Prompt Lab（可选模块，失败静默降级）。"""
        try:
            from core.prompt_lab import get_prompt_lab

            get_prompt_lab().record_outcome()
        except (ImportError, OSError):
            logger.debug('spectrum module not available')


def merge_tool_calls(fragments: list[dict]) -> list[dict]:
    """合并流式 tool_calls 分片（按 index 聚合 name + arguments 字符串）。

    OpenAI 流式把一个 tool_call 拆成多个 delta：
    [{"index":0,"id":"x","function":{"name":"generate_image","arguments":""}},
     {"index":0,"function":{"arguments":"{\\"pr"}}, ...]
    合并成完整 dict。

    契约扩展（输出不重复 DNA · 工具副作用层）：
    推理模型（DeepSeek V4 Pro 等）会跨"思考/回答"阶段对**同一逻辑工具**
    发出不同 `index` 的分片，导致下游 dispatch loop 对同一工具多次执行。
    故在 index 聚合后追加**语义去重**：相同 (name, normalized_arguments)
    只保留首个完整条目（含 id），其余丢弃。

    模块级函数：同步版 AsyncChatSession 共用此纯计算逻辑。
    """
    merged: dict[int, dict] = {}
    for frag in fragments:
        idx = frag.get("index", 0)
        slot = merged.setdefault(
            idx, {"id": frag.get("id", ""), "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if frag.get("id"):
            slot["id"] = frag["id"]
        fn = frag.get("function", {}) or {}
        if fn.get("name"):
            slot["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]

    ordered = [merged[k] for k in sorted(merged.keys())]

    # ── 语义去重：相同 (name, args-signature) 只保留首个 ──
    # signature 用归一化后的 arguments（去空白 + 排序 key），避免
    # {"a":1,"b":2} vs {"b":2,"a":1} 被误判为不同调用。
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for entry in ordered:
        name = (entry.get("function", {}).get("name") or "").strip()
        args_raw = entry.get("function", {}).get("arguments", "") or ""
        sig = (name, _normalize_tool_args(args_raw))
        if not name or sig in seen:
            continue  # 重复逻辑调用，丢弃
        seen.add(sig)
        deduped.append(entry)
    return deduped


# 向后兼容：注入 _merge_tool_calls 到已定义的 ChatSession 类上
ChatSession._merge_tool_calls = staticmethod(merge_tool_calls)


# ═══════════════════════════════════════════════════════════════
# 消息历史安全网 — 清洗孤儿 tool_calls
# ═══════════════════════════════════════════════════════════════


def sanitize_tool_call_history(messages: list[dict]) -> list[dict]:
    """清洗消息历史中的孤儿 tool_calls，保证发给 API 的消息始终合法。

    OpenAI 兼容 API 要求:含 tool_calls 的 assistant 消息后面必须有对应
    数量的 role=tool 消息（每个 tool_call_id 匹配一条）。
    若缺失配对 → API 返回 400 invalid_request_error。

    本函数扫描消息列表，对每个含 tool_calls 的 assistant 消息:
    1. 计算后续有多少条 role=tool 消息的 tool_call_id 在其 tool_calls 列表中
    2. 若不足（或为零）→ 剥离该 assistant 消息的 tool_calls 字段（保留 content）
    3. 同时剥离多余的 role=tool 消息（无对应 assistant 的 orphan tool 消息）

    是纯函数（不修改输入），返回清洗后的副本。
    同步/异步版 ChatSession 在发 API 前调用。
    """
    if not messages:
        return messages

    result = [dict(m) for m in messages]

    # 收集所有 assistant 消息中 tool_calls 的 id 集合
    # 同时找出 assistant→tool 的配对关系
    assistant_indices: list[int] = []
    for i, msg in enumerate(result):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_indices.append(i)

    # 对每个含 tool_calls 的 assistant，向后数配对的 tool 消息
    tool_ids_from_assistant: dict[int, set[str]] = {}
    for ai in assistant_indices:
        tc_ids = {tc.get("id", "") for tc in result[ai].get("tool_calls", []) if tc.get("id")}
        tool_ids_from_assistant[ai] = tc_ids

    # 扫描所有 tool 消息，记录它们配对到哪个 assistant
    tool_msg_indices: list[int] = []
    tool_msg_matched_to: dict[int, int] = {}  # tool index → assistant index
    unmatched_tool_indices: set[int] = set()

    for i, msg in enumerate(result):
        if msg.get("role") == "tool":
            tool_msg_indices.append(i)
            tcid = msg.get("tool_call_id", "")
            # 找最近的、包含此 id 的 assistant
            matched = False
            for ai in assistant_indices:
                if ai >= i:
                    break  # assistant 在 tool 之后，不可能配对
                if tcid in tool_ids_from_assistant.get(ai, set()):
                    tool_msg_matched_to[i] = ai
                    matched = True
                    break
            if not matched:
                unmatched_tool_indices.add(i)

    # 检测孤儿:含 tool_calls 的 assistant 消息配对不足
    orphan_assistants: set[int] = set()
    for ai in assistant_indices:
        tc_ids = tool_ids_from_assistant[ai]
        matched_tool_count = sum(1 for _, a in tool_msg_matched_to.items() if a == ai)
        if matched_tool_count < len(tc_ids):
            orphan_assistants.add(ai)

    # 构建 result:剥离孤儿 assistant 的 tool_calls,移除 unmatched tool 消息
    indices_to_remove = set(unmatched_tool_indices)
    for ai in orphan_assistants:
        # 剥离 tool_calls，保留 content
        result[ai] = {k: v for k, v in result[ai].items() if k != "tool_calls"}

    # 移除 unmatched tool 消息
    cleaned = [msg for i, msg in enumerate(result) if i not in indices_to_remove]
    return cleaned


# ═══════════════════════════════════════════════════════════════
# ChatSession._dispatch_tool — 放在 merge_tool_calls 之后（模块级函数下）
# 实际上这是 ChatSession 的方法，放回类内更清晰，但当前结构为
# merge_tool_calls 把 _dispatch_tool 包进去了。修复：将其作为独立函数
# 重新定义并注入类。为避免大范围缩进重排，直接在 merge_tool_calls 后
# 重新定义类方法并用赋值注入。
# ═══════════════════════════════════════════════════════════════


def _dispatch_tool_impl(self, name: str, args_json: str, *, confirmed: bool = False) -> tuple[str, list[tuple]]:
    """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

    副作用列表元素: ("info", str) / ("image", dict) / ("video", dict) / ("confirm", dict)

    与命令式路径对齐：均经过 SmartBrain Prompt 增强后再调引擎。
    支持生命周期 hook（PRE_TOOL_USE / POST_TOOL_USE）和高风险工具确认。

    Args:
        confirmed: 若 True，跳过高风险工具确认检查（用户已在 UI 层确认）。
            由 _run_tool_calls 在 confirm 通过后二次调用时传入。
    """
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        args = {}

    # ── 权限分级确认机制（核心：core/permission.py + core/constraints.py）──
    # PermissionManager 根据当前模式（YOLO/AUTO/MANUAL）决定是否需要确认。
    # confirmed=True 表示 UI 层已确认，直接执行，不再拦截。
    if not confirmed:
        from core.permission import get_permission_manager

        pm = get_permission_manager()
        if pm.needs_confirmation(name, args):
            confirm_data = {"tool": name, "args": args, "mode": pm.get_mode_name()}
            return "", [("confirm", confirm_data)]

    # ── PRE_TOOL_USE hook ──
    try:
        from core.hooks import HookType, hook_manager

        pre_evt = hook_manager.fire(HookType.PRE_TOOL_USE, data={"tool_name": name, "args": args})
        if pre_evt.stop_processing:
            return "工具调用被拦截（PRE_TOOL_USE hook）", []
    except (ImportError, OSError):
        pass  # hooks 模块不可用时静默降级

    prompt = args.get("prompt", "")
    image_url = args.get("image_url", "") or args.get("image", "")

    def _zhipu_media_client(self):
        """Get a zhipu provider client for free image/video generation."""
        try:
            from core.provider import get_provider_manager
            return get_provider_manager().create_client("zhipu")
        except (ImportError, RuntimeError):
            return self.media_client

    if name == "generate_image":
        side: list[tuple[str, str | dict]] = [("info", f"正在生成图片: {prompt}")]
        # Use zhipu client for cogview (free); fallback to media_client for agnes models
        gen_client = self._zhipu_media_client() if "cogview" in str(args.get("model","")) or not args.get("model") else self.media_client
        try:
            # Prompt 增强（与命令式 /img 路径对齐）
            # Brain 调用走当前供应商，可能因上游间歇故障失败（404/5xx 等）；
            # 增强失败不应阻断生成——退化为原始 prompt 继续。
            try:
                r = self.brain.enhance_image_prompt(prompt)
                fp = r.get("optimized_prompt", prompt)
                neg = r.get("negative_prompt", "") or None
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                # 增强失败不阻断生成——退化为原始 prompt 继续；记录原因便于排查上游间歇故障
                logger.debug("brain.enhance_image_prompt failed: %s: %s", type(e).__name__, e)
                fp, neg = prompt, None

            if image_url:
                from engines.image_to_image import ImageToImageEngine
                from utils import image_input
                url = image_input.load_image_as_url_or_data(image_url)
                i2i = ImageToImageEngine(gen_client)
                data = i2i.edit(prompt=fp, image_urls=url)
            else:
                t2i = TextToImageEngine(gen_client)
                data = t2i.generate(prompt=fp, negative_prompt=neg)
            side.append(("image", data))
            # #6 成本追踪：记录本次图像调用花费（失败时静默降级，不阻断生成）
            try:
                from core.cost_tracker import record_usage

                record_usage(model="agnes-image-2.1-flash", kind="image", label="generate_image", call_count=1)
            except (ImportError, OSError) as e:
                logger.debug("cost_tracker.record_usage(image) failed: %s: %s", type(e).__name__, e)
            return f"图片已生成并保存: {data.get('local_path', '')}", side
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            return f"图片生成失败: {e}", side

    if name == "generate_video":
        side: list[tuple[str, str | dict]] = [("info", f"正在生成视频（可能需几分钟）: {prompt}")]
        try:
            # Prompt 增强（与命令式 /video 路径对齐）
            # Brain 调用可能因上游间歇故障失败，增强失败不回退为原始 prompt 继续
            try:
                r = self.brain.enhance_video_prompt(prompt)
                fp = r.get("optimized_prompt", prompt)
                neg = r.get("negative_prompt", "") or None
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                # Brain 调用可能因上游间歇故障失败，增强失败不回退为原始 prompt 继续
                logger.debug("brain.enhance_video_prompt failed: %s: %s", type(e).__name__, e)
                fp, neg = prompt, None
            w, h = 1152, 768

            if image_url:
                # 图生视频路径
                from utils import image_input

                url = image_input.load_image_as_url_or_data(image_url)
                data = self.vid.image_to_video(
                    prompt=fp, image_url=url, width=w, height=h, negative_prompt=neg, timeout=120.0
                )
            else:
                data = self.vid.text_to_video(prompt=fp, width=w, height=h, negative_prompt=neg, timeout=120.0)

            side.append(("video", data))
            # #6 成本追踪：视频调用按次计费（较贵），记录花费供 /cost 查询
            try:
                from core.cost_tracker import record_usage

                record_usage(model="agnes-video-v2.0", kind="video", label="generate_video", call_count=1)
            except (ImportError, OSError) as e:
                logger.debug("cost_tracker.record_usage(video) failed: %s: %s", type(e).__name__, e)
            # 检测超时状态
            if data.get("status") == "timeout":
                vid = data.get("video_id", "")
                pct = data.get("progress", 0)
                return (f"视频生成超时（进度 {pct:.0f}%），请稍后用 video_id={vid} 查询状态"), side
            return f"视频已生成: {data.get('local_path', '')}", side
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            return f"视频生成失败: {e}", side

    if name == "multi_agent":
        goal = args.get("goal", "")
        side: list[tuple[str, str | dict]] = [("info", f"正在启动多智能体协调: {goal}")]
        try:
            from core.multi_agent import coordinate

            def _tool_exec(tool, tool_args):
                if self.tools.has(tool):
                    return self.tools.execute(tool, tool_args)
                return f"[multi_agent] 工具 {tool} 不可用"

            result = coordinate(goal, _tool_exec)
            summary = (
                f"多智能体协调完成: {result['tasks_done']}/{result['tasks_total']} 任务成功, 耗时 {result['elapsed']}s"
            )
            if result["tasks_failed"]:
                summary += f", {result['tasks_failed']} 失败"
            return summary, side
        except (RuntimeError, OSError, ValueError) as e:
            return f"多智能体协调失败: {e}", side

    # 外部工具（tools.json 中定义）→ 通过 ToolRegistry 执行
    if self.tools.has(name):
        # 中间状态可见：耗时工具先提示
        from core.constraints import LONG_RUNNING_TOOLS

        _LONG_RUNNING = LONG_RUNNING_TOOLS
        side: list[tuple[str, str | dict]] = []
        if name in _LONG_RUNNING:
            side.append(("info", f"正在执行 {name}..."))
        result = self.tools.execute(name, args)

        # POST_TOOL_USE hook：验证 / 回滚 / 学习
        try:
            from core.hooks import HookType, hook_manager

            # NEW (#4): 标记 error key，供反思引擎优先分析失败序列
            is_error = isinstance(result, str) and result.startswith("[错误]")
            post_evt = hook_manager.fire(
                HookType.POST_TOOL_USE,
                data={"tool_name": name, "args": args, "result": result, "error": is_error},
            )
            # hook 可能改写 result（如追加语法错误提示）
            if isinstance(post_evt.result, str) and post_evt.result:
                result = post_evt.result
        except (ImportError, OSError):
            logger.debug('spectrum module not available')

        side.append(("info", f"工具 {name} 执行完成"))
        return result, side

    return f"未知工具: {name}", []


# 注入到 ChatSession
ChatSession._dispatch_tool = _dispatch_tool_impl
