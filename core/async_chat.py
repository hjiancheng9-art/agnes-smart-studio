"""AsyncChatSession — ChatSession 的 asyncio 原生异步对应物。

与 core/chat.py 同步版 ChatSession 对应，提供完全 async 的多轮对话能力。
所有阻塞点替换为 await / async for / asyncio.to_thread。

核心映射：
- AgnesClient            → AsyncAgnesClient
- SmartBrain             → AsyncSmartBrain
- TextToImageEngine      → AsyncTextToImageEngine
- ImageToImageEngine     → AsyncImageToImageEngine
- VideoEngine            → AsyncVideoEngine
- ToolRegistry.execute() → asyncio.to_thread(self.tools.execute, ...)

yield 协议（send_stream）与同步版完全一致：
    ("text", str)            文本增量
    ("info", str)            中间提示
    ("image", dict)          图片生成结果
    ("video", dict)          视频生成结果
    ("confirm", dict)        高风险工具确认
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator

from core.async_client import AsyncAgnesClient
from core.brain import AsyncSmartBrain
from core.context_tools import truncate_tool_result, truncate_messages
from core.observability import TraceContext, metrics
from core.chat import (
    AGENT_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    MAX_TOOL_LOOPS,
    _normalize_tool_args,
    merge_tool_calls,
)
from core.config import AGNES_VISION_MODEL
from core.provider import (
    get_provider_name,
    get_tool_calling_models,
    get_vision_models,
    model_supports_tools,
)
from core.tools import get_registry, ToolRegistry
from core.skills import get_manager, SkillManager
from engines.text_to_image import AsyncTextToImageEngine
from engines.image_to_image import AsyncImageToImageEngine
from engines.video import AsyncVideoEngine


__all__ = ["AsyncChatSession"]


class AsyncChatSession:
    """ChatSession 的 asyncio 原生异步版本。

    维护 messages 历史 + 混合调度（纯聊天 / tool calling / 多模态），
    所有 I/O 操作均为 async，可安全嵌入 asyncio event loop。
    """

    def __init__(
        self,
        client: AsyncAgnesClient,
        default_model: str = "agnes-1.5-flash",
        vision_client: AsyncAgnesClient | None = None,
        vision_model: str = AGNES_VISION_MODEL,
    ) -> None:
        self.client = client
        self.vision_client = vision_client or client
        self.vision_model = vision_model
        self.brain = AsyncSmartBrain(client)
        self.t2i = AsyncTextToImageEngine(client)
        self.i2i = AsyncImageToImageEngine(client)
        self.vid = AsyncVideoEngine(client)
        self.model = default_model
        self.enable_thinking = False
        self.code_mode = False
        self.mode = "chat"
        self.unlimited_tools = False
        self.agent_mode = False
        self.tools: ToolRegistry = get_registry()
        self.skills: SkillManager = get_manager()
        self.active_skill: str = ""
        self.messages: list[dict] = [{"role": "system", "content": self._build_system_prompt()}]

    # ── 属性 / 状态切换（纯计算，无需 async）─────────────────

    @property
    def supports_tools(self) -> bool:
        """支持 tool calling 自动调度的模型"""
        return model_supports_tools(self.model)

    def toggle_code_mode(self) -> bool:
        """切换代码助手模式（纯状态操作，无需 await）"""
        self.code_mode = not self.code_mode
        self.enable_thinking = self.code_mode
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        self.messages = [self.messages[0]]
        return self.code_mode

    def toggle_agent_mode(self) -> bool:
        """切换智能体模式（纯状态操作，无需 await）"""
        self.agent_mode = not self.agent_mode
        self.enable_thinking = True
        self.unlimited_tools = self.agent_mode
        if self.agent_mode:
            self.tools = get_registry()
            self.tools.load()
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

    def load_skill(self, name: str) -> str | None:
        """加载技能包（纯状态操作）"""
        self.skills.discover()
        skill = self.skills.load(name)
        if skill:
            self.active_skill = name
            self.enable_thinking = True
            pipeline = self.active_skill == "showrunner"
            comfyui = self.active_skill == "comfyui-bridge"
            if pipeline or comfyui:
                self.tools = get_registry()
                self.tools.load(pipeline=pipeline, comfyui=comfyui)
            base = self._current_base_prompt()
            prompt = self.skills.get_system_prompt(base)
            self.messages[0] = {"role": "system", "content": prompt}
            self.messages = [self.messages[0]]
            for t in self.skills.get_extra_tools():
                self.tools.register(
                    t["name"], t.get("description", ""),
                    t.get("parameters", {}),
                    lambda **kw: f"[{name}] 工具已执行",
                )
            return name
        return None

    def unload_skill(self):
        """卸载当前技能（纯状态操作）"""
        self.active_skill = ""
        self.skills.unload()
        self.tools = get_registry()
        self.tools.load(pipeline=False, comfyui=False)
        base = self._current_base_prompt()
        self.messages[0] = {"role": "system", "content": base}
        self.messages = [self.messages[0]]

    def _current_base_prompt(self) -> str:
        """获取当前模式的基础提示词"""
        if self.code_mode:
            return self._build_system_prompt()
        if self.agent_mode:
            return AGENT_SYSTEM_PROMPT + self._render_tool_categories()
        return self._build_system_prompt()

    def _render_tool_categories(self) -> str:
        """渲染工具分类为 system prompt 片段"""
        cats = self.tools.tool_categories
        if not cats:
            return f"\n当前可用工具: {self.tools.tool_names}"
        lines = ["\n\n## 当前可用工具（按分类）"]
        for cat_name, tools in cats.items():
            lines.append(f"- **{cat_name}**: {', '.join(tools)}")
        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        """构建动态系统提示词（纯计算，无 I/O）"""
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
        try:
            from core.rules import get_rules
            base += get_rules().inject_prompt()
        except (ImportError, OSError):
            pass
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
        return base

    def reset(self):
        """清空对话历史（保留 system）"""
        self.messages = [self.messages[0]]

    # ── 视觉 fallback（async I/O）──────────────────────────

    def _vision_model_chain(self) -> list[str]:
        """构建视觉模型 fallback 链"""
        chain: list[str] = []
        if self.vision_model:
            chain.append(self.vision_model)
        for mid in get_vision_models():
            if mid not in chain:
                chain.append(mid)
        return chain

    async def _vision_fallback(self, text: str, image_url: str) -> str:
        """视觉理解调用 + fallback 链（async 版）"""
        chain = self._vision_model_chain()
        tried: list[str] = []
        last_reason = ""
        for model_id in chain:
            tried.append(model_id)
            try:
                r = await self.vision_client.chat_multimodal(
                    text=text, image_url=image_url,
                    model=model_id, max_tokens=2048,
                )
                content = r["choices"][0]["message"]["content"] or ""
                return content
            except (KeyError, IndexError) as e:
                last_reason = f"返回格式异常: {e}"
                continue
            except (OSError, TimeoutError) as e:
                last_reason = f"网络/超时: {e}"
                continue
            except RuntimeError as e:
                last_reason = f"上游错误: {e}"
                continue
            except Exception as e:  # noqa: BLE001
                last_reason = f"未知错误: {e}"
                continue
        return (
            f"(视觉理解失败 · 已尝试 {len(tried)} 个模型: {', '.join(tried)})\n"
            f"最后错误: {last_reason}\n"
            "建议：检查网络/供应商 Key，或用 /provider 切换视觉供应商后重试。"
        )

    # ── 工具调度（async I/O）───────────────────────────────

    async def _dispatch_tool(self, name: str, args_json: str) -> tuple[str, list[tuple]]:
        """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

        与同步版 _dispatch_tool_impl 逻辑完全一致，仅将阻塞 I/O
        替换为 async 版本：
        - SmartBrain.enhance_*_prompt → await
        - Engine.generate/edit/text_to_video/image_to_video → await
        - ToolRegistry.execute → asyncio.to_thread
        """
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            args = {}

        # ── 高风险工具确认机制 ──
        _HIGH_RISK_TOOLS = {
            "git_add_commit", "git_push", "git_pr_create", "git_pr_merge",
        }
        _RISKY_ARGS_PATTERN = re.compile(r'\b(rm|delete|drop|truncate)\b', re.IGNORECASE)
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
            pass

        prompt = args.get("prompt", "")
        image_url = args.get("image_url", "") or args.get("image", "")

        if name == "generate_image":
            side: list[tuple[str, str | dict]] = [("info", f"正在生成图片: {prompt}")]
            try:
                r = await self.brain.enhance_image_prompt(prompt)
                fp = r.get("optimized_prompt", prompt)
                neg = r.get("negative_prompt", "") or None

                if image_url:
                    from utils import image_input
                    url = image_input.load_image_as_url_or_data(image_url)
                    data = await self.i2i.edit(prompt=fp, image_urls=url)
                else:
                    data = await self.t2i.generate(prompt=fp, negative_prompt=neg)
                side.append(("image", data))
                return f"图片已生成并保存: {data.get('local_path', '')}", side
            except (RuntimeError, OSError, ValueError) as e:
                return f"图片生成失败: {e}", side

        if name == "generate_video":
            side: list[tuple[str, str | dict]] = [("info", f"正在生成视频（可能需几分钟）: {prompt}")]
            try:
                r = await self.brain.enhance_video_prompt(prompt)
                fp = r.get("optimized_prompt", prompt)
                neg = r.get("negative_prompt", "") or None
                w, h = 1152, 768

                if image_url:
                    from utils import image_input
                    url = image_input.load_image_as_url_or_data(image_url)
                    data = await self.vid.image_to_video(
                        prompt=fp, image_url=url,
                        width=w, height=h, negative_prompt=neg, timeout=120.0)
                else:
                    data = await self.vid.text_to_video(
                        prompt=fp, width=w, height=h,
                        negative_prompt=neg, timeout=120.0)

                side.append(("video", data))
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
                from core.multi_agent import async_coordinate
                def _tool_exec(tool, tool_args):
                    if self.tools.has(tool):
                        return self.tools.execute(tool, tool_args)
                    return f"[multi_agent] 工具 {tool} 不可用"
                result = await async_coordinate(goal, _tool_exec)
                summary = (
                    f"多智能体协调完成: {result['tasks_done']}/{result['tasks_total']} 任务成功, "
                    f"耗时 {result['elapsed']}s"
                )
                if result["tasks_failed"]:
                    summary += f", {result['tasks_failed']} 失败"
                return summary, side
            except (RuntimeError, OSError, ValueError) as e:
                return f"多智能体协调失败: {e}", side

        # 外部工具（tools.json）→ asyncio.to_thread 包装
        if self.tools.has(name):
            _LONG_RUNNING = {"run_bash", "run_test", "run_python", "web_fetch", "web_search"}
            side: list[tuple[str, str | dict]] = []
            if name in _LONG_RUNNING:
                side.append(("info", f"正在执行 {name}..."))
            result = await asyncio.to_thread(self.tools.execute, name, args)

            # POST_TOOL_USE hook
            try:
                from core.hooks import hook_manager, HookType
                # NEW (#4): 标记 error key，供反思引擎优先分析失败序列
                is_error = isinstance(result, str) and result.startswith("[错误]")
                post_evt = hook_manager.fire(
                    HookType.POST_TOOL_USE,
                    data={"tool_name": name, "args": args, "result": result, "error": is_error},
                )
                if isinstance(post_evt.result, str) and post_evt.result:
                    result = post_evt.result
            except (ImportError, OSError):
                pass

            side.append(("info", f"工具 {name} 执行完成"))
            return result, side

        return f"未知工具: {name}", []

    # ── 流式对话（核心 async generator）────────────────────

    async def send_stream(self, user_text: str, image_url: str | None = None) -> AsyncIterator[tuple]:
        """发送用户消息，流式 yield (kind, payload) 元组。

        与同步版 ChatSession.send_stream 协议完全一致，
        仅将所有 I/O 替换为 async 版本。
        """
        # ── 多模态分支 ──
        if image_url:
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
            content = await self._vision_fallback(user_text, image_url)
            self.messages.append({"role": "assistant", "content": content})
            yield ("text", content)
            return

        # ── 纯文本分支 ──
        self.messages.append({"role": "user", "content": user_text})

        # Tier 1 轻量截断：对历史 messages 中超限单条做 head+tail 截断。
        # 零 API 调用、O(n) 纯计算——防止之前轮次未截断的历史消息撑爆上下文。
        self.messages = truncate_messages(self.messages)

        tools = self.tools.definitions if self.supports_tools else None

        _effective_max = MAX_TOOL_LOOPS * 2 if getattr(self, 'unlimited_tools', False) else MAX_TOOL_LOOPS
        buffer = ""
        _WRITE_TOOLS = {"write_file", "edit_file", "github_write_file",
                        "git_add_commit", "git_push", "run_bash"}
        _executed_signatures: set[tuple[str, str]] = set()
        _executed_cache: dict[tuple[str, str], str] = {}

        for _loop in range(_effective_max):
            buffer, tool_calls = "", []
            kwargs: dict = {}
            if self.enable_thinking:
                kwargs["chat_template_kwargs"] = {"enable_thinking": True}

            async for delta in self.client.chat_stream(
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
                for tc in merged:
                    fname = tc["function"]["name"]
                    fargs = tc["function"].get("arguments", "{}")

                    # 跨轮去重（与同步版逻辑一致）
                    sig = (fname, _normalize_tool_args(fargs))
                    if fname not in _WRITE_TOOLS and sig in _executed_signatures:
                        tool_result = _executed_cache.get(sig, "")
                    else:
                        with TraceContext("tool_call", tool_name=fname, call_id=tc.get("id", "")) as span:
                            tool_result, side_effects = await self._dispatch_tool(fname, fargs)
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
                        for se in side_effects:
                            yield se
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

            # 无 tool_calls：收尾
            self.messages.append({"role": "assistant", "content": buffer})
            # #5 Prompt Lab: 记录本次会话 outcome
            try:
                from core.prompt_lab import get_prompt_lab
                get_prompt_lab().record_outcome()
            except (ImportError, OSError):
                pass
            return

        # 超出最大轮次
        yield ("info", f"已达到最大工具调用轮次 ({_effective_max})，已中止。请尝试简化你的请求。")
        self.messages.append({"role": "assistant", "content": buffer})
        # #5 Prompt Lab: 超限也记录 outcome
        try:
            from core.prompt_lab import get_prompt_lab
            get_prompt_lab().record_outcome()
        except (ImportError, OSError):
            pass

