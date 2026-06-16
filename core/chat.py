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
from core.brain import SmartBrain
from core.tools import get_registry, ToolRegistry, AGENT_SYSTEM_PROMPT, BUILTIN_TOOLS
from core.skills import get_manager, SkillManager
from engines.text_to_image import TextToImageEngine
from engines.video import VideoEngine


CHAT_SYSTEM_PROMPT = """你是 Agnes 智能助手，基于 Agnes AI。你擅长：
- 日常问答、创意写作、知识解释、方案讨论
- 当用户明确想生成图片时，调用 generate_image 工具
- 当用户明确想生成视频/动画时，调用 generate_video 工具
- 普通对话不要调用任何工具

风格：简洁、中文优先、回答到位。不确定就问。"""

CODE_SYSTEM_PROMPT = """你是 Agnes 编程助手，基于 Agnes AI 2.0 Flash（256K 上下文）。
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
- 如需调用图片/视频工具，明确告知用户用 /img 或 /video 命令"""

# 工具定义已迁移到 core/tools.py (BUILTIN_TOOLS)，通过 ToolRegistry 统一管理
# 外部工具通过 tools.json 配置文件加载

# 命令别名 → 模型ID
MODEL_ALIASES = {
    "light": "agnes-1.5-flash",
    "pro": "agnes-2.0-flash",
}

# 模型ID → 能力说明
MODEL_INFO = {
    "agnes-1.5-flash": "1.5 Flash（多模态图片理解，快，无自动生成）",
    "agnes-2.0-flash": "2.0 Flash（深度思考 + AI自动生图/视频，无图片理解）",
}


class ChatSession:
    """多轮聊天会话，维护历史 + 混合调度"""

    def __init__(self, client: AgnesClient, default_model: str = "agnes-1.5-flash"):
        self.client = client
        self.brain = SmartBrain(client)
        self.t2i = TextToImageEngine(client)
        self.vid = VideoEngine(client)
        self.model = default_model
        self.enable_thinking = False
        self.code_mode = False
        self.agent_mode = False
        self.tools: ToolRegistry = get_registry()
        self.skills: SkillManager = get_manager()
        self.active_skill: str = ""
        self.messages: list[dict] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    @property
    def supports_tools(self) -> bool:
        """仅 2.0-flash 支持 tool calling 自动调度"""
        return self.model == "agnes-2.0-flash"

    def toggle_code_mode(self) -> bool:
        """切换代码助手模式，返回切换后的状态"""
        self.code_mode = not self.code_mode
        self.model = "agnes-2.0-flash"  # 代码模式强制 pro
        self.enable_thinking = True     # 代码模式自动开启 thinking
        prompt = CODE_SYSTEM_PROMPT if self.code_mode else CHAT_SYSTEM_PROMPT
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
            prompt = CHAT_SYSTEM_PROMPT
        prompt = self.skills.get_system_prompt(prompt)
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
        return self.agent_mode

    def load_skill(self, name: str) -> Optional[str]:
        """加载技能包，返回技能名称或 None"""
        self.skills.discover()
        skill = self.skills.load(name)
        if skill:
            self.active_skill = name
            self.model = "agnes-2.0-flash"
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
        self.active_skill = ""
        self.skills.unload()
        base = self._current_base_prompt()
        self.messages[0] = {"role": "system", "content": base}
        self.messages = [self.messages[0]]

    def _current_base_prompt(self) -> str:
        """获取当前模式的基础提示词"""
        if self.code_mode:
            return CODE_SYSTEM_PROMPT
        if self.agent_mode:
            return AGENT_SYSTEM_PROMPT + f"\n当前可用工具: {self.tools.tool_names}"
        return CHAT_SYSTEM_PROMPT

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    def send_stream(self, user_text: str, image_url: str | None = None):
        """发送用户消息，流式 yield (kind, payload) 元组。

        - 多模态（light + image_url）：走 chat_multimodal 整块输出（1.5 不支持流式 tool）
        - tool 调度（pro）：流式累积 → 检测 tool_calls → 执行 engine → 喂回 → 二次流式
        - 纯文本：流式 yield ('text', 增量)
        """
        # ── 多模态分支：light 模型 + 图片 ──
        if image_url and self.model == "agnes-1.5-flash":
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
            try:
                r = self.client.chat_multimodal(
                    text=user_text, image_url=image_url,
                    model=self.model, max_tokens=2048,
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

        # tool calling 循环（无 tool 时只跑一次）
        while True:
            buffer, tool_calls = "", []
            kwargs = {}
            if self.enable_thinking:
                kwargs["chat_template_kwargs"] = {"enable_thinking": True}
            for delta in self.client.chat_stream(
                model=self.model, messages=self.messages,
                tools=tools, max_tokens=2048, **kwargs,
            ):
                if "content" in delta and delta["content"]:
                    buffer += delta["content"]
                    yield ("text", delta["content"])
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
                    for eff_kind, eff_payload in side_effects:
                        yield (eff_kind, eff_payload)
                    self.messages.append({
                        "role": "tool", "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    })
                continue  # 二次请求：让模型基于 tool 结果生成总结

            # 无 tool_calls：收尾，存 assistant 回复
            self.messages.append({"role": "assistant", "content": buffer})
            return

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
            side = [("info", f"正在生成图片: {prompt}")]
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
            except Exception as e:
                return f"图片生成失败: {e}", side

        if name == "generate_video":
            side = [("info", f"正在生成视频（可能需几分钟）: {prompt}")]
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
            except Exception as e:
                return f"视频生成失败: {e}", side

        # 外部工具（tools.json 中定义）→ 通过 ToolRegistry 执行
        if self.tools.has(name):
            result = self.tools.execute(name, args)
            return result, [("info", f"工具 {name} 执行完成")]

        return f"未知工具: {name}", []
