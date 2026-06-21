"""基础设施 Mixin：输入/渲染/选择/分发。被所有其他 Mixin 依赖。

包含: 多行输入、评分记忆、尺寸/比例/时长选择、路径文本分离、
模式提示、模型配置加载、命令分发表、流式渲染。"""

import re
from typing import TYPE_CHECKING

from rich.prompt import Prompt

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from core.config import (VIDEO_ASPECT_RATIOS, IMAGE_SIZES,
                          VIDEO_DURATION_MAP, VALID_NUM_FRAMES)
from utils import history, templates, memory
from ui.display import (console, show_image_result, show_video_result,
                         show_warning,
                         show_info)
from ui.render import StreamingRenderer

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ['SharedMixin']



class SharedMixin:
    # 类级复用 prompt_toolkit session
    _prompt_session = None

    # Dispatch 返回值标记
    _DISPATCH_OK = True
    _DISPATCH_UNKNOWN = None
    _DISPATCH_EXIT = "EXIT"

    # 延迟构建的 dispatch table
    _dispatch_table: dict | None = None


    @classmethod
    def _prompt_user(cls, label: str) -> str:
        """支持换行的用户输入。

        Enter → 发送
        Alt+Enter → 换行
        Ctrl+J → 换行
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

            style = Style.from_dict({
                "prompt": "cyan bold",
            })
            cls._prompt_session = PromptSession(
                key_bindings=kb,
                style=style,
                multiline=False,
            )

        return cls._prompt_session.prompt([("class:prompt", label)])

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
        ch = Prompt.ask("选择", choices=[str(i) for i in range(1, len(keys)+1)], default="1")
        return list(VIDEO_ASPECT_RATIOS.values())[int(ch)-1]

    @staticmethod
    def _pick_video_duration() -> tuple[int, int]:
        """选择视频时长，返回 (num_frames, frame_rate)"""
        console.print("[dim]可选视频时长 (fps=24):[/]")
        for i, nf in enumerate(VALID_NUM_FRAMES, 1):
            dur = VIDEO_DURATION_MAP[nf]["24fps"]
            console.print(f"  {i}. {nf} 帧 ≈ {dur}")
        ch = Prompt.ask("选择", choices=[str(i) for i in range(1, len(VALID_NUM_FRAMES)+1)], default="2")
        return VALID_NUM_FRAMES[int(ch)-1], 24

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
        path_pattern = r'(?:[A-Za-z]:[\\/][^\s:?*\"<>|]+|[~/][^\s:?*\"<>|]+)\.(?:png|jpg|jpeg|webp|gif|bmp)'
        paths = re.findall(path_pattern, raw, re.IGNORECASE)

        text = raw
        for p in paths:
            text = text.replace(p, ' ', 1)
        text = ' '.join(text.split()).strip()

        first_path = paths[0] if paths else raw.strip()
        return first_path, text

    def _read_multiline(self) -> str | None:
        """多行输入：逐行读取直到再次输入 \"\"\"

        首行 \"\"\" 已在上层被消费，本方法读后续行直到终止符。
        Returns: 合并后的字符串（None 表示取消）
        """
        console.print("[dim]已进入多行编辑，输入 \\\"\\\"\\\" 结束（Ctrl+C 取消）[/]")
        lines = []
        try:
            while True:
                line = Prompt.ask(f"[dim]  第{len(lines)+1}行[/]")
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
        """返回当前模式的提示标签，显示在输入提示符后"""
        hints = []
        if session.code_mode:
            hints.append("🔧代码")
        if session.agent_mode:
            hints.append("🤖智能体")
        if session.enable_thinking:
            hints.append("💭思考")
        return f" [{', '.join(hints)}]" if hints else ""

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

    def _stream_chat(self, session: "ChatSession", user: str):
        """流式渲染自然语言对话，处理 tool 调度的副作用透出。

        Ctrl+C 中断当前流式输出，回滚不完整的 assistant 消息后重新传播。

        渲染契约由 ui.render.StreamingRenderer 守护（"输出不重复"DNA 的代码层固化）：
        - transient 预览 + 单一落盘点（commit），保证每个字符只打印一次。
        - 副作用（info/image/video）是落盘边界：先固化文本，再展示副作用。
        详见 ui/render.py 的契约不变式与 tests/test_render.py / test_stream_chat_dedup.py。
        """
        # 副作用处理：渲染器在落盘边界后回调，本层负责 ChatSession 相关动作
        # （历史记录 / 超时警告）；渲染器本身只认识 console + 文本。
        def _on_image(kind: str, payload: object) -> None:
            img_data: dict = payload  # type: ignore[assignment]
            show_image_result(img_data)
            history.add_record("text_to_image", "chat", img_data.get("model", ""), img_data)

        def _on_video(kind: str, payload: object) -> None:
            vid_data: dict = payload  # type: ignore[assignment]
            if vid_data.get("status") == "timeout":
                show_warning(f"视频超时，进度 {vid_data.get('progress', 0):.0f}%")
            else:
                show_video_result(vid_data)
            history.add_record("text_to_video", "chat", "agnes-video-v2.0", vid_data)

        def _on_info(kind: str, payload: object) -> None:
            show_info(payload)  # type: ignore[arg-type]

        renderer = StreamingRenderer(
            console,
            side_effect_handlers={"info": _on_info, "image": _on_image, "video": _on_video},
        )
        renderer.start()
        try:
            for kind, payload in session.send_stream(user):
                if kind == "text":
                    renderer.append_text(payload)
                else:
                    renderer.run_side_effect(kind, payload)
        except KeyboardInterrupt:
            console.print()
            show_info("⏹ 已中断当前输出")
            if session.messages and session.messages[-1].get("role") == "assistant":
                session.messages.pop()
            renderer.stop()  # 中断路径：擦除 transient 浮层，不落盘残余（保持旧行为）
            raise
        finally:
            # 正常完成路径：stop() 擦除预览 + commit() 落盘末尾增量（无增量空操作）。
            # KeyboardInterrupt 在 raise 前已 stop()，此处再 stop()/commit() 是空安全操作。
            renderer.stop()
            renderer.commit()
