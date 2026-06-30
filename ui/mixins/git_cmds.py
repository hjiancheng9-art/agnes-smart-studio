"""Git 命令 Mixin：自动生成 commit 消息和 CHANGELOG。"""

import subprocess
from typing import TYPE_CHECKING

from core.mcp_servers._mcp_utils import run_subprocess
from rich.panel import Panel
from rich.prompt import Confirm

from ui.badges import print_reply_header, print_route_reason
from ui.display import show_error, show_success, show_warning
from ui.theme import console

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ["GitCommandsMixin"]


class GitCommandsMixin:
    pass  # 占位，下方方法会替换

    def _chat_commit(self, session: "ChatSession"):
        """从 git staged diff 自动生成 commit 消息并提交"""
        try:
            diff = run_subprocess(["git", "diff", "--staged", "--stat"], timeout=10)
            if not diff.stdout.strip():
                show_warning("无 staged 更改，先 git add")
                return
            full_diff = run_subprocess(["git", "diff", "--staged"], timeout=10)
            prompt = f"根据以下 git diff 生成简洁中文 commit 消息（格式：<类型>: <一句话描述>）：\n\n{full_diff.stdout[:3000]}"
            # 用 router 统一处理模型切换（避免直接设 model 不切 client 导致不匹配）
            from core.router import apply, resolve

            decision = resolve("quick_fix", session)
            old_model = session.model
            apply(decision, session)
            if decision.model_id and decision.model_id != old_model:
                print_reply_header(session)
                if decision.reason:
                    print_route_reason(decision.reason)
            r = session.client.chat(model=session.model, messages=[{"role": "user", "content": prompt}], max_tokens=200)
            msg = r["choices"][0]["message"]["content"].strip()
            show_success(f"建议 commit: {msg}")
            if Confirm.ask("执行 commit?", default=True):
                # 用列表传参避免 shell 注入
                run_subprocess(["git", "commit", "-m", msg], timeout=10)
                show_success("已提交")
        except (RuntimeError, OSError, KeyError, subprocess.SubprocessError) as e:
            show_error(str(e))

    def _chat_changelog(self, session: "ChatSession", arg: str):
        """从 git log 自动生成 CHANGELOG.md（分组：新增/修复/优化/其他）"""
        since = arg.strip() or "7 days ago"
        try:
            log = run_subprocess(
                ["git", "log", f"--since={since}", "--oneline", "--no-merges"],
                timeout=10,
            )
            if not log.stdout.strip():
                show_warning(f"{since} 内无提交")
                return
            prompt = f"根据以下 git log 生成 CHANGELOG.md（分组：新增/修复/优化/其他）：\n\n{log.stdout[:3000]}"
            # 用 router 统一处理模型切换（避免直接设 model 不切 client 导致不匹配）
            from core.router import apply, resolve

            decision = resolve("quick_fix", session)
            old_model = session.model
            apply(decision, session)
            if decision.model_id and decision.model_id != old_model:
                print_reply_header(session)
                if decision.reason:
                    print_route_reason(decision.reason)
            r = session.client.chat(
                model=session.model, messages=[{"role": "user", "content": prompt}], max_tokens=1000
            )
            changelog = r["choices"][0]["message"]["content"].strip()
            console.print(Panel(changelog[:2000], title="[cyan]CHANGELOG[/]"))
            if Confirm.ask("保存为 CHANGELOG.md?", default=True):
                with open("CHANGELOG.md", "w", encoding="utf-8") as f:
                    f.write(changelog)
                show_success("已保存 CHANGELOG.md")
        except (RuntimeError, OSError, KeyError, subprocess.SubprocessError) as e:
            show_error(str(e))
