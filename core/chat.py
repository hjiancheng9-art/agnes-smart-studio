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

import json
import re

from core.client import CruxClient
from core.config import CRUX_VISION_MODEL
from core.brain import SmartBrain
from core.context_tools import truncate_tool_result, truncate_messages
from core.observability import TraceContext, metrics
from core.provider import (
    get_tool_calling_models,
    get_provider_name,
    get_vision_models,
)
from core.tools import get_registry, ToolRegistry, AGENT_SYSTEM_PROMPT
from core.skills import get_manager, SkillManager
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

# ── 模型元数据已迁移到 core/provider.py (MODEL_REGISTRY) ──
# 以下别名保留向后兼容，但新代码应使用 core.provider 的函数接口。
# 支持接口:
#   resolve_model_alias(name)      → 别名/名 → 模型ID
#   get_tool_calling_models()       → set[str] 支持 tool calling 的模型 ID
#   get_model_description(id)       → str 模型能力描述
#   get_provider_name(id)           → str 供应商名称
#   model_supports_tools(id)        → bool

MODEL_ALIASES = {"light": "agnes-1.5-flash", "pro": "agnes-2.0-flash"}

MODEL_INFO = {
    "agnes-1.5-flash": "1.5 Flash（多模态图片理解，快，无自动生成）",
    "agnes-2.0-flash": "2.0 Flash（深度思考 + AI自动生图/视频，无图片理解）",
    "deepseek-v4-pro": "DeepSeek V4 Pro（百万上下文，代码/推理，视觉走独立通道）",
    "Pro/moonshotai/Kimi-K2.6": "Kimi K2.6 via SiliconFlow（备选，视觉走独立通道）",
}

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

    def __init__(self, client: CruxClient, default_model: str = "agnes-1.5-flash",
                 vision_client: CruxClient | None = None, vision_model: str = CRUX_VISION_MODEL) -> None:
        self.client = client
        self.vision_client = vision_client or client  # 未指定时退化为主客户端（向后兼容）
        self.vision_model = vision_model
        self.brain = SmartBrain(client)
        self.t2i = TextToImageEngine(client)
        self.vid = VideoEngine(client)
        self.model = default_model
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
        self.messages = [self.messages[0]]  # 清空历史
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
                from core.hooks import register_reflection_hook
                from core.config import SETTINGS
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
        self.messages = [self.messages[0]]
        return self.agent_mode

    def toggle_browser(self) -> bool:
        """切换 Browser Companion 网页生成工具（8 个 provider：可灵/即梦/Runway/Luma/DALL-E/Gemini/Opal/Veo）。"""
        self.browser_enabled = not self.browser_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
        return self.browser_enabled

    def toggle_notebook(self) -> bool:
        """切换 Notebook (.ipynb) 工具（数据科学场景：打开/编辑/执行/保存 Jupyter notebook）。"""
        self.notebook_enabled = not self.notebook_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
        return self.notebook_enabled

    def toggle_audio(self) -> bool:
        """切换音频工具（edge-tts 旁白/BGM/SFX/混音，补齐 Showrunner 音轨缺口）。"""
        self.audio_enabled = not self.audio_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
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
            pipeline=pipeline, comfyui=comfyui,
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
            self.messages = [self.messages[0]]
            # 注入技能的额外工具
            for t in self.skills.get_extra_tools():
                self.tools.register(
                    t["name"], t.get("description", ""),
                    t.get("parameters", {}),
                    lambda **kw: f"[{name}] 工具已执行"
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
        self.messages = [self.messages[0]]

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
        """构建动态系统提示词，注入当前供应商和模型名 + 已启用规则"""
        provider = get_provider_name(self.model)
        template = CODE_SYSTEM_PROMPT if self.code_mode else CHAT_SYSTEM_PROMPT
        base = template.format(provider_name=provider, model_name=self.model)
        base += (
            "\n\n## 回答质量规范\n"
            "- 直接回答，不要重复用户的问题\n"
            "- 不要在 3 轮内重复相同内容\n"
            "- 不要逐字复述已有的上下文\n"
            "- 回答尽量在 2 段以内，简洁到位\n"
            "- 避免无意义的寒暄和套话"
        )
        # 注入已启用规则（与 get_provider_name 同模式，所有 mode 切换自动存活）
        try:
            from core.rules import get_rules
            base += get_rules().inject_prompt()
        except (ImportError, OSError):
            pass  # rules 模块不可用时静默降级
        # 注入技能市场概况 + 能力来源总览（让 AI 知道可用资源）
        try:
            from core.marketplace import get_marketplace
            base += "\n\n" + get_marketplace().summary()
        except (ImportError, OSError):
            pass
        try:
            from core.orchestra import get_orchestra
            base += "\n\n" + get_orchestra().summary()
        except (ImportError, OSError):
            pass
        # #5 注入 Prompt Lab 变体差异化指令
        try:
            from core.prompt_lab import get_prompt_lab
            base += get_prompt_lab().get_active_instructions()
        except (ImportError, OSError):
            pass
        # #7/#9 条件注入：browser / notebook / audio 工具使用说明
        if self.browser_enabled:
            base += (
                "\n\n## Browser Companion 网页生成\n"
                "你可以通过 browser_generate 在 8 个网页平台上全自动生成图片/视频：\n"
                "可灵(Kling) / 即梦(Jimeng) / Runway / Luma / DALL-E / Gemini / Opal / Veo\n"
                "优先用官方 API（需配置 API Key），无 Key 时自动降级到 Playwright 浏览器自动化。\n"
                "首次使用某个平台前需 browser_setup 登录一次，之后 session 自动保存。\n"
                "用 browser_providers 查看可用平台状态，browser_check 查询任务进度。"
            )
        if self.notebook_enabled:
            base += (
                "\n\n## Notebook 工具\n"
                "你可以操作 Jupyter notebook (.ipynb)：打开/编辑/执行代码单元格/保存。\n"
                "适合数据分析、实验记录、可视化等数据科学场景。"
            )
        if self.audio_enabled:
            base += (
                "\n\n## 音频工具\n"
                "你可以生成音频内容：tts_narration(文字转语音旁白)、generate_bgm(背景音乐)、\n"
                "generate_sfx(音效)、audio_mixdown(多轨混音)。\n"
                "所有输出保存到 output/audio/。补齐 Showrunner 旁白+BGM 音轨。"
            )
        return base

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    def _vision_model_chain(self) -> list[str]:
        """构建视觉模型 fallback 链（去重，保持顺序）。

        顺序：self.vision_model 优先 → 其余 vision-capable 模型按注册顺序补位。
        单一真相源是 provider.get_vision_models()；本方法只做去重和优先级排序。
        """
        chain: list[str] = []
        if self.vision_model:
            chain.append(self.vision_model)
        for mid in get_vision_models():
            if mid not in chain:
                chain.append(mid)
        return chain

    def _vision_fallback(self, text: str, image_url: str) -> str:
        """视觉理解调用 + fallback 链。

        依次尝试 _vision_model_chain() 中的模型，首个成功即返回其文本；
        全部失败时返回包含尝试列表的人类可读错误（不抛异常，保证流式不中断）。

        失败原因分类：
        - KeyError/IndexError: 返回 JSON 结构异常（供应商换了 schema）
        - OSError/TimeoutError: 网络/超时（最常见，触发下一档 fallback）
        - RuntimeError: 供应商上游错误
        """
        chain = self._vision_model_chain()
        tried: list[str] = []
        last_reason = ""
        for idx, model_id in enumerate(chain):
            tried.append(model_id)
            try:
                r = self.vision_client.chat_multimodal(
                    text=text, image_url=image_url,
                    model=model_id, max_tokens=2048,
                )
                content = r["choices"][0]["message"]["content"] or ""
                # #6 成本追踪：视觉调用按 token 计费（text kind），usage 来自 API 返回
                try:
                    from core.cost_tracker import record_usage
                    record_usage(model=model_id, kind="text",
                                 usage=r.get("usage"), label="vision")
                except (ImportError, OSError, KeyError, TypeError):
                    pass
                return content
            except (KeyError, IndexError) as e:
                last_reason = f"返回格式异常: {e}"
                continue  # 格式问题换模型也无济于事，但仍按链尝试
            except (OSError, TimeoutError) as e:
                last_reason = f"网络/超时: {e}"
                continue
            except RuntimeError as e:
                last_reason = f"上游错误: {e}"
                continue
            except Exception as e:  # noqa: BLE001 — 视觉通道不能让流式中断
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
        except (ImportError, OSError):
            pass

        # ── 多模态分支：有图片 → 走独立视觉客户端 ──
        if image_url:
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
            content = self._vision_fallback(user_text, image_url)
            self.messages.append({"role": "assistant", "content": content})
            yield ("text", content)
            return

        # ── 纯文本分支：加 user message ──
        self.messages.append({"role": "user", "content": user_text})

        # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
        # 零 API 调用、O(n) 纯计算——防止之前轮次未截断的历史消息撑爆上下文。
        # 新写入的 tool result 已由 cache-point 截断（task ②），此步兜底历史。
        self.messages = truncate_messages(self.messages)

        tools = self.tools.definitions if self.supports_tools else None

        # tool calling 循环（有上限，防止死循环）
        _effective_max = MAX_TOOL_LOOPS * 2 if getattr(self, 'unlimited_tools', False) else MAX_TOOL_LOOPS
        buffer = ""  # 循环外预绑定，保证超出最大轮次时引用安全
        # 本次 send_stream 已执行的工具签名 → 防止模型跨轮重发同一调用导致重复副作用。
        # 契约：输出不重复 DNA · 工具副作用层。配合 _merge_tool_calls 的单轮内去重，
        # 形成"单轮内 + 跨轮"双层去重。只对幂等性敏感的工具去重；写操作类工具
        # 不缓存（避免吞掉用户对同一文件的连续修改意图）。
        _WRITE_TOOLS = {"write_file", "edit_file", "github_write_file",
                        "git_add_commit", "git_push", "run_bash"}
        _executed_signatures: set[tuple[str, str]] = set()
        _executed_cache: dict[tuple[str, str], str] = {}
        for _loop in range(_effective_max):
            buffer, tool_calls = "", []
            kwargs = {}
            if self.enable_thinking:
                kwargs["chat_template_kwargs"] = {"enable_thinking": True}
            for delta in self.client.chat_stream(
                model=self.model, messages=self.messages,
                tools=tools, max_tokens=2048, **kwargs,
            ):
                if "content" in delta and delta["content"]:
                    chunk = delta["content"]
                    buffer += chunk
                    yield ("text", chunk)
                if "tool_calls" in delta and delta["tool_calls"]:
                    tool_calls.extend(delta["tool_calls"])

            if tool_calls:
                merged = merge_tool_calls(tool_calls)

                self.messages.append({
                    "role": "assistant", "content": buffer, "tool_calls": merged,
                })
                # 执行每个 tool，结果喂回 + 透出给用户
                for tc in merged:
                    fname = tc["function"]["name"]
                    fargs = tc["function"].get("arguments", "{}")
                    sig = (fname, _normalize_tool_args(fargs))
                    # 跨轮去重：非写工具且本会话已执行过 → 复用缓存，不重复 dispatch
                    if fname not in _WRITE_TOOLS and sig in _executed_signatures:
                        tool_result = _executed_cache.get(sig, "")
                        # 不 yield 副作用（用户已见过一次）
                    else:
                        with TraceContext("tool_call", tool_name=fname, call_id=tc.get("id", "")) as span:
                            tool_result, side_effects = self._dispatch_tool(fname, fargs)
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
                        yield from side_effects
                        if fname not in _WRITE_TOOLS:
                            _executed_signatures.add(sig)
                            # 缓存保留原始结果（高保真），跨轮复用时仍可重新截断
                            _executed_cache[sig] = tool_result
                    # 上下文窗口防护：智能压缩（抽取→LLM→截断三级路由），
                    # 防止大文件/长输出撑爆 LLM 上下文。原始结果仍在 cache 中。
                    from core.context_tools import compress_tool_result
                    self.messages.append({
                        "role": "tool", "tool_call_id": tc.get("id", ""),
                        "content": compress_tool_result(tool_result, self.client, self.model),
                    })
                continue  # 进入下一轮

            # 无 tool_calls：收尾，存 assistant 回复
            self.messages.append({"role": "assistant", "content": buffer})
            # #5 Prompt Lab: 记录本次会话 outcome
            try:
                from core.prompt_lab import get_prompt_lab
                get_prompt_lab().record_outcome()
            except (ImportError, OSError):
                pass
            return

        # 超出最大轮次：强制收尾
        yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
        self.messages.append({"role": "assistant", "content": buffer})
        # #5 Prompt Lab: 超限也记录 outcome
        try:
            from core.prompt_lab import get_prompt_lab
            get_prompt_lab().record_outcome()
        except (ImportError, OSError):
            pass

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
        slot = merged.setdefault(idx, {"id": frag.get("id", ""), "type": "function",
                                        "function": {"name": "", "arguments": ""}})
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
# ChatSession._dispatch_tool — 放在 merge_tool_calls 之后（模块级函数下）
# 实际上这是 ChatSession 的方法，放回类内更清晰，但当前结构为
# merge_tool_calls 把 _dispatch_tool 包进去了。修复：将其作为独立函数
# 重新定义并注入类。为避免大范围缩进重排，直接在 merge_tool_calls 后
# 重新定义类方法并用赋值注入。
# ═══════════════════════════════════════════════════════════════

def _dispatch_tool_impl(self, name: str, args_json: str) -> tuple[str, list[tuple]]:
    """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

    副作用列表元素: ("info", str) / ("image", dict) / ("video", dict) / ("confirm", dict)

    与命令式路径对齐：均经过 SmartBrain Prompt 增强后再调引擎。
    支持生命周期 hook（PRE_TOOL_USE / POST_TOOL_USE）和高风险工具确认。
    """
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        args = {}

    # ── 高风险工具确认机制 ──
    _HIGH_RISK_TOOLS = {
        "git_add_commit",   # 本地提交（可能误提交敏感内容）
        "git_push",         # 推送到远端
        "git_pr_create",    # 创建 PR（含推送）
        "git_pr_merge",     # 合并 PR（不可逆）
    }
    _RISKY_ARGS_PATTERN = re.compile(r'\b(rm|delete|drop|truncate)\b', re.IGNORECASE)
    # github_write_file: 推默认分支（main/master）视为高风险；feature 分支放行
    is_write_to_default_branch = (
        name == "github_write_file"
        and not args.get("branch", "").strip()
    )
    is_high_risk = (
        name in _HIGH_RISK_TOOLS
        or is_write_to_default_branch
        or (name == "run_bash" and _RISKY_ARGS_PATTERN.search(args.get("command", "")))
    )
    if is_high_risk:
        confirm_data = {"tool": name, "args": args}
        return "", [("confirm", confirm_data)]

    # ── PRE_TOOL_USE hook ──
    try:
        from core.hooks import hook_manager, HookType
        pre_evt = hook_manager.fire(HookType.PRE_TOOL_USE, data={"tool_name": name, "args": args})
        if pre_evt.stop_processing:
            return "工具调用被拦截（PRE_TOOL_USE hook）", []
    except (ImportError, OSError):
        pass  # hooks 模块不可用时静默降级

    prompt = args.get("prompt", "")
    image_url = args.get("image_url", "") or args.get("image", "")

    if name == "generate_image":
        side: list[tuple[str, str | dict]] = [("info", f"正在生成图片: {prompt}")]
        try:
            # Prompt 增强（与命令式 /img 路径对齐）
            r = self.brain.enhance_image_prompt(prompt)
            fp = r.get("optimized_prompt", prompt)
            neg = r.get("negative_prompt", "") or None

            if image_url:
                # 图生图/编辑路径
                from utils import image_input
                from engines.image_to_image import ImageToImageEngine
                url = image_input.load_image_as_url_or_data(image_url)
                i2i = ImageToImageEngine(self.client)
                data = i2i.edit(prompt=fp, image_urls=url)
            else:
                data = self.t2i.generate(prompt=fp, negative_prompt=neg)
            side.append(("image", data))
            # #6 成本追踪：记录本次图像调用花费（失败时静默降级，不阻断生成）
            try:
                from core.cost_tracker import record_usage
                record_usage(model="agnes-image-2.1-flash", kind="image",
                             label="generate_image", call_count=1)
            except (ImportError, OSError):
                pass
            return f"图片已生成并保存: {data.get('local_path', '')}", side
        except (RuntimeError, OSError, ValueError) as e:
            return f"图片生成失败: {e}", side

    if name == "generate_video":
        side: list[tuple[str, str | dict]] = [("info", f"正在生成视频（可能需几分钟）: {prompt}")]
        try:
            # Prompt 增强（与命令式 /video 路径对齐）
            r = self.brain.enhance_video_prompt(prompt)
            fp = r.get("optimized_prompt", prompt)
            neg = r.get("negative_prompt", "") or None
            w, h = 1152, 768

            if image_url:
                # 图生视频路径
                from utils import image_input
                url = image_input.load_image_as_url_or_data(image_url)
                data = self.vid.image_to_video(
                    prompt=fp, image_url=url,
                    width=w, height=h, negative_prompt=neg, timeout=120.0)
            else:
                data = self.vid.text_to_video(
                    prompt=fp, width=w, height=h,
                    negative_prompt=neg, timeout=120.0)

            side.append(("video", data))
            # #6 成本追踪：视频调用按次计费（较贵），记录花费供 /cost 查询
            try:
                from core.cost_tracker import record_usage
                record_usage(model="agnes-video-v2.0", kind="video",
                             label="generate_video", call_count=1)
            except (ImportError, OSError):
                pass
            # 检测超时状态
            if data.get("status") == "timeout":
                vid = data.get("video_id", "")
                pct = data.get("progress", 0)
                return (f"视频生成超时（进度 {pct:.0f}%），"
                        f"请稍后用 video_id={vid} 查询状态"), side
            return f"视频已生成: {data.get('local_path', '')}", side
        except (RuntimeError, OSError, ValueError) as e:
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
                f"多智能体协调完成: {result['tasks_done']}/{result['tasks_total']} 任务成功, "
                f"耗时 {result['elapsed']}s"
            )
            if result["tasks_failed"]:
                summary += f", {result['tasks_failed']} 失败"
            return summary, side
        except (RuntimeError, OSError, ValueError) as e:
            return f"多智能体协调失败: {e}", side

    # 外部工具（tools.json 中定义）→ 通过 ToolRegistry 执行
    if self.tools.has(name):
        # 中间状态可见：耗时工具先提示
        _LONG_RUNNING = {"run_bash", "run_test", "run_python", "web_fetch", "web_search"}
        side: list[tuple[str, str | dict]] = []
        if name in _LONG_RUNNING:
            side.append(("info", f"正在执行 {name}..."))
        result = self.tools.execute(name, args)

        # POST_TOOL_USE hook：验证 / 回滚 / 学习
        try:
            from core.hooks import hook_manager, HookType
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
            pass

        side.append(("info", f"工具 {name} 执行完成"))
        return result, side

    return f"未知工具: {name}", []


# 注入到 ChatSession
ChatSession._dispatch_tool = _dispatch_tool_impl
