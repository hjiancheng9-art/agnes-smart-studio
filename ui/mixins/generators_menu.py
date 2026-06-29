"""菜单生成组 Mixin：文生图/图生图/文生视频/图生视频/流水线/历史/模板。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

from ui.display import (
    show_history_table,
    show_image_result,
    show_info,
    show_pipeline_result,
    show_success,
    show_templates_list,
    show_video_result,
    show_warning,
)
from ui.theme import LAYOUT, console
from utils import history, image_input

if TYPE_CHECKING:
    from core.brain import SmartBrain
    from engines.image_to_image import ImageToImageEngine
    from engines.text_to_image import TextToImageEngine
    from engines.video import VideoEngine
    from engines.pipeline.workflows import PipelineOrchestrator

__all__ = ["GeneratorsMenuMixin"]


class GeneratorsMenuMixin:
    # Attributes provided by CruxCLI at runtime (multiple inheritance)
    brain: SmartBrain
    t2i: TextToImageEngine
    i2i: ImageToImageEngine
    vid: VideoEngine
    pipe: PipelineOrchestrator

    # Methods provided by SharedMixin (sibling in MRO)
    def _ask_rating(self, record: dict, kind: str, prompt: str, data: dict) -> None: ...
    def _pick_size(self) -> str: ...
    def _pick_template(self) -> str | None: ...
    def _pick_video_aspect(self) -> tuple[int, int]: ...

    @staticmethod
    def _pick_video_duration() -> tuple[int, int]: ...

    @staticmethod
    def _extract_path_and_text(raw: str) -> tuple[str, str]: ...

    def _t2i(self):
        prompt = Prompt.ask("[cyan]图片描述[/]")
        size = self._pick_size()
        enhance = Confirm.ask("Prompt增强?", default=True)
        style = self._pick_template() if enhance else None
        if enhance:
            show_info("优化提示词...")
            r = self.brain.enhance_image_prompt(prompt, style)
            prompt = r.get("optimized_prompt", prompt)
            show_info(f"优化后: {prompt[:60]}...")
        show_info("生成中...")
        data = self.t2i.generate(prompt=prompt, size=size)
        show_image_result(data)
        record = history.add_record("text_to_image", prompt, data.get("model", ""), data)
        self._ask_rating(record, "text_to_image", prompt, data)

    def _i2i(self):
        raw_prompt = Prompt.ask("[cyan]编辑描述[/]")
        raw_src = Prompt.ask("[cyan]图片路径/URL[/]")

        # 智能分离路径和文本
        path_from_prompt, clean_prompt = self._extract_path_and_text(raw_prompt)
        path_from_src, extra_text = self._extract_path_and_text(raw_src)

        if path_from_prompt != raw_prompt and path_from_src == raw_src:
            src = path_from_prompt
            prompt = clean_prompt or extra_text or raw_src
        elif path_from_src != raw_src and not clean_prompt:
            src = path_from_src
            prompt = extra_text or raw_prompt
        else:
            src = path_from_src
            prompt = clean_prompt or raw_prompt

        if extra_text and extra_text not in prompt:
            prompt = f"{prompt} {extra_text}".strip()

        url = image_input.load_image_as_url_or_data(src)
        size = self._pick_size()
        show_info("理解图片并生成编辑...")
        data = self.i2i.edit(prompt=prompt, image_urls=url, size=size)
        show_image_result(data)
        record = history.add_record("image_to_image", prompt, data.get("model", ""), data)
        self._ask_rating(record, "image_to_image", prompt, data)

    def _t2v(self):
        prompt = Prompt.ask("[cyan]视频描述[/]")
        w, h = self._pick_video_aspect()
        nf, fps = self._pick_video_duration()
        enhance = Confirm.ask("Prompt增强?", default=True)
        submit_only = Confirm.ask("仅提交(不等待)?", default=False)
        neg = ""
        if enhance:
            show_info("优化提示词...")
            r = self.brain.enhance_video_prompt(prompt)
            prompt = r.get("optimized_prompt", prompt)
            neg = r.get("negative_prompt", "")
        if submit_only:
            show_info("提交视频任务...")
            data = self.vid.submit_only(
                prompt=prompt, width=w, height=h, num_frames=nf, frame_rate=fps, negative_prompt=neg or None
            )
            display_id = data.get("video_id", "N/A")
            show_success(f"任务已提交! video_id: {display_id}")
            if display_id and display_id != "N/A":
                show_info(f"查询: crux query {display_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
            record = history.add_record("text_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "text_to_video", prompt, data)
        else:
            show_info("生成视频（可能需要几分钟）...")
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[{LAYOUT['bar_style']}]{{task.description}}"),
                BarColumn(style=LAYOUT["bar_style"], complete_style=LAYOUT["bar_complete_style"]),
                TextColumn("{task.percentage:>3.0f}%"),
                console=console,
            ) as prog:
                task = prog.add_task("生成中", total=100)

                def on_p(status, progress, data):
                    prog.update(task, completed=min(progress, 100), description=status)

                data = self.vid.text_to_video(
                    prompt=prompt,
                    width=w,
                    height=h,
                    num_frames=nf,
                    frame_rate=fps,
                    negative_prompt=neg or None,
                    on_progress=on_p,
                    timeout=120.0,
                )
            if data.get("status") == "timeout":
                show_warning(f"超时，当前进度 {data.get('progress', 0):.0f}%")
                query_id = data.get("video_id", "")
                if query_id:
                    show_info(f"继续查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，无法自动查询")
            else:
                show_video_result(data)
            record = history.add_record("text_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "text_to_video", prompt, data)

    def _i2v(self):
        raw_prompt = Prompt.ask("[cyan]视频描述[/]")
        raw_src = Prompt.ask("[cyan]图片路径/URL[/]")

        # 智能分离：用户可能把路径和描述黏在一起
        path_from_prompt, clean_prompt = self._extract_path_and_text(raw_prompt)
        path_from_src, extra_text = self._extract_path_and_text(raw_src)

        # 如果描述中包含了路径，优先用描述中的路径（用户可能是先粘贴了图片再写描述）
        if path_from_prompt != raw_prompt and path_from_src == raw_src:
            src = path_from_prompt
            prompt = clean_prompt or extra_text or raw_src
        elif path_from_src != raw_src and not clean_prompt:
            src = path_from_src
            prompt = extra_text or raw_prompt
        else:
            src = path_from_src
            prompt = clean_prompt or raw_prompt

        # 如果还有额外文本，追加到描述
        if extra_text and extra_text not in prompt:
            prompt = f"{prompt} {extra_text}".strip()

        url = image_input.load_image_as_url_or_data(src)
        w, h = self._pick_video_aspect()
        nf, fps = self._pick_video_duration()
        submit_only = Confirm.ask("仅提交(不等待)?", default=False)
        if submit_only:
            show_info("提交图生视频任务...")
            data = self.vid.submit_only(prompt=prompt, image=url, width=w, height=h, num_frames=nf, frame_rate=fps)
            display_id = data.get("video_id", "N/A")
            show_success(f"任务已提交! video_id: {display_id}")
            if display_id and display_id != "N/A":
                show_info(f"查询: crux query {display_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
            record = history.add_record("image_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "image_to_video", prompt, data)
        else:
            show_info("生成视频...")
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[{LAYOUT['bar_style']}]{{task.description}}"),
                BarColumn(style=LAYOUT["bar_style"], complete_style=LAYOUT["bar_complete_style"]),
                TextColumn("{task.percentage:>3.0f}%"),
                console=console,
            ) as prog:
                task = prog.add_task("生成中", total=100)

                def on_p(status, progress, data):
                    prog.update(task, completed=min(progress, 100), description=status)

                data = self.vid.image_to_video(
                    prompt=prompt,
                    image_url=url,
                    width=w,
                    height=h,
                    num_frames=nf,
                    frame_rate=fps,
                    on_progress=on_p,
                    timeout=120.0,
                )
            if data.get("status") == "timeout":
                show_warning(f"超时，当前进度 {data.get('progress', 0):.0f}%")
                query_id = data.get("video_id", "")
                if query_id:
                    show_info(f"继续查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，无法自动查询")
            else:
                show_video_result(data)
            record = history.add_record("image_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "image_to_video", prompt, data)

    def _pipeline(self):
        prompt = Prompt.ask("[cyan]一句话描述你的创意[/]")
        submit_only = Confirm.ask("仅提交(不等待)?", default=False)
        show_info("启动一站式流水线: 文本→图片→视频...")
        if submit_only:
            result = self.pipe.text_to_image_to_video(prompt, submit_only=True)
            vid_result = result.get("video", {})
            display_id = vid_result.get("video_id", "N/A")
            show_success(f"视频任务已提交! ID: {display_id}")
            query_id = vid_result.get("video_id", "")
            if query_id:
                show_info(f"查询: crux query {query_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[{LAYOUT['bar_style']}]{{task.description}}"),
                BarColumn(style=LAYOUT["bar_style"], complete_style=LAYOUT["bar_complete_style"]),
                console=console,
            ) as prog:
                task = prog.add_task("Processing", total=100)

                def on_img(data):
                    prog.update(task, completed=30, description="图片完成，转视频...")

                def on_vid(status, progress, data):
                    prog.update(task, completed=30 + int(progress * 0.7), description=status)

                result = self.pipe.text_to_image_to_video(prompt, on_image_done=on_img, on_video_progress=on_vid)
            if result.get("video", {}).get("status") == "timeout":
                show_warning(f"视频超时，进度 {result['video'].get('progress', 0):.0f}%")
                vid_result = result.get("video", {})
                query_id = vid_result.get("video_id", "")
                if query_id:
                    show_info(f"继续查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，无法自动查询")
            else:
                show_pipeline_result(result)
        record = history.add_record("pipeline", prompt, "multi", result)
        # 合并 image 和 video data 用于学习
        combined = {**result.get("image", {}), **result.get("video", {})}
        self._ask_rating(record, "pipeline", prompt, combined)

    def _hist(self):
        records = history.load_history()
        show_history_table(records)
        if records:
            rid = Prompt.ask("输入ID收藏/取消收藏(留空跳过)", default="")
            if rid:
                fav = history.toggle_favorite(rid)
                show_success(f"已{'收藏' if fav else '取消收藏'}")

    def _tmpl(self):
        show_templates_list()

    def _chat_agnes(self, session, arg: str):
        """Open Agnes multimodal generation menu (/agnes [t2i/i2i/t2v/i2v/pipeline])."""
        mode = arg.strip().lower()
        mode_map = {"t2i": self._t2i, "i2i": self._i2i, "t2v": self._t2v, "i2v": self._i2v, "pipeline": self._pipeline}
        if mode in mode_map:
            mode_map[mode]()
        else:
            show_info("Agnes 多模态生成:")
            console.print("  /agnes t2i  — 文生图（可选尺寸 + prompt增强）")
            console.print("  /agnes i2i  — 图生图/编辑/风格迁移")
            console.print("  /agnes t2v  — 文生视频（可选尺寸 + 时长）")
            console.print("  /agnes i2v  — 图生视频")
            console.print("  /agnes pipeline — 一键创作流水线")
            console.print("  [dim]不加参数 = 打开交互式菜单[/]")
            self._gen_menu() if not mode else None

    def _chat_comfy(self, session, arg: str):
        """ComfyUI bridge management (/comfy [connect/list/run/status])."""
        show_info("ComfyUI 工作流管理")
        console.print("  [dim]ComfyUI 桥接通过 tools.json 自动加载[/]")
        console.print("  [dim]可用工具: comfy_list_workflows, comfy_run_workflow, comfy_check_status[/]")
        console.print("  [dim]用法: 在智能体模式中直接对话即可调用[/]")
        console.print("  [dim]状态: 检查 MCP 连接 → /mcp tools comfy[/]")
