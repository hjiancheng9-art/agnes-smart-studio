"""任务工程命令 Mixin：规划/子智能体/压缩/项目/团队/部署/TODO/重构。"""

import os
import re
from datetime import datetime
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from ui.display import console, show_info, show_success, show_warning, show_error
from ui.render import StreamingRenderer
from ui.badges import print_reply_header, print_route_reason
from core.router import route_command, resolve, apply

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ['EngineeringCommandsMixin']



class EngineeringCommandsMixin:
    pass  # 占位，下方方法会替换


    def _chat_plan(self, session: "ChatSession", task: str):
        """先规划再执行：让 LLM 输出计划 → 解析步骤 → 逐步执行"""
        if not task:
            show_warning("用法: /plan <任务描述>")
            return
        from core.agent import PLAN_PROMPT, parse_plan

        # 智能路由：plan 命令走命令路由表，自动选最优模型
        decision = route_command("plan", task, session)
        if decision.profile.value != "skip" and decision.model_id:
            apply(decision, session)
        session.enable_thinking = True

        show_info(f"正在制定计划: {task[:40]}...")
        plan_msg = f"{PLAN_PROMPT}\n\n用户任务: {task}\n请输出计划并开始执行。"
        session.messages.append({"role": "user", "content": plan_msg})

        # 流式输出计划（经 StreamingRenderer 单一落盘点，杜绝重复）
        buffer = ""
        renderer = StreamingRenderer(console)
        # badge 头：/plan 经 route_command 切到 deepseek-v4-pro + thinking，
        # 在 transient Live 启动前先打印当前模式，让用户看到状态变化。
        print_reply_header(session)
        renderer.start()
        try:
            for delta in session.client.chat_stream(
                model=session.model, messages=session.messages,
                max_tokens=3072,
            ):
                if "content" in delta and delta["content"]:
                    buffer += delta["content"]
                    renderer.append_text(delta["content"])
        except (RuntimeError, OSError, KeyError) as e:
            renderer.stop()
            renderer.commit()  # 固化已生成的半截计划（transient 浮层被擦除后，让用户看到已有内容）
            show_error(f"计划生成失败: {e}")
            session.messages.pop()
            return

        renderer.stop()
        renderer.commit()  # 单一落盘：固化末尾增量（无增量时空操作）
        console.print()    # 结尾换行（习惯性空行分隔）
        session.messages.append({"role": "assistant", "content": buffer})

        steps = parse_plan(buffer)
        if steps:
            console.print(f"\n[dim]解析到 {len(steps)} 个步骤[/]")

    def _chat_subagent(self, session: "ChatSession", task: str):
        """启动子智能体处理独立任务"""
        if not task:
            show_warning("用法: /sub <子任务描述>")
            return
        from core.agent import spawn_subagent

        # 智能路由：sub 命令走命令路由表，自动选最优模型
        decision = route_command("sub", task, session)
        if decision.profile.value != "skip" and decision.model_id:
            apply(decision, session)
            print_reply_header(session)
            if decision.reason:
                print_route_reason(decision.reason)

        show_info(f"子智能体启动: {task[:40]}...")
        result = spawn_subagent(session.client, task, model=session.model)
        console.print(Panel(result[:2000], title="[cyan]子智能体结果[/]"))

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
        result = run_team(session.client, team_type, context, model=session.model)

        if "error" in result:
            show_error(result["error"])
            return

        console.print(Panel(result["summary"][:2000], title=f"[cyan]{result['team']}[/]"))

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
        console.print(Panel(result[:1000] or "[无输出]", title="[cyan]部署结果[/]"))

    def _chat_todo(self, session: "ChatSession", arg: str):
        """扫描项目中待办标记 (TODO/FIXME/HACK/XXX/OPTIMIZE/BUG) — 纯 Python 实现"""
        import os
        import re
        path = arg.strip() or "."
        show_info(f"扫描 {path} 中的 TODO/FIXME/HACK/XXX ...")
        markers = re.compile(r'TODO|FIXME|HACK|XXX|OPTIMIZE|BUG')
        exts = ('.py', '.js', '.ts', '.md', '.html', '.css', '.sh', '.bat')
        skip_dirs = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'output', '.codebuddy'}
        results = []
        try:
            for dp, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
                for f in files:
                    if not f.endswith(exts):
                        continue
                    fp = os.path.join(dp, f)
                    try:
                        with open(fp, encoding='utf-8', errors='replace') as fh:
                            for n, line in enumerate(fh, 1):
                                if markers.search(line):
                                    results.append(f"{os.path.relpath(fp)}:{n}: {line.strip()[:120]}")
                    except (OSError, PermissionError):
                        pass
            if results:
                show_warning(f"发现 {len(results)} 个待办:")
                for item in results[:20]:
                    console.print(f"  [dim]{item}[/]")
            else:
                show_success("无待办项")
        except (RuntimeError, OSError, ValueError) as e:
            show_error(str(e))

    def _chat_refactor(self, session: "ChatSession", arg: str):
        """批量重命名/替换文本（不可逆，确认后执行）- 纯 Python 实现，无 shell 风险"""
        parts = arg.strip().split(" ", 2)
        if len(parts) < 2:
            show_warning("用法: /refactor <旧名> <新名> [路径]")
            return
        old, new, path = parts[0], parts[1], parts[2] if len(parts) > 2 else "."
        show_info(f"将 {path} 中的 '{old}' 替换为 '{new}' (仅 .py/.js/.ts/.md)")

        show_warning("⚠ 批量替换不可逆")
        if not Confirm.ask("确认执行?", default=False):
            return
        import os
        allowed_exts = ('.py', '.js', '.ts', '.md')
        count = 0
        try:
            for dp, _, files in os.walk(path):
                if '.git' in dp or '__pycache__' in dp or '.codebuddy' in dp:
                    continue
                for f in files:
                    if not f.endswith(allowed_exts):
                        continue
                    fp = os.path.join(dp, f)
                    try:
                        with open(fp, encoding='utf-8') as fh:
                            content = fh.read()
                    except (OSError, PermissionError):
                        continue
                    if old not in content:
                        continue
                    new_content = content.replace(old, new)
                    try:
                        with open(fp, 'w', encoding='utf-8') as fh:
                            fh.write(new_content)
                        count += 1
                    except (OSError, PermissionError):
                        pass
            show_success(f"替换完成: {count} 个文件 (检查 git diff 确认)")
        except (RuntimeError, OSError, ValueError) as e:
            show_error(str(e))
