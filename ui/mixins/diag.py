"""诊断配置命令 Mixin：自诊断/审计/规范/自动化/供应商/进化/知识库/模型切换。"""

import os
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from core.client import AgnesClient
from utils import memory
from ui.display import (console, COLORS, show_warning, show_success, show_info)
import contextlib

if TYPE_CHECKING:
    from core.chat import ChatSession

__all__ = ['DiagCommandsMixin']



class DiagCommandsMixin:
    # Method provided by SharedMixin (sibling in MRO)
    def _stream_chat(self, session: "ChatSession", user: str) -> None:
        ...  # defined in SharedMixin, available via MRO


    def _self_diagnose(self, session: "ChatSession", arg: str):
        """工具自诊断 — 让工具检查自身健康、分析源码、发现并修复 bug

        用法:
            /self check  — 遍历所有 .py 文件进行语法检查
            /self files  — 树状打印项目目录结构
            /self health — 检测 API Key / Python版本 / 依赖 / 使用统计
            /self fix    — 将 core/engines 源码喂给 AI，让 AI 分析问题并提出修复方案
        """
        from core.audit_runner import audit_syntax, project_tree_data, health_checks, collect_source_snippets

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
            tree = Tree("[cyan]agnes-smart-studio[/]")
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
            console.print(f"  📊 生成: {stats.get('total', 0)} 次 | ⭐评分: {stats.get('rated_count', 0)} 条 | 🚫过滤: {stats.get('content_policy_hits', 0)} 次")

        # ── /self fix：AI 源码分析 ─────────────────────
        elif arg == "fix":
            session.unlimited_tools = True
            session.toggle_code_mode()
            ctx = "你是 Agnes Smart Studio 维护者。以下是核心源码，请分析 bug/合规性/优化建议：\n\n"
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
            self._stream_chat(session, "你是 Agnes Smart Studio 维护者。请对项目做源码审计，输出：Bug 风险 | API 合规性 | 优化建议。")
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
                r = subprocess.run(["pip", "list", "--outdated", "--format", "columns"],
                                   capture_output=True, text=True, timeout=30)
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
        import os
        import json
        from datetime import datetime
        automations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "automations")
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
            with open(cfg_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(cfg, indent=2, ensure_ascii=False))

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

        if stats['image'] + stats['video'] < 5:
            console.print("\n  [dim]评分越多，进化越快。生成后给 4-5 星即可积累案例。[/]")
            console.print("\n  [bold]提示词速成:[/]")
            console.print("  [dim]主体+场景[/] '一只狐狸在雪地里'")
            console.print("  [dim]主体+风格[/] '一只狐狸 水墨画'")
            console.print("  [dim]主体+动作+场景[/] '冲锋的战士 雨夜战场'")
            console.print("  [dim]只需这 3 种格式，增强器负责补全 10 段细节。[/]")

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

        1. 扫描所有 providers，收集有 API Key 的
        2. 1 个外部供应商 → 自动激活
        3. ≥2 个外部供应商 → 弹出菜单让用户选择
        4. 0 个外部供应商 → 使用 Agnes

        Returns: (provider_id, model_id)
        """
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
        self.client.close()
        self.client = AgnesClient(api_key=api_key, base_url=p["base_url"])
        cfg["active"] = pid
        with contextlib.suppress(OSError, TypeError):
            Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        from core.chat import MODEL_INFO
        cap = MODEL_INFO.get(model, pid)
        show_success(f"已激活 {p['name']} → {model}（{cap}）")

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
                cfg["active"] = "agnes"
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
        from core.chat import MODEL_ALIASES, MODEL_INFO
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
                    new_client = mgr.create_client(pid)
                    session.client = new_client
                    console.print(f"  [dim]已切至 {pdata.get('name', pid)} 供应商[/]")
                break
        if target in MODEL_INFO:
            cap = MODEL_INFO[target]
        else:
            cap = f"外部模型（{'支持 tool calling' if session.supports_tools else '纯文本对话'}）"
        # 刷新系统提示词，让 AI 知道当前使用的模型
        session.messages[0] = {"role": "system", "content": session._build_system_prompt()}
        show_success(f"已切换到 {target} — {cap}")
