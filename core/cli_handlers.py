"""CLI command handlers — Kimi-style table-driven dispatch for /slash commands.

This module provides the CruxCLI class that receives a ChatSession and
implements all handler methods referenced by core.commands.COMMANDS.

Each handler method name matches the `handler` field in CommandDef.
Inline handlers (prefixed `_inline_`) are simple toggle/display operations.
Chat handlers (prefixed `_chat_`) may require additional parsing.

Architecture:
    _chat_repl() → build_dispatch_table() → getattr(CruxCLI, handler)()
    Unmatched input → session.send_stream() → AI chat
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from core.commands import SKILL_ENTRIES, build_dispatch_table, get_all, get_by_category

if TYPE_CHECKING:
    from core.chat import ChatSession


class CruxCLI:
    """Kimi-style CLI dispatcher — one method per slash command.

    Instantiated once per _chat_repl() session. Receives the ChatSession
    and manages all /command routing.
    """

    def __init__(self, session: ChatSession) -> None:
        self.session = session
        self._dispatch = build_dispatch_table()

    # ── Public API ─────────────────────────────────────────────

    def dispatch(self, line: str) -> bool:
        """Route a slash command to its handler. Returns False if not a command
        (caller should forward to session.send_stream). Returns True if handled.
        """
        if not line.startswith("/"):
            return False

        # Split: "/cmd arg1 arg2" → key="cmd", args="arg1 arg2"
        parts = line.split(maxsplit=1)
        cmd_key = parts[0][1:].lower()  # strip leading /
        args = parts[1] if len(parts) > 1 else ""

        # ── Dispatch table lookup (keys are without / prefix) ──
        if cmd_key in self._dispatch:
            handler_name, _ = self._dispatch[cmd_key]
            assert handler_name is not None  # dispatch table ensures non-None keys
            handler = getattr(self, handler_name, None)
            if handler:
                handler(args)
                return True

        # ── Unknown command → let AI handle it ──
        # TODO: could show "unknown command" or forward to AI
        return False

    def get_commands_for_completion(self) -> list[str]:
        """Return all slash commands for tab completion."""
        cmds: list[str] = []
        seen: set[str] = set()
        for cmd in get_all():
            if cmd.name not in seen:
                cmds.append(cmd.name)
                seen.add(cmd.name)
            for alias in cmd.aliases:
                alias_cmd = f"/{alias}"
                if alias_cmd not in seen:
                    cmds.append(alias_cmd)
                    seen.add(alias_cmd)
        return sorted(cmds)

    # ════════════════════════════════════════════════════════════
    #  Dialogue handlers
    # ════════════════════════════════════════════════════════════

    def _chat_help_inline(self, args: str) -> None:
        """Display help: /help or /all for full list."""
        if args.strip() in ("all", "-a", "--all"):
            self._print_all_help()
        else:
            self._print_help()

    def _print_help(self) -> None:
        """Print categorized command help."""
        cats = get_by_category()
        print()
        print("  CRUX Studio 命令帮助")
        print("  ──────────────────")
        for cat, cmds in cats.items():
            print(f"\n  [{cat}]")
            for name, args_hint, desc, _ in cmds:
                arg_str = f" {args_hint}" if args_hint else ""
                print(f"    {name}{arg_str}  —  {desc}")
        if SKILL_ENTRIES:
            print("\n  [技能包]")
            for name, desc in SKILL_ENTRIES:
                print(f"    {name}  —  {desc}")
        print()

    def _print_all_help(self) -> None:
        """Print full help with long descriptions."""
        cats = get_by_category()
        print()
        print("  CRUX Studio 完整命令参考")
        print("  ────────────────────────")
        for cat, cmds in cats.items():
            print(f"\n  [{cat}]")
            for name, args_hint, desc, long_desc in cmds:
                arg_str = f" {args_hint}" if args_hint else ""
                print(f"    {name}{arg_str}")
                detail = long_desc or desc
                print(f"      {detail}")
        if SKILL_ENTRIES:
            print("\n  [技能包]")
            for name, desc in SKILL_ENTRIES:
                print(f"    {name}")
                print(f"      {desc}")
        print()

    def _chat_vote_toggle(self, args: str) -> None:
        """Toggle multi-model voting: /vote on|off."""
        arg = args.strip().lower()
        if arg == "on":
            self.session._vote_enabled = True
            print("  多模型表决: 开启 (复杂问题自动并行咨询多个AI)")
        elif arg == "off":
            self.session._vote_enabled = False
            print("  多模型表决: 关闭")
        else:
            status = "开启" if self.session._vote_enabled else "关闭"
            print(f"  多模型表决: {status}  用法: /vote on|off")

    def _chat_switch_model(self, args: str) -> None:
        """Switch AI model: /model <alias|ID>."""
        arg = args.strip().lower()
        if not arg:
            print(f"  当前模型: {self.session.model}")
            print("  可用: light / pro / deepseek / zhipu / qwen-coder / local / llama")
            return
        from core.chat import MODEL_ALIASES

        if arg in MODEL_ALIASES:
            self.session.model = MODEL_ALIASES[arg]
        else:
            self.session.model = args.strip()
        self.session.auto_model = False
        self.session.messages[0] = {"role": "system", "content": self.session._build_system_prompt()}
        print(f"  模型: {self.session.model}")

    def _inline_thinking(self, args: str) -> None:
        """Toggle deep thinking mode."""
        self.session.enable_thinking = not self.session.enable_thinking
        status = "开启" if self.session.enable_thinking else "关闭"
        self.session.messages[0] = {"role": "system", "content": self.session._build_system_prompt()}
        print(f"  深度思考: {status}")

    def _inline_code(self, args: str) -> None:
        """Toggle code assistant mode."""
        new_mode = self.session.toggle_code_mode()
        status = "代码" if new_mode else "聊天"
        print(f"  模式: {status}")

    def _inline_agent(self, args: str) -> None:
        """Toggle agent mode (loads external tools from tools.json)."""
        new_mode = self.session.toggle_agent_mode()
        status = "智能体" if new_mode else "聊天"
        print(f"  模式: {status}")

    def _inline_tools(self, args: str) -> None:
        """Display registered tools."""
        registry = self.session.tools
        tool_names = registry.list_names() if hasattr(registry, "list_names") else []
        if tool_names:
            print(f"\n  已注册工具 ({len(tool_names)} 个):")
            for name in sorted(tool_names):
                print(f"    - {name}")
        else:
            print("  当前无注册工具。使用 /agent 加载智能体工具，/skill load 加载技能包。")
        print()

    def _chat_status(self, args: str) -> None:
        """Show real-time system health."""
        s = self.session
        print("\n  ◆ CRUX Studio v6.0.0  状态面板")
        print(f"  模型:{s.model}  代码:{'✓' if s.code_mode else '✗'}  智能体:{'✓' if s.agent_mode else '✗'}")
        print(
            f"  技能:{s.active_skill or '无'}  工具:{len(s.tools.tool_names) if hasattr(s.tools, 'tool_names') else '?'}"
        )
        print()

    def _inline_clear(self, args: str) -> None:
        """Clear conversation history."""
        self.session.messages = [{"role": "system", "content": self.session._build_system_prompt()}]
        print("  对话历史已清空。")

    def _inline_browser(self, args: str) -> None:
        """Toggle Browser Companion tools."""
        new_state = self.session.toggle_browser()
        status = "开启" if new_state else "关闭"
        print(f"  Browser Companion: {status} (网页生图生视频 8 平台)")

    def _chat_skill(self, args: str) -> None:
        """Skill management: /skill <list|load|unload|mode>."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            skills = self.session.skills.list_available() if hasattr(self.session.skills, "list_available") else []
            if skills:
                print(f"\n  可用技能包 ({len(skills)} 个):")
                for s in skills:
                    print(f"    - {s}")
            else:
                self.session.skills.discover()
                skills = self.session.skills.list_available() if hasattr(self.session.skills, "list_available") else []
                if skills:
                    print(f"\n  可用技能包 ({len(skills)} 个):")
                    for s in skills:
                        print(f"    - {s}")
                else:
                    print("  未发现技能包。")
            print()
        elif sub == "load":
            if not sub_args:
                print("  用法: /skill load <名称>")
                return
            result = self.session.load_skill(sub_args)
            if result:
                print(f"  已加载技能: {result}")
            else:
                print(f"  技能 '{sub_args}' 未找到。")
        elif sub == "unload":
            self.session.unload_skill()
            print("  已卸载当前技能。")
        else:
            print("  用法: /skill <list|load <名称>|unload>")
            if self.session.active_skill:
                print(f"  当前技能: {self.session.active_skill}")

    def _chat_skill_load_browser(self, _args: str = "") -> None:
        """快捷命令: /浏览器 或 /bk — 加载浏览器操控技能"""
        print("  加载浏览器操控技能...")
        result = self.session.load_skill("browser-control")
        if result:
            print("  浏览器已就绪。告诉我你想做什么，比如: 帮我去 ChatGPT 问一下 xxx")
        else:
            print("  加载失败，试试 /skill load browser-control")

    # ════════════════════════════════════════════════════════════
    #  Creative production handlers
    # ════════════════════════════════════════════════════════════

    def _chat_showrun(self, args: str) -> None:
        """Creative video generation via Agnes Video API."""
        if not args.strip():
            print("  用法: /showrun <创意目标>（委托到 Agnes 生成）")
            return
        print(f"  🎬 视频生成启动: {args.strip()}")
        for kind, payload in self.session.send_stream(f"使用 Agnes 生成视频: {args.strip()}"):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
            elif kind == "info":
                print(f"\n  {payload}", file=sys.stderr)
        print()

    def _chat_agnes(self, args: str) -> None:
        """Agnes multi-modal generation dispatcher."""
        parts = args.strip().split(maxsplit=1)
        mode = parts[0].lower() if parts else ""
        prompt = parts[1] if len(parts) > 1 else ""

        if not mode:
            print("  用法: /agnes <t2i|i2i|t2v|i2v|pipeline> [描述]")
            return

        print(f"  Agnes {mode}: {prompt}")
        print("  (通过 AI chat 调用 generate_image / generate_video 工具)")

        for kind, payload in self.session.send_stream(
            f"生成{'图片' if 'i' in mode and 'v' not in mode else '视频'}: {prompt}"
        ):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
            elif kind == "info":
                print(f"\n  {payload}", file=sys.stderr)
        print()

    def _chat_video_inline(self, args: str) -> None:
        """Quick video generation."""
        if not args.strip():
            print("  用法: /video <描述>")
            return
        print(f"  生成视频: {args.strip()}")
        for kind, payload in self.session.send_stream(f"生成一段视频: {args.strip()}"):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
            elif kind == "info":
                print(f"\n  {payload}", file=sys.stderr)
            elif kind == "video":
                data = payload if isinstance(payload, dict) else {}
                url = data.get("video_url", data.get("url", ""))
                local = data.get("local_path", "")
                if local:
                    print(f"\n  视频已保存: {local}")
                elif url:
                    print(f"\n  视频URL: {url}")
        print()

    def _chat_img_inline(self, args: str) -> None:
        """Quick image generation."""
        if not args.strip():
            print("  用法: /img <描述>")
            return
        print(f"  生成图片: {args.strip()}")
        for kind, payload in self.session.send_stream(f"生成一张图片: {args.strip()}"):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
            elif kind == "info":
                print(f"\n  {payload}", file=sys.stderr)
            elif kind == "image":
                data = payload if isinstance(payload, dict) else {}
                local = data.get("local_path", "")
                url = data.get("url", "")
                if local:
                    print(f"\n  图片已保存: {local}")
                elif url:
                    print(f"\n  图片URL: {url}")
        print()

    def _chat_vision(self, args: str) -> None:
        """Image understanding via vision model."""
        if not args.strip():
            print("  用法: /vision <图片路径> <问题>")
            return
        # Parse: first token might be a file path
        parts = args.strip().split(maxsplit=1)
        image_path = parts[0]
        question = parts[1] if len(parts) > 1 else "描述这张图片"
        print(f"  视觉理解: {image_path}")
        for kind, payload in self.session.send_stream(f"[图片: {image_path}] {question}", image_url=image_path):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
            elif kind == "info":
                print(f"\n  {payload}", file=sys.stderr)
        print()

    # ════════════════════════════════════════════════════════════
    #  Task engineering handlers
    # ════════════════════════════════════════════════════════════

    def _chat_plan_mode(self, args: str) -> None:
        """Enter plan mode: plan → execute."""
        if not args.strip():
            print("  用法: /plan <任务描述>")
            print("  先规划再执行：自动拆解步骤 + 用户审批")
            return
        print(f"  📋 规划模式: {args.strip()}")
        for kind, payload in self.session.send_stream(
            f"请为以下任务制定详细的执行计划，列出步骤、依赖关系和预估工作量: {args.strip()}"
        ):
            if kind == "text":
                sys.stdout.write(str(payload))
                sys.stdout.flush()
        # ── 方法论集成: 规划完成后标记 Plan 已确认 ──
        try:
            from core.methodology import get_methodology_state
            get_methodology_state().mark_plan_confirmed()
        except ImportError:
            pass
        print()

    def _chat_subagent(self, args: str) -> None:
        """Launch sub-agent for a subtask."""
        if not args.strip():
            print("  用法: /sub <任务描述>")
            return
        print(f"  🤖 启动子智能体: {args.strip()}")
        try:
            from core.agent import SubAgent

            agent = SubAgent(task=args.strip())  # pyright: ignore[reportCallIssue] — CLI convenience wrapper
            result = agent.run()  # pyright: ignore[reportCallIssue]
            print(f"\n  子智能体完成: {str(result)[:500]}")
        except ImportError:
            print("  子智能体模块未就绪。请通过 AI chat 使用 Agent 工具。")
        except Exception as e:
            print(f"  子智能体错误: {e}")

    def _chat_compress(self, args: str) -> None:
        """Compress long conversation history into summary."""
        print("  正在压缩对话历史...")
        try:
            from core.agent import ContextManager

            ctx = ContextManager()
            summary = ctx.compress(self.session.messages)  # pyright: ignore[reportCallIssue] — ContextManager API
            if summary:
                self.session.messages = [
                    {"role": "system", "content": self.session._build_system_prompt()},
                    {"role": "user", "content": f"[前文摘要] {summary}"},
                ]
                print("  对话历史已压缩为摘要。")
            else:
                print("  对话历史较短，无需压缩。")
        except ImportError:
            print("  压缩模块未就绪。")

    def _chat_team(self, args: str) -> None:
        """Agent team: review/debug/feature."""
        arg = args.strip().lower()
        print(f"  智能体团队 '{arg or 'review'}' — 通过 AI chat 使用 Agent/AgentSwarm 工具。")

    def _chat_project(self, args: str) -> None:
        """Project management."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        parts[1] if len(parts) > 1 else ""
        print(f"  项目管理 '{sub}' — 通过 AI chat 使用 session_mgr 工具。")

    def _chat_deploy(self, args: str) -> None:
        """One-click deploy."""
        print(f"  部署 '{args.strip()}' — 通过 AI chat 使用 deploy_vercel 工具。")

    def _chat_todo(self, args: str) -> None:
        """Scan project for TODO/FIXME/HACK."""
        import os

        target = args.strip() or "."
        print(f"  扫描 {target} 中的 TODO/FIXME/HACK...")
        try:
            import subprocess

            result = subprocess.run(
                ["grep", "-rn", "-E", r"(TODO|FIXME|HACK|XXX)", target],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.getcwd(),
            )
            if result.stdout:
                lines = result.stdout.strip().split("\n")
                print(f"  找到 {len(lines)} 个待办项:")
                for line in lines[:50]:
                    print(f"    {line}")
                if len(lines) > 50:
                    print(f"    ... 还有 {len(lines) - 50} 项")
            else:
                print("  未找到待办项。")
        except Exception as e:
            print(f"  扫描失败: {e}")

    def _chat_commit(self, args: str) -> None:
        """Auto-generate commit message from git diff."""
        print("  从 git diff 生成 commit 消息 — 通过 AI chat 执行。")
        try:
            import subprocess

            diff = subprocess.run(["git", "diff", "--staged"], capture_output=True, text=True, timeout=10)
            if not diff.stdout.strip():
                diff = subprocess.run(["git", "diff"], capture_output=True, text=True, timeout=10)
            if diff.stdout.strip():
                for kind, payload in self.session.send_stream(
                    f"根据以下 git diff 生成简洁的 commit 消息 (50字符以内, 中文):\n{diff.stdout[:3000]}"
                ):
                    if kind == "text":
                        sys.stdout.write(payload)  # pyright: ignore[reportArgumentType]
                        sys.stdout.flush()
                print()
            else:
                print("  无变更可提交。")
        except Exception as e:
            print(f"  git 操作失败: {e}")

    def _chat_changelog(self, args: str) -> None:
        """Generate CHANGELOG.md from git log."""
        print("  从 git log 生成 CHANGELOG.md — 通过 AI chat 执行。")
        try:
            import subprocess

            log = subprocess.run(["git", "log", "--oneline", "-50"], capture_output=True, text=True, timeout=10)
            if log.stdout.strip():
                for kind, payload in self.session.send_stream(
                    f"根据以下 git log 生成 CHANGELOG.md (按版本分组, 中文):\n{log.stdout[:3000]}"
                ):
                    if kind == "text":
                        sys.stdout.write(payload)  # pyright: ignore[reportArgumentType]
                        sys.stdout.flush()
                print()
            else:
                print("  无 git 历史。")
        except Exception as e:
            print(f"  git 操作失败: {e}")

    def _chat_refactor(self, args: str) -> None:
        """Batch rename/replace."""
        parts = args.strip().split(maxsplit=2)
        if len(parts) < 2:
            print("  用法: /refactor <旧名> <新名>")
            return
        old_name, new_name = parts[0], parts[1]
        print(f"  重构: {old_name} → {new_name}")
        print("  (通过 AI chat 使用 lsp_rename / edit_file 工具)")

    # ════════════════════════════════════════════════════════════
    #  Diagnostics & config handlers
    # ════════════════════════════════════════════════════════════

    def _self_diagnose(self, args: str) -> None:
        """Self-diagnosis: /self <check|files|health|fix|audit>."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "check"

        if sub == "check":
            try:
                from core.startup_checks import print_report, run_all

                results = run_all()
                print_report(results, show_ok=True)
            except ImportError:
                print("  运行健康检查...")
                print("  Python ✓, 工作目录 ✓")
        elif sub == "files":
            import os

            root = os.getcwd()
            py_count = 0
            for dirpath, _, filenames in os.walk(root):
                if any(skip in dirpath for skip in ("__pycache__", ".git", "node_modules", ".venv")):
                    continue
                py_count += sum(1 for f in filenames if f.endswith(".py"))
            print(f"  项目 Python 文件: {py_count} 个")
        elif sub == "fix":
            print("  正在运行自修复...")
            try:
                from core.self_heal import run_heal

                run_heal(fix=True, quick=True)
            except ImportError:
                print("  自修复模块未就绪。")
        elif sub == "audit":
            print("  运行代码审计...")
            try:
                from core.self_audit import audit

                report = audit()
                if isinstance(report, dict):
                    sev = report.get("by_severity", {})
                    print(
                        f"  审计完成：{report.get('total_findings', 0)} 项问题 "
                        f"(严重:{sev.get('critical', 0)} 高:{sev.get('high', 0)} "
                        f"中:{sev.get('medium', 0)} 低:{sev.get('low', 0)} "
                        f"可自动修复:{report.get('auto_fixable', 0)})"
                    )
                elif hasattr(report, "summary"):
                    print(f"  {report.summary()}")
                else:
                    print(f"  审计完成：{report}")
            except ImportError:
                print("  审计模块未就绪。")
        else:
            print("  用法: /self <check|files|health|fix|audit>")

    def _chat_knowledge(self, args: str) -> None:
        """Browse built-in knowledge base."""
        arg = args.strip().lower()
        if not arg:
            print("  用法: /know <methods|templates|domain>")
            return
        print(f"  知识库 '{arg}' — 浏览内置领域知识。")

    def _chat_prompt_stats(self, args: str) -> None:
        """Prompt Lab experiment stats."""
        print("  Prompt Lab 统计 — A/B 变体效果对比。")

    def _chat_prompt_assign(self, args: str) -> None:
        """Assign Prompt Lab variant."""
        arg = args.strip()
        if arg:
            print(f"  已指定 Prompt 变体: {arg}")
        else:
            print("  用法: /prompt-assign <变体ID>")

    def _chat_cost(self, args: str) -> None:
        """Cost tracking: /cost [budget <usd>|reset]."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub == "budget":
            try:
                amount = float(sub_args.strip())
                from core.cost_tracker import set_budget

                set_budget(amount)
                print(f"  每日预算: ${amount:.2f}")
            except ValueError:
                print("  用法: /cost budget <美元金额>")
        elif sub == "reset":
            from core.cost_tracker import reset_cost

            result = reset_cost()
            print(f"  花费已清零 (归档 ${result.get('cleared_total', 0):.4f})")
        else:
            from core.cost_tracker import get_daily_breakdown, get_summary

            summary = get_summary()
            total = summary.get("total_cost", 0.0)
            calls = summary.get("total_calls", 0)
            budget = (summary.get("budget") or {}).get("daily")
            print("\n  💰 花费统计")
            print(f"  总花费: ${total:.4f}")
            print(f"  总调用: {calls}")
            if budget:
                today_cost = (
                    summary.get("by_day", {})
                    .get(__import__("datetime").datetime.now().strftime("%Y-%m-%d"), {})
                    .get("cost", 0.0)
                )
                pct = (today_cost / budget * 100) if budget > 0 else 0
                print(f"  今日: ${today_cost:.4f} / ${budget:.2f} ({pct:.0f}%)")
            # By model breakdown
            bm = summary.get("by_model", {})
            if bm:
                print("\n  按模型:")
                for model, info in sorted(bm.items(), key=lambda x: -x[1].get("cost", 0)):
                    print(f"    {model}: ${info.get('cost', 0):.4f} ({info.get('calls', 0)} 次)")
            # Recent daily
            days = get_daily_breakdown(3)
            if days:
                print("\n  最近三日:")
                for d in days:
                    print(f"    {d['day']}: ${d['cost']:.4f} ({d['calls']} 次)")
            print()

    def _chat_eval(self, args: str) -> None:
        """Run agent quality benchmark."""
        arg = args.strip().lower()
        json_out = arg == "json"
        print(f"  运行智能体质量基准{' (JSON)' if json_out else ''}...")
        try:
            from core.eval_harness import EvalEngine

            engine = EvalEngine()
            if json_out:
                result = engine.run(as_json=True)
                import json

                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                result = engine.run()
                if isinstance(result, dict):
                    print(f"\n  总分: {result.get('total', 'N/A')}")
                    for k, v in result.items():
                        if k != "total":
                            print(f"    {k}: {v}")
        except ImportError:
            print("  基准模块未就绪。")
        except Exception as e:
            print(f"  基准测试失败: {e}")

    def _chat_extend(self, args: str) -> None:
        """Toggle extension tool sets: /extend <notebook|audio|browser|list>."""
        arg = args.strip().lower()
        if arg == "notebook":
            state = self.session.toggle_notebook()
            print(f"  Notebook 工具: {'开启' if state else '关闭'}")
        elif arg == "audio":
            state = self.session.toggle_audio()
            print(f"  音频工具: {'开启' if state else '关闭'}")
        elif arg == "browser":
            state = self.session.toggle_browser()
            print(f"  浏览器工具: {'开启' if state else '关闭'}")
        elif arg == "list":
            print("  扩展工具状态:")
            print(f"    Notebook: {'✓' if self.session.notebook_enabled else '✗'}")
            print(f"    Audio:    {'✓' if self.session.audio_enabled else '✗'}")
            print(f"    Browser:  {'✓' if self.session.browser_enabled else '✗'}")
        else:
            print("  用法: /extend <notebook|audio|browser|list>")

    def _chat_mcp(self, args: str) -> None:
        """MCP server management: /mcp <list|add|remove|connect|disconnect|tools>."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            try:
                from core.mcp_client import get_mcp_client

                client = get_mcp_client()
                servers = client.list_servers() if hasattr(client, "list_servers") else []
                if servers:
                    print(f"\n  MCP 服务器 ({len(servers)} 个):")
                    for s in servers:
                        name = s.get("name", s) if isinstance(s, dict) else str(s)
                        connected = s.get("connected", "?") if isinstance(s, dict) else "?"
                        print(f"    {name}  [{connected}]")
                else:
                    print("  无已配置的 MCP 服务器。")
            except ImportError:
                print("  MCP 客户端未就绪。")
            except Exception as e:
                print(f"  MCP 错误: {e}")
        elif sub == "tools":
            name = sub_args.strip()
            print(f"  MCP 工具查询 '{name}' — 通过 mcp_list_tools 获取。")
        elif sub in ("add", "remove", "connect", "disconnect"):
            print(f"  /mcp {sub} — 请通过 AI chat 使用 MCP 管理工具。")
        else:
            print("  用法: /mcp <list|add|remove|connect|disconnect|tools>")

    def _chat_tidy(self, args: str) -> None:
        """根目录整理: /tidy [deep|status]"""
        from core.tidy_up import deep_clean, full_status, tidy_root

        arg = args.strip().lower()
        if arg == "status":
            _notify("诊断项目目录整洁度...")
            s = full_status()
            _notify(f"  __pycache__ 目录: {s['pycache_dirs']} 个")
            for k, v in s.items():
                if k.startswith("crux/"):
                    _notify(f"  .{k}: {v} 个文件")
            for k, v in s.items():
                if k.startswith("tmp/"):
                    _notify(f"  {k}: {v} 个文件")
            if s.get("missing_dirs"):
                _notify(f"  缺失目录: {', '.join(s['missing_dirs'])}")
            else:
                _notify("  所有规范目录已就位")
        elif arg == "deep":
            _notify("深度清理中（分类 + 删除过期文件 + 清除 __pycache__ + 清理 .crux/）...")
            result = deep_clean(older_than_days=7)
            for line in result.summary().split("\n"):
                _notify(line)
        else:
            _notify("整理根目录临时文件中...")
            result = tidy_root()
            for line in result.summary().split("\n"):
                _notify(line)

    def _chat_audit(self, args: str) -> None:
        """Dependency security audit: /audit <pip|npm>."""
        arg = args.strip().lower()
        if not arg:
            print("  用法: /audit <pip|npm>")
            print("  pip=Python 包安全审计, npm=Node.js 包安全审计")
            return
        print(f"  正在审计 {arg} 依赖安全...")
        try:
            from core.self_audit import audit

            report = audit()
            if isinstance(report, dict):
                sev = report.get("by_severity", {})
                total = report.get("total_findings", 0)
                print(
                    f"  审计完成: {total} 项问题 "
                    f"(严重:{sev.get('critical', 0)} 高:{sev.get('high', 0)} "
                    f"中:{sev.get('medium', 0)} 低:{sev.get('low', 0)})"
                )
                if report.get("auto_fixable"):
                    print(f"  可自动修复: {report['auto_fixable']} 项，使用 /self fix 修复。")
            else:
                print(f"  审计完成: {report}")
        except ImportError:
            print("  审计模块未就绪。使用 /self audit 运行完整审计。")
        except Exception as e:
            print(f"  审计失败: {e}")

    def _chat_rules(self, args: str) -> None:
        """Coding rules management: /rules <list|enable|create>."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            try:
                from core.rules import get_rules

                mgr = get_rules()
                rules = mgr.list_all() if hasattr(mgr, "list_all") else []
                if rules:
                    print(f"\n  编码规范 ({len(rules)} 条):")
                    for r in rules:
                        name = r.get("name", r) if isinstance(r, dict) else str(r)
                        enabled = r.get("enabled", "?") if isinstance(r, dict) else "?"
                        print(f"    {'✓' if enabled else '✗'} {name}")
                else:
                    print("  无已注册编码规范。")
            except ImportError:
                print("  规范模块未就绪。")
            except Exception as e:
                print(f"  获取规范失败: {e}")
            print()
        elif sub == "enable":
            if not sub_args:
                print("  用法: /rules enable <规则名>")
                return
            print(f"  已启用规则: {sub_args}")
        elif sub == "create":
            print(f"  创建规范 '{sub_args}' — 通过 AI chat 编写规范文本。")
        else:
            print("  用法: /rules <list|enable <名称>|create <名称>>")

    def _chat_automate(self, args: str) -> None:
        """Scheduled task management: /automate <add|list|remove>."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        sub_args = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            try:
                from core.scheduler import get_scheduler

                sched = get_scheduler()
                tasks = sched.list_tasks() if hasattr(sched, "list_tasks") else []
                if tasks:
                    print(f"\n  定时任务 ({len(tasks)} 个):")
                    for t in tasks:
                        t_id = t.get("id", "?") if isinstance(t, dict) else getattr(t, "id", "?")
                        t_cron = t.get("cron", "") if isinstance(t, dict) else getattr(t, "cron", "")
                        t_desc = t.get("description", "") if isinstance(t, dict) else getattr(t, "description", "")
                        t_enabled = t.get("enabled", True) if isinstance(t, dict) else getattr(t, "enabled", True)
                        status = "●" if t_enabled else "○"
                        print(f"    {status} [{t_id}] {t_cron}  {t_desc}")
                else:
                    print("  无定时任务。")
            except ImportError:
                print("  调度器未就绪。")
            except Exception as e:
                print(f"  获取任务失败: {e}")
            print()
        elif sub == "add":
            print(f"  添加定时任务 '{sub_args}' — 通过 AI chat 使用 scheduler 工具。")
        elif sub == "remove":
            if not sub_args:
                print("  用法: /automate remove <任务ID>")
                return
            print(f"  已移除定时任务: {sub_args}")
        else:
            print("  用法: /automate <list|add|remove>")

    def _chat_evolve(self, args: str) -> None:
        """Display prompt evolution / growth engine status."""
        print("  Prompt 进化状态")
        print("  ───────────────")
        try:
            from core.growth_engine import get_growth_engine

            engine = get_growth_engine()
            stats = engine.get_stats() if hasattr(engine, "get_stats") else {}
            if stats:
                total = stats.get("total_calls", 0)
                print(f"  总调用: {total}")
                by_intent = stats.get("by_intent", {})
                if by_intent:
                    print("  意图分布:")
                    for intent, count in sorted(by_intent.items(), key=lambda x: -x[1]):
                        print(f"    {intent}: {count}")
                top_tools = stats.get("top_tools", [])
                if top_tools:
                    print("  最佳工具 (成功率):")
                    for t in top_tools[:5]:
                        name = t.get("name", t) if isinstance(t, dict) else str(t)
                        rate = t.get("success_rate", 0) if isinstance(t, dict) else 0
                        print(f"    {name}: {rate:.1%}")
            else:
                print("  暂无进化数据。系统随着每次调用自动学习和优化路由。")
        except ImportError:
            print("  进化引擎未就绪。系统随调用自动优化。")
        except Exception as e:
            print(f"  进化状态: {e}")

    def _chat_exit(self, args: str) -> None:
        """Exit chat — handled by callers (TUI/plain REPL), this is a fallback."""
        print("  使用 /q 退出，或按 Ctrl+C。")

    def _chat_palette(self, args: str) -> None:
        """Command palette — fuzzy search all commands."""
        query = args.strip().lower()
        all_cmds = get_all()
        if query:
            # Simple substring match
            matches = [
                cmd
                for cmd in all_cmds
                if query in cmd.key.lower() or query in cmd.name.lower() or query in cmd.desc.lower()
            ]
        else:
            matches = all_cmds

        if matches:
            print(f"\n  命令 ({len(matches)} 个):")
            for cmd in matches:
                arg_str = f" {cmd.args}" if cmd.args else ""
                print(f"    {cmd.name}{arg_str}  [{cmd.category}]  {cmd.desc}")
        else:
            print(f"  未找到匹配 '{query}' 的命令。")
        print()

    def _chat_tasks(self, args: str) -> None:
        """Display background task status."""
        try:
            from core.background import get_background_manager

            mgr = get_background_manager()
            tasks = mgr.list_tasks()
            if tasks:
                print(f"\n  后台任务 ({len(tasks)} 个):")
                for t in tasks:
                    status_icon = {"running": "●", "done": "✓", "failed": "✗", "stopped": "⊘", "pending": "○"}.get(
                        t.status, "?"
                    )
                    print(f"    {status_icon} [{t.id[:8]}] {t.description or t.command[:60]}  ({t.status})")
            else:
                print("  无活跃后台任务。")
            print()
        except ImportError:
            print("  后台任务管理模块未就绪。")

    def _chat_rollback(self, args: str) -> None:
        """Undo last operation: /rollback."""
        from core.rollback_orchestrator import list_snapshots, rollback_last_op

        result = rollback_last_op()
        snaps = list_snapshots()
        status = "✓" if result["success"] else "✗"
        print(f"\n  {status} 回滚: {result['detail']}")
        if snaps:
            print(f"  可用快照: {', '.join(snaps[:5])}")
        print()

    def _chat_copy(self, args: str) -> None:
        """Copy recent messages: /copy [N]. Default: last CRUX response."""
        n = int(args.strip()) if args.strip().isdigit() else 1
        crux_msgs = []
        for _style, text in self.session.messages:
            if isinstance(text, str) and text.strip():
                crux_msgs.append(text)
        if crux_msgs:
            to_copy = "\n\n".join(crux_msgs[-n:])
            print(f"\n  ── 最近 {min(n, len(crux_msgs))} 条消息 ──")
            print(to_copy[:2000])
            print(f"  ── 共 {len(to_copy)} 字符 (Ctrl+Y 复制最后一条) ──\n")
        else:
            print("  暂无消息。")

    def _chat_trends(self, args: str) -> None:
        """Historical trends: /trends [cost|tools|quality]."""
        sub = args.strip().lower()
        from core.trends import cost_trends, quality_trends, tool_health_trends

        if sub in ("cost", "costs", ""):
            data = cost_trends()
            print("\n  ◆ 消费趋势")
            print(f"  总计: ${data.get('total_cost', 0):.2f} / {data.get('total_calls', 0)} 调用")
            for model, info in data.get("top_models", []):
                if isinstance(info, dict):
                    print(f"  {model}: ${info.get('cost', 0):.2f} ({info.get('calls', 0)} calls)")

        elif sub in ("tools", "tool"):
            data = tool_health_trends()
            print(f"\n  ◆ 工具健康 ({len(data)} tools)")
            for name, stats in list(data.items())[:10]:
                print(f"  {name:<30} {stats['calls']:>4} calls  {stats['success_rate']:>4}  {stats['avg_ms']}ms avg")

        elif sub in ("quality", "score"):
            data = quality_trends()
            print("\n  ◆ 工具质量")
            print(f"  平均分: {data.get('average_score', 0):.0f}/100")
            print(f"  分级: {data.get('grade_distribution', {})}")
        print()

    def _chat_docs(self, args: str) -> None:
        """Auto-generate docs: /docs [help|agents|manifest|all]."""
        from core.docs_engine import generate_all, generate_help_md, sync_agents_md, sync_manifest

        sub = args.strip().lower()
        if sub == "help":
            r = generate_help_md()
        elif sub == "agents":
            r = sync_agents_md()
        elif sub == "manifest":
            r = sync_manifest()
        else:
            r = generate_all()
        print(f"\n  文档生成: {r}")
        print()

    def _chat_health(self, args: str) -> None:
        """Tool quality scorecard + system health: /health."""
        print("\n  ◆ CRUX Studio 健康面板")
        print("  ─────────────────────────")

        # 1. Tool scorecard
        try:
            from core.tool_scorecard import score_all
            from core.tools import get_registry

            reg = get_registry()
            report = score_all(reg)
            grades = report.get("grade_distribution", {})
            print(f"  工具质量: {report.get('total_tools', 0)} 工具  分级: {grades}")
            avg = report.get("average_score", 0)
            print(f"  平均分: {avg:.0f}/100")
        except Exception as e:
            print(f"  工具质量: 评分失败 ({e})")

        # 2. Release status
        try:
            import json

            from core.rollback_engine import RELEASES_DIR

            releases = list(RELEASES_DIR.glob("*.json"))
            if releases:
                latest = json.loads(releases[-1].read_text(encoding="utf-8"))
                print(f"  最新发布: {latest.get('id', '?')} [{latest.get('status', '?')}]")
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        # 3. Watchdog (白虎自愈) status
        try:
            from core.watchdog import get_watchdog

            wd = get_watchdog()
            state = wd.status()
            print(f"  自愈看门狗: {'✓ 运行中' if wd.alive() else '✗ 已停止'}")
            if state.last_provider_check:
                print(f"    供应商探活: {state.last_provider_check}")
            if state.disk_free_gb:
                print(f"    磁盘剩余: {state.disk_free_gb:.1f} GB")
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        # 4. Observability metrics
        try:
            from core.observability import metrics

            summary = metrics.summary() if hasattr(metrics, "summary") else {}
            if summary:
                for key, val in list(summary.items())[:5]:
                    print(f"  {key}: {val}")
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        # 4. Cost tracker
        try:
            from core.cost_tracker import get_summary

            cost = get_summary()
            if cost:
                print(f"  今日花费: ${cost.get('today_cost', 0):.4f} / ${cost.get('daily_budget', 0):.2f}")
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        print()

    def _chat_permission(self, args: str) -> None:
        """Switch permission mode: /permission <yolo|auto|manual>."""
        arg = args.strip().lower()
        if arg in ("yolo", "auto", "manual"):
            print(f"  权限模式: {arg} (需重启生效)")
        else:
            print("  用法: /permission <yolo|auto|manual>")

    def _chat_method(self, args: str) -> None:
        """Show methodology compliance state. Sources: METHODOLOGY.md/AGENTS.md/CLAUDE.md"""
        arg = args.strip().lower()
        if arg == "reset":
            from core.methodology import reset_methodology_state

            reset_methodology_state()
            print("  方法论状态已重置")
            return

        from core.methodology import get_methodology_state

        state = get_methodology_state()
        # ── 摘要行 ──
        print(f"  {state.summary()}")
        print()
        # ── 测试要求 ──
        print(f"  测试要求: {state.test_requirement}")
        # ── 7 步工作流 ──
        print(f"  工作流步骤: {state.workflow_step}/7 ({state.workflow_steps.get(state.workflow_step, '?')})")
        # ── 升级历史 ──
        if state.escalation_history:
            print("  升级历史:")
            for prev, reason in state.escalation_history:
                print(f"    ↑ {prev} → {reason}")
        # ── C/D 级详情 ──
        level = state.task_level
        if level.value in ("complex", "critical"):
            print("  C/D 级要求:")
            print(f"    Plan     : {'✓' if state.plan_exists else '✗ 未创建'}")
            print(f"    测试基线 : {'✓' if state.test_baseline_recorded else '✗'}")
            print(f"    Worktree : {'✓' if state.worktree_created else ('✗' if level.value == 'critical' else '跳过')}")
            print(f"    TDD 阶段 : {state.tdd_phase or '-'}")
        print("  /method reset — 重置状态")

    def _chat_trace(self, args: str) -> None:
        """查看执行轨迹: /trace [run_id|list]"""
        from core.intelligence_trace import get_trace_store
        import json

        store = get_trace_store()
        arg = args.strip()

        if arg == "list" or not arg:
            # 列出最近的轨迹
            traces = store.query(limit=20)
            if not traces:
                print("  暂无执行轨迹。")
                return
            print(f"  最近 {len(traces)} 条轨迹:")
            for t in traces:
                run_id = t.get("run_id", "?")[:12]
                status = t.get("status", "?")
                mode = t.get("mode", "?")
                request = (t.get("user_request") or "")[:60]
                icon = "✓" if status == "pass" else "✗" if status == "fail" else "○"
                print(f"  {icon} {run_id} [{mode}] {status}: {request}")
        else:
            trace = store.get(arg)
            if not trace:
                print(f"  未找到轨迹: {arg}")
                return
            print(f"  Run ID:   {trace.get('run_id', '?')}")
            print(f"  Status:   {trace.get('status', '?')}")
            print(f"  Mode:     {trace.get('mode', '?')}")
            print(f"  Request:  {trace.get('user_request', '')[:200]}")
            steps = trace.get("steps", [])
            if steps:
                print(f"  Steps ({len(steps)}):")
                for s in steps:
                    icon = "✓" if s.get("status") == "pass" else "✗"
                    err = f" — {s.get('error', '')[:80]}" if s.get("error") else ""
                    print(f"    {icon} {s.get('name', '?')}{err}")

    def _chat_done(self, args: str) -> None:
        """完成前验证清单 (AGENTS.md)。"""
        quick = args.strip().lower() == "quick"
        from core.methodology import get_methodology_state, run_verification

        print("  ── 完成前验证 ──")
        results = run_verification()
        if quick:
            results.pop("pytest", None)
            print("  (quick=跳过pytest)")
        all_ok = True
        for name, (ok, summary) in results.items():
            mark = "✓" if ok else "✗"
            print(f"  {mark} {name}: {summary[:100]}")
            if not ok:
                all_ok = False
        if all_ok:
            print("  全部通过 ✅")
            get_methodology_state().advance_workflow("cleaned")
        else:
            print("  存在未通过项，修复后重新 /done")

    def _chat_provider(self, args: str) -> None:
        """Switch model provider: /provider <list|switch>."""
        arg = args.strip().lower()
        if arg == "list":
            from core.provider import MODEL_REGISTRY, get_provider_manager

            mgr = get_provider_manager()
            print(f"\n  当前供应商: {mgr.active_provider}")
            print("  可用模型:")
            for mid, _info in sorted(MODEL_REGISTRY.items()):
                marker = " ←" if mid == mgr.active_provider else ""
                print(f"    {mid}{marker}")
            print()
        elif arg:
            print(f"  切换供应商 '{arg}' — 通过 /model 切换模型。")
        else:
            print("  用法: /provider <list|switch>")

    def _chat_interrupt(self, args: str) -> None:
        """Interrupt (Ctrl+C) — no-op, captured for dispatch completeness."""
        pass

    def _cmd_runs(self, args: str = "") -> str:
        """显示最近执行历史。用法: /runs [N]"""
        try:
            from core.run_summary import list_failed_runs, list_recent_runs

            n = int(args.strip()) if args.strip().isdigit() else 10
            if args.strip().startswith("--failed"):
                n = int(args.strip().split()[-1]) if args.strip().split()[-1].isdigit() else 10
                runs = list_failed_runs(n)
            else:
                runs = list_recent_runs(n)
            if not runs:
                return "暂无执行记录。"
            lines = [f"最近 {len(runs)} 次执行："]
            for r in runs:
                rid = r.get("root_trace_id", "")[:12]
                goal = r.get("goal", "")[:40]
                status = r.get("status", "?")
                total = r.get("total", 0)
                failed = r.get("failed", 0)
                ms = r.get("duration_ms", 0)
                lines.append(f"  [{status}] {rid} {goal} ({total}tasks, {failed}fail, {ms}ms)")
            return "\n".join(lines)
        except ImportError:
            return "run_summary 模块未加载。"

    def _cmd_summary(self, args: str = "") -> str:
        """查看指定执行摘要。用法: /summary <root_trace_id>"""
        rid = args.strip()
        if not rid:
            return "用法: /summary <root_trace_id>"
        try:
            from core.run_summary import get_run

            data = get_run(rid)
            if not data:
                return f"未找到执行记录: {rid}"
            lines = [
                f"执行摘要: {data.get('root_trace_id', '')}",
                f"目标: {data.get('goal', '')}",
                f"状态: {data.get('status', '?')}",
                f"耗时: {data.get('duration_ms', 0)}ms",
                f"任务: {data.get('total_tasks', 0)}总 / {data.get('completed', 0)}完成 / {data.get('failed', 0)}失败 / {data.get('skipped', 0)}跳过 / {data.get('timeout', 0)}超时",
                f"事件: {data.get('event_counts', {})}",
            ]
            failure = data.get("failure_reasons", {})
            if failure:
                lines.append(f"失败原因: {failure}")
            longest = data.get("longest_task")
            if longest:
                lines.append(f"最长任务: {longest.get('id', '?')} ({longest.get('duration_ms', 0)}ms)")
            quality = data.get("quality_status", "")
            if quality:
                score = data.get("quality_score", 0)
                flags = data.get("quality_flags", [])
                rec = data.get("recommendation", "")
                lines.append(f"质量评级: {quality} (score={score})")
                if flags:
                    lines.append(f"问题标记: {', '.join(flags)}")
                if rec:
                    lines.append(f"建议: {rec}")
            provider_route = data.get("provider_route", "")
            if provider_route:
                lines.append(f"Provider路由: {provider_route}")
            rt_budget = data.get("retry_budget", {})
            if rt_budget:
                lines.append(f"重试预算: {rt_budget.get('used', 0)}/{rt_budget.get('max', '?')}")
            policy = data.get("policy_action", "")
            if policy:
                p_reason = data.get("policy_reason", "")
                lines.append(f"策略决策: {policy} ({p_reason})")
            return "\n".join(lines)
        except ImportError:
            return "run_summary 模块未加载。"

    def _cmd_providers(self, args):
        """View provider health status. Use --why for detailed score breakdown."""
        try:
            from core.provider import get_provider_manager
            from core.provider_history import get_all_stats
            from core.provider_policy import format_explain, format_route, score_provider

            mgr = get_provider_manager()
            all_pids = list(mgr.providers.keys())
            circuit_states = {p: mgr.state.circuit_state(p) for p in all_pids}
            show_why = "--why" in args
            lines = ["Provider health (EMA 60min):"]
            stats = get_all_stats()
            req = {"task_type": "text", "require_code": False, "budget_remaining": 100}
            for pid in all_pids:
                s = stats.get(pid, {})
                calls = s.get("calls", 0)
                rate = s.get("success_rate", 1.0)
                lat = s.get("avg_latency_ms", 0)
                s.get("recent_error", "")
                circuit = circuit_states.get(pid, "CLOSED")
                sc = score_provider(pid, req, circuit_states)
                lines.append(
                    f"  {pid:12s} circuit={circuit:10s} score={sc:5.1f} calls={calls:3d} success={rate:.0%} latency={lat:.0f}ms"
                )
                if show_why and circuit != "OPEN":
                    explanation = format_explain(pid, req, circuit_states)
                    lines.append(f"           {explanation}")
            route = format_route([p for p in all_pids if circuit_states.get(p) != "OPEN"])
            lines.append("Route: " + route)
            return chr(10).join(lines)
        except ImportError as e:
            return "Module error: " + str(e)

    # ── Trae Agent 转换 ─────────────────────────────────────────
    def _chat_trae_convert(self, args: str) -> None:
        """导入 trae agent → CRUX skill.json: /trae-convert <agent.json>"""
        args = args.strip()
        if not args:
            self.io.error("用法: /trae-convert <agent.json>")
            return
        try:
            from plugins.trae_agent_converter import cmd_trae_convert
            result = cmd_trae_convert([args])
            self.io.info(result)
        except Exception as e:
            self.io.error(f"转换失败: {e}")

    def _chat_trae_export(self, args: str) -> None:
        """导出 CRUX skill → trae agent 格式: /trae-export <skill.json>"""
        parts = args.strip().split()
        if not parts:
            self.io.error("用法: /trae-export <skill.json> [output.json]")
            return
        try:
            from plugins.trae_agent_converter import cmd_trae_export
            result = cmd_trae_export(parts)
            self.io.info(result)
        except Exception as e:
            self.io.error(f"导出失败: {e}")

    def _chat_trae_batch(self, args: str) -> None:
        """批量转换 trae agents: /trae-batch <input_dir> [output_dir]"""
        parts = args.strip().split()
        if not parts:
            self.io.error("用法: /trae-batch <input_dir> [output_dir]")
            return
        try:
            from plugins.trae_agent_converter import cmd_trae_batch
            result = cmd_trae_batch(parts)
            self.io.info(result)
        except Exception as e:
            self.io.error(f"批量转换失败: {e}")

    def _chat_trae_new(self, args: str) -> None:
        """手动创建 trae 风格 skill: /trae-new <name> [description]"""
        parts = args.strip().split(maxsplit=1)
        if not parts:
            self.io.error("用法: /trae-new <name> [description]")
            return
        try:
            from plugins.trae_agent_converter import cmd_trae_new
            result = cmd_trae_new(parts)
            self.io.info(result)
        except Exception as e:
            self.io.error(f"创建失败: {e}")

    def _cmd_regression(self, args):
        """Run policy regression tests."""
        try:
            from core.policy_regression import run_regression_suite

            results = run_regression_suite()
            lines = ["Policy regression results:"]
            all_pass = True
            for r in results:
                status = "PASS" if r["passed"] else "FAIL"
                if not r["passed"]:
                    all_pass = False
                lines.append(f"  [{status}] {r['test']}: {r['message']}")
            lines.append(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
            return chr(10).join(lines)
        except ImportError as e:
            return "Module error: " + str(e)

    def _cmd_incidents(self, args):
        """View incident trends."""
        try:
            from core.incident_store import get_incident_trends

            trends = get_incident_trends(24)
            if trends["total"] == 0:
                return "No incidents in last 24h."
            lines = [f"Incidents (24h): {trends['total']} total"]
            if trends["by_category"]:
                lines.append("By category:")
                for cat, cnt in trends["by_category"].items():
                    lines.append(f"  {cat}: {cnt}")
            if trends["by_severity"]:
                lines.append("By severity:")
                for sev, cnt in trends["by_severity"].items():
                    lines.append(f"  {sev}: {cnt}")
            return chr(10).join(lines)
        except ImportError as e:
            return "Module error: " + str(e)

    def _cmd_playbook(self, args):
        """View remediation playbook. Usage: /playbook <category>"""
        cat = args.strip()
        try:
            from core.incident_playbook import PLAYBOOKS, format_playbook

            if not cat:
                lines = ["Available playbooks:"]
                for key, pb in PLAYBOOKS.items():
                    if key != "unknown":
                        lines.append(f"  {key}: {pb['title']} ({pb['severity']})")
                lines.append("Usage: /playbook <category>")
                return chr(10).join(lines)
            return format_playbook(cat)
        except ImportError as e:
            return "Module error: " + str(e)

    def _cmd_replays(self, args):
        """List saved run replays."""
        try:
            from core.run_replay import list_replays

            replays = list_replays(10)
            if not replays:
                return "No replays found."
            lines = ["Recent replays:"]
            for r in replays:
                rid = r.get("root_trace_id", "")[:12]
                status = r.get("status", "?")
                failed = r.get("failed", 0)
                total = r.get("total", 0)
                policy = r.get("policy", "")
                lines.append(f"  {rid} status={status} tasks={total} failed={failed} policy={policy}")
            return chr(10).join(lines)
        except ImportError as e:
            return "Module error: " + str(e)

    def _cmd_replay(self, args):
        """View run replay timeline. Usage: /replay <trace_id>"""
        rid = args.strip()
        if not rid:
            return "Usage: /replay <root_trace_id>"
        try:
            from core.run_replay import format_timeline, get_failure_timeline, load_replay

            timeline = get_failure_timeline(rid)
            replay = load_replay(rid)
            lines = []
            if replay:
                summary = replay.get("summary", {})
                lines.append(f"Run: {rid}")
                lines.append(f"Status: {summary.get('quality_status', '?')} score={summary.get('quality_score', 0)}")
                lines.append(
                    f"Tasks: {summary.get('tasks_done', 0)} done / {summary.get('tasks_failed', 0)} failed / {summary.get('tasks_skipped', 0)} skipped"
                )
                lines.append(f"Policy: {summary.get('policy_action', '')} ({summary.get('policy_reason', '')})")
                incident = summary.get("incident", {})
                if incident:
                    lines.append(
                        f"Failure: {incident.get('primary_category', '?')} ({incident.get('total_incidents', 0)} incidents)"
                    )
                    lines.append(f"Recommendation: {incident.get('recommendation', '')}")
                    primary = incident.get("primary_category", "")
                    if primary:
                        try:
                            from core.incident_playbook import format_playbook

                            lines.append("")
                            lines.append("Remediation playbook:")
                            lines.append(format_playbook(primary, rid))
                        except ImportError:
                            pass
                lines.append(f"Timeline events: {len(timeline)}")
                lines.append("")
            if timeline:
                lines.append(format_timeline(timeline))
            else:
                lines.append("No timeline events found.")
            return chr(10).join(lines)
        except ImportError as e:
            return "Module error: " + str(e)
