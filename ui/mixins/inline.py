"""Inline 命令 Mixin：简单的内联命令处理器。

这些命令不需要独立的大方法，直接内联处理 session 状态切换。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel

from ui.badges import print_mode_banner
from ui.display import show_info, show_success, show_warning
from ui.theme import COLORS, LAYOUT, console

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ["InlineCommandsMixin"]


class InlineCommandsMixin:
    # Method provided by SharedMixin (sibling in MRO)
    def _chat_generate(
        self, session: ChatSession, kind: str, prompt: str
    ) -> None: ...  # defined in CreativeCommandsMixin, available via MRO

    def _inline_clear(self, session, arg: str):
        session.reset()
        show_success("Conversation history cleared")

    def _inline_thinking(self, session, arg: str):
        session.enable_thinking = not session.enable_thinking
        state = "on" if session.enable_thinking else "off"
        show_success(f"Deep thinking {state} (pro models only)")
        print_mode_banner(session)

    def _inline_code(self, session, arg: str):
        is_code = session.toggle_code_mode()
        if is_code:
            show_success("🌿 Code mode enabled (type /code again to exit, Ctrl+C to stop)")
        else:
            show_success("Exited code mode, back to general chat")
        print_mode_banner(session)

    def _inline_agent(self, session, arg: str):
        is_agent = session.toggle_agent_mode()
        if is_agent:
            cnt = len(session.tools.tool_names)
            show_success(f"🧬 Agent mode enabled, loaded {cnt} tools")
            console.print(f"  [dim]Tools: {', '.join(session.tools.tool_names[:8])}[/]")
            console.print("  [dim]Type /agent again to exit · Ctrl+C to stop[/]")
            # Capability hint: suggest switching if current model doesn't support tool calling
            if not session.supports_tools:
                show_warning(
                    f"Current model {session.model} doesn't support tool calling, "
                    "agent dispatch will degrade to pure text reasoning. Use /model to switch to a tools-capable model (e.g. deepseek-v4-pro)."
                )
        else:
            show_success("Exited agent mode, back to general chat")
        print_mode_banner(session)

    def _inline_tools(self, session, arg: str):
        arg = (arg or "").strip()
        if arg.startswith("score"):
            self._tool_scorecard(session, arg[len("score") :].strip())
            return

        names = session.tools.tool_names
        if names:
            console.print(f"[dim]{len(names)} registered tools:[/]")
            for n in names:
                console.print(f"  [{COLORS['primary']}]{n}[/]")
            console.print("  [dim]提示: /tools score 查看工具健康度评分[/]")
        else:
            show_info("No tools available, create tools.json to add")

    def _tool_scorecard(self, session, arg: str):
        """工具评分看板 — 静态健康度 + 运行时质量。

        用法:
            /tools score          静态评分表格（测试/schema/风险/可达性）
            /tools score runtime  运行时评分（基于 tool_calls.jsonl）
            /tools score json     JSON 格式输出（CI/CD 集成）
            /tools score <name>   单工具详情
        """
        from rich.table import Table

        try:
            from core.tool_scorecard import (
                save_report,
                score_all,
                score_tool_static,
            )
        except ImportError:
            show_info("tool_scorecard 模块不可用")
            return

        # 子模式：json / runtime / <tool_name>
        output_json = arg.lower() == "json"
        show_runtime = arg.lower() == "runtime"
        single_tool = ""
        if arg and not output_json and not show_runtime:
            single_tool = arg.split()[0]

        # 生成报告（含运行时分，若有日志数据）
        try:
            from core import tool_call_log

            runtime_calls = tool_call_log.group_by_tool()
        except ImportError:
            runtime_calls = None

        report = score_all(session.tools, runtime_calls=runtime_calls)
        save_report(report)  # 持久化到 output/tool_scorecard.json

        # ── 单工具详情 ──
        if single_tool:
            if not session.tools.has(single_tool) and single_tool not in session.tools.tool_names:
                show_info(f"未找到工具: {single_tool}")
                return
            s = next((t for t in report["tools"] if t["name"] == single_tool), None)
            if not s:
                s = score_tool_static(single_tool, session.tools)
            console.print(
                Panel(
                    f"[bold cyan]{s['name']}[/]  ·  [bold]{s['score']}/100[/]  ·  等级 [bold]{s['grade']}[/]",
                    border_style=COLORS["primary"],
                )
            )
            dt = Table(title="维度详情", border_style="dim", show_lines=True)
            dt.add_column("维度", style="cyan", width=18)
            dt.add_column("得分", justify="right", width=10)
            dt.add_column("满分", justify="right", width=8)
            dt.add_column("说明")
            for dim_name, info in s["dimensions"].items():
                dt.add_row(dim_name, str(info["score"]), str(info["max"]), info["detail"])
            console.print(dt)
            if "runtime" in s and s["runtime"].get("score") is not None:
                rt = s["runtime"]
                console.print(
                    f"  [dim]运行时: {rt['score']}分({rt['grade']}) · "
                    f"{rt['call_count']}次调用 · 成功率{rt['success_rate']}% · "
                    f"均耗{rt['avg_ms']}ms · P95 {rt['p95_ms']}ms[/]"
                )
            return

        # ── JSON 输出 ──
        if output_json:
            import json

            console.print_json(json.dumps(report, ensure_ascii=False))
            return

        # ── 汇总表 ──
        summary = Table(title="[bold]📊 工具评分总览[/]", border_style=COLORS["primary"], show_lines=True)
        summary.add_column("指标", style="bold cyan", width=16)
        summary.add_column("值", justify="right")
        gd = report["grade_distribution"]
        summary.add_row("工具总数", str(report["total_tools"]))
        summary.add_row("平均分", f"{report['average_score']}/100")
        summary.add_row(
            "分级分布", f"A {gd.get('A', 0)} · B {gd.get('B', 0)} · C {gd.get('C', 0)} · D {gd.get('D', 0)}"
        )
        summary.add_row("零测试工具", f"{report['untested_count']} 个")
        summary.add_row("最差 TOP5", " · ".join(report["worst_5"]))
        console.print(summary)

        # ── 静态/运行时明细表 ──
        if show_runtime:
            title = "[bold]📈 运行时质量评分[/] (基于 tool_calls.jsonl)"
            detail = Table(title=title, border_style="dim", show_lines=True)
            detail.add_column("工具", style="cyan", width=20)
            detail.add_column("运行时分", justify="right", width=8)
            detail.add_column("等级", justify="center", width=4)
            detail.add_column("调用数", justify="right", width=6)
            detail.add_column("成功率", justify="right", width=8)
            detail.add_column("均耗时", justify="right", width=10)
            detail.add_column("P95", justify="right", width=8)
            detail.add_column("参数失败", justify="right", width=8)
            rows = [t for t in report["tools"] if "runtime" in t and t["runtime"].get("score") is not None]
            rows.sort(key=lambda x: x["runtime"]["score"])
            if not rows:
                show_info("暂无运行时数据，请先执行一些工具调用（output/tool_calls.jsonl 为空）")
                return
            for t in rows[:30]:
                rt = t["runtime"]
                grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}.get(rt["grade"], "white")
                detail.add_row(
                    t["name"],
                    f"{rt['score']}",
                    f"[{grade_color}]{rt['grade']}[/]",
                    str(rt["call_count"]),
                    f"{rt['success_rate']}%",
                    f"{rt['avg_ms']}ms",
                    f"{rt['p95_ms']}ms",
                    f"{rt['arg_fail_rate']}%",
                )
            console.print(detail)
        else:
            title = "[bold]🔧 工具健康度评分[/] (静态: 测试/schema/风险/可达性)"
            detail = Table(title=title, border_style="dim", show_lines=True)
            detail.add_column("工具", style="cyan", width=22)
            detail.add_column("总分", justify="right", width=6)
            detail.add_column("等级", justify="center", width=4)
            detail.add_column("测试", justify="right", width=6)
            detail.add_column("Schema", justify="right", width=7)
            detail.add_column("风险", justify="right", width=6)
            detail.add_column("可达", justify="right", width=6)
            # 按总分升序（最差在前），便于优先关注
            for t in sorted(report["tools"], key=lambda x: x["score"])[:40]:
                grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}.get(t["grade"], "white")
                d = t["dimensions"]
                detail.add_row(
                    t["name"],
                    f"{t['score']}",
                    f"[{grade_color}]{t['grade']}[/]",
                    f"{d['test_coverage']['score']}",
                    f"{d['schema']['score']}",
                    f"{d['risk']['score']}",
                    f"{d['reachability']['score']}",
                )
            console.print(detail)

        # ── 零测试清单（如果不多，全列；多则给数字）──
        if report["untested_count"] and report["untested_count"] <= 30:
            console.print(f"  [yellow]⚠ 零测试工具 ({report['untested_count']}):[/] " + " · ".join(report["untested"]))
        console.print(
            "  [dim]报告已保存: output/tool_scorecard.json · "
            "更多: /tools score runtime | /tools score json | /tools score <name>[/]"
        )

    def _inline_browser(self, session, arg: str):
        is_on = session.toggle_browser()
        if is_on:
            cnt = len([n for n in session.tools.tool_names if n.startswith("browser_")])
            show_success(f"🌐 Browser Companion enabled ({cnt} tools: generate/check/download/providers/setup/cancel)")
            console.print("  [dim]Covers 8 platforms: Kling/Dreamina/Runway/Luma/DALL-E/Gemini/Opal/Veo[/]")
            console.print("  [dim]Run browser_setup to login first, type /browser again to close[/]")
        else:
            show_success("Browser Companion disabled, back to general chat")
        print_mode_banner(session)

    def _chat_help_inline(self, session, show_all: bool = False):
        """Inline wrapper: /help → _chat_help (保持与原始接口兼容)。"""
        self._chat_help(session.model, session.enable_thinking, session.code_mode, show_all=show_all)

    def _chat_img_inline(self, session, arg: str):
        """/img → _chat_generate(image)。"""
        self._chat_generate(session, "image", arg)

    def _chat_video_inline(self, session, arg: str):
        """/video → _chat_generate(video)。"""
        self._chat_generate(session, "video", arg)

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
                "/eval [json]       /browser",
                "/extend <nb|au>    /cost [budget]",
                "/mcp <cmd>         /clear",
                "/exit",
            ]
            text = "\n".join(cmds)
            cap = "AI auto" if current_model == "agnes-2.0-flash" else "manual"
            console.print(
                Panel(
                    text,
                    title=f"[bold {COLORS['primary']}]33 commands[/] ({current_model} | think:{think_state} | {cap})",
                    border_style=COLORS["primary"],
                    padding=LAYOUT["panel_padding"],
                )
            )
            return
        console.print(
            Panel(
                f"""\
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
    /eval [json]       运行智能体质量基准测试
    /extend <nb|au>    切换扩展工具集（notebook/audio/browser）
    /browser           Browser Companion 网页生成（8 平台开关）
    /cost [budget]     查看花费 / 设日预算
    /mcp <cmd>         MCP 服务器管理 (list/add/remove/connect/disconnect/tools)
    /clear             清空对话历史
    /exit              退出聊天

    当前模型: {current_model} | 模式: {code_state}
    能力: {"AI 可自动触发生成" if current_model == "agnes-2.0-flash" else "需用 /img /video 手动生成"} | 视觉: {"独立通道可用" if current_model != "agnes-1.5-flash" else "主模型内置"}
    供应商: /provider switch agnes|deepseek|siliconflow""",
                title=f"[bold {COLORS['accent']}]✿ Chat commands[/]",
                border_style=COLORS["primary"],
                padding=LAYOUT["panel_padding"],
            )
        )
