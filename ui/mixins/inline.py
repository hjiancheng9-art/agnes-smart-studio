"""Inline 命令 Mixin：简单的内联命令处理器。

这些命令不需要独立的大方法，直接内联处理 session 状态切换。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel

from ui.display import console, COLORS, show_success, show_info

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ['InlineCommandsMixin']


class InlineCommandsMixin:
    # Method provided by SharedMixin (sibling in MRO)
    def _chat_generate(self, session: "ChatSession", kind: str, prompt: str) -> None:
        ...  # defined in CreativeCommandsMixin, available via MRO


    def _inline_clear(self, session, arg: str):
        session.reset()
        show_success("已清空对话历史")

    def _inline_thinking(self, session, arg: str):
        session.enable_thinking = not session.enable_thinking
        state = "开" if session.enable_thinking else "关"
        show_success(f"深度思考已{state}启（仅 pro 模型生效）")

    def _inline_code(self, session, arg: str):
        is_code = session.toggle_code_mode()
        if is_code:
            show_success("🔧 已进入代码助手模式（再输 /code 切回，Ctrl+C 中止运行）")
        else:
            show_success("已退出代码助手，回到普通聊天")

    def _inline_agent(self, session, arg: str):
        is_agent = session.toggle_agent_mode()
        if is_agent:
            cnt = len(session.tools.tool_names)
            show_success(f"🤖 已进入智能体模式，加载了 {cnt} 个工具")
            console.print(f"  [dim]工具: {', '.join(session.tools.tool_names[:8])}[/]")
            console.print("  [dim]再输 /agent 退出 · Ctrl+C 中止运行[/]")
        else:
            show_success("已退出智能体模式，回到普通聊天")

    def _inline_tools(self, session, arg: str):
        names = session.tools.tool_names
        if names:
            console.print(f"[dim]已注册 {len(names)} 个工具:[/]")
            for n in names:
                console.print(f"  [cyan]{n}[/]")
        else:
            show_info("当前无可用工具，创建 tools.json 来添加")

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
