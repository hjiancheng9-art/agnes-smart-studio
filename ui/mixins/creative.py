"""创意生产命令 Mixin：生图/视频/视觉理解/技能管理/总导演。"""

from typing import TYPE_CHECKING

from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from core.config import SETTINGS
from ui.badges import print_mode_banner
from ui.display import show_error, show_image_result, show_info, show_success, show_video_result, show_warning
from ui.theme import COLORS, LAYOUT, console
from utils import history, image_input

if TYPE_CHECKING:
    from core.chat import ChatSession
    from engines.image_to_image import ImageToImageEngine

__all__ = ["CreativeCommandsMixin"]


class CreativeCommandsMixin:
    # Attributes/methods provided by sibling Mixins in MRO
    i2i: "ImageToImageEngine"  # noqa: E704 — type stub only, set by CruxCLI.__init__

    # Method provided by SharedMixin (sibling in MRO)
    def _stream_chat(self, session: "ChatSession", user: str) -> None: ...  # defined in SharedMixin, available via MRO

    # Method provided by SharedMixin (sibling in MRO)
    @staticmethod
    def _extract_path_and_text(raw: str) -> tuple[str, str]: ...  # defined in SharedMixin, available via MRO

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

    def _chat_generate(self, session: "ChatSession", kind: str, prompt: str, flags: dict | None = None):
        """命令式生成：增强 + 引擎，支持自动检测图片路径做图生图/图生视频

        Optional flags: --size WxH, --duration Ns, --system name
        """
        if flags is None:
            flags = {}
        if not prompt:
            prompt = Prompt.ask("[cyan]描述[/]").strip()
            if not prompt:
                return

        # 智能分离图片路径和文本描述
        img_path, clean_text = self._extract_path_and_text(prompt)
        has_image = img_path != prompt and img_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))
        final_prompt = clean_text if has_image else prompt
        if not final_prompt:
            final_prompt = prompt

        # Apply system flag: prepend style tag to prompt
        system = flags.get("system", "")
        if system:
            final_prompt = f"[{system}] {final_prompt}"

        try:
            if kind == "image":
                show_info("优化图片提示词...")
                r = session.brain.enhance_image_prompt(final_prompt)
                fp = r.get("optimized_prompt", final_prompt)
                neg = r.get("negative_prompt", "") or None
                size = flags.get("size", "1024x768")

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
                # Parse --size and --duration flags for video
                size_flag = flags.get("size", "")
                if size_flag and "x" in size_flag:
                    try:
                        w_str, h_str = size_flag.split("x")
                        w, h = int(w_str), int(h_str)
                    except (ValueError, AttributeError):
                        w = SETTINGS.default_video_width
                        h = SETTINGS.default_video_height
                else:
                    w = SETTINGS.default_video_width
                    h = SETTINGS.default_video_height
                dur_flag = flags.get("duration", "")
                if dur_flag:
                    try:
                        nf = int(float(dur_flag.rstrip("s")) * 24)  # seconds → frames at 24fps
                        nf = ((nf - 1) // 8) * 8 + 1  # normalize to 8n+1
                        nf = max(81, min(401, nf))
                    except (ValueError, TypeError):
                        nf = 121
                else:
                    nf = 121

                show_info("Generating video (may take several minutes)...")
                with Progress(
                    SpinnerColumn(),
                    TextColumn(f"[{LAYOUT['bar_style']}]{{task.description}}"),
                    BarColumn(style=f"{LAYOUT['bar_style']}", complete_style=f"{LAYOUT['bar_complete_style']}"),
                    TextColumn("{task.percentage:>3.0f}%"),
                    console=console,
                ) as prog:
                    task = prog.add_task("Generating", total=100)

                    def on_p(status, progress, data):
                        prog.update(task, completed=min(progress, 100), description=status)

                    if has_image:
                        url = image_input.load_image_as_url_or_data(img_path)
                        data = session.vid.image_to_video(
                            prompt=fp,
                            image_url=url,
                            width=w,
                            height=h,
                            num_frames=nf,
                            negative_prompt=neg,
                            on_progress=on_p,
                            timeout=120.0,
                        )
                    else:
                        data = session.vid.text_to_video(
                            prompt=fp, width=w, height=h, num_frames=nf,
                            negative_prompt=neg, on_progress=on_p, timeout=120.0
                        )

                if data.get("status") == "timeout":
                    show_warning(f"视频超时，进度 {data.get('progress', 0):.0f}%")
                else:
                    show_video_result(data)
                record_type = "image_to_video" if has_image else "text_to_video"
                history.add_record(record_type, final_prompt, "agnes-video-v2.0", data)

        except Exception as e:
            import httpx
            if isinstance(e, httpx.HTTPStatusError):
                show_error(f"API 错误 (HTTP {e.response.status_code})，请稍后重试")
            else:
                show_error(f"{type(e).__name__}: {e}")

    def _chat_vision(self, session: "ChatSession", arg: str):
        """图片理解：始终使用独立视觉客户端（CRUX light），与主模型供应商解耦"""
        path, question = self._extract_path_and_text(arg)
        img_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
        if not path.lower().endswith(img_exts) and not path.startswith(("http://", "https://")):
            path = Prompt.ask("[cyan]图片路径/URL[/]").strip()
            question = Prompt.ask("[cyan]问什么[/]", default="描述这张图片").strip()
        if not question:
            question = "描述这张图片"
        try:
            url = image_input.load_image_as_url_or_data(path)
            show_info("理解图片中...")
            # Try Zhipu first (free, capable), fallback to Agnes on content rejection
            content = None
            for attempt in ("zhipu", "agnes"):
                if attempt == "zhipu":
                    vc = session.vision_client
                    vision_model = session.vision_model
                    if vision_model.lower().startswith("glm-"):
                        try:
                            from core.provider import get_provider_manager
                            vc = get_provider_manager().create_client("zhipu")
                        except (ImportError, RuntimeError):
                            pass
                else:
                    vc = session.vision_client  # CRUX endpoint
                    vision_model = "agnes-1.5-flash"
                try:
                    r = vc.chat_multimodal(
                        text=question, image_url=url, model=vision_model, temperature=0.3, max_tokens=1024
                    )
                    raw = r["choices"][0]["message"]["content"] or ""
                    # Detect Zhipu content rejection
                    rejected = any(phrase in raw for phrase in (
                        "超出", "能力范围", "建议您尝试其他", "无法", "不支持",
                    ))
                    if rejected and attempt == "zhipu":
                        continue  # 智谱内容审核拒绝 → 降级到 Agnes
                    content = raw
                    break
                except (RuntimeError, OSError, ValueError, KeyError, IndexError):
                    if attempt == "zhipu":
                        continue
                    raise
            if content is None:
                content = "(视觉模型均不可用，请稍后重试)"
        except (KeyError, IndexError):
            content = "(多模态返回格式异常)"
        except Exception as e:
            import httpx
            if isinstance(e, httpx.HTTPStatusError):
                show_error(f"视觉 API 错误 (HTTP {e.response.status_code})，请检查网络或切换供应商")
            else:
                show_error(f"图片理解失败: {type(e).__name__}: {e}")
            return
        console.print(
            Panel(Markdown(content), title=f"[{COLORS['success']}]图片理解[/]", border_style=COLORS["success"])
        )
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
            "视频": "showrunner",
            "做视频": "showrunner",
            "拍片": "showrunner",
            "一键视频": "showrunner",
            "制片": "showrunner",
            "showrunner": "showrunner",
            # ComfyUI
            "作图": "comfyui-bridge",
            "生图": "comfyui-bridge",
            "画画": "comfyui-bridge",
            "comfyui": "comfyui-bridge",
            "本地生图": "comfyui-bridge",
            "炼丹": "comfyui-bridge",
            # 写作
            "写剧本": "script-writer",
            "剧本": "script-writer",
            "写小说": "novel-writer",
            "小说": "novel-writer",
            "写文案": "story-copywriter",
            "文案": "story-copywriter",
            "漫剧": "comic-drama-writer",
            # 视觉
            "视觉导演": "visual-director",
            "分镜": "storyboard-director",
            "运镜": "motion-director",
            "电影化": "cinematic-master",
            "关键帧": "cinematic-keyframe",
            "动作戏": "gaming-action-engine",
            # 工具
            "提示词": "prompt-director",
            "质检": "qc-inspector",
            "模型路由": "model-routing",
            "资产管理": "asset-manager",
            "修复": "recovery-playbooks",
            "世界观": "world-building-engine",
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
            # trigger 态标记：auto 标亮，manual 默认，off 不出现在 list（被 discover 排除）
            _TRIGGER_MARK = {
                "auto": "[bold green]⚡auto[/]",
                "manual": "[dim]手[/]",
            }
            console.print(f"[bold]可用技能 ({len(names)}):[/]")
            console.print("[dim]加载方式: /skill load <中文别名>  如: /skill load 视频[/]")
            console.print("[dim]⚡auto = 自动注入 system prompt · 三态切换: /skill mode <名称> <auto|manual|off>[/]")
            for n in sorted(names):
                s = skills.get(n)
                icon = s.icon + " " if s and s.icon else ""
                desc = s.description if s else ""
                aliases_str = ""
                if n in alias_rev:
                    aliases_str = " [" + "/".join(alias_rev[n][:3]) + "]"
                marker = " [cyan]← 当前[/]" if session.active_skill == n else ""
                trigger_val = session.skills.get_trigger(n)
                trig = _TRIGGER_MARK.get(trigger_val, "[dim]手[/]") if trigger_val else "[dim]手[/]"
                console.print(f"  {icon}[cyan]{n}[/]{aliases_str} {trig} [dim]{desc}{marker}[/]")

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

        elif arg.startswith("mode"):
            # /skill mode <name> <auto|manual|off>
            # /skill mode（无参数）→ 列出全部技能含 off 态 + 当前 trigger
            parts = arg.split()
            if len(parts) == 1:
                # 列出全量（含 off）
                all_skills = session.skills.list_all()
                if not all_skills:
                    show_info("无技能文件")
                    return
                _TRIG_LABEL = {"auto": "⚡auto", "manual": "手 manual", "off": "⊘ off"}
                console.print(f"[bold]全部技能 ({len(all_skills)}) — 含 off 态:[/]")
                console.print("[dim]切换: /skill mode <名称> <auto|manual|off>[/]")
                for s in all_skills:
                    trigger_val = session.skills.get_trigger(s.name)
                    trig = _TRIG_LABEL.get(trigger_val, "?") if trigger_val else "?"
                    icon = s.icon + " " if s.icon else ""
                    console.print(f"  {icon}[cyan]{s.name}[/] [{trig}] [dim]{s.description}[/]")
                return
            if len(parts) < 3:
                show_warning("用法: /skill mode <名称> <auto|manual|off>")
                return
            sname, smode = parts[1], parts[2].lower()
            if session.skills.get_trigger(sname) is None:
                show_warning(f"未找到技能 '{sname}'，/skill mode 查看全部")
                return
            ok = session.skills.set_trigger(sname, smode)
            if ok:
                show_success(f"已设置 {sname} → {smode}")
                # auto 态变化需重建 system prompt 才能生效
                session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
                if smode == "auto":
                    show_info(f"⚡ {sname} 现在会自动注入到 system prompt（所有模式生效）")
                elif smode == "off":
                    show_info(f"⊘ {sname} 已隐藏，不再出现在 /skill list（仍可用 /skill mode 恢复）")
                else:
                    show_info(f"手 {sname} 回到默认，需 /skill load 显式加载")
            else:
                show_warning(f"无效 trigger '{smode}'，可选: auto / manual / off")

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
            show_info("用法: /skill [list|load|create|unload|mode|validate|import <path>]")
            show_info("  /skill mode <名称> <auto|manual|off>  切换技能三态（auto=自动注入提示词）")

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
                model=session.model,
                messages=session.messages,
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
            json_match = re.search(r"\{.*\}", buffer, re.DOTALL)
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

    def _chat_plan_mode(self, session: "ChatSession", arg: str):
        """/plan <目标> — 进入规划审批模式"""
        from core.plan_mode import get_plan_mode_manager

        if not arg or not arg.strip():
            show_warning("用法: /plan <目标描述>")
            return

        pm = get_plan_mode_manager()
        if pm.in_plan_mode:
            show_warning("已在规划模式中，请先 /exit 或审批当前方案")
            return

        show_info(f"正在规划: {arg}")
        plan = pm.enter(arg.strip())

        # 展示方案
        console.print(f"\n[bold green]生成了 {len(plan.options)} 个方案:[/]")
        for i, opt in enumerate(plan.options):
            tag = " [bold yellow](推荐)[/]" if opt.is_recommended else ""
            console.print(f"  [{i}] {opt.label}{tag}")
            if opt.description:
                console.print(f"      [dim]{opt.description}[/]")
            if opt.steps:
                console.print(f"      [dim]步骤数: {len(opt.steps)}[/]")

        console.print("\n[dim]请审核方案后: 输入方案编号审批通过，或 /reject 拒绝[/]")
