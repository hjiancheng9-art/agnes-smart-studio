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
"""

import json

from core.client import AgnesClient
from core.config import AGNES_VISION_MODEL
from core.brain import SmartBrain
from core.provider import (
    get_tool_calling_models,
    get_provider_name,
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

规则：
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
MAX_TOOL_LOOPS = 20


class ChatSession:
    """多轮聊天会话，维护历史 + 混合调度

    vision_client: 独立视觉客户端（始终指向 Agnes API），与主对话供应商解耦。
                   为 None 时退化为 self.client，向后兼容原有行为。
    vision_model:  视觉理解专用模型 ID，默认 agnes-1.5-flash。
    """

    def __init__(self, client: AgnesClient, default_model: str = "agnes-1.5-flash",
                 vision_client: AgnesClient | None = None, vision_model: str = AGNES_VISION_MODEL) -> None:
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
        self._rep_chunks = []
        self._rep_silenced = False
        self._rep_nudge_sent = False
        self.agent_mode = False
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
        """切换智能体模式，加载 tools.json 中定义的外部工具"""
        self.agent_mode = not self.agent_mode
        self.model = "agnes-2.0-flash"
        self.enable_thinking = True
        if self.agent_mode:
            self.tools = get_registry()  # 重新加载工具配置
            self.tools.load()
            prompt = AGENT_SYSTEM_PROMPT + f"\n当前可用工具: {self.tools.tool_names}"
        else:
            prompt = self._build_system_prompt()
        prompt = self.skills.get_system_prompt(prompt)
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
        return self.agent_mode

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
            self.model = "agnes-2.0-flash"
            self.enable_thinking = True

            # ── 根据技能类型启用对应工具集 ──
            pipeline = self.active_skill == "showrunner"
            comfyui = self.active_skill == "comfyui-bridge"

            if pipeline or comfyui:
                self.tools = get_registry()
                self.tools.load(pipeline=pipeline, comfyui=comfyui)

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
        self.tools.load(pipeline=False, comfyui=False)
        base = self._current_base_prompt()
        self.messages[0] = {"role": "system", "content": base}
        self.messages = [self.messages[0]]

    def _current_base_prompt(self) -> str:
        """获取当前模式的基础提示词（动态注入供应商和模型名）"""
        if self.code_mode:
            return self._build_system_prompt()
        if self.agent_mode:
            return AGENT_SYSTEM_PROMPT + f"\n当前可用工具: {self.tools.tool_names}"
        return self._build_system_prompt()

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
        return base

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    def send_stream(self, user_text: str, image_url: str | None = None):
        """发送用户消息，流式 yield (kind, payload) 元组。

        - 多模态（有 image_url）：走 vision_client 整块输出，与主模型供应商解耦
        - tool 调度（pro）：流式累积 → 检测 tool_calls → 执行 engine → 喂回 → 二次流式
        - 纯文本：流式 yield ('text', 增量)
        """
        # ── 多模态分支：有图片 → 走独立视觉客户端 ──
        if image_url:
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
            try:
                r = self.vision_client.chat_multimodal(
                    text=user_text, image_url=image_url,
                    model=self.vision_model, max_tokens=2048,
                )
                content = r["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError):
                content = "(多模态返回格式异常)"
            self.messages.append({"role": "assistant", "content": content})
            yield ("text", content)
            return

        # ── 纯文本分支：加 user message ──
        self.messages.append({"role": "user", "content": user_text})

        tools = self.tools.definitions if self.supports_tools else None

        # tool calling 循环（有上限，防止死循环）
        _effective_max = MAX_TOOL_LOOPS * 2 if getattr(self, 'unlimited_tools', False) else MAX_TOOL_LOOPS
        buffer = ""  # 循环外预绑定，保证超出最大轮次时引用安全
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
                    # Sliding window dedup: 80-char chunks, 2 repeats max
                    sample = chunk[:80] if len(chunk) >= 20 else ""
                    if sample:
                        self._rep_chunks.append(sample)
                        if len(self._rep_chunks) > 10:
                            self._rep_chunks.pop(0)
                        if self._rep_chunks.count(sample) >= 2:
                            if not self._rep_nudge_sent:
                                self._rep_nudge_sent = True
                                self.messages.append({"role": "system", "content": "[silent] You are repeating. Vary your output."})
                            self._rep_silenced = True
                            continue
                    self._rep_silenced = False
                    yield ("text", chunk)
                if "tool_calls" in delta and delta["tool_calls"]:
                    tool_calls.extend(delta["tool_calls"])

            if tool_calls:
                merged = self._merge_tool_calls(tool_calls)

                self.messages.append({
                    "role": "assistant", "content": buffer, "tool_calls": merged,
                })
                # 执行每个 tool，结果喂回 + 透出给用户
                for tc in merged:
                    fname = tc["function"]["name"]
                    fargs = tc["function"].get("arguments", "{}")
                    tool_result, side_effects = self._dispatch_tool(fname, fargs)
                    yield from side_effects
                    self.messages.append({
                        "role": "tool", "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    })
                continue  # 进入下一轮

            # 无 tool_calls：收尾，存 assistant 回复
            self.messages.append({"role": "assistant", "content": buffer})
            return

        # 超出最大轮次：强制收尾
        yield ("info", f"已达到最大工具调用轮次 ({MAX_TOOL_LOOPS})，已中止。请尝试简化你的请求。")
        self.messages.append({"role": "assistant", "content": buffer})

    @staticmethod
    def _merge_tool_calls(fragments: list[dict]) -> list[dict]:
        """合并流式 tool_calls 分片（按 index 聚合 name + arguments 字符串）。

        OpenAI 流式把一个 tool_call 拆成多个 delta：
        [{"index":0,"id":"x","function":{"name":"generate_image","arguments":""}},
         {"index":0,"function":{"arguments":"{\\"pr"}}, ...]
        合并成完整 dict。
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
        return [merged[k] for k in sorted(merged.keys())]

    def _dispatch_tool(self, name: str, args_json: str) -> tuple[str, list[tuple]]:
        """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

        副作用列表元素: ("info", str) / ("image", dict) / ("video", dict)

        与命令式路径对齐：均经过 SmartBrain Prompt 增强后再调引擎。
        """
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            args = {}
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
                # 检测超时状态
                if data.get("status") == "timeout":
                    vid = data.get("video_id", "")
                    pct = data.get("progress", 0)
                    return (f"视频生成超时（进度 {pct:.0f}%），"
                            f"请稍后用 video_id={vid} 查询状态"), side
                return f"视频已生成: {data.get('local_path', '')}", side
            except (RuntimeError, OSError, ValueError) as e:
                return f"视频生成失败: {e}", side

        # 外部工具（tools.json 中定义）→ 通过 ToolRegistry 执行
        if self.tools.has(name):
            result = self.tools.execute(name, args)
            return result, [("info", f"工具 {name} 执行完成")]

        return f"未知工具: {name}", []
