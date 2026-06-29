"""基础设施 Mixin：输入/渲染/选择/分发。被所有其他 Mixin 依赖。

包含: 多行输入、评分记忆、尺寸/比例/时长选择、路径文本分离、
模式提示、模型配置加载、命令分发表、流式渲染。"""

import re
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.prompt import Prompt

from core.config import IMAGE_SIZES, VALID_NUM_FRAMES, VIDEO_ASPECT_RATIOS, VIDEO_DURATION_MAP
from ui.display import show_info, show_warning
from ui.render import StreamingRenderer

# 注：show_image_result/show_video_result 的展示逻辑已下沉到
# core.async_render.default_side_effect_handlers（sync/async 共享单一来源），
# 故本模块不再直接 import 它们，避免死 import。
from ui.theme import console
from utils import history, memory, templates

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ["SharedMixin"]


class SharedMixin:
    # 类级复用 prompt_toolkit session
    _prompt_session = None

    # Dispatch 返回值标记
    _DISPATCH_OK = True
    _DISPATCH_UNKNOWN = None
    _DISPATCH_EXIT = "EXIT"

    # 延迟构建的 dispatch table
    _dispatch_table: dict | None = None

    # 图片粘贴目录（懒创建，一次）
    _paste_dir_ready = False

    @staticmethod
    def _ensure_paste_dir():
        import os
        if not SharedMixin._paste_dir_ready:
            os.makedirs("output/screenshots", exist_ok=True)
            SharedMixin._paste_dir_ready = True

    @classmethod
    def _paste_image_handler(cls, event) -> bool:
        """检测剪贴板是否有图片，有则保存并插入路径。返回 True 表示已处理。"""
        try:
            from PIL import ImageGrab

            img = ImageGrab.grabclipboard()
            if img is None:
                return False

            cls._ensure_paste_dir()

            if isinstance(img, list):
                # 文件路径列表（Windows 资源管理器复制文件）
                if not img:
                    return False
                text = " ".join(str(p) for p in img)
            else:
                # PIL Image 对象 — 保存为 PNG
                import time
                ts = int(time.time() * 1000)
                path = f"output/screenshots/paste_{ts}.png"
                img.save(path, "PNG")
                text = path

            event.current_buffer.insert_text(text)
            return True
        except Exception:
            return False

    @classmethod
    def _prompt_user(cls, label: str, session=None) -> str:
        """支持换行的用户输入 — Claude Code / Copilot CLI 风格。

        Enter → 发送
        Alt+Enter → 换行
        Ctrl+J → 换行
        Ctrl+V → 智能粘贴（图片自动保存为文件路径，文本正常粘贴）
        Ctrl+C → 中断

        底部 toolbar 显示键盘提示。
        """
        if cls._prompt_session is None:
            kb = KeyBindings()

            @kb.add("enter")
            def submit(event):
                event.current_buffer.validate_and_handle()

            @kb.add("escape", "enter")
            def alt_newline(event):
                event.current_buffer.insert_text("\n")

            @kb.add("c-j")
            def ctrl_j_newline(event):
                event.current_buffer.insert_text("\n")

            @kb.add("c-v")
            def paste_handler(event):
                # 图片优先：剪贴板有图片 → 保存为文件并插入路径
                if cls._paste_image_handler(event):
                    return
                # 无图片 → 默认文本粘贴
                data = event.app.clipboard.get_data()
                if data:
                    event.current_buffer.paste_clipboard_data(data)

            style = Style.from_dict(
                {
                    "prompt": "#58a6ff bold",
                    "input": "#e6edf3",
                }
            )
            cls._prompt_session = PromptSession(
                key_bindings=kb,
                style=style,
                multiline=False,
            )

        return cls._prompt_session.prompt([("class:prompt", label)])

    @classmethod
    async def _prompt_user_async(cls, label: str) -> str:
        """Async variant: prompt with full blocking wait."""
        return cls._prompt_user(label)

    @classmethod
    async def _poll_input_async(cls, label: str, timeout: float = 0.5) -> str | None:
        """Poll for input with timeout. Returns None if no input within timeout.

        Uses prompt_toolkit's async prompt with a timeout. The user can type
        while AI is generating; their input is captured and queued.
        """
        import asyncio
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(cls._prompt_user, label),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            return None

    def _ask_rating(self, record: dict, kind: str, prompt: str, data: dict):
        """生成后询问评分，记录偏好用于学习"""
        # 跟踪统计
        memory.track_generation(kind, prompt, data)

        # 学习偏好
        if data.get("size"):
            memory.record_preference("image_size", data["size"])
        if kind in ("text_to_video", "image_to_video", "pipeline") and data.get("num_frames"):
            memory.record_preference("num_frames", data["num_frames"])

        # 询问评分（可跳过）
        try:
            r = Prompt.ask("  [dim]评分 1-5 (5=完美, 回车跳过)[/]", default="")
            if r.strip().isdigit():
                rating = int(r)
                if 1 <= rating <= 5:
                    memory.rate_record(record["id"], rating)
                    # 高分案例自动进入进化库，优化下次增强效果
                    if rating >= 4 and data.get("prompt"):
                        # data.prompt 是增强后的提示词，prompt 参数是原始用户提示词
                        enhanced = data.get("prompt", "")
                        evo_kind = "video" if "video" in kind else "image"
                        memory.record_prompt_pair(prompt, enhanced, evo_kind, rating, record["id"])
                    if rating <= 2:
                        show_info("收到低评分，下次会调整策略")
                    elif rating >= 4:
                        history.toggle_favorite(record["id"])  # 高分自动收藏
        except (ValueError, TypeError, KeyError):
            pass  # 输入异常不阻断流程

    def _pick_size(self) -> str:
        console.print("[dim]可选图片尺寸:[/]")
        for k, v in IMAGE_SIZES.items():
            console.print(f"  {k}: {v}")
        s = Prompt.ask("选择比例", choices=list(IMAGE_SIZES.keys()), default="4:3")
        return IMAGE_SIZES[s]

    def _pick_video_aspect(self) -> tuple[int, int]:
        console.print("[dim]可选视频比例:[/]")
        keys = list(VIDEO_ASPECT_RATIOS.keys())
        for i, k in enumerate(keys, 1):
            w, h = VIDEO_ASPECT_RATIOS[k]
            console.print(f"  {i}. {k} ({w}x{h})")
        ch = Prompt.ask("选择", choices=[str(i) for i in range(1, len(keys) + 1)], default="1")
        return list(VIDEO_ASPECT_RATIOS.values())[int(ch) - 1]

    @staticmethod
    def _pick_video_duration() -> tuple[int, int]:
        """选择视频时长，返回 (num_frames, frame_rate)"""
        console.print("[dim]可选视频时长 (fps=24):[/]")
        for i, nf in enumerate(VALID_NUM_FRAMES, 1):
            dur = VIDEO_DURATION_MAP[nf]["24fps"]
            console.print(f"  {i}. {nf} 帧 ≈ {dur}")
        ch = Prompt.ask("选择", choices=[str(i) for i in range(1, len(VALID_NUM_FRAMES) + 1)], default="2")
        return VALID_NUM_FRAMES[int(ch) - 1], 24

    def _pick_template(self) -> str | None:
        tpls = templates.list_templates()
        if not tpls:
            return None
        console.print("[dim]可用风格模板:[/]")
        for i, t in enumerate(tpls, 1):
            console.print(f"  {i}. {t}")
        console.print("  0. 不使用模板")
        ch = Prompt.ask("选择模板", default="0")
        if ch == "0":
            return None
        idx = int(ch) - 1
        return tpls[idx] if 0 <= idx < len(tpls) else None

    @staticmethod
    def _extract_path_and_text(raw: str) -> tuple[str, str]:
        """从混合输入中分离文件路径和纯文本

        用户粘贴时可能把路径和描述黏在一起，例如:
          "C:\\foo\\bar.png角色骑上摩托车"
          "C:\\foo\\a.pngC:\\foo\\b.png"
        返回: (第一个有效路径, 去除路径后的纯文本)
        """
        # 匹配 Windows/Unix 文件路径（含中文、空格）
        path_pattern = r"(?:[A-Za-z]:[\\/][^\s:?*\"<>|]+|[~/][^\s:?*\"<>|]+)\.(?:png|jpg|jpeg|webp|gif|bmp)"
        paths = re.findall(path_pattern, raw, re.IGNORECASE)

        text = raw
        for p in paths:
            text = text.replace(p, " ", 1)
        text = " ".join(text.split()).strip()

        first_path = paths[0] if paths else raw.strip()
        return first_path, text

    def _read_multiline(self) -> str | None:
        """多行输入：逐行读取直到再次输入 \"\"\"

        首行 \"\"\" 已在上层被消费，本方法读后续行直到终止符。
        Returns: 合并后的字符串（None 表示取消）
        """
        console.print('[dim]已进入多行编辑，输入 \\"\\"\\" 结束（Ctrl+C 取消）[/]')
        lines = []
        try:
            while True:
                line = Prompt.ask(f"[dim]  第{len(lines) + 1}行[/]")
                stripped = line.strip()
                if stripped == '"""':
                    break
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            console.print()
            show_info("已取消多行输入")
            return None
        if not lines:
            return None
        return "\n".join(lines)

    @staticmethod
    def _mode_hint(session: "ChatSession") -> str:
        """返回提示符文本，用作 prompt_toolkit 输入提示。

        格式: ``model_name › ``  或  ``⚡ model_name › ``（Code 模式）
        prompt_toolkit 不认 Rich markup，返回纯文本。
        参考 Claude Code 的简洁提示风格。
        """
        model = getattr(session, "model", "") or ""
        try:
            from core.provider import get_model_info

            info = get_model_info(model)
            label = info.name if info and info.name != model else model
        except Exception:
            label = model

        # 模式前缀图标（纯 Unicode，兼容 prompt_toolkit）
        prefix = ""
        if getattr(session, "code_mode", False):
            prefix = "⚡ "
        elif getattr(session, "agent_mode", False):
            prefix = "◈ "

        return f"{prefix}{label} › "

    def _get_dispatch_table(self) -> dict:
        """构建/缓存命令分发表。"""
        if self._dispatch_table is None:
            from core.commands import build_dispatch_table

            self._dispatch_table = build_dispatch_table()
        return self._dispatch_table

    def _dispatch_command(self, cmd: str, arg: str, session) -> object:
        """表驱动命令分发。返回 DISPATCH_OK / DISPATCH_UNKNOWN / DISPATCH_EXIT。"""
        table = self._get_dispatch_table()
        entry = table.get(cmd)
        if entry is None:
            return self._DISPATCH_UNKNOWN

        handler_name, cmd_def = entry
        method = getattr(self, handler_name, None)
        if method is not None:
            # help 命令需要额外参数
            if handler_name == "_chat_help_inline":
                method(session, show_all=(cmd == "all"))
            else:
                method(session, arg)
            return self._DISPATCH_OK

        return self._DISPATCH_UNKNOWN

    def _prepare_chat_renderer(self, session: "ChatSession", user: str) -> StreamingRenderer:
        """构造流式渲染器 + 智能路由。

        渲染/执行分离（Phase 5）后，本方法是同步/异步两条接入点
        （`_stream_chat` / `_stream_async_chat`）共享的"流开始前"动作：
        - 构造带默认副作用 handler 的 StreamingRenderer
        - 智能路由：分析 user 输入，自动切到最优模型/供应商

        返回**已构造但未 start**的 renderer —— start()/stop()/commit() 的生命周期
        交给调用方。
        """
        from core.async_render import default_side_effect_handlers

        renderer = StreamingRenderer(
            console,
            side_effect_handlers=default_side_effect_handlers(),
        )

        # 智能路由：分析用户输入，自动切到最优模型/供应商
        from core.router import apply, route

        decision = route(user, session)
        if decision.profile.value != "skip" and decision.model_id:
            apply(decision, session)
            if decision.reason:
                from ui.badges import print_route_reason
                print_route_reason(decision.reason)

        return renderer

    def _stream_chat(self, session: "ChatSession", user: str):
        """流式渲染自然语言对话，处理 tool 调度的副作用透出。

        Ctrl+C 中断当前流式输出，回滚不完整的 assistant 消息后重新传播。

        渲染契约由 ui.render.StreamingRenderer 守护（"输出不重复"DNA 的代码层固化）：
        - transient 预览 + 单一落盘点（commit），保证每个字符只打印一次。
        - 副作用（info/image/video）是落盘边界：先固化文本，再展示副作用。
        详见 ui/render.py 的契约不变式与 tests/test_render.py / test_stream_chat_dedup.py。

        渲染/执行分离（Phase 5）：流的消费 + 异常路径收尾下沉到
        core.async_render.render_session_stream，与 async 版 `_stream_async_chat`
        共享同一份语义，不再在本方法内手写 for 循环与 try/except。
        """
        renderer = self._prepare_chat_renderer(session, user)

        def _on_permission_denied(e: PermissionError) -> None:
            # 用户拒绝了高风险工具确认：友好提示，不中止会话
            show_warning(f"🚫 {e}")

        def _on_interrupt(e: KeyboardInterrupt) -> None:
            console.print()
            show_info("⏹ 已中断当前输出")
            if session.messages and session.messages[-1].get("role") == "assistant":
                session.messages.pop()
            renderer.stop()  # 中断路径：擦除 transient 浮层，不落盘残余（保持旧行为）

        from core.async_render import render_session_stream

        renderer.start()
        try:
            render_session_stream(
                renderer,
                session.send_stream(user),
                on_permission_denied=_on_permission_denied,
                on_interrupt=_on_interrupt,
            )
        finally:
            renderer.stop()
            renderer.commit()

        # 回复完成后打印对话分隔线（输入提示前的视觉断点）
        from ui.badges import print_chat_separator
        print_chat_separator()

    async def _stream_async_chat(self, session, user: str):
        """AsyncChatSession 的流式渲染前端 —— `_stream_chat` 的 async 对应物。

        行为与 `_stream_chat` 完全一致（同一渲染契约、同一副作用 handler、
        同一异常路径），仅把"流的消费"从同步 `render_session_stream` 换成
        异步 `render_async_session_stream`。

        本接入点为 Phase 5 渲染/执行分离预留：它让 async runtime
        （MultiAgent asyncio 重写 / AsyncTaskExecutor / FastAPI web_api）
        可以用与同步 CLI **完全相同**的渲染前端消费 AsyncChatSession.send_stream，
        避免为 async 路径另写一套会与同步版漂移的渲染逻辑。

        调用方负责在 asyncio 事件循环内 await 本方法。同步 CLI 主循环
        （ui/cli.py）目前仍走 `_stream_chat`；本方法供 async runtime 直接 await。
        """
        from core.async_render import render_async_session_stream

        # AsyncChatSession 与 ChatSession 接口同构（_mode_hint/badge 头用相同属性）
        renderer = self._prepare_chat_renderer(session, user)

        def _on_permission_denied(e: PermissionError) -> None:
            show_warning(f"🚫 {e}")

        def _on_interrupt(e: KeyboardInterrupt) -> None:
            console.print()
            show_info("⏹ 已中断当前输出")
            if session.messages and session.messages[-1].get("role") == "assistant":
                session.messages.pop()
            renderer.stop()

        renderer.start()
        try:
            await render_async_session_stream(
                renderer,
                session.send_stream(user),
                on_permission_denied=_on_permission_denied,
                on_interrupt=_on_interrupt,
            )
        finally:
            renderer.stop()
            renderer.commit()
