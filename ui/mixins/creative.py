"""创意生产命令 Mixin：生图/视频/视觉理解/技能管理/总导演。"""

from typing import TYPE_CHECKING

from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.prompt import Prompt

from core.config import SETTINGS
from utils import history, image_input
from ui.theme import COLORS, ICONS, LAYOUT, console
from ui.display import (show_error, show_image_result, show_video_result,
                         show_warning, show_info, show_success)
from ui.badges import print_mode_banner

if TYPE_CHECKING:
    from core.chat import ChatSession
    from engines.image_to_image import ImageToImageEngine

__all__ = ['CreativeCommandsMixin']



class CreativeCommandsMixin:
    # Attributes/methods provided by sibling Mixins in MRO
    i2i: "ImageToImageEngine"  # noqa: E704 — type stub only, set by CruxCLI.__init__

    # Method provided by SharedMixin (sibling in MRO)
    def _stream_chat(self, session: "ChatSession", user: str) -> None:
        ...  # defined in SharedMixin, available via MRO

    # Method provided by SharedMixin (sibling in MRO)
    @staticmethod
    def _extract_path_and_text(raw: str) -> tuple[str, str]:
        ...  # defined in SharedMixin, available via MRO


    def _chat_showrun(self, session, arg: str):
        """/showrun — 总导演模式入口。

        如果已加载 showrunner 技能，直接提示用户描述目标（arg 作为初始目标）。
        否则自动加载技能后再执行。
        """
        if not arg:
            arg = Prompt.ask("[cyan]创意目标[/]")
        # 确保 showrunner 技能已加载（带管道工具）
        if session.active_skill != "showrunner":
            session.load_skill("showrunner")
            # 能力提示：showrunner 依赖 tool calling 编排流水线
            if not session.supports_tools:
                show_warning(
                    f"当前模型 {session.model} 不支持 tool calling，"
                    "showrunner 的流水线工具可能无法自动调度。用 /model 切到支持 tools 的模型（如 deepseek-v4-pro）。"
                )
        # 把目标作为用户消息送入会话，触发 AI 总导演编排
        self._stream_chat(session, f"目标：{arg}\n请作为总导演规划并执行完整创意流水线。")

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
                show_info("Enhancing video prompt...")
                r = session.brain.enhance_video_prompt(final_prompt)
                fp = r.get("optimized_prompt", final_prompt)
                neg = r.get("negative_prompt", "") or None
                w = SETTINGS.default_video_width
                h = SETTINGS.default_video_height

                show_info("Generating video (may take several minutes)...")
                with Progress(SpinnerColumn(), TextColumn(f"[{LAYOUT['bar_style']}]{task.description}"),
                              BarColumn(style=f"{LAYOUT['bar_style']}", complete_style=f"{LAYOUT['bar_complete_style']}"),
                              TextColumn("{task.percentage:>3.0f}%"),
                              console=console) as prog:
                    task = prog.add_task("Generating", total=100)
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

        except (RuntimeError, OSError, ValueError, KeyError) as e:
            show_error(str(e))

    def _chat_vision(self, session: "ChatSession", arg: str):
        """图片理解：始终使用独立视觉客户端（CRUX light），与主模型供应商解耦"""
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
        except (RuntimeError, OSError, ValueError) as e:
            show_error(str(e))
            return
        console.print(Panel(Markdown(content), title=f"[{COLORS['success']}]图片理解[/]",
                            border_style=COLORS["success"]))
        # 记入会话历史（便于追问）
        session.messages.append({"role": "user", "content": f"[图片理解] {question}"})
        session.messages.append({"role": "assistant", "content": content})

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
                print_mode_banner(session)
                # 能力提示：技能依赖 tool calling，若当前模型不支持则建议切换
                if not session.supports_tools:
                    show_warning(
                        f"当前模型 {session.model} 不支持 tool calling，"
                        f"技能 '{result}' 的工具链可能无法调度。用 /model 切到支持 tools 的模型（如 deepseek-v4-pro）。"
                    )
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
                print_mode_banner(session)
            else:
                show_info("当前无已加载技能")

        elif arg == "validate":
            result = session.skills.validate()
            console.print(f"[bold]品质门禁:[/] ✅ {len(result['passed'])} 通过")
            for f in result["passed"]:
                console.print(f"  [green]✓[/] {f}")
            if result["warnings"]:
                console.print("[bold]⚠ 警告:[/]")
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
            console.print("[bold]导入结果:[/]")
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
        except (RuntimeError, OSError, KeyError) as e:
            show_error(f"生成失败: {e}")
            session.messages.pop()
            return

        # 提取 JSON
        import json
        import re
        try:
            # 尝试解析 AI 输出的 JSON
            json_match = re.search(r'\{.*\}', buffer, re.DOTALL)
            data = json.loads(json_match.group()) if json_match else json.loads(buffer)
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
        except (OSError, TypeError, ValueError) as e:
            show_error(f"写入文件失败: {e}")
            session.messages.pop()
