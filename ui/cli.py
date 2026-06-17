"""Rich CLI交互界面"""

import os
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.live import Live
from rich.markdown import Markdown

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from core.client import AgnesClient, ContentPolicyError
from core.brain import SmartBrain
from core.config import SETTINGS, VIDEO_ASPECT_RATIOS, IMAGE_SIZES, VIDEO_DURATION_MAP, VALID_NUM_FRAMES, AGNES_VISION_MODEL, AGNES_VISION_BASE_URL
from engines.text_to_image import TextToImageEngine
from engines.image_to_image import ImageToImageEngine
from engines.video import VideoEngine
from pipeline.workflows import PipelineOrchestrator
from utils import history, templates, image_input, memory
from ui.display import (
    console, COLORS, show_image_result, show_video_result,
    show_pipeline_result, show_error, show_warning, show_success, show_info,
    show_history_table, show_templates_list,
)

LOGO = """[bold cyan]
  ___                     _   ____ _               _
 / _ \\ _ __   ___ _ __  (_) / ___| |__   ___  ___| | __
| | | | '_ \\ / _ \\ '_ \\ | || |   | '_ \\ / _ \\/ __| |/ /
| |_| | | | |  __/ | | || || |___| | | |  __/ (__|   <
 \\___/|_| |_|\\___|_| |_||_| \\____|_| |_|\\___|\\___|_|\\_\\[/][dim] v2.0[/]"""


