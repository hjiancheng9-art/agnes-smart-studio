"""诊断配置命令 Mixin：自诊断/审计/规范/自动化/供应商/进化/知识库/模型切换。"""

import contextlib
import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from core.client import CruxClient
from ui.badges import print_mode_banner
from ui.display import show_info, show_success, show_warning
from ui.theme import COLORS, console
from utils import memory

# 项目根目录：diag.py 在 ui/mixins/ 下，往上两级是项目根
_DIAG_ROOT = Path(__file__).resolve().parent.parent.parent
if TYPE_CHECKING:
    from core.chat import ChatSession
__all__ = ["DiagCommandsMixin"]


class DiagCommandsMixin:
    # Method provided by SharedMixin (sibling in MRO)
    def _stream_chat(self, session: "ChatSession", user: str) -> None: ...  #
    def _self_diagnose(self, session: "ChatSession", arg: str):
        """工具自诊断 — 让工具检查自身健康、分析源码、发现并修复 bug
        用法:
            /self check  — 遍历所有 .py 文件进行语法检查
            /self files  — 树状打印项目目录结构
            /self health — 检测 API Key / Python版本 / 依赖 / 使用统计
            /self fix    — 将 core/engines 源码喂给 AI，让 AI 分析问题并提出修复方案
        """
        from core.audit_runner import audit_syntax, collect_source_snippets, health_checks, project_tree_data

        arg = arg.strip()
        # ── /self check：语法扫描 ──────────────────────
        if arg == "check":
            errors = audit_syntax()
            if errors:
                show_warning(f"发现 {len(errors)} 个语法错误:")
                for e in errors:
                    console.print(f"  ❌ {e}")
            else:
                show_success("所有 Python 文件语法检查通过")
        # ── /self files：项目结构展示 ──────────────────
        elif arg == "files":
            from rich.tree import Tree

            tree = Tree("[cyan]crux-studio[/]")
            for item in project_tree_data():
                if item["is_dir"]:
                    branch = tree.add(f"[cyan]{item['name']}[/]")
                    for sub in item["children"]:
                        if sub["is_dir"]:
                            branch.add(f"[cyan]{sub['name']}[/]")
                        else:
                            branch.add(f"[dim]{sub['name']}[/]")
                else:
                    tree.add(f"[white]{item['name']}[/]")
            console.print(tree)
        # ── /self health：健康度诊断 ──────────────────
        elif arg == "health":
            for check in health_checks():
                icon = "✅" if check["ok"] else "❌"
                console.print(f"  {icon} {check['category']}: {check['message']}")
            # 使用统计
            mem = memory.load_memory()
            stats = mem.get("stats", {})
            console.print(
                f"  📊 生成: {stats.get('total', 0)} 次 | ⭐评分: {stats.get('rated_count', 0)} 条 | 🚫过滤: {stats.get('content_policy_hits', 0)} 次"
            )
        # ── /self fix：AI 源码分析 ─────────────────────
        elif arg == "fix":
            session.unlimited_tools = True
            session.toggle_code_mode()
            ctx = "你是 CRUX Studio 维护者。以下是核心源码，请分析 bug/合规性/优化建议：\n\n"
            ctx += collect_source_snippets()
            show_info("AI 正在分析源码...")
            session.messages.append({"role": "user", "content": ctx})
            self._stream_chat(session, ctx)
        elif arg in ("audit", "all"):
            show_info("═══ 阶段 1/3: 语法扫描 ═══")
            errors = audit_syntax()
            if errors:
                show_warning(f"发现 {len(errors)} 个语法错误:")
                for e in errors:
                    console.print(f"  ❌ {e}")
            else:
                show_success("所有 Python 文件语法检查通过")
            show_info("═══ 阶段 2/3: 健康度诊断 ═══")
            for check in health_checks():
                icon = "✅" if check["ok"] else "❌"
                console.print(f"  {icon} {check['category']}")
            show_info("═══ 阶段 3/3: AI 源码分析 ═══")
            session.unlimited_tools = True
            self._stream_chat(
                session, "你是 CRUX Studio 维护者。请对项目做源码审计，输出：Bug 风险 | API 合规性 | 优化建议。"
            )
            session.unlimited_tools = False
        else:
            show_info("用法: /self [check|files|health|fix|audit]")
            console.print("  [dim]check[/]  - 扫描所有 .py 语法")
            console.print("  [dim]files[/]  - 展示项目结构")
            console.print("  [dim]health[/] - API Key / Python / 依赖 / 统计")
            console.print("  [dim]fix[/]    - AI 读源码分析问题")
            console.print("  [dim]audit[/]  - 全量自检 (check+health+fix)")

    def _chat_audit(self, session: "ChatSession", arg: str):
        """依赖安全审计：检查过期版本 + 已知漏洞 (pip/npm/all)"""
        kinds = arg.strip() or "all"
        if kinds in ("pip", "all"):
            show_info("检查 pip 依赖...")
            try:
                r = subprocess.run(
                    ["pip", "list", "--outdated", "--format", "columns"], capture_output=True, text=True, timeout=30
                )
                if r.stdout.strip():
                    console.print(Panel(r.stdout[:2000], title="[yellow]pip 过期包[/]"))
                else:
                    show_success("pip: 全部最新")
            except (subprocess.SubprocessError, OSError):
                pass
            # 安全检查
            try:
                r2 = subprocess.run(["pip-audit"], capture_output=True, text=True, timeout=60)
                if r2.stdout.strip():
                    console.print(Panel(r2.stdout[:1500], title="[red]安全漏洞[/]"))
            except FileNotFoundError:
                console.print("  [dim]pip-audit 未安装 (pip install pip-audit)[/]")
            except (subprocess.SubprocessError, OSError):
                pass
        if kinds in ("npm", "all"):
            show_info("检查 npm 依赖...")
            try:
                r = subprocess.run(["npm", "outdated"], capture_output=True, text=True, timeout=30)
                if r.stdout.strip():
                    console.print(Panel(r.stdout[:2000], title="[yellow]npm 过期包[/]"))
                else:
                    show_success("npm: 全部最新")
            except FileNotFoundError:
                console.print("  [dim]非 npm 项目或 npm 未安装[/]")
            except (subprocess.SubprocessError, OSError):
                pass
            try:
                r2 = subprocess.run(["npm", "audit"], capture_output=True, text=True, timeout=60)
                if "vulnerabilities" in (r2.stdout + r2.stderr).lower():
                    console.print(Panel((r2.stdout + r2.stderr)[:1500], title="[red]npm 安全漏洞[/]"))
            except (subprocess.SubprocessError, OSError):
                pass

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
        # 每次操作后重建 system prompt（rules 现已在 _build_system_prompt 内部注入）
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}

    def _chat_automate(self, session: "ChatSession", arg: str):
        """管理自动化定时任务 (list|add <描述> <cron>|remove)"""
        import json
        import os
        from datetime import datetime

        automations_dir = os.path.join(_DIAG_ROOT, "output", "automations")
        os.makedirs(automations_dir, exist_ok=True)
        data_path = os.path.join(automations_dir, "tasks.json")
        tasks = []
        if os.path.exists(data_path):
            with open(data_path, encoding="utf-8") as fh:
                tasks = json.loads(fh.read())
        arg = arg.strip()
        if not arg or arg == "list":
            if not tasks:
                show_info("无自动化任务")
                return
            for i, t in enumerate(tasks, 1):
                console.print(f"  {i}. [{t.get('cron', '?')}] {t.get('desc', '')[:50]} [dim]({t.get('id', '')})[/]")
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
            with open(data_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(tasks, indent=2, ensure_ascii=False))
            show_success(f"已添加: {desc} ({cron})")
            console.print("  [dim]提示: cron 格式为 '分 时 日 月 周'，如 '0 9 * * 1'=每周一早9点[/]")
        elif arg.startswith("remove "):
            tid = arg[7:].strip()
            before = len(tasks)
            tasks = [t for t in tasks if t.get("id") != tid]
            if len(tasks) < before:
                with open(data_path, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(tasks, indent=2, ensure_ascii=False))
                show_success("已移除")
            else:
                show_warning("未找到该任务")
        else:
            show_info("用法: /automate [list|add <描述> <cron>|remove <id>]")

    def _chat_provider(self, session: "ChatSession", arg: str):
        """切换模型供应商 (list|switch crux/deepseek/local)"""
        import json

        cfg_path = os.path.join(_DIAG_ROOT, "models.json")
        cfg = self._load_models_config()
        providers = cfg.get("providers", {})
        arg = arg.strip()
        if not arg or arg == "list":
            active = cfg.get("active", "crux")
            fallback = cfg.get("fallback", {})
            priority = fallback.get("priority", [])
            from core.provider import MODEL_REGISTRY

            for pid, p in providers.items():
                marker = " [green]← 当前[/]" if pid == active else ""
                models = p.get("models", {})
                # 从 MODEL_REGISTRY 动态构建带能力标签的模型列表
                model_parts = []
                for tier, mid in models.items():
                    mi = MODEL_REGISTRY.get(mid)
                    cap = ""
                    if mi:
                        if mi.supports_tools: cap += "🔧"
                        if mi.supports_vision: cap += "👁"
                        if mi.supports_thinking: cap += "🧠"
                    cap_str = f" {cap}" if cap else ""
                    model_parts.append(f"[dim]{tier}=[/]{mid}{cap_str}")
                model_info = ", ".join(model_parts)
                key_env = f"{pid.upper()}_API_KEY"
                has_key = "有 Key" if os.getenv(key_env) else "无 Key"
                prio_marker = f" [yellow]#{priority.index(pid) + 1}优先[/]" if pid in priority else ""
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
            # 从 .env 或 provider 配置查找 API key
            key_env = f"{pid.upper()}_API_KEY"
            api_key = (
                os.getenv(key_env) or os.getenv("CRUX_API_KEY") or os.getenv("AGNES_API_KEY") or p.get("api_key") or ""
            )
            # auth_required=false 的 provider 无需 Key
            if not api_key and not p.get("auth_required", True):
                api_key = "no-auth-needed"
            elif not api_key:
                key = Prompt.ask(f"[cyan]输入 {p['name']} API Key[/]")
                if not key:
                    show_warning("已取消")
                    return
                api_key = key
            # 更新 client 和 session
            from core.client import CruxClient

            session.client.close()
            session.client = CruxClient(api_key=api_key, base_url=p["base_url"])
            cfg["active"] = pid
            with open(cfg_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(cfg, indent=2, ensure_ascii=False))
            # 切换 model 到该供应商的 pro 模型
            pro_model = p.get("models", {}).get("pro", "")
            if pro_model:
                session.model = pro_model
            show_success(f"已切换到 {p['name']} ({pro_model})")
            print_mode_banner(session)
            # 刷新系统提示词，让 AI 知道当前供应商
            session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
            session.reset()
        else:
            show_info("用法: /provider [list|switch <name>]")

    def _chat_evolve(self, session: "ChatSession"):
        """查看 Prompt 进化状态 — 高分案例统计"""
        from utils.memory import get_evolution_stats, get_successful_prompts

        stats = get_evolution_stats()
        console.print("[bold]Prompt 进化库:[/]")
        console.print(f"  图片: {stats['image']} 条成功案例")
        console.print(f"  视频: {stats['video']} 条成功案例")
        for kind in ["image", "video"]:
            samples = get_successful_prompts(kind, limit=3)
            if samples:
                console.print(f"\n  [cyan]{kind} 最佳案例:[/]")
                for s in samples:
                    console.print(f"    ⭐{s['rating']} | 你: {s['user'][:50]}")
                    console.print(f"    → 增强: {s['enhanced'][:80]}...")
        if stats["image"] + stats["video"] < 5:
            console.print("\n  [dim]评分越多，进化越快。生成后给 4-5 星即可积累案例。[/]")
            console.print("\n  [bold]提示词速成:[/]")
            console.print("  [dim]主体+场景[/] '一只狐狸在雪地里'")
            console.print("  [dim]主体+风格[/] '一只狐狸 水墨画'")
            console.print("  [dim]主体+动作+场景[/] '冲锋的战士 雨夜战场'")
            console.print("  [dim]只需这 3 种格式，增强器负责补全 10 段细节。[/]")

    def _chat_knowledge(self, session: "ChatSession", arg: str):
        """浏览内置知识库 /know [methods|templates|moves|antipatterns|sweetspot]"""
        from core.brain import ANTI_PATTERN_MAP, CREATIVE_DOMAIN_MAP, SWEET_SPOT_TEMPLATES, THINKING_METHOD_MAP

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
            console.print("[bold]提示词模板:[/]")
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

    def _select_provider(self):
        """交互式供应商选择（多 Key 时弹出菜单，单 Key 自动激活）
        1. 扫描所有 providers，收集有 API Key 或 auth_required=false 的
        2. 1 个外部供应商 → 自动激活
        3. ≥2 个外部供应商 → 弹出菜单让用户选择
        4. 0 个外部供应商 → 使用 CRUX
        Returns: (provider_id, model_id)
        """
        cfg = self._load_models_config()
        cfg_path = os.path.join(_DIAG_ROOT, "models.json")
        providers = cfg.get("providers", {})
        # 收集所有可用供应商：有 API Key 或 auth_required=false
        available = []
        for pid, p in providers.items():
            key_env = f"{pid.upper()}_API_KEY"
            api_key = p.get("api_key") or os.getenv(key_env)
            # auth_required=false 的 provider 无需 Key
            if api_key or not p.get("auth_required", True):
                model = p.get("models", {}).get("pro", "unknown")
                if not api_key:
                    api_key = "no-auth-needed"
                available.append((pid, p, model, api_key))
        if not available:
            # 没有任何 Key → CRUX
            p = providers.get("crux", providers.get(list(providers.keys())[0], {}))
            model = p.get("models", {}).get("light", "agnes-1.5-flash")
            show_info("无外部供应商 Key，使用默认 CRUX light")
            return ("crux", model)
        # 只有 CRUX → 直接用
        if len(available) == 1 and available[0][0] == "crux":
            pid, p, model, _ = available[0]
            return (pid, model)
        # 过滤出非 CRUX 的外部供应商
        external = [(pid, p, m, k) for pid, p, m, k in available if pid != "crux"]
        if len(external) == 1:
            # 只有一个外部供应商 → 自动激活
            pid, p, model, api_key = external[0]
            self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
            return (pid, model)
        # ≥2 个外部供应商 → 弹出菜单
        console.print()
        # 从 MODEL_REGISTRY（模型编排单一真源）动态获取描述和能力标签
        from core.provider import MODEL_REGISTRY

        def _capability_badges(mid: str) -> str:
            """从 MODEL_REGISTRY 构建能力徽章字符串。"""
            mi = MODEL_REGISTRY.get(mid)
            if not mi:
                return "[dim]—[/]"
            badges = []
            if mi.supports_tools:
                badges.append("🔧")
            if mi.supports_vision:
                badges.append("👁")
            if mi.supports_thinking:
                badges.append("🧠")
            return " ".join(badges) if badges else "[dim]对话[/]"

        def _model_desc(pid: str, p: dict, mid: str) -> str:
            """从 MODEL_REGISTRY 获取模型描述，fallback 到供应商级描述。"""
            mi = MODEL_REGISTRY.get(mid)
            if mi and mi.description:
                return mi.description
            return p.get("description", "") or {
                "crux": "原生模型 · 轻量快速",
                "deepseek": "百万上下文 · 代码/推理",
                "zhipu": "免费模型矩阵 · 视觉/推理/生图",
                "copilot": "Copilot 订阅免费 · 快速对话/代码",
            }.get(pid, "外部供应商")

        table = Table(
            title="[bold cyan]选择主对话供应商[/]（视觉始终走 CRUX 独立通道）", border_style=COLORS["primary"]
        )
        table.add_column("#", style="bold cyan", width=3)
        table.add_column("供应商", style="white", width=16)
        table.add_column("主模型", style="bold", width=20)
        table.add_column("能力", style="cyan", width=10)
        table.add_column("说明", style="dim")
        choices = []
        idx = 1
        for pid, p, model, _ in available:
            label = f"{idx}"
            badges = _capability_badges(model)
            desc = _model_desc(pid, p, model)
            table.add_row(label, p["name"], model, badges, desc)
            choices.append((str(idx), pid, p, model))
            idx += 1
        # Add auto-select option
        table.add_row("[bold green]0[/]", "[bold green]自动选择[/]", "auto", "[green]智能[/]", "根据任务复杂度智能路由到最优模型")
        console.print(table)
        console.print()
        choice = Prompt.ask(
            "[cyan]选择供应商[/]",
            choices=["0"] + [c[0] for c in choices] + ["q"],
            default="1",
        )
        if choice == "0":
            # Auto mode: use the first available external provider as default, route per-prompt
            best_pid, best_p, best_model = available[0][0], available[0][1], available[0][2]
            if best_pid != "crux":
                key_env = f"{best_pid.upper()}_API_KEY"
                api_key = best_p.get("api_key") or os.getenv(key_env)
                self._activate_provider(best_pid, best_p, best_model, api_key, cfg, cfg_path)
            show_success("已激活自动选择模式 — 每轮对话智能路由到最优模型")
            return ("auto", best_model)
        if choice == "q":
            show_info("已取消，使用默认 CRUX light")
            p = providers.get("crux", {})
            return ("crux", p.get("models", {}).get("light", "agnes-1.5-flash"))
        # 找到选中的供应商
        for num, pid, p, model in choices:
            if num == choice:
                if pid == "crux":
                    return (pid, model)
                # 外部供应商需要激活
                key_env = f"{pid.upper()}_API_KEY"
                api_key = p.get("api_key") or os.getenv(key_env)
                self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
                return (pid, model)
        return ("crux", "agnes-1.5-flash")

    def _activate_provider(self, pid, p, model, api_key, cfg, cfg_path):
        """激活指定供应商：切换 client 并写入 models.json"""
        self.client.close()
        self.client = CruxClient(api_key=api_key, base_url=p["base_url"])
        cfg["active"] = pid
        with contextlib.suppress(OSError, TypeError):
            Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        from core.provider import get_model_description

        cap = get_model_description(model) or model
        show_success(f"已激活 {p['name']} → {model}（{cap}）")

    @staticmethod
    def _load_models_config() -> dict:
        """安全加载 models.json（项目根），文件缺失/空/损坏时返回默认配置"""
        import json

        cfg_path = os.path.join(_DIAG_ROOT, "models.json")

        def _default_cfg():
            return {
                "providers": {
                    "crux": {
                        "name": "CRUX AI",
                        "base_url": "https://apihub.agnes-ai.com/v1",
                        "api_key": "",
                        "models": {"light": "agnes-1.5-flash", "pro": "agnes-2.0-flash"},
                    },
                    "deepseek": {
                        "name": "DeepSeek V4 Pro (1M)",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "",
                        "models": {"pro": "deepseek-v4-pro", "light": "deepseek-v4-flash", "chat": "deepseek-chat", "reasoner": "deepseek-reasoner"},
                    },
                    "zhipu": {
                        "name": "Zhipu GLM (Free)",
                        "base_url": "https://open.bigmodel.cn/api/paas/v4",
                        "api_key": "",
                        "cost_tier": "free",
                    },
                },
                "active": "deepseek",
                "fallback": {"enabled": True, "priority": ["deepseek", "zhipu"]},
            }

        if not os.path.exists(cfg_path):
            # 新建默认文件
            cfg = _default_cfg()
            with contextlib.suppress(OSError, TypeError):
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
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
                cfg["active"] = "crux"
            return cfg
        except (json.JSONDecodeError, ValueError) as e:
            # 文件损坏或为空 → 重建
            show_warning(f"models.json 损坏 ({e})，已自动重建默认配置")
            cfg = _default_cfg()
            with contextlib.suppress(OSError, TypeError):
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return cfg

    @staticmethod
    def _chat_switch_model(session: "ChatSession", arg: str):
        from core.chat import MODEL_ALIASES, MODEL_INFO, _refresh_aliases_and_info
        from core.provider import get_provider_manager

        if not arg:
            show_warning("用法: /model light 或 /model pro 或 /model <模型ID>")
            return
        # 先查 models.json 中的 model_aliases（供应商维度）
        mgr = get_provider_manager()
        mgr.load()
        for _pid, pdata in mgr.providers.items():
            aliases = pdata.get("model_aliases", {})
            if isinstance(aliases, dict) and arg in aliases:
                arg = aliases[arg]
                break
        # 先查别名，再查 raw ID（如 deepseek-chat、kimi-k2.6）
        _refresh_aliases_and_info()
        if arg in MODEL_ALIASES:
            session.model = MODEL_ALIASES[arg]
            target = session.model
        else:
            session.model = arg
            target = arg
        # 供应商自动切换：模型属于哪个供应商就用哪个 client
        for pid, pdata in mgr.providers.items():
            models = pdata.get("models", {})
            if isinstance(models, dict) and target in models.values():
                if session.client.base_url != pdata.get("base_url", ""):
                    expected_url = pdata.get("base_url", "")
                    new_client = mgr.create_client(pid)
                    # 防御性校验：create_client 的 auth_required fallback 可能
                    # 跑偏到别的 provider，导致 client.base_url 与目标不一致
                    if new_client.base_url.rstrip("/") != expected_url.rstrip("/"):
                        show_warning(
                            f"切换失败：{pdata.get('name', pid)} 不可用 (client 被重定向到 {new_client.base_url})"
                        )
                        # 回滚 session.model（未实际切换成功）
                        if arg in MODEL_ALIASES:
                            session.model = arg  #
                        else:
                            session.model = target  #
                        return
                    session.client = new_client
                    console.print(f"  [dim]已切至 {pdata.get('name', pid)} 供应商[/]")
                break
        # 从 provider 派生描述，避免回退到旧缓存
        try:
            from core.provider import get_model_description
            cap = get_model_description(target) or f"外部模型（{'支持 tool calling' if session.supports_tools else '纯文本对话'}）"
        except Exception:
            cap = f"外部模型（{'支持 tool calling' if session.supports_tools else '纯文本对话'}）"
        # 刷新系统提示词，让 AI 知道当前使用的模型
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        show_success(f"已切换到 {target} — {cap}")
        print_mode_banner(session)

    def _chat_prompt_stats(self, session: "ChatSession", arg: str):
        """Prompt Lab 实验统计 — 查看各变体效果对比"""
        try:
            from core.prompt_lab import get_prompt_lab
        except ImportError:
            show_warning("Prompt Lab 模块不可用")
            return
        lab = get_prompt_lab()
        arg = arg.strip()
        if not arg or arg == "summary":
            console.print(lab.summary_text())
            return
        # 查看变体列表
        if arg == "variants" or arg == "list":
            variants = lab.list_variants()
            if not variants:
                show_info("暂无实验变体。")
                console.print("  [dim]提示: 可通过代码 create_variant() 创建[/]")
                return
            console.print("[bold]Prompt Lab 变体:[/]")
            for v in variants:
                active = "[green]●[/]" if v.is_active else "[dim]○[/]"
                cur = " [yellow]← 当前[/]" if lab.current_variant and lab.current_variant.id == v.id else ""
                console.print(f"  {active} [cyan]{v.id}[/] {v.label} ({v.name}) ratio={v.traffic_ratio}{cur}")
                console.print(f"    [dim]{v.instructions[:100]}[/]")
            return
        if arg == "reset":
            lab.reset_session()
            show_success("Prompt Lab 会话已重置")
            return
        show_info("用法: /prompt-stats [summary|variants|reset]")

    def _chat_prompt_assign(self, session: "ChatSession", arg: str):
        """手动分配 Prompt Lab 变体到当前会话"""
        try:
            from core.prompt_lab import get_prompt_lab
        except ImportError:
            show_warning("Prompt Lab 模块不可用")
            return
        arg = arg.strip()
        if not arg:
            # 显示可用变体
            lab = get_prompt_lab()
            variants = lab.list_variants(active_only=True)
            if not variants:
                show_info("无可用变体，先用 create_variant() 创建")
                return
            console.print("[bold]可用变体:[/]")
            for v in variants:
                cur = " [yellow]← 当前[/]" if lab.current_variant and lab.current_variant.id == v.id else ""
                console.print(f"  [cyan]{v.id}[/] {v.label}{cur}")
            show_info("用法: /prompt-assign <变体ID>")
            return
        lab = get_prompt_lab()
        v = lab.assign_variant(arg)
        if v:
            show_success(f"已分配变体: [{v.label}] ({v.id})")
            # 重建 system prompt 让变体指令生效
            session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        else:
            show_warning(f"变体 '{arg}' 不存在或未激活")
            console.print("  [dim]用 /prompt-stats variants 查看可用变体[/]")

    def _chat_extend(self, session: "ChatSession", arg: str):
        """切换扩展工具集 — 统一入口管理 notebook/audio/browser。
        用法:
            /extend                  显示所有扩展状态（list 视图）
            /extend notebook         切换 Notebook (.ipynb) 工具
            /extend audio            切换音频工具（TTS/BGM/SFX/混音）
            /extend browser          切换 Browser Companion（8 平台网页生成）
            /extend list             等同于无参，显示状态表
        """
        arg = arg.strip().lower()
        # ── 子命令分发 ──
        toggles = {
            "notebook": ("notebook_enabled", "toggle_notebook", "📓 Notebook", "打开/编辑/执行/保存 .ipynb 文件"),
            "audio": ("audio_enabled", "toggle_audio", "🎵 音频", "TTS 旁白/BGM/SFX/混音（edge-tts+ffmpeg）"),
            "browser": (
                "browser_enabled",
                "toggle_browser",
                "🌐 Browser",
                "可灵/即梦/Runway/Luma/DALL-E/Gemini/Opal/Veo 网页生成",
            ),
        }
        # 无参或 list：显示状态表
        if not arg or arg == "list":
            tbl = Table(title="[bold]🔌 扩展工具集状态[/]", border_style=COLORS["primary"], show_lines=True)
            tbl.add_column("扩展", style="cyan", width=20)
            tbl.add_column("状态", width=8)
            tbl.add_column("说明", style="dim")
            for _key, (attr, _, label, desc) in toggles.items():
                is_on = getattr(session, attr, False)
                status = "[green]● 启用[/]" if is_on else "[dim]○ 停用[/]"
                tbl.add_row(label, status, desc)
            console.print(tbl)
            console.print("  [dim]用法: /extend <notebook|audio|browser> 切换 · /extend list 重显状态[/]")
            return
        # 切换指定扩展
        if arg not in toggles:
            show_warning(f"未知扩展: {arg}。可用: notebook / audio / browser")
            console.print("  [dim]用法: /extend <notebook|audio|browser|list>[/]")
            return
        attr, toggle_fn, label, desc = toggles[arg]
        toggle = getattr(session, toggle_fn)
        is_on = toggle()
        if is_on:
            show_success(f"{label} 已启用 — {desc}")
        else:
            show_success(f"{label} 已停用")
        print_mode_banner(session)

    def _chat_eval(self, session: "ChatSession", arg: str):
        """运行智能体质量基准测试 — 覆盖代码搜索/代码质量/理解能力。
        无参或 table：表格展示结果
        json：输出 JSON 格式报告（适合 CI/CD 集成）
        """
        try:
            from core.eval_harness import BENCHMARKS, EvalEngine
        except ImportError:
            show_warning("eval_harness 模块不可用")
            return
        arg = arg.strip()
        output_json = arg.lower() == "json"
        show_info("正在运行智能体质量基准测试...")
        engine = EvalEngine()
        report = engine.run_all()
        if output_json:
            console.print(json.dumps(report, indent=2, ensure_ascii=False))
            return
        # ── 表格展示 ──
        summary_tbl = Table(title="[bold]📊 智能体质量基准[/]", border_style=COLORS["primary"], show_lines=True)
        summary_tbl.add_column("指标", style="bold cyan", width=20)
        summary_tbl.add_column("值", justify="right")
        summary_tbl.add_row("总分", f"{report['score']:.1f} / 100")
        summary_tbl.add_row("通过", f"{report['passed']} / {report['total']}")
        summary_tbl.add_row("失败", f"{report['failed']}")
        console.print(summary_tbl)
        # ── 各项详情表 ──
        detail_tbl = Table(title="详细结果", border_style="dim", show_lines=True)
        detail_tbl.add_column("ID", style="cyan", width=22)
        detail_tbl.add_column("类别", width=14)
        detail_tbl.add_column("状态", width=6)
        detail_tbl.add_column("得分", justify="right", width=6)
        detail_tbl.add_column("耗时", justify="right", width=8)
        for r in report.get("results", []):
            status_icon = (
                "[green]PASS[/]"
                if r["status"] == "pass"
                else ("[red]FAIL[/]" if r["status"] == "fail" else "[yellow]ERR[/]")
            )
            detail_tbl.add_row(
                r["id"],
                r["category"],
                status_icon,
                f"{r['score']:.2f}",
                f"{r['elapsed']}s",
            )
        console.print(detail_tbl)
        console.print(f"  [dim]基准集: {report['suite']} · {len(BENCHMARKS)} 项 · /eval json 输出 JSON 格式[/]")

    def _chat_cost(self, session: "ChatSession", arg: str):
        """花费统计 — 查看 / 设日预算 / 清零
        无参或 summary：显示总花费 + 今日 + 按模型分桶表格
        budget <usd>：设置每日预算上限（美元），超过时 send_stream 开头会提示
        budget off：关闭预算
        reset：清零累计花费并归档旧日志
        """
        try:
            from core.cost_tracker import (
                get_daily_breakdown,
                get_summary,
                reset_cost,
                set_budget,
            )
        except ImportError:
            show_warning("cost_tracker 模块不可用")
            return
        arg = arg.strip()
        parts = arg.split() if arg else []
        # ── budget <usd>|off ──
        if parts and parts[0] == "budget":
            if len(parts) < 2:
                show_info("用法: /cost budget <usd>  或  /cost budget off")
                return
            if parts[1].lower() == "off":
                set_budget(None)
                show_success("已关闭每日预算上限")
                return
            try:
                usd = float(parts[1])
            except ValueError:
                show_warning(f"无效金额: {parts[1]}（应为数字，如 1.5）")
                return
            if usd <= 0:
                show_warning("预算必须大于 0")
                return
            set_budget(usd)
            show_success(f"已设置每日预算上限: ${usd:.2f}")
            return
        # ── reset ──
        if parts and parts[0] == "reset":
            result = reset_cost()
            show_success(f"已清零花费统计（此前累计 ${result.get('cleared_total', 0):.4f}），旧日志已归档")
            return
        # ── 默认：汇总表格 ──
        summary = get_summary()
        total = summary.get("total_cost", 0.0)
        calls = summary.get("total_calls", 0)
        today = summary.get("by_day", {})
        # 今日花费
        from datetime import datetime

        today_key = datetime.now().strftime("%Y-%m-%d")
        today_cost = today.get(today_key, {}).get("cost", 0.0)
        # 预算状态行
        budget = summary.get("budget")
        if budget and "daily" in budget:
            daily_limit = budget["daily"]
            pct = (today_cost / daily_limit * 100) if daily_limit > 0 else 0
            budget_line = f"  [dim]日预算: ${daily_limit:.2f} · 今日已用 {pct:.0f}%[/]"
        else:
            budget_line = "  [dim]日预算: 未设置（/cost budget <usd> 设置）[/]"
        console.print(
            Panel(
                f"[bold green]总花费: ${total:.4f}[/]  ·  [cyan]{calls} 次调用[/]  ·  [yellow]今日: ${today_cost:.4f}[/]\n"
                + budget_line,
                title="[bold]💰 花费统计[/]",
                border_style=COLORS["primary"],
            )
        )
        # 按模型分桶表格
        by_model = summary.get("by_model", {})
        if by_model:
            tbl = Table(title="按模型", show_lines=False, border_style="dim")
            tbl.add_column("模型", style="cyan")
            tbl.add_column("花费", justify="right", style="green")
            tbl.add_column("调用次数", justify="right")
            for model, info in sorted(by_model.items(), key=lambda x: x[1].get("cost", 0), reverse=True):
                tbl.add_row(model, f"${info.get('cost', 0):.4f}", str(info.get("calls", 0)))
            console.print(tbl)
        # 最近 7 天趋势
        daily = get_daily_breakdown(7)
        if daily:
            dtbl = Table(title="最近 7 天", show_lines=False, border_style="dim")
            dtbl.add_column("日期", style="cyan")
            dtbl.add_column("花费", justify="right", style="green")
            dtbl.add_column("调用次数", justify="right")
            for d in daily:
                dtbl.add_row(d["day"], f"${d.get('cost', 0):.4f}", str(d.get("calls", 0)))
            console.print(dtbl)
        console.print("  [dim]子命令: /cost budget <usd> · /cost budget off · /cost reset[/]")

    # ── MCP 服务器管理 ──────────────────────────────────────────
    def _chat_mcp(self, session: "ChatSession", arg: str):
        """MCP 服务器管理 — 注册/启停/查看远程 MCP server 连接。
        子命令：
            /mcp list                         显示所有配置的服务器
            /mcp add <name> -- <command>      注册新服务器
            /mcp remove <name>                移除服务器
            /mcp connect <name>               启动连接
            /mcp disconnect <name>            断开连接
            /mcp tools <name>                 查看服务器提供的工具
        """
        try:
            from core.mcp_client import get_mcp_client
        except ImportError:
            show_warning("mcp_client 模块不可用")
            return
        from rich.console import Console

        console = Console()
        client = get_mcp_client()
        arg = arg.strip()
        parts = arg.split() if arg else []
        sub = parts[0] if parts else ""
        # ── list：显示所有服务器 ──
        if not sub or sub == "list":
            servers = client.list_servers()
            if not servers:
                show_info("没有配置任何 MCP 服务器")
                console.print("  [dim]用 /mcp add <name> -- <command> 注册服务器[/]")
                console.print("  [dim]例: /mcp add claude -- claude-code mcp[/]")
                return
            tbl = Table(title="MCP 服务器", show_lines=False, border_style="cyan")
            tbl.add_column("名称", style="bold cyan")
            tbl.add_column("命令", style="white")
            tbl.add_column("状态", justify="center")
            tbl.add_column("启用", justify="center")
            for s in servers:
                name = s.get("name", "?")
                cmd = s.get("command", "?")
                args_list = s.get("args", [])
                full_cmd = cmd + (" " + " ".join(args_list) if args_list else "")
                enabled = s.get("enabled", True)
                # 判断是否已连接
                connected = name in client._processes
                status = "[green]● 已连接[/]" if connected else "[dim]○ 未连接[/]"
                enabled_str = "[green]✓[/]" if enabled else "[red]✗[/]"
                tbl.add_row(name, full_cmd, status, enabled_str)
            console.print(tbl)
            console.print("  [dim]子命令: /mcp add · /mcp remove · /mcp connect · /mcp disconnect · /mcp tools[/]")
            return
        # ── add：注册新服务器 ──
        if sub == "add":
            # 格式: /mcp add <name> -- <command> [args...]
            if len(parts) < 4 or "--" not in parts:
                show_warning("用法: /mcp add <name> -- <command> [args...]")
                console.print("  [dim]例: /mcp add claude -- claude-code mcp[/]")
                console.print("  [dim]例: /mcp add fs -- node /path/to/server.js[/]")
                return
            sep_idx = parts.index("--")
            name = parts[1]
            if sep_idx < 2:
                show_warning("用法: /mcp add <name> -- <command> [args...]")
                return
            command = parts[sep_idx + 1] if sep_idx + 1 < len(parts) else ""
            cmd_args = parts[sep_idx + 2 :] if sep_idx + 2 < len(parts) else []
            if not name or not command:
                show_warning("服务器名称和命令不能为空")
                return
            result = client.add_server(name=name, command=command, args=cmd_args if cmd_args else None)
            if "error" in result:
                show_warning(result["error"])
            else:
                show_success(f"已注册 MCP 服务器 [bold]{name}[/]（命令: {command} {' '.join(cmd_args)}）")
                console.print(f"  [dim]用 /mcp connect {name} 启动连接[/]")
            return
        # ── remove：移除服务器 ──
        if sub == "remove":
            if len(parts) < 2:
                show_warning("用法: /mcp remove <name>")
                return
            name = parts[1]
            if client.remove_server(name):
                show_success(f"已移除 MCP 服务器 [bold]{name}[/]")
            else:
                show_warning(f"服务器 '{name}' 不存在")
            return
        # ── connect：启动连接 ──
        if sub == "connect":
            if len(parts) < 2:
                show_warning("用法: /mcp connect <name>")
                return
            name = parts[1]
            show_info(f"正在连接 {name}...")
            result = client.connect(name)
            if "error" in result:
                show_warning(f"连接失败: {result['error']}")
            else:
                caps = result.get("capabilities", {})
                tools_count = len(caps.get("tools", []))
                show_success(f"已连接到 [bold]{name}[/]（发现 {tools_count} 个工具）")
            return
        # ── disconnect：断开连接 ──
        if sub == "disconnect":
            if len(parts) < 2:
                show_warning("用法: /mcp disconnect <name>")
                return
            name = parts[1]
            result = client.disconnect(name)
            if "error" in result:
                show_warning(result["error"])
            else:
                show_success(f"已断开 [bold]{name}[/]")
            return
        # ── tools：查看服务器工具 ──
        if sub == "tools":
            if len(parts) < 2:
                show_warning("用法: /mcp tools <name>")
                return
            name = parts[1]
            tools = client.list_tools(name)
            if tools and "error" in tools[0]:
                show_warning(tools[0]["error"])
                console.print(f"  [dim]可能需要先 /mcp connect {name}[/]")
                return
            if not tools:
                show_info(f"{name} 没有暴露任何工具")
                return
            ttbl = Table(title=f"{name} 的工具", show_lines=False, border_style="green")
            ttbl.add_column("#", justify="right", style="dim", width=3)
            ttbl.add_column("工具名", style="bold green")
            ttbl.add_column("描述")
            for i, t in enumerate(tools, 1):
                tname = t.get("name", "?")
                tdesc = t.get("description", "")[:60]
                ttbl.add_row(str(i), tname, tdesc)
            console.print(ttbl)
            return
        # ── 未知子命令 ──
        show_warning(f"未知子命令: {sub}")
        console.print("  [dim]可用: list · add · remove · connect · disconnect · tools[/]")