class AgnesCLI:
    def __init__(self):
        self.client = AgnesClient()
        # 独立视觉客户端：始终指向 Agnes API，与主对话供应商解耦
        self.vision_client = AgnesClient(
            api_key=SETTINGS.api_key,
            base_url=AGNES_VISION_BASE_URL,
        )
        self.brain = SmartBrain(self.client)
        self.t2i = TextToImageEngine(self.client)
        self.i2i = ImageToImageEngine(self.client)
        self.vid = VideoEngine(self.client)
        self.pipe = PipelineOrchestrator(self.client)

    def close(self):
        self.client.close()
        self.vision_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── 多行输入支持 ───────────────────────────────

    _prompt_session = None  # 类级复用 prompt_toolkit session

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

    # ── 评分与记忆 ────────────────────────────────

    def _ask_rating(self, record: dict, kind: str, prompt: str, data: dict):
        """生成后询问评分，记录偏好用于学习"""
        # 跟踪统计
        memory.track_generation(kind, prompt, data)

        # 学习偏好
        if data.get("size"):
            memory.record_preference("image_size", data["size"])
        if kind in ("text_to_video", "image_to_video", "pipeline"):
            if data.get("num_frames"):
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
        except Exception:
            pass  # 输入异常不阻断流程

    def run(self):
        console.print(LOGO)
        while True:
            console.print()
            menu = Table(title="功能菜单", show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style=f"bold {COLORS['primary']}", width=4)
            menu.add_column("Name", style="white", width=16)
            menu.add_column("Desc", style="dim")
            for k, n, d in [
                ("1","文生图","从文字描述生成图片"),
                ("2","图生图","基于已有图片编辑/风格迁移"),
                ("3","文生视频","从文字描述生成视频"),
                ("4","图生视频","让图片动起来"),
                ("5","一站式","文本→图片→视频"),
                ("6","历史","查看生成历史"),
                ("7","模板","浏览风格模板"),
                ("8","聊天","与AI对话，可触发生图/视频"),
                ("0","退出",""),
            ]:
                menu.add_row(k, n, d)
            console.print(menu)

            ch = Prompt.ask("[cyan]选择[/]", choices=["0","1","2","3","4","5","6","7","8"], default="1")
            if ch == "0": break
            try:
                {"1": self._t2i, "2": self._i2i, "3": self._t2v,
                 "4": self._i2v, "5": self._pipeline, "6": self._hist, "7": self._tmpl,
                 "8": self._chat}[ch]()
            except ContentPolicyError as e:
                show_warning(str(e))
            except Exception as e:
                show_error(str(e))

        # 退出时显示记忆统计
        tips = memory.get_tips()
        if tips:
            console.print(f"\n[dim]{'─' * 40}[/]")
            for t in tips:
                console.print(f"  [dim]💡 {t}[/]")

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
        if not tpls: return None
        console.print("[dim]可用风格模板:[/]")
        for i, t in enumerate(tpls, 1):
            console.print(f"  {i}. {t}")
        console.print(f"  0. 不使用模板")
        ch = Prompt.ask("选择模板", default="0")
        if ch == "0": return None
        idx = int(ch) - 1
        return tpls[idx] if 0 <= idx < len(tpls) else None

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
        record = history.add_record("text_to_image", prompt, data.get("model",""), data)
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
        record = history.add_record("image_to_image", prompt, data.get("model",""), data)
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
            data = self.vid.submit_only(prompt=prompt, width=w, height=h, num_frames=nf, frame_rate=fps, negative_prompt=neg or None)
            display_id = data.get('video_id', 'N/A')
            show_success(f"任务已提交! video_id: {display_id}")
            if display_id and display_id != 'N/A':
                show_info(f"查询: python agnes_studio.py --video-id {display_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
            record = history.add_record("text_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "text_to_video", prompt, data)
        else:
            show_info("生成视频（可能需要几分钟）...")
            with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), BarColumn(), TextColumn("{task.percentage:>3.0f}%"), console=console) as prog:
                task = prog.add_task("生成中", total=100)
                def on_p(status, progress, data):
                    prog.update(task, completed=min(progress, 100), description=status)
                data = self.vid.text_to_video(prompt=prompt, width=w, height=h, num_frames=nf, frame_rate=fps, negative_prompt=neg or None, on_progress=on_p, timeout=120.0)
            if data.get("status") == "timeout":
                show_warning(f"超时，当前进度 {data.get('progress', 0):.0f}%")
                query_id = data.get('video_id', '')
                if query_id:
                    show_info(f"继续查询: python agnes_studio.py --video-id {query_id}")
                else:
                    show_warning("未返回 video_id，无法自动查询")
            else:
                show_video_result(data)
            record = history.add_record("text_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "text_to_video", prompt, data)

    @staticmethod
    def _extract_path_and_text(raw: str) -> tuple[str, str]:
        """从混合输入中分离文件路径和纯文本

        用户粘贴时可能把路径和描述黏在一起，例如:
          "C:\\foo\\bar.png角色骑上摩托车"
          "C:\\foo\\a.pngC:\\foo\\b.png"
        返回: (第一个有效路径, 去除路径后的纯文本)
        """
        import re
        # 匹配 Windows/Unix 文件路径（含中文、空格）
        path_pattern = r'(?:[A-Za-z]:[\\/][^\s:?*\"<>|]+|[~/][^\s:?*\"<>|]+)\.(?:png|jpg|jpeg|webp|gif|bmp)'
        paths = re.findall(path_pattern, raw, re.IGNORECASE)

        text = raw
        for p in paths:
            text = text.replace(p, ' ', 1)
        text = ' '.join(text.split()).strip()

        first_path = paths[0] if paths else raw.strip()
        return first_path, text

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
            display_id = data.get('video_id', 'N/A')
            show_success(f"任务已提交! video_id: {display_id}")
            if display_id and display_id != 'N/A':
                show_info(f"查询: python agnes_studio.py --video-id {display_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
            record = history.add_record("image_to_video", prompt, "agnes-video-v2.0", data)
            data["num_frames"] = nf
            self._ask_rating(record, "image_to_video", prompt, data)
        else:
            show_info("生成视频...")
            with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), BarColumn(), TextColumn("{task.percentage:>3.0f}%"), console=console) as prog:
                task = prog.add_task("生成中", total=100)
                def on_p(status, progress, data):
                    prog.update(task, completed=min(progress, 100), description=status)
                data = self.vid.image_to_video(prompt=prompt, image_url=url, width=w, height=h, num_frames=nf, frame_rate=fps, on_progress=on_p, timeout=120.0)
            if data.get("status") == "timeout":
                show_warning(f"超时，当前进度 {data.get('progress', 0):.0f}%")
                query_id = data.get('video_id', '')
                if query_id:
                    show_info(f"继续查询: python agnes_studio.py --video-id {query_id}")
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
            vid_result = result.get('video', {})
            display_id = vid_result.get('video_id', 'N/A')
            show_success(f"视频任务已提交! ID: {display_id}")
            query_id = vid_result.get('video_id', '')
            if query_id:
                show_info(f"查询: python agnes_studio.py --video-id {query_id}")
            else:
                show_warning("未返回 video_id，请检查任务响应")
        else:
            with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"), BarColumn(), console=console) as prog:
                task = prog.add_task("处理中", total=100)
                def on_img(data):
                    prog.update(task, completed=30, description="图片完成，转视频...")
                def on_vid(status, progress, data):
                    prog.update(task, completed=30 + int(progress * 0.7), description=status)
                result = self.pipe.text_to_image_to_video(prompt, on_image_done=on_img, on_video_progress=on_vid)
            if result.get("video", {}).get("status") == "timeout":
                show_warning(f"视频超时，进度 {result['video'].get('progress', 0):.0f}%")
                vid_result = result.get('video', {})
                query_id = vid_result.get('video_id', '')
                if query_id:
                    show_info(f"继续查询: python agnes_studio.py --video-id {query_id}")
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

    # ── 供应商自助选择 ──────────────────────────────────

    def _select_provider(self):
        """交互式供应商选择（多 Key 时弹出菜单，单 Key 自动激活）

        1. 扫描所有 providers，收集有 API Key 的
        2. 1 个外部供应商 → 自动激活
        3. ≥2 个外部供应商 → 弹出菜单让用户选择
        4. 0 个外部供应商 → 使用 Agnes

        Returns: (provider_id, model_id)
        """
        import json
        cfg = self._load_models_config()
        root = os.path.dirname(os.path.dirname(__file__))
        cfg_path = os.path.join(root, "models.json")

        providers = cfg.get("providers", {})

        # 收集所有有 Key 的供应商
        available = []
        for pid, p in providers.items():
            key_env = f"{pid.upper()}_API_KEY"
            api_key = p.get("api_key") or os.getenv(key_env)
            if api_key:
                model = p.get("models", {}).get("pro", "unknown")
                available.append((pid, p, model, api_key))

        if not available:
            # 没有任何 Key → Agnes
            p = providers.get("agnes", providers.get(list(providers.keys())[0], {}))
            model = p.get("models", {}).get("light", "agnes-1.5-flash")
            show_info("无外部供应商 Key，使用默认 Agnes light")
            return ("agnes", model)

        # 只有 Agnes → 直接用
        if len(available) == 1 and available[0][0] == "agnes":
            pid, p, model, _ = available[0]
            return (pid, model)

        # 过滤出非 Agnes 的外部供应商
        external = [(pid, p, m, k) for pid, p, m, k in available if pid != "agnes"]
        has_agnes = any(pid == "agnes" for pid, _, _, _ in available)

        if len(external) == 1:
            # 只有一个外部供应商 → 自动激活
            pid, p, model, api_key = external[0]
            self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
            return (pid, model)

        # ≥2 个外部供应商 → 弹出菜单
        console.print()
        table = Table(title="[bold cyan]选择主对话供应商[/]（视觉始终走 Agnes 独立通道）",
                       border_style=COLORS["primary"])
        table.add_column("#", style="bold cyan", width=3)
        table.add_column("供应商", style="white", width=16)
        table.add_column("模型", style="dim")
        table.add_column("说明", style="dim")

        choices = []
        idx = 1
        for pid, p, model, _ in available:
            label = f"{idx}"
            desc = ""
            if pid == "deepseek":
                desc = "百万上下文 · 代码/推理"
            elif pid == "siliconflow":
                desc = "Kimi-K2.6 · 备选链路"
            elif pid == "agnes":
                desc = "原生模型 · 轻量快速"
            table.add_row(label, p["name"], model, desc)
            choices.append((str(idx), pid, p, model))
            idx += 1

        console.print(table)
        console.print()

        choice = Prompt.ask(
            "[cyan]选择供应商[/]",
            choices=[c[0] for c in choices] + ["q"],
            default="1",
        )
        if choice == "q":
            show_info("已取消，使用默认 Agnes light")
            p = providers.get("agnes", {})
            return ("agnes", p.get("models", {}).get("light", "agnes-1.5-flash"))

        # 找到选中的供应商
        for num, pid, p, model in choices:
            if num == choice:
                if pid == "agnes":
                    return (pid, model)
                # 外部供应商需要激活
                key_env = f"{pid.upper()}_API_KEY"
                api_key = p.get("api_key") or os.getenv(key_env)
                self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
                return (pid, model)

        return ("agnes", "agnes-1.5-flash")

    def _activate_provider(self, pid, p, model, api_key, cfg, cfg_path):
        """激活指定供应商：切换 client 并写入 models.json"""
        from core.client import AgnesClient
        self.client.close()
        self.client = AgnesClient(api_key=api_key, base_url=p["base_url"])
        cfg["active"] = pid
        try:
            Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        from core.chat import MODEL_INFO
        cap = MODEL_INFO.get(model, pid)
        show_success(f"已激活 {p['name']} → {model}（{cap}）")

    # ── 聊天辅助方法 ──────────────────────────────────────

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

    # ── 聊天模式 ──────────────────────────────────────────

    def _chat(self):
        """聊天模式：多轮流式对话 + 命令式生成 + AI 自动调度（pro）
        
        按 models.json fallback.priority 自动探测可用供应商，
        主对话走优先供应商，视觉始终走 Agnes 独立通道。
        - 多行输入：首行输入 \"\"\" 进入，再输入 \"\"\" 结束
        - 中止操作：Ctrl+C 中断当前运行
        - 退出模式：/code、/agent 再次输入即切回，/exit 完全退出
        """
        from core.chat import ChatSession, MODEL_ALIASES, MODEL_INFO

        # 自助选择供应商（多 Key 时弹出菜单，单 Key 自动激活）
        active_provider, active_model = self._select_provider()

        console.print(Panel(
            "直接输入文字即可对话（流式输出）。\n"
            "命令: /help /model /img /video /vision /clear /exit\n"
            "技能: /skill load 视频|作图|写剧本|分镜|质检...\n"
            "换行: Alt+Enter / Ctrl+J 换行，Enter 发送\n"
            "图片: 直接粘贴图片路径即可自动识别\n"
            "提示: Ctrl+C 中止运行 · Ctrl+C 再次退出\n"
            f"默认模型: {active_model}（{MODEL_INFO.get(active_model, active_provider)}）\n"
            "视觉通道: 独立 Agnes · 图片理解始终可用",
            title=f"[{COLORS['accent']}]💬 聊天模式[/]",
            border_style=COLORS["accent"],
        ))

        session = ChatSession(self.client, vision_client=self.vision_client, vision_model=AGNES_VISION_MODEL)
        session.model = active_model
        # 用实际模型重建系统提示词（避免 init 用默认模型构建的过期提示词）
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        while True:
            try:
                raw = self._prompt_user(f"你 {self._mode_hint(session)}").strip()
            except (EOFError, KeyboardInterrupt):
                console.print()
                break
            if not raw:
                continue

            # ── 文本 \\n → 真实换行 ──
            if "\\n" in raw:
                raw = raw.replace("\\n", "\n")

            # ── 多行输入：\\\"\\\"\\\" 开头进入多行模式 ──
            if raw == '"""':
                user = self._read_multiline()
                if user is None:
                    continue
            else:
                user = raw

            # ── 斜杠命令（确定性，不过 LLM）──
            if user.startswith("/"):
                cmd, _, arg = user[1:].partition(" ")
                arg = arg.strip()
                if cmd in ("exit", "quit", "q"):
                    break
                elif cmd in ("help", "all"):
                    self._chat_help(session.model, session.enable_thinking, session.code_mode, show_all=(cmd == "all"))
                elif cmd == "model":
                    self._chat_switch_model(session, arg)
                elif cmd == "clear":
                    session.reset()
                    show_success("已清空对话历史")
                elif cmd == "img":
                    self._chat_generate(session, "image", arg)
                elif cmd == "video":
                    self._chat_generate(session, "video", arg)
                elif cmd == "vision":
                    self._chat_vision(session, arg)
                elif cmd == "thinking":
                    session.enable_thinking = not session.enable_thinking
                    state = "开" if session.enable_thinking else "关"
                    show_success(f"深度思考已{state}启（仅 pro 模型生效）")
                elif cmd == "code":
                    is_code = session.toggle_code_mode()
                    if is_code:
                        show_success("🔧 已进入代码助手模式（再输 /code 切回，Ctrl+C 中止运行）")
                    else:
                        show_success("已退出代码助手，回到普通聊天")
                elif cmd == "agent":
                    is_agent = session.toggle_agent_mode()
                    if is_agent:
                        cnt = len(session.tools.tool_names)
                        show_success(f"🤖 已进入智能体模式，加载了 {cnt} 个工具")
                        console.print(f"  [dim]工具: {', '.join(session.tools.tool_names[:8])}[/]")
                        console.print(f"  [dim]再输 /agent 退出 · Ctrl+C 中止运行[/]")
                    else:
                        show_success("已退出智能体模式，回到普通聊天")
                elif cmd == "tools":
                    names = session.tools.tool_names
                    if names:
                        console.print(f"[dim]已注册 {len(names)} 个工具:[/]")
                        for n in names:
                            console.print(f"  [cyan]{n}[/]")
                    else:
                        show_info("当前无可用工具，创建 tools.json 来添加")
                elif cmd == "skill":
                    self._chat_skill(session, arg)
                elif cmd == "plan":
                    self._chat_plan(session, arg)
                elif cmd == "sub":
                    self._chat_subagent(session, arg)
                elif cmd == "compress":
                    self._chat_compress(session)
                elif cmd == "project":
                    self._chat_project(session, arg)
                elif cmd == "team":
                    self._chat_team(session, arg)
                elif cmd == "deploy":
                    self._chat_deploy(session, arg)
                elif cmd == "todo":
                    self._chat_todo(session, arg)
                elif cmd == "commit":
                    self._chat_commit(session)
                elif cmd == "changelog":
                    self._chat_changelog(session, arg)
                elif cmd == "refactor":
                    self._chat_refactor(session, arg)
                elif cmd == "audit":
                    self._chat_audit(session, arg)
                elif cmd == "rules":
                    self._chat_rules(session, arg)
                elif cmd == "automate":
                    self._chat_automate(session, arg)
                elif cmd == "provider":
                    self._chat_provider(session, arg)
                elif cmd == "evolve":
                    self._chat_evolve(session)
                elif cmd == "know":
                    self._chat_knowledge(session, arg)
                elif cmd == "self":
                    self._self_diagnose(session, arg)
                else:
                    show_warning(f"未知命令 /{cmd}，输入 /help 查看")
                continue

            # ── 智能图片路由：检测到图片路径 → 自动走视觉通道 ──
            img_path, clean_text = self._extract_path_and_text(user)
            if img_path and img_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                self._chat_vision(session, user)
                continue

                    # ── 自然语言对话（流式）──
            try:
                self._stream_chat(session, user)
            except KeyboardInterrupt:
                console.print()
                show_info("已中止 · 按 Ctrl+C 退出聊天，或继续输入")
                # 回滚刚加进去的 user message
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()
            except Exception as e:
                show_error(f"对话出错: {e}")
                # 回滚刚加进去的 user message，避免历史污染
                if session.messages and session.messages[-1].get("role") == "user":
                    session.messages.pop()

    # ── 自诊断 ─────────────────────────────────


    def _self_diagnose(self, session: "ChatSession", arg: str):
        """工具自诊断 — 让工具检查自身健康、分析源码、发现并修复 bug

        用法:
            /self check  — 遍历所有 .py 文件进行语法检查
            /self files  — 树状打印项目目录结构
            /self health — 检测 API Key / Python版本 / 依赖 / 使用统计
            /self fix    — 将 core/engines 源码喂给 AI，让 AI 分析问题并提出修复方案
        """
        import os
        # 项目根目录 = ui 的上一级 = agnes-smart-studio/
        root = os.path.dirname(os.path.dirname(__file__))
        arg = arg.strip()

        # ── /self check：语法扫描 ──────────────────────
        # 遍历所有 .py 文件，用 Python 内置 ast 模块做语法解析
        # 如果解析失败 → 报告该文件有语法错误
        if arg == "check":
            import subprocess
            results = []
            for dp, _, files in os.walk(root):          # 递归遍历项目目录
                for f in files:
                    if f.endswith(".py"):               # 只检查 Python 文件
                        fp = os.path.join(dp, f)
                        try:
                            # 用独立进程执行 ast.parse，避免污染当前进程
                            subprocess.run(["python", "-c",
                                f"import ast; ast.parse(open({fp!r}, encoding='utf-8').read())"],
                                capture_output=True, timeout=5, check=True)
                        except subprocess.CalledProcessError:
                            # 语法错误 → 记录文件名（相对路径）
                            results.append(f"  ❌ {os.path.relpath(fp, root)}")
                        except Exception:
                            pass  # 超时等其他异常跳过
            if results:
                show_warning(f"发现 {len(results)} 个语法错误:")
                for r in results:
                    console.print(r)
            else:
                show_success("所有 Python 文件语法检查通过")

        # ── /self files：项目结构展示 ──────────────────
        # 用 rich.Tree 树形打印 agnes-smart-studio/ 下的目录和文件
        elif arg == "files":
            from rich.tree import Tree
            tree = Tree("[cyan]agnes-smart-studio[/]")
            for item in sorted(os.listdir(root)):
                if item.startswith(".") or item == "__pycache__":
                    continue  # 跳过隐藏文件和缓存
                path = os.path.join(root, item)
                if os.path.isdir(path):
                    branch = tree.add(f"[cyan]{item}/[/]")
                    for sub in sorted(os.listdir(path)):
                        if not sub.startswith("."):
                            branch.add(f"[dim]{sub}[/]")
                else:
                    tree.add(f"[white]{item}[/]")
            console.print(tree)

        # ── /self health：健康度诊断 ──────────────────
        # 检查项目运行所需的四个关键条件
        elif arg == "health":
            issues = []

            # 1. API Key 配置
            from core.config import SETTINGS
            if not SETTINGS.api_key or "sk-your" in SETTINGS.api_key:
                issues.append("❌ API Key 未配置")
            else:
                issues.append("✅ API Key 已配置")

            # 2. Python 版本
            import sys
            issues.append(f"{'✅' if sys.version_info >= (3,10) else '❌'} Python {sys.version.split()[0]}")

            # 3. 核心依赖
            try:
                import httpx, rich, PIL, dotenv
                issues.append("✅ 依赖已安装")
            except ImportError:
                issues.append("❌ 缺少依赖，运行 pip install -r requirements.txt")

            # 4. 使用统计（来自 memory 模块）
            mem = memory.load_memory()
            stats = mem.get("stats", {})
            issues.append(f"📊 生成: {stats.get('total', 0)} 次 | ⭐评分: {stats.get('rated_count', 0)} 条 | 🚫过滤: {stats.get('content_policy_hits', 0)} 次")
            for i in issues:
                console.print(f"  {i}")

        # ── /self fix：AI 源码分析 ─────────────────────
        # 1. 切换到代码模式（pro+thinking+程序员人设）
        # 2. 读取 core/ 和 engines/ 下的 Python 文件
        # 3. 将源码喂给 AI，让它分析 bug / API 合规性 / 优化建议
        elif arg == "fix":
            session.toggle_code_mode()  # 切到代码助手模式（自动 pro+thinking）
            ctx = "你是 Agnes Smart Studio 维护者。以下是核心源码，请分析 bug/合规性/优化建议：\n\n"
            total = 0
            # 只读 core 和 engines 两个核心目录
            for sub in ["core", "engines"]:
                for dp, _, files in os.walk(os.path.join(root, sub)):
                    for f in files[:4]:         # 每个目录最多取 4 个文件
                        if f.endswith(".py"):
                            fp = os.path.join(dp, f)
                            rel = os.path.relpath(fp, root)
                            try:
                                content = open(fp, encoding="utf-8").read()
                                ctx += f"### {rel}\n```python\n{content[:3000]}\n```\n\n"
                                total += 3000
                                if total > 50000:   # 控制上下文在 50K 以内
                                    break
                            except Exception:
                                pass
                    if total > 50000:
                        break
            show_info("AI 正在分析源码...")
            # 将源码作为用户消息塞入对话，走流式输出 AI 的分析结果
            session.messages.append({"role": "user", "content": ctx})
            self._stream_chat(session, ctx)

        else:
            # 用法提示
            show_info("用法: /self [check|files|health|fix]")
            console.print("  [dim]check[/]  - 扫描所有 .py 语法")
            console.print("  [dim]files[/]  - 展示项目结构")
            console.print("  [dim]health[/] - API Key / Python / 依赖 / 统计")
            console.print("  [dim]fix[/]    - AI 读源码分析问题")

    def _chat_skill(self, session: "ChatSession", arg: str):
        """管理技能包 /skill [list|load <name>|unload|create <name> <描述>]

        支持中文别名，如: 视频=showrunner, 作图=comfyui-bridge, 写剧本=script-writer
        """
        session.skills.discover()
        names = session.skills.available_names
        skills = session.skills._available
        arg = arg.strip()

        # ── 中文别名映射 ──
        SKILL_ALIASES = {
            # Showrunner & Pipeline
            "视频": "showrunner", "做视频": "showrunner", "拍片": "showrunner",
            "一键视频": "showrunner", "制片": "showrunner", "showrunner": "showrunner",
            # ComfyUI
            "作图": "comfyui-bridge", "生图": "comfyui-bridge", "画画": "comfyui-bridge",
            "comfyui": "comfyui-bridge", "本地生图": "comfyui-bridge", "炼丹": "comfyui-bridge",
            # 写作
            "写剧本": "script-writer", "剧本": "script-writer",
            "写小说": "novel-writer", "小说": "novel-writer",
            "写文案": "story-copywriter", "文案": "story-copywriter",
            "漫剧": "comic-drama-writer",
            # 视觉
            "视觉导演": "visual-director", "分镜": "storyboard-director",
            "运镜": "motion-director", "电影化": "cinematic-master",
            "关键帧": "cinematic-keyframe", "动作戏": "gaming-action-engine",
            # 工具
            "提示词": "prompt-director", "质检": "qc-inspector",
            "模型路由": "model-routing", "资产管理": "asset-manager",
            "修复": "recovery-playbooks", "世界观": "world-building-engine",
            "世界观构建": "world-building-engine",
        }

        # 解析中文别名
        resolved = SKILL_ALIASES.get(arg) or (SKILL_ALIASES.get(arg.split()[0]) if " " in arg else None)

        if not arg or arg == "list":
            if not names:
                show_info("无可用技能，用 /skill create <名称> <描述> 让 AI 创建")
                return
            # ── 构建反向别名映射（英文名 → 中文别名）──
            alias_rev = {}
            for cn, en in SKILL_ALIASES.items():
                alias_rev.setdefault(en, []).append(cn)
            console.print(f"[bold]可用技能 ({len(names)}):[/]")
            console.print("[dim]加载方式: /skill load <中文别名>  如: /skill load 视频[/]")
            for n in sorted(names):
                s = skills.get(n)
                icon = s.icon + " " if s and s.icon else ""
                desc = s.description if s else ""
                aliases_str = ""
                if n in alias_rev:
                    aliases_str = " [" + "/".join(alias_rev[n][:3]) + "]"
                marker = " [cyan]← 当前[/]" if session.active_skill == n else ""
                console.print(f"  {icon}[cyan]{n}[/]{aliases_str} [dim]{desc}{marker}[/]")

        elif arg.startswith("load "):
            name = arg[5:].strip()
            # ── 中文别名解析 ──
            resolved = SKILL_ALIASES.get(name) or (SKILL_ALIASES.get(name.split()[0]) if " " in name else None)
            if resolved:
                name = resolved
                show_info(f"[dim]别名映射: {arg[5:].strip()} → {name}[/]")
            if not name:
                show_warning("用法: /skill load <名称>  (中文别名: 视频/作图/写剧本/分镜/质检...)")
                return
            result = session.load_skill(name)
            if result:
                s = skills.get(result)
                icon = s.icon + " " if s and s.icon else ""
                show_success(f"已加载: {icon}{result}")
            else:
                show_warning(f"未找到技能 '{name}'，/skill list 查看或用中文名如: 视频 作图 写剧本")

        elif arg.startswith("create "):
            parts = arg[7:].strip().split(" ", 1)
            name = parts[0].strip() if parts else ""
            desc = parts[1].strip() if len(parts) > 1 else ""
            if not name:
                show_warning("用法: /skill create <name> <描述>")
                return
            self._skill_create(session, name, desc)

        elif arg == "unload":
            if session.active_skill:
                show_info(f"已卸载技能: {session.active_skill}")
                session.unload_skill()
            else:
                show_info("当前无已加载技能")

        elif arg == "validate":
            result = session.skills.validate()
            console.print(f"[bold]品质门禁:[/] ✅ {len(result['passed'])} 通过")
            for f in result["passed"]:
                console.print(f"  [green]✓[/] {f}")
            if result["warnings"]:
                console.print(f"[bold]⚠ 警告:[/]")
                for w in result["warnings"]:
                    console.print(f"  [yellow]⚠[/] {w}")
            if result["failed"]:
                console.print(f"[bold]❌ {len(result['failed'])} 失败:[/]")
                for f in result["failed"]:
                    console.print(f"  [red]✗[/] {f['file']}: {', '.join(f.get('errors', []))}")

        elif arg.startswith("import "):
            market_path = arg[7:].strip()
            if not market_path:
                show_warning("用法: /skill import <market_path>")
                return
            show_info(f"正在从 {market_path} 导入技能...")
            result = session.skills.import_from_marketplace(market_path)
            console.print(f"[bold]导入结果:[/]")
            console.print(f"  ✅ 导入: {len(result['imported'])} 个")
            if result["imported"]:
                console.print(f"     {', '.join(result['imported'][:10])}")
            if result["skipped"]:
                console.print(f"  ⏭ 跳过: {len(result['skipped'])} 个")
            if result["errors"]:
                console.print(f"  ❌ 错误: {len(result['errors'])} 个")
                for e in result["errors"][:5]:
                    console.print(f"     {e}")

        else:
            show_info("用法: /skill [list|load|create|unload|validate|import <path>]")

    def _skill_create(self, session: "ChatSession", name: str, desc: str):
        """让 AI 自动生成技能文件"""
        import os
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")
        filepath = os.path.join(skills_dir, f"{name}.skill.json")

        # 构建生成技能的提示词
        prompt = (
            f"创建一个名为 '{name}' 的 skill 文件。用 JSON 格式输出：\n\n"
            f"描述：{desc or '一个实用技能'}\n\n"
            f"输出格式（只输出 JSON，不要其他文字）：\n"
            f'{{"name": "{name}", "description": "...", "version": "1.0", "icon": "🔧", '
            f'"prompt": "激活 ... 模式。规则：..."}}\n\n'
            f"prompt 字段要写详细的 AI 行为规范（中文，至少 5 条规则）。"
        )

        session.toggle_code_mode()
        session.messages.append({"role": "user", "content": prompt})
        show_info(f"AI 正在生成技能 '{name}' ...")

        # 流式收集 AI 输出
        buffer = ""
        try:
            for delta in session.client.chat_stream(
                model=session.model, messages=session.messages,
                max_tokens=2048,
            ):
                if "content" in delta and delta["content"]:
                    buffer += delta["content"]
        except Exception as e:
            show_error(f"生成失败: {e}")
            session.messages.pop()
            return

        # 提取 JSON
        import json, re
        try:
            # 尝试解析 AI 输出的 JSON
            json_match = re.search(r'\{.*\}', buffer, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(buffer)
        except json.JSONDecodeError:
            # 如果 AI 没输出纯 JSON，手动构建
            match = re.search(r'"prompt":\s*"(.+?)"\s*\}', buffer, re.DOTALL)
            skill_prompt = match.group(1) if match else buffer[:500]
            data = {
                "name": name,
                "description": desc or "AI 生成的技能",
                "version": "1.0",
                "icon": "🔧",
                "prompt": skill_prompt,
            }

        # 确保必要字段
        data.setdefault("name", name)
        data.setdefault("description", desc or "AI 生成的技能")
        data.setdefault("version", "1.0")
        data.setdefault("icon", "🔧")
        data.setdefault("prompt", buffer[:1000])

        # 写入文件
        os.makedirs(skills_dir, exist_ok=True)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            show_success(f"技能已创建: skills/{name}.skill.json")
            console.print(f"  [dim]加载: /skill load {name}[/]")
            # 清理 AI 消息，避免污染历史
            session.messages.pop()
        except Exception as e:
            show_error(f"写入文件失败: {e}")
            session.messages.pop()

    # ── 计划模式 ──────────────────────────────

    def _chat_plan(self, session: "ChatSession", task: str):
        """先规划再执行：让 LLM 输出计划 → 解析步骤 → 逐步执行"""
        if not task:
            show_warning("用法: /plan <任务描述>")
            return
        from core.agent import PLAN_PROMPT, parse_plan
        session.model = "agnes-2.0-flash"
        session.enable_thinking = True

        show_info(f"正在制定计划: {task[:40]}...")
        plan_msg = f"{PLAN_PROMPT}\n\n用户任务: {task}\n请输出计划并开始执行。"
        session.messages.append({"role": "user", "content": plan_msg})

        # 流式输出计划
        buffer = ""
        try:
            for delta in session.client.chat_stream(
                model=session.model, messages=session.messages,
                max_tokens=3072,
            ):
                if "content" in delta and delta["content"]:
                    buffer += delta["content"]
                    console.print(delta["content"], end="")
        except Exception as e:
            show_error(f"计划生成失败: {e}")
            session.messages.pop()
            return

        console.print()
        session.messages.append({"role": "assistant", "content": buffer})

        steps = parse_plan(buffer)
        if steps:
            console.print(f"\n[dim]解析到 {len(steps)} 个步骤[/]")

    # ── 子智能体 ──────────────────────────────

    def _chat_subagent(self, session: "ChatSession", task: str):
        """启动子智能体处理独立任务"""
        if not task:
            show_warning("用法: /sub <子任务描述>")
            return
        from core.agent import spawn_subagent
        show_info(f"子智能体启动: {task[:40]}...")
        result = spawn_subagent(session.client, task)
        console.print(Panel(result[:2000], title="[cyan]子智能体结果[/]"))

    # ── 上下文压缩 ────────────────────────────

    def _chat_compress(self, session: "ChatSession"):
        """压缩长对话历史为摘要"""
        from core.agent import compress_messages
        if len(session.messages) < 6:
            show_info("消息较少，无需压缩")
            return
        show_info("正在压缩对话历史...")
        summary = compress_messages(session.messages, session.client)
        if summary:
            # 保留 system + 摘要 + 最近 2 轮
            session.messages = [
                session.messages[0],
                {"role": "user", "content": f"[对话摘要]\n{summary}"},
                {"role": "assistant", "content": "已理解。继续。"},
            ] + session.messages[-4:]
            show_success(f"已压缩为 {len(session.messages)} 条消息")
        else:
            show_warning("压缩失败")

    # ── 项目管理 ──────────────────────────────

    def _chat_project(self, session: "ChatSession", arg: str):
        """项目管理 /project [new|list|save|load|analyze] [name]"""
        from core.project import Project, PROJECTS_DIR
        arg = arg.strip()

        if arg.startswith("new ") or not arg:
            name = arg[4:].strip() if arg.startswith("new ") else arg
            name = name or f"project_{datetime.now().strftime('%Y%m%d_%H%M')}"
            p = Project(name)
            show_success(f"项目已创建: {name}")

        elif arg.startswith("save "):
            name = arg[5:].strip()
            p = Project(name)
            sid = datetime.now().strftime("%Y%m%d_%H%M%S")
            p.save_session(sid, session.messages)
            # 同时记录变更中的文件
            for m in session.messages:
                content = m.get("content", "")
                if isinstance(content, str):
                    files = re.findall(r'["\']?[\w./-]+\.(py|js|ts|md|json|html|css)["\']?', content)
                    for f in files[:5]:
                        p.record_file_change(f, "modified")
            show_success(f"会话已保存: {name} (ID: {sid})")

        elif arg.startswith("load "):
            name = arg[5:].strip()
            p = Project(name)
            sessions = p.list_sessions()
            if not sessions:
                show_warning(f"项目 {name} 无已保存会话")
                return
            console.print(f"[bold]项目 {name} 的会话:[/]")
            for i, s in enumerate(sessions[:5], 1):
                console.print(f"  {i}. {s['id']} ({s['messages']}msg, {s['saved_at'][:16]})")
            ch = Prompt.ask("加载哪个 (序号)", default="1")
            try:
                s = sessions[int(ch)-1]
                msgs = p.load_session(s["id"])
                if msgs:
                    session.messages = msgs
                    show_success(f"已加载: {len(msgs)} 条消息")
            except (IndexError, ValueError):
                show_warning("无效选择")

        elif arg.startswith("list"):
            if not PROJECTS_DIR.exists():
                show_info("暂无项目")
                return
            for d in sorted(PROJECTS_DIR.iterdir()):
                if d.is_dir():
                    p = Project(d.name)
                    cfg = p.load_config()
                    ts = cfg.get("last_access", "")[:10]
                    s = cfg.get("summary", "")[:40]
                    console.print(f"  [cyan]{d.name}[/] [dim]{ts} {s}[/]")

        elif arg.startswith("analyze "):
            name = arg[8:].strip()
            p = Project(name)
            stats = p.analyze_codebase()
            console.print(f"[bold]{name} 分析:[/]")
            console.print(f"  文件: {stats['files']} | 总行数: {stats['total_lines']}")
            console.print(f"  语言: {stats['languages']}")

        else:
            show_info("用法: /project [new|list|save|load|analyze] [name]")

    # ── 智能体团队 ────────────────────────────

    def _chat_team(self, session: "ChatSession", arg: str):
        """启动智能体团队 /team [review|debug|feature] [上下文]"""
        from core.project import run_team, TEAM_CONFIGS
        parts = arg.strip().split(" ", 1)
        team_type = parts[0] if parts and parts[0] in ("review", "debug", "feature") else "review"
        context = parts[1] if len(parts) > 1 else ""

        if not context:
            # 没有上下文时，用最近的对话内容作为上下文
            context = ""
            for m in session.messages[-6:]:
                c = m.get("content", "")
                if isinstance(c, str):
                    context += c[:500] + "\n"

        show_info(f"启动智能体团队: {team_type} ({len(TEAM_CONFIGS.get(team_type, {}).get('agents', []))} 成员)...")
        result = run_team(session.client, team_type, context)

        if "error" in result:
            show_error(result["error"])
            return

        console.print(Panel(result["summary"][:2000], title=f"[cyan]{result['team']}[/]"))

    # ── 部署集成 ──────────────────────────────

    def _chat_deploy(self, session: "ChatSession", arg: str):
        """一键部署 /deploy [vercel|netlify|github] [path]"""
        from core.project import deploy_to_vercel, deploy_to_netlify, deploy_to_github_pages
        parts = arg.strip().split(" ", 1)
        target = parts[0].lower() if parts else "vercel"
        path = parts[1] if len(parts) > 1 else os.getcwd()

        show_info(f"部署到 {target}: {path}")
        deploy_fn = {"vercel": deploy_to_vercel, "netlify": deploy_to_netlify, "github": deploy_to_github_pages}.get(target)
        if not deploy_fn:
            show_warning(f"未知目标 {target}，可选: vercel, netlify, github")
            return

        result = deploy_fn(path)
        console.print(Panel(result[:1000] or "[无输出]", title=f"[cyan]部署结果[/]"))

    # ── TODO 扫描 ─────────────────────────────
    # 递归遍历项目文件，用正则匹配 TODO / FIXME / HACK / XXX / OPTIMIZE / BUG 标签
    # 只扫描代码和文档文件（.py/.js/.ts/.md/.html/.css/.sh/.bat），输出文件名+行号+内容

    def _chat_todo(self, session: "ChatSession", arg: str):
        """扫描项目中待办标记 (TODO/FIXME/HACK/XXX/OPTIMIZE/BUG)"""
        import subprocess
        path = arg.strip() or "."
        show_info(f"扫描 {path} 中的 TODO/FIXME/HACK/XXX ...")
        try:
            r = subprocess.run(
                f'python -c "import os,re; '
                f'[print(f\'{{os.path.relpath(dp,os.getcwd())}}:{{n}}: {{l.strip()}}\') '
                f'for dp,_,fs in os.walk(\'{path}\') '
                f'for f in fs if f.endswith((\'.py\',\'.js\',\'.ts\',\'.md\',\'.html\',\'.css\',\'.sh\',\'.bat\')) '
                f'for n,l in enumerate(open(dp+\'/\'+f,encoding=\'utf-8\',errors=\'replace\'),1) '
                f'if re.search(r\'TODO|FIXME|HACK|XXX|OPTIMIZE|BUG\', l)]"',
                shell=True, capture_output=True, text=True, timeout=30)
            lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
            if lines:
                show_warning(f"发现 {len(lines)} 个待办:")
                for l in lines[:20]:
                    console.print(f"  [dim]{l}[/]")
            else:
                show_success("无待办项")
        except Exception as e:
            show_error(str(e))

    # ── 自动 Commit ───────────────────────────
    # 1. 读取 git diff --staged（已暂存的更改）
    # 2. 将 diff 内容发给 LLM，让它生成简洁的中文 commit 消息
    # 3. 确认后自动执行 git commit

    def _chat_commit(self, session: "ChatSession"):
        """从 git staged diff 自动生成 commit 消息并提交"""
        import subprocess
        try:
            diff = subprocess.run("git diff --staged --stat", shell=True, capture_output=True, text=True, timeout=10)
            if not diff.stdout.strip():
                show_warning("无 staged 更改，先 git add")
                return
            full_diff = subprocess.run("git diff --staged", shell=True, capture_output=True, text=True, timeout=10)
            prompt = f"根据以下 git diff 生成简洁中文 commit 消息（格式：<类型>: <一句话描述>）：\n\n{full_diff.stdout[:3000]}"
            session.model = "agnes-2.0-flash"
            r = session.client.chat(model=session.model, messages=[
                {"role": "user", "content": prompt}], max_tokens=200)
            msg = r["choices"][0]["message"]["content"].strip()
            show_success(f"建议 commit: {msg}")
            if Confirm.ask("执行 commit?", default=True):
                subprocess.run(f'git commit -m "{msg}"', shell=True, timeout=10)
                show_success("已提交")
        except Exception as e:
            show_error(str(e))

    # ── Changelog ─────────────────────────────
    # 1. 读取 git log（默认最近 7 天，可指定时间段如 "14 days ago"）
    # 2. 发给 LLM 分类汇总（新增/修复/优化/其他）
    # 3. 可选保存为 CHANGELOG.md

    def _chat_changelog(self, session: "ChatSession", arg: str):
        """从 git log 自动生成 CHANGELOG.md（分组：新增/修复/优化/其他）"""
        import subprocess
        since = arg.strip() or "7 days ago"
        try:
            log = subprocess.run(f'git log --since="{since}" --oneline --no-merges', shell=True, capture_output=True, text=True, timeout=10)
            if not log.stdout.strip():
                show_warning(f"{since} 内无提交")
                return
            prompt = f"根据以下 git log 生成 CHANGELOG.md（分组：新增/修复/优化/其他）：\n\n{log.stdout[:3000]}"
            session.model = "agnes-2.0-flash"
            r = session.client.chat(model=session.model, messages=[{"role": "user", "content": prompt}], max_tokens=1000)
            changelog = r["choices"][0]["message"]["content"].strip()
            console.print(Panel(changelog[:2000], title="[cyan]CHANGELOG[/]"))
            if Confirm.ask("保存为 CHANGELOG.md?", default=True):
                with open("CHANGELOG.md", "w", encoding="utf-8") as f:
                    f.write(changelog)
                show_success("已保存 CHANGELOG.md")
        except Exception as e:
            show_error(str(e))

    # ── 批量重构 ──────────────────────────────
    # 用 sed 在指定路径下批量替换文本（仅 .py/.js/.ts/.md 文件）
    # ⚠ 不可逆操作，执行前会确认

    def _chat_refactor(self, session: "ChatSession", arg: str):
        """批量重命名/替换文本（不可逆，确认后执行）"""
        import subprocess
        parts = arg.strip().split(" ", 2)
        if len(parts) < 2:
            show_warning("用法: /refactor <旧名> <新名> [路径]")
            return
        old, new, path = parts[0], parts[1], parts[2] if len(parts) > 2 else "."
        show_info(f"将 {path} 中的 '{old}' 替换为 '{new}' (仅 .py/.js/.ts/.md)")

        cmd = (f'python -c "import os; '
               f'[os.system(f\'sed -i s/{old}/{new}/g {{fp}}\') '
               f'for dp,_,fs in os.walk(\'{path}\') '
               f'for f in fs if f.endswith((\'.py\',\'.js\',\'.ts\',\'.md\')) '
               f'for fp in [dp+\'/\'+f.replace(chr(92),chr(47))]]"')
        show_warning("⚠ 批量替换不可逆")
        if Confirm.ask("确认执行?", default=False):
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                show_success("替换完成 (检查 git diff 确认)")
            except Exception as e:
                show_error(str(e))

    # ── 依赖审计 ──────────────────────────────
    # 检查 pip 和 npm 依赖的：
    # 1. 过期版本（pip list --outdated / npm outdated）
    # 2. 已知安全漏洞（pip-audit / npm audit）
    # 支持 pip / npm / all 三种范围

    def _chat_audit(self, session: "ChatSession", arg: str):
        """依赖安全审计：检查过期版本 + 已知漏洞 (pip/npm/all)"""
        import subprocess
        kinds = arg.strip() or "all"

        if kinds in ("pip", "all"):
            show_info("检查 pip 依赖...")
            try:
                r = subprocess.run("pip list --outdated --format columns", shell=True, capture_output=True, text=True, timeout=30)
                if r.stdout.strip():
                    console.print(Panel(r.stdout[:2000], title="[yellow]pip 过期包[/]"))
                else:
                    show_success("pip: 全部最新")
            except Exception:
                pass
            # 安全检查
            try:
                r2 = subprocess.run("pip-audit 2>&1 || pip install pip-audit -q && pip-audit", shell=True, capture_output=True, text=True, timeout=60)
                if r2.stdout.strip():
                    console.print(Panel(r2.stdout[:1500], title="[red]安全漏洞[/]"))
            except Exception:
                console.print("  [dim]pip-audit 未安装 (pip install pip-audit)[/]")

        if kinds in ("npm", "all"):
            show_info("检查 npm 依赖...")
            try:
                r = subprocess.run("npm outdated 2>&1", shell=True, capture_output=True, text=True, timeout=30)
                if r.stdout.strip():
                    console.print(Panel(r.stdout[:2000], title="[yellow]npm 过期包[/]"))
                else:
                    show_success("npm: 全部最新")
            except Exception:
                console.print("  [dim]非 npm 项目或 npm 未安装[/]")
            try:
                r2 = subprocess.run("npm audit 2>&1", shell=True, capture_output=True, text=True, timeout=60)
                if "vulnerabilities" in r2.stdout.lower():
                    console.print(Panel(r2.stdout[:1500], title="[red]npm 安全漏洞[/]"))
            except Exception:
                pass

    # ── Rules 系统 ────────────────────────────
    # 管理持久化编码规范，启用后自动注入到每次会话的 system prompt
    # rules/ 目录下的 .rules.md 文件即规范内容

    def _chat_rules(self, session: "ChatSession", arg: str):
        """管理编码规范 (list|enable|create) — 启用后自动注入会话"""
        from core.rules import get_rules
        rules = get_rules()
        arg = arg.strip()

        if not arg or arg == "list":
            rules.discover()
            names = rules.available_names
            if not names:
                show_info("无规则文件，创建 rules/*.rules.md 添加")
                return
            for n in sorted(names):
                r = rules.load(n)
                active = " [green]● 激活[/]" if n in rules._active else ""
                console.print(f"  [cyan]{n}[/] [dim]{r.description if r else ''}{active}[/]")

        elif arg.startswith("enable "):
            name = arg[7:].strip()
            if rules.enable(name):
                show_success(f"已启用规则: {name}")
            else:
                show_warning(f"未找到规则 '{name}'")

        elif arg == "disable":
            rules._active.clear()
            show_info("已禁用所有规则")

        elif arg.startswith("create "):
            parts = arg[7:].strip().split(" ", 1)
            name = parts[0] if parts else ""
            content = parts[1] if len(parts) > 1 else ""
            if not name or not content:
                show_warning("用法: /rules create <name> <内容>")
                return
            path = rules.create_rule(name, content, f"{name} 规则")
            show_success(f"规则已创建: {path}")

        else:
            show_info("用法: /rules [list|enable <name>|disable|create <name> <内容>]")

        # 每次操作后注入规则到会话
        prompt = rules.inject_prompt()
        if prompt and session.messages:
            session.messages[0] = {"role": "system", "content":
                session.messages[0].get("content", "")[:200] + prompt}

    # ── 自动化任务 ────────────────────────────
    # 存储定时任务定义到 output/automations/tasks.json
    # cron 格式: "分 时 日 月 周"，如 "0 9 * * 1" = 每周一早 9 点
    # 实际执行需配合外部调度器（如 Windows 任务计划 / cron）

    def _chat_automate(self, session: "ChatSession", arg: str):
        """管理自动化定时任务 (list|add <描述> <cron>|remove)"""
        import os, json
        from datetime import datetime
        automations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "automations")
        os.makedirs(automations_dir, exist_ok=True)
        data_path = os.path.join(automations_dir, "tasks.json")
        tasks = []
        if os.path.exists(data_path):
            tasks = json.loads(open(data_path, encoding="utf-8").read())

        arg = arg.strip()

        if not arg or arg == "list":
            if not tasks:
                show_info("无自动化任务")
                return
            for i, t in enumerate(tasks, 1):
                console.print(f"  {i}. [{t.get('cron','?')}] {t.get('desc','')[:50]} [dim]({t.get('id','')})[/]")

        elif arg.startswith("add "):
            parts = arg[4:].strip().split(" ", 2)
            if len(parts) < 2:
                show_warning("用法: /automate add <描述> <cron表达式>")
                return
            desc, cron = parts[0], parts[1]
            task = {
                "id": datetime.now().strftime("auto_%Y%m%d_%H%M%S"),
                "desc": desc,
                "cron": cron,
                "created": datetime.now().isoformat(),
                "last_run": "",
                "enabled": True,
            }
            tasks.append(task)
            open(data_path, "w", encoding="utf-8").write(json.dumps(tasks, indent=2, ensure_ascii=False))
            show_success(f"已添加: {desc} ({cron})")
            console.print("  [dim]提示: cron 格式为 '分 时 日 月 周'，如 '0 9 * * 1'=每周一早9点[/]")

        elif arg.startswith("remove "):
            tid = arg[7:].strip()
            before = len(tasks)
            tasks = [t for t in tasks if t.get("id") != tid]
            if len(tasks) < before:
                open(data_path, "w", encoding="utf-8").write(json.dumps(tasks, indent=2, ensure_ascii=False))
                show_success("已移除")
            else:
                show_warning("未找到该任务")

        else:
            show_info("用法: /automate [list|add <描述> <cron>|remove <id>]")

    # ── 多模型供应商 ──────────────────────────
    # 从 models.json 读取供应商配置，运行时切换 base_url + api_key
    # 支持 Agnes / DeepSeek / Kimi 等任意 OpenAI 兼容 API
    # API Key 从环境变量 {PROVIDER}_API_KEY 或手动输入

    @staticmethod
    def _load_models_config() -> dict:
        """安全加载 models.json，文件缺失/空/损坏时返回默认配置"""
        import json
        root = os.path.dirname(os.path.dirname(__file__))
        cfg_path = os.path.join(root, "models.json")

        def _default_cfg():
            return {
                "providers": {
                    "agnes": {"name": "Agnes AI", "base_url": "https://apihub.agnes-ai.com/v1",
                              "api_key": "", "models": {"light": "agnes-1.5-flash", "pro": "agnes-2.0-flash"}},
                    "deepseek": {"name": "DeepSeek V4 Pro (1M)", "base_url": "https://api.deepseek.com/v1",
                                 "api_key": "", "models": {"pro": "deepseek-v4-pro", "light": "deepseek-v4-pro"}},
                    "siliconflow": {"name": "SiliconFlow (Kimi-K2.6)", "base_url": "https://api.siliconflow.cn/v1",
                                    "api_key": "", "models": {"pro": "Pro/moonshotai/Kimi-K2.6", "light": "Pro/moonshotai/Kimi-K2.6"}},
                },
                "active": "agnes",
                "fallback": {"enabled": True, "priority": ["deepseek", "siliconflow"]},
            }

        if not os.path.exists(cfg_path):
            # 新建默认文件
            cfg = _default_cfg()
            try:
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return cfg

        raw = ""
        try:
            raw = Path(cfg_path).read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("空文件")
            cfg = json.loads(raw)
            # 确保必要字段存在
            if "providers" not in cfg:
                cfg["providers"] = _default_cfg()["providers"]
            if "active" not in cfg:
                cfg["active"] = "agnes"
            return cfg
        except (json.JSONDecodeError, ValueError) as e:
            # 文件损坏或为空 → 重建
            show_warning(f"models.json 损坏 ({e})，已自动重建默认配置")
            cfg = _default_cfg()
            try:
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return cfg

    def _chat_provider(self, session: "ChatSession", arg: str):
        """切换模型供应商 (list|switch agnes/deepseek/siliconflow)"""
        import json
        root = os.path.dirname(os.path.dirname(__file__))
        cfg_path = os.path.join(root, "models.json")
        cfg = self._load_models_config()
        providers = cfg.get("providers", {})
        arg = arg.strip()

        if not arg or arg == "list":
            active = cfg.get("active", "agnes")
            fallback = cfg.get("fallback", {})
            priority = fallback.get("priority", [])
            for pid, p in providers.items():
                marker = " [green]← 当前[/]" if pid == active else ""
                models = p.get("models", {})
                model_info = ", ".join(f"{k}={v}" for k, v in models.items())
                key_env = f"{pid.upper()}_API_KEY"
                has_key = "有 Key" if os.getenv(key_env) else "无 Key"
                prio_marker = f" [yellow]#{priority.index(pid)+1}优先[/]" if pid in priority else ""
                console.print(f"  [cyan]{pid}[/] {p['name']} ({has_key}){prio_marker}{marker}\n    模型: {model_info}")
            if priority:
                console.print(f"  [dim]回退链: {' → '.join(priority)}[/]")
            return

        if arg.startswith("switch "):
            pid = arg[7:].strip()
            if pid not in providers:
                show_warning(f"未知供应商 '{pid}'，支持: {list(providers.keys())}")
                return

            p = providers[pid]
            # 从 .env 查找对应 API key
            key_env = f"{pid.upper()}_API_KEY"
            api_key = os.getenv(key_env) or os.getenv("AGNES_API_KEY") or ""

            if not api_key:
                key = Prompt.ask(f"[cyan]输入 {p['name']} API Key[/]")
                if not key:
                    show_warning("已取消")
                    return
                api_key = key

            # 更新 client 和 session
            from core.client import AgnesClient
            session.client.close()
            session.client = AgnesClient(api_key=api_key, base_url=p["base_url"])
            cfg["active"] = pid
            open(cfg_path, "w", encoding="utf-8").write(json.dumps(cfg, indent=2, ensure_ascii=False))

            # 切换 model 到该供应商的 pro 模型
            pro_model = p.get("models", {}).get("pro", "")
            if pro_model:
                session.model = pro_model

            show_success(f"已切换到 {p['name']} ({pro_model})")
            # 刷新系统提示词，让 AI 知道当前供应商
            session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
            session.reset()
        else:
            show_info("用法: /provider [list|switch <name>]")

    # ── Prompt 进化 ────────────────────────────

    def _chat_evolve(self, session: "ChatSession"):
        """查看 Prompt 进化状态 — 高分案例统计"""
        from utils.memory import get_evolution_stats, get_successful_prompts
        stats = get_evolution_stats()
        console.print(f"[bold]Prompt 进化库:[/]")
        console.print(f"  图片: {stats['image']} 条成功案例")
        console.print(f"  视频: {stats['video']} 条成功案例")

        for kind in ["image", "video"]:
            samples = get_successful_prompts(kind, limit=3)
            if samples:
                console.print(f"\n  [cyan]{kind} 最佳案例:[/]")
                for s in samples:
                    console.print(f"    ⭐{s['rating']} | 你: {s['user'][:50]}")
                    console.print(f"    → 增强: {s['enhanced'][:80]}...")

        if stats['image'] + stats['video'] < 5:
            console.print("\n  [dim]评分越多，进化越快。生成后给 4-5 星即可积累案例。[/]")
            console.print("\n  [bold]提示词速成:[/]")
            console.print("  [dim]主体+场景[/] '一只狐狸在雪地里'")
            console.print("  [dim]主体+风格[/] '一只狐狸 水墨画'")
            console.print("  [dim]主体+动作+场景[/] '冲锋的战士 雨夜战场'")
            console.print("  [dim]只需这 3 种格式，增强器负责补全 10 段细节。[/]")

    # ── 知识库探索 ────────────────────────────

    def _chat_knowledge(self, session: "ChatSession", arg: str):
        """浏览内置知识库 /know [methods|templates|moves|antipatterns|sweetspot]"""
        from core.brain import (
            THINKING_METHOD_MAP, SWEET_SPOT_TEMPLATES,
            ANTI_PATTERN_MAP, CREATIVE_DOMAIN_MAP
        )
        arg = arg.strip()

        if not arg or arg == "list":
            console.print("[bold]内置知识库:[/]")
            console.print("  [cyan]methods[/]       思维方法 (SCAMPER,六顶帽...)")
            console.print("  [cyan]templates[/]     提示词模板 (人像/动物/美食/风景/二次元/动作)")
            console.print("  [cyan]sweetspot[/]     甜点区参数 (每种模板的 suffix+negative)")
            console.print("  [cyan]antipatterns[/]  反模式 (常见失败模式+修复方案)")
            console.print("  [cyan]domain[/]        跨域创意嫁接 (动作×载体×物理×视觉)")

        elif arg == "methods":
            console.print(f"[bold]思维方法 ({len(THINKING_METHOD_MAP)} 种):[/]")
            for k, v in THINKING_METHOD_MAP.items():
                desc = v.get("name_cn", k)
                console.print(f"  [cyan]{k}[/] — {desc}")
                if v.get("description"):
                    console.print(f"    [dim]{v['description'][:100]}[/]")

        elif arg == "templates" or arg == "sweetspot":
            console.print(f"[bold]提示词模板:[/]")
            for k, v in SWEET_SPOT_TEMPLATES.items():
                console.print(f"  [cyan]{k}[/] — {v.get('name', k)}")
                console.print(f"    [dim]+ {v.get('suffix', '')[:80]}[/]")
                neg = v.get("negative", "")
                if neg:
                    console.print(f"    [dim]- {neg[:60]}[/]")

        elif arg == "antipatterns":
            console.print(f"[bold]反模式 ({len(ANTI_PATTERN_MAP)} 种):[/]")
            for k, v in ANTI_PATTERN_MAP.items():
                console.print(f"  [cyan]{k}[/] — {v.get('name_cn', k)}")
                desc = v.get("description", "")
                if desc:
                    console.print(f"    [dim]{desc[:100]}[/]")
                formula = v.get("prompt_formula", "")
                if formula:
                    console.print(f"    [dim]修复: {formula[:80]}[/]")

        elif arg == "domain":
            for domain_key, items in CREATIVE_DOMAIN_MAP.items():
                console.print(f"\n[bold cyan]{domain_key} 域:[/]")
                if isinstance(items, dict):
                    for k, v in items.items():
                        if isinstance(v, dict):
                            console.print(f"  {v.get('name_cn', k)} [dim]{v.get('description', '')[:60]}[/]")
                        else:
                            console.print(f"  [dim]{v[:60]}[/]")

        else:
            show_info("用法: /know [methods|templates|antipatterns|domain|list]")

    @staticmethod
    def _chat_help(current_model: str, thinking: bool = False, code_mode: bool = False, show_all: bool = False):
        think_state = "开" if thinking else "关"
        code_state = "代码助手" if code_mode else "通用助手"
        if show_all:
            cmds = [
                "/help              /all",
                "/model light|pro   /thinking",
                "/code              /agent",
                "/skill list|load   /plan <renwu>",
                "/sub <renwu>         /compress",
                "/img <miaoshu>       /video <miaoshu>",
                "/vision <tu> <wen>   /project new|save",
                "/team review|debug /deploy vercel|github",
                "/todo [path]       /commit",
                "/changelog         /refactor <jiu> <xin>",
                "/audit pip|npm     /rules list|create",
                "/automate add      /provider switch",
                "/evolve            /know methods",
                "/tools             /self check|fix",
                "/clear             /exit",
            ]
            text = "\n".join(cmds)
            cap = "AI auto" if current_model == "agnes-2.0-flash" else "manual"
            console.print(Panel(text, title=f"[bold cyan]29 commands[/] ({current_model} | think:{think_state} | {cap})", border_style=COLORS["primary"]))
            return
        console.print(Panel(f"""\
操作提示: Ctrl+C 中止运行 · 输入 \"\"\" 进入多行编辑 · /code 或 /agent 再输一次退出

/help              显示本帮助
/model [light|pro|<id>] 切换模型（支持别名或 raw ID）
/code              切换代码助手模式（当前：{code_state}，再次输入退出）
/agent             切换智能体模式（加载 tools.json 外部工具，再次输入退出）
/skill [cmd]       技能包管理 (list/load/create/unload)
/plan <任务>        先规划再执行（自动拆解步骤）
/sub <任务>          启动子智能体并处理子任务
/compress          压缩长对话历史为摘要
/project [cmd]     项目管理 (new/save/load/analyze)
/team [type]       启动智能体团队 (review/debug/feature)
/deploy [target]   一键部署 (vercel/netlify/github)
/todo [path]       扫描项目 TODO/FIXME/HACK
/commit            从 git diff 自动生成 commit 消息
/changelog         从 git log 生成 CHANGELOG.md
/refactor <旧><新>  批量重命名/替换
/audit [pip|npm]   依赖安全审计 + 过期检测
/rules [cmd]       编码规范管理 (list/enable/create)
/automate [cmd]    自动化定时任务 (add/list/remove)
/provider [cmd]    切换模型供应商 (list/switch)
/evolve            查看 Prompt 进化状态（成功案例统计）
/know [cmd]        浏览内置知识库 (methods/templates/domain)
/tools             查看已注册的工具列表
/thinking          切换深度思考模式（当前：{think_state}）
/img <描述>        生成图片（带 Prompt 增强）
/video <描述>      生成视频
/vision <图> <问>  图片理解（始终可用，独立视觉通道）
/self [cmd]        自诊断 (check/files/health/fix)
/clear             清空对话历史
/exit              退出聊天

当前模型: {current_model} | 模式: {code_state}
能力: {'AI 可自动触发生成' if current_model == 'agnes-2.0-flash' else '需用 /img /video 手动生成'} | 视觉: {'独立通道可用' if current_model != 'agnes-1.5-flash' else '主模型内置'}
供应商: /provider switch agnes|deepseek|siliconflow""",
            title="[bold cyan]聊天命令[/]",
            border_style=COLORS["primary"],
        ))

    @staticmethod
    def _chat_switch_model(session: "ChatSession", arg: str):
        from core.chat import MODEL_ALIASES, MODEL_INFO
        if not arg:
            show_warning(f"用法: /model light 或 /model pro 或 /model <模型ID>")
            return
        # 先查别名，再查 raw ID（如 deepseek-chat、kimi-k2.6）
        if arg in MODEL_ALIASES:
            session.model = MODEL_ALIASES[arg]
            if session.model in MODEL_INFO:
                cap = MODEL_INFO[session.model]
            else:
                cap = f"外部模型（{'支持 tool calling' if session.supports_tools else '纯文本对话'}）"
        else:
            # raw model ID 直接赋值
            session.model = arg
            cap = f"外部模型{'（支持 tool calling + 自动生图/视频）' if session.supports_tools else '（纯文本对话，需 /img /video 手动生成）'}"
        # 刷新系统提示词，让 AI 知道当前使用的模型
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        show_success(f"已切换到 {session.model} — {cap}")

    def _chat_generate(self, session: "ChatSession", kind: str, prompt: str):
        """命令式生成：增强 + 引擎，支持自动检测图片路径做图生图/图生视频"""
        if not prompt:
            prompt = Prompt.ask("[cyan]描述[/]").strip()
            if not prompt:
                return

        # 智能分离图片路径和文本描述
        img_path, clean_text = self._extract_path_and_text(prompt)
        has_image = img_path != prompt and img_path.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))
        final_prompt = clean_text if has_image else prompt
        if not final_prompt:
            final_prompt = prompt

        try:
            if kind == "image":
                show_info("优化图片提示词...")
                r = session.brain.enhance_image_prompt(final_prompt)
                fp = r.get("optimized_prompt", final_prompt)
                neg = r.get("negative_prompt", "") or None
                size = "1024x768"

                if has_image:
                    url = image_input.load_image_as_url_or_data(img_path)
                    show_info("图生图生成中...")
                    data = self.i2i.edit(prompt=fp, image_urls=url, size=size)
                else:
                    show_info("生成图片...")
                    data = session.t2i.generate(prompt=fp, size=size, negative_prompt=neg)

                show_image_result(data)
                record_type = "image_to_image" if has_image else "text_to_image"
                history.add_record(record_type, final_prompt, data.get("model", ""), data)

            else:  # video
                show_info("优化视频提示词...")
                r = session.brain.enhance_video_prompt(final_prompt)
                fp = r.get("optimized_prompt", final_prompt)
                neg = r.get("negative_prompt", "") or None
                w = SETTINGS.default_video_width
                h = SETTINGS.default_video_height

                show_info("生成视频（可能需几分钟）...")
                with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}"),
                              BarColumn(), TextColumn("{task.percentage:>3.0f}%"),
                              console=console) as prog:
                    task = prog.add_task("生成中", total=100)
                    def on_p(status, progress, data):
                        prog.update(task, completed=min(progress, 100), description=status)

                    if has_image:
                        url = image_input.load_image_as_url_or_data(img_path)
                        data = session.vid.image_to_video(
                            prompt=fp, image_url=url, width=w, height=h,
                            negative_prompt=neg, on_progress=on_p, timeout=120.0)
                    else:
                        data = session.vid.text_to_video(
                            prompt=fp, width=w, height=h, negative_prompt=neg,
                            on_progress=on_p, timeout=120.0)

                if data.get("status") == "timeout":
                    show_warning(f"视频超时，进度 {data.get('progress', 0):.0f}%")
                else:
                    show_video_result(data)
                record_type = "image_to_video" if has_image else "text_to_video"
                history.add_record(record_type, final_prompt, "agnes-video-v2.0", data)

        except Exception as e:
            show_error(str(e))

    def _chat_vision(self, session: "ChatSession", arg: str):
        """图片理解：始终使用独立视觉客户端（Agnes light），与主模型供应商解耦"""
        path, question = self._extract_path_and_text(arg)
        img_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
        if not path.lower().endswith(img_exts) and not path.startswith(("http://", "https://")):
            path = Prompt.ask("[cyan]图片路径/URL[/]").strip()
            question = Prompt.ask("[cyan]问什么[/]", default="描述这张图片").strip()
        if not question:
            question = "描述这张图片"
        try:
            url = image_input.load_image_as_url_or_data(path)
            show_info("理解图片中...")
            # 直接使用独立视觉客户端，不依赖 brain（brain 绑定主 client）
            r = session.vision_client.chat_multimodal(
                text=question, image_url=url,
                model=session.vision_model,
                temperature=0.3, max_tokens=1024,
            )
            content = r["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            content = "(多模态返回格式异常)"
        except Exception as e:
            show_error(str(e))
            return
        console.print(Panel(Markdown(content), title=f"[{COLORS['success']}]图片理解[/]",
                            border_style=COLORS["success"]))
        # 记入会话历史（便于追问）
        session.messages.append({"role": "user", "content": f"[图片理解] {question}"})
        session.messages.append({"role": "assistant", "content": content})

    def _stream_chat(self, session: "ChatSession", user: str):
        """流式渲染自然语言对话，处理 tool 调度的副作用透出
        
        Ctrl+C 中断当前流式输出，回滚不完整的 assistant 消息后重新传播。
        """
        live = Live(Markdown(""), console=console, refresh_per_second=12,
                    vertical_overflow="visible")
        live.start()
        buf = ""
        try:
            for kind, payload in session.send_stream(user):
                if kind == "text":
                    buf += payload
                    live.update(Markdown(buf))
                elif kind == "info":
                    live.stop()
                    show_info(payload)
                    live = Live(Markdown(buf), console=console, refresh_per_second=12,
                                vertical_overflow="visible")
                    live.start()
                elif kind == "image":
                    live.stop()
                    show_image_result(payload)
                    history.add_record("text_to_image", "chat", payload.get("model", ""), payload)
                    # 保留缓冲区文字，让模型后续的总结内容可见
                    live = Live(Markdown(buf), console=console, refresh_per_second=12,
                                vertical_overflow="visible")
                    live.start()
                elif kind == "video":
                    live.stop()
                    if payload.get("status") == "timeout":
                        show_warning(f"视频超时，进度 {payload.get('progress', 0):.0f}%")
                    else:
                        show_video_result(payload)
                    history.add_record("text_to_video", "chat", "agnes-video-v2.0", payload)
                    # 保留缓冲区文字，让模型后续的总结内容可见
                    live = Live(Markdown(buf), console=console, refresh_per_second=12,
                                vertical_overflow="visible")
                    live.start()
        except KeyboardInterrupt:
            live.stop()
            console.print()
            show_info("⏹ 已中断当前输出")
            # 回滚不完整的 assistant 消息，避免历史污染
            if session.messages and session.messages[-1].get("role") == "assistant":
                session.messages.pop()
            raise  # 传播到 _chat() 外层继续交互
        finally:
            live.stop()

