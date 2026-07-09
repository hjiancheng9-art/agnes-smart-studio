"""智能体工具注册与执行系统

让 crux-smart-studio 作为主脑，调用和管理外部工具/脚本/API。
工具可从 tools.json 配置文件加载，也可通过 Python API 动态注册。

结构:
    tools.json         ← 用户定义的工具清单
    core/tools.py      ← 本文件：注册、执行、格式转换

工具类型:
    "shell"    - 执行本地命令，返回 stdout
    "http"     - 调用 HTTP API，返回响应
    "python"   - 调用 Python 函数（import 路径）
    "pipeline" - 一键流视频管道工具（Showrunner 专用）
"""

import importlib
import json
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

TOOLS_CONFIG = Path(__file__).parent.parent / "tools.json"


# ── 轻量 no-op 上下文管理器（observability 不可用时降级）──
@contextmanager
def _noop_cm():
    """Yield None, no-op.  Used when core.observability is not importable."""
    yield None


__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "BUILTIN_TOOLS",
    "CORE_TOOL_NAMES",
    "PIPELINE_TOOL_DEFS",
    "TOOLS_CONFIG",
    "TOOL_EXPANSION_CATEGORIES",
    "ToolRegistry",
    "_resolve_tool_names",
    "get_registry",
    "reload_registry",
]


# ── 工具定义数据从 tools_defs.py 导入（facade re-export）──
from core.tools_defs import (  # noqa: F401
    _BUILTIN_MODULE,
    _PY_TYPE_MAP,
    AGENT_SYSTEM_PROMPT,
    BUILTIN_TOOLS,
    CORE_TOOL_NAMES,
    PIPELINE_TOOL_DEFS,
    TOOL_CATEGORIES,
    TOOL_EXPANSION_CATEGORIES,
    _levenshtein,
    _resolve_tool_names,
    _suggest_similar_tool,
    _validate_args,
)


class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []  # OpenAI function 格式
        self._executors: dict[str, Callable[..., str]] = {}  # name → 执行函数
        self._tool_modules: dict[str, str] = {}  # name → 模块路径（分类用）
        self.model_router = None  # Optional ModelRouter for sub-agent dispatch

    # ── 加载 ──
    def load(
        self,
        pipeline: bool = False,
        browser: bool = False,
        notebook: bool = False,
        audio: bool = False,
        mcp: bool = False,
        agnes: bool = False,
        showrunner: bool = False,
    ) -> int:
        """从 tools.json 加载工具，返回已加载数量

        Args:
            pipeline: 是否加载一键流视频管道工具（Showrunner 模式）
            browser: 是否加载 Browser Companion 网页生成工具
            notebook: 是否加载 Notebook (.ipynb) 工具
            agnes: 是否加载 Agnes 多模态生成工具
            showrunner: 是否加载 Showrunner 专业流水线工具
            audio: 是否加载音频工具（TTS/BGM/SFX/混音）
            mcp: 是否加载 MCP Client 桥接工具（四象融合：调 claude/codex/codebuddy）
            多个可同时为 True（协作模式）
        """
        self._definitions = list(BUILTIN_TOOLS)
        self._executors.clear()
        self._tool_modules.clear()
        # builtin 工具的模块标记
        for d in self._definitions:
            self._tool_modules[d["function"]["name"]] = _BUILTIN_MODULE

        # ── 管道工具 ──
        if pipeline:
            self._definitions.extend(PIPELINE_TOOL_DEFS)
            from core.pipeline_tools import EXECUTOR_MAP as PIPELINE_EXECUTORS

            for name, executor in PIPELINE_EXECUTORS.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.pipeline_tools"

        # ── Agnes 多模态生成（文生图/图生图/文生视频/图生视频）──
        if agnes:
            from core.agnes_multimodal import AGNES_EXECUTOR_MAP, AGNES_TOOL_DEFS

            self._definitions.extend(AGNES_TOOL_DEFS)
            for name, executor in AGNES_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.agnes_multimodal"

        # ── Showrunner 专业流水线（文案→图片→视频→影片）──
        if showrunner:
            from core.showrunner_pipeline import (
                SHOWRUNNER_EXECUTOR_MAP,
                SHOWRUNNER_TOOL_DEFS,
            )

            self._definitions.extend(SHOWRUNNER_TOOL_DEFS)
            for name, executor in SHOWRUNNER_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.showrunner_pipeline"

        # ── Browser Companion 网页生成工具 ──
        if browser:
            from core.browser_tools import BROWSER_EXECUTOR_MAP, BROWSER_TOOL_DEFS

            self._definitions.extend(BROWSER_TOOL_DEFS)
            for name, executor in BROWSER_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.browser_tools"

        # ── Notebook (.ipynb) 工具 ──
        if notebook:
            from core.notebook import NOTEBOOK_EXECUTOR_MAP, NOTEBOOK_TOOL_DEFS

            self._definitions.extend(NOTEBOOK_TOOL_DEFS)
            for name, executor in NOTEBOOK_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.notebook"

        # ── 音频工具（TTS/BGM/SFX/混音）──
        if audio:
            from core.audio_tools import AUDIO_EXECUTOR_MAP, AUDIO_TOOL_DEFS

            self._definitions.extend(AUDIO_TOOL_DEFS)
            for name, executor in AUDIO_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.audio_tools"

        # ── LSP 代码智能工具（常驻加载）──
        # goto_definition / hover / diagnostics / find_references / completion / rename
        from core.lsp import LSP_EXECUTOR_MAP, LSP_TOOL_DEFS

        self._definitions.extend(LSP_TOOL_DEFS)
        for name, executor in LSP_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.lsp"

        # ── Git 工作流工具 (P-2: 常驻加载, 不需要 toggle) ──
        # branch / push / pull / pr / stash / tag / worktree / conflict_check
        # 与 tools.json 中 git_status/diff/log/add_commit 互补,不重名。
        # 注入后 _HIGH_RISK_TOOLS 确认门对 git_push/pr_create/pr_merge/tag 真正生效。
        from core.git_tools import GIT_WORKFLOW_EXECUTOR_MAP
        from core.git_tools import GIT_WORKFLOW_TOOL_DEFS as _GIT_WF_DEFS

        self._definitions.extend(_GIT_WF_DEFS)
        for name, executor in GIT_WORKFLOW_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.git_tools"

        # ── 后台任务管理工具（常驻加载）──
        # task_launch / task_list / task_output / task_stop
        # 移植自 Kimi Code CLI，填补 run_in_background 功能空白
        from core.background import BACKGROUND_EXECUTOR_MAP, BACKGROUND_TOOL_DEFS

        self._definitions.extend(BACKGROUND_TOOL_DEFS)
        for name, executor in BACKGROUND_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.background"

        # ── 目标评估器工具（常驻加载）──
        # goal_evaluate: 评估目标完成度，给出 pass/fail/needs_fix 裁决
        from core.goal_evaluator import GOAL_EVALUATE_TOOL_DEF, _exec_goal_evaluate

        self._definitions.append(GOAL_EVALUATE_TOOL_DEF)
        self._executors["goal_evaluate"] = _exec_goal_evaluate
        self._tool_modules["goal_evaluate"] = "core.goal_evaluator"

        # ── 规划模式工具（常驻加载）──
        # enter_plan_mode / exit_plan_mode / plan_status
        from core.plan_mode import PLAN_MODE_EXECUTOR_MAP, PLAN_MODE_TOOL_DEFS

        self._definitions.extend(PLAN_MODE_TOOL_DEFS)
        for name, executor in PLAN_MODE_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Quest Engine (方法论第5章) ──
        from core.quest_engine import QUEST_EXECUTOR_MAP, QUEST_TOOL_DEFS

        self._definitions.extend(QUEST_TOOL_DEFS)
        for name, executor in QUEST_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── WorkBuddy 办公Agent (方法论第19章) ──
        from core.workbuddy import WORKBUDDY_EXECUTOR_MAP, WORKBUDDY_TOOL_DEFS

        self._definitions.extend(WORKBUDDY_TOOL_DEFS)
        for name, executor in WORKBUDDY_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Repo Wiki 知识库 (方法论第6章) ──
        from core.repo_wiki import WIKI_EXECUTOR_MAP, WIKI_TOOL_DEFS

        self._definitions.extend(WIKI_TOOL_DEFS)
        for name, executor in WIKI_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── ADR 架构决策记录 (方法论第8章) ──
        from core.adr_engine import ADR_EXECUTOR_MAP, ADR_TOOL_DEFS

        self._definitions.extend(ADR_TOOL_DEFS)
        for name, executor in ADR_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── TDD 工作流 (方法论第10章) ──
        from core.tdd_workflow import TDD_EXECUTOR_MAP, TDD_TOOL_DEFS

        self._definitions.extend(TDD_TOOL_DEFS)
        for name, executor in TDD_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Retro 复盘 (方法论第9章) ──
        from core.retro_engine import RETRO_EXECUTOR_MAP, RETRO_TOOL_DEFS

        self._definitions.extend(RETRO_TOOL_DEFS)
        for name, executor in RETRO_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.plan_mode"

        # ── Agent Swarm 工具（常驻加载）──
        from core.multi_agent import AGENT_SWARM_TOOL_DEF, _exec_agent_swarm

        self._definitions.append(AGENT_SWARM_TOOL_DEF)
        self._executors["agent_swarm"] = _exec_agent_swarm
        self._tool_modules["agent_swarm"] = "core.multi_agent"

        # ── 代码审查工具（常驻加载）──
        # code_review / security_review — 借鉴 Copilot CLI /review + /security-review
        from core.code_review import CODE_REVIEW_EXECUTOR_MAP, CODE_REVIEW_TOOL_DEFS

        self._definitions.extend(CODE_REVIEW_TOOL_DEFS)
        for name, executor in CODE_REVIEW_EXECUTOR_MAP.items():
            self._executors[name] = executor
        # ── CI/CD Pipeline (方法论第10章) ──
        from core.ci_pipeline import PIPELINE_EXECUTOR_MAP
        from core.ci_pipeline import PIPELINE_TOOL_DEFS as CI_PIPELINE_TOOL_DEFS

        self._definitions.extend(CI_PIPELINE_TOOL_DEFS)
        for name, executor in PIPELINE_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Artifact Pipeline (方法论第13章) ──
        from core.artifact_pipeline import ARTIFACT_EXECUTOR_MAP, ARTIFACT_TOOL_DEFS

        self._definitions.extend(ARTIFACT_TOOL_DEFS)
        for name, executor in ARTIFACT_EXECUTOR_MAP.items():
            self._executors[name] = executor

        # ── Rollback/Gray-release (方法论第14章) ──
        from core.rollback_engine import RELEASE_EXECUTOR_MAP, RELEASE_TOOL_DEFS

        self._definitions.extend(RELEASE_TOOL_DEFS)
        for name, executor in RELEASE_EXECUTOR_MAP.items():
            self._executors[name] = executor

            self._tool_modules[name] = "core.code_review"

        # ── 会话任务追踪工具（常驻加载）──
        # todo_add / todo_list / todo_update / todo_delete / todo_dep / todo_blocked / todo_stats
        # 借鉴 Copilot CLI SQL todos + todo_deps 表设计
        from core.session_tracker import SESSION_TRACKER_EXECUTOR_MAP, SESSION_TRACKER_TOOL_DEFS

        self._definitions.extend(SESSION_TRACKER_TOOL_DEFS)
        for name, executor in SESSION_TRACKER_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.session_tracker"

        # ── 代码格式化 & 静态检查工具（常驻加载）──
        # run_format: ruff format + isort (Python) / prettier (JS/TS)
        # run_lint: ruff check (Python) / eslint (JS/TS)
        from core.format_tools import FORMAT_EXECUTOR_MAP, FORMAT_TOOL_DEFS

        self._definitions.extend(FORMAT_TOOL_DEFS)
        for name, executor in FORMAT_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.format_tools"

        # ── 运行时检查工具（常驻加载）──
        # debug_inspect: run test/script, capture traceback + frame locals on failure
        from core.runtime_inspect import INSPECT_EXECUTOR_MAP, INSPECT_TOOL_DEFS

        self._definitions.extend(INSPECT_TOOL_DEFS)
        for name, executor in INSPECT_EXECUTOR_MAP.items():
            self._executors[name] = executor
            self._tool_modules[name] = "core.runtime_inspect"

        # ── 自愈工具（常驻加载）──
        # self_heal: audit + auto-fix the entire codebase

        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "self_heal",
                    "description": "Audit and auto-fix the CRUX codebase. Scans for: silent exceptions, syntax errors, config drift, import failures, test failures. Use --fix to auto-patch fixable issues.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fix": {
                                "type": "boolean",
                                "description": "Auto-fix what can be safely fixed (default: audit only)",
                            },
                            "quick": {
                                "type": "boolean",
                                "description": "Skip slow scans (imports, tests) for fast feedback",
                            },
                        },
                        "required": [],
                    },
                },
            }
        )
        self._executors["self_heal"] = lambda **kw: _exec_self_heal(
            fix=bool(kw.get("fix", False)),
            quick=bool(kw.get("quick", False)),
        )
        self._tool_modules["self_heal"] = "core.self_heal"

        # ── MCP Client 桥接工具（四象融合）──
        # 注入 mcp_list_servers / mcp_list_tools / mcp_call_tool / mcp_read_resource，
        # 让 LLM 能通过 MCP 协议调 claude/codex/codebuddy 的工具。
        # 远程 server 通过 `crux mcp add <name> -- <command>` 配置，
        # executor 自带 auto-connect（首次调用时自动启动子进程握手）。
        if mcp:
            from core.mcp_client import MCP_EXECUTOR_MAP, MCP_TOOL_DEFS

            self._definitions.extend(MCP_TOOL_DEFS)
            for name, executor in MCP_EXECUTOR_MAP.items():
                self._executors[name] = executor
                self._tool_modules[name] = "core.mcp_client"

        if not self._config_path.exists():
            return len(self._definitions)

        try:
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return len(self._definitions)

        for tool_cfg in config.get("tools", []):
            name = tool_cfg.get("name", "")

            # P-4 去重：如果同名工具已由 toggle/内置加载（如 comfyui_*），跳过
            # 避免工具定义中出现重复条目导致 LLM 看到重复工具。
            if name in self._executors:
                continue

            desc = tool_cfg.get("description", name)
            params = tool_cfg.get("parameters", {})
            properties = {}
            required = []

            # 构建 OpenAI function 格式的参数 schema
            for pname, pinfo in params.items():
                if not isinstance(pinfo, dict):
                    # 防御：pinfo 是字符串/列表等非预期类型 → 跳到顶层 schema 字段
                    continue
                properties[pname] = {
                    "type": pinfo.get("type", "string"),
                    "description": pinfo.get("description", pname),
                }
                if pinfo.get("required", False):
                    required.append(pname)

            func_def = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            self._definitions.append(func_def)

            # 注册执行器 + 记录模块路径（分类用）
            self._executors[name] = self._make_executor(name, tool_cfg)
            self._tool_modules[name] = tool_cfg.get("function", "").rsplit(".", 1)[0]

        # ── Fast Scanner ──
        try:
            from core.fast_scanner import SCANNER_EXECUTOR_MAP, SCANNER_TOOL_DEFS

            self._definitions.extend(SCANNER_TOOL_DEFS)
            for _n, _e in SCANNER_EXECUTOR_MAP.items():
                self._executors[_n] = _e
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        # ── MCP Health Check ──
        try:
            self._definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_health_check",
                        "description": "Check MCP connection health and reconnect if dead.",
                        "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}}},
                    },
                }
            )
            from core.mcp_client import get_mcp_client

            def _hchk(**kw):
                import json

                mc = get_mcp_client()
                if kw.get("server_name"):
                    return json.dumps(mc.health_check(kw["server_name"]))
                return json.dumps(mc.health_check_all())

            self._executors["mcp_health_check"] = _hchk
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        # 去重
        seen = set()
        self._definitions = [
            d
            for d in self._definitions
            if not (d.get("function", {}).get("name") in seen or seen.add(d.get("function", {}).get("name")))
        ]

        return len(self._definitions)

    # ── 执行器工厂 ──
    def _make_executor(self, name: str, cfg: dict) -> Callable[..., str]:  # pyright: ignore[reportReturnType]
        """根据类型创建执行函数"""
        t = cfg.get("type", "shell")

        def shell_executor(**kwargs):
            import shlex
            import shutil
            import subprocess as _sp
            import sys

            # ── 提取 shell 控制参数（Copilot CLI 三模式）──
            run_in_background = kwargs.pop("run_in_background", False)
            detach = kwargs.pop("detach", False)
            description = kwargs.pop("description", "")

            safe_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, str):
                    safe_kwargs[k] = shlex.quote(v)
                else:
                    safe_kwargs[k] = v

            raw_cmd = cfg.get("command", "{command}")
            cmd = raw_cmd.format(**safe_kwargs)

            # ── 沙箱验证 ──
            try:
                from core.sandbox import sandbox_restrict

                cmd = sandbox_restrict(cmd)
            except RuntimeError as e:
                return f"[沙箱拒绝] {e}"
            except ImportError:
                pass

            # ── detach 模式：Popen 后台启动，立即返回 pid ──
            if detach:
                if sys.platform == "win32" and not shutil.which("bash"):
                    popen_cmd = cmd
                else:
                    popen_cmd = cmd
                proc = _sp.Popen(
                    popen_cmd,
                    shell=True,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    stdin=_sp.DEVNULL,
                    creationflags=_sp.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
                return f"[detached] pid={proc.pid}" + (f" ({description})" if description else "")

            # ── 超时控制：background 模式放宽超时 ──
            _timeout = cfg.get("timeout", 30)
            if run_in_background:
                _timeout = max(_timeout, 300)  # 后台任务至少 5 分钟

            # ── 跨平台执行 ──
            if sys.platform == "win32" and not shutil.which("bash"):
                r = _sp.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout,
                )
            else:
                r = _sp.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout,
                )
            return r.stdout.strip() or r.stderr.strip() or f"[exit: {r.returncode}]"

        def http_executor(**kwargs):
            import httpx

            url = cfg["url"].format(**kwargs)
            method = cfg.get("method", "GET").upper()
            headers = cfg.get("headers", {})
            timeout = cfg.get("timeout", 30)
            resp = httpx.request(method, url, headers=headers, timeout=timeout)
            return resp.text[:2000]

        def python_executor(**kwargs):
            mod_path, func_name = cfg["function"].rsplit(".", 1)
            # 导入白名单：仅允许 core./engines./pipeline./ui./utils. 下的模块
            _ALLOWED_PREFIXES = ("core.", "engines.", "pipeline.", "ui.", "utils.")
            if not any(mod_path.startswith(p) for p in _ALLOWED_PREFIXES):
                return f"[安全拒绝] 禁止导入外部模块: {mod_path}"
            _BLOCKED_MODULES = {
                "os",
                "subprocess",
                "shutil",
                "ctypes",
                "socket",
                "signal",
                "sys",
                "pty",
                "importlib",
                "inspect",
            }
            if mod_path.split(".")[-1] in _BLOCKED_MODULES:
                return f"[安全拒绝] 禁止导入危险模块: {mod_path}"
            mod = importlib.import_module(mod_path)
            return getattr(mod, func_name)(**kwargs)

        if t == "http":
            return http_executor
        if t == "python":
            return python_executor
        return shell_executor

    # ── 注册/注销 ──
    def register(
        self, name: str, description: str, parameters: dict, executor: Callable[..., str], override: bool = False
    ):
        """动态注册一个工具"""
        if name in self._executors and not override:
            return False
        func_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._definitions.append(func_def)
        self._executors[name] = executor

        return True

    def unregister(self, name: str) -> bool:
        """注销工具"""
        self._definitions = [d for d in self._definitions if d.get("function", {}).get("name") != name]
        return self._executors.pop(name, None) is not None

    # ── 查询 ──
    @property
    def definitions(self) -> list[dict]:
        return self._definitions

    def get_filtered_definitions(self, user_input: str = "", *, full: bool = False) -> list[dict]:
        """按需返回工具定义，降低每次请求的 token 开销。

        默认只返回核心工具（~25 个，约 2.5K tokens vs 全量 14K tokens）。
        - full=True 或 user_input 匹配扩展关键词时，额外展开对应分类。
        - 传空 user_input 且 full=False → 仅核心工具。
        """
        names = _resolve_tool_names(user_input, full=full)
        if not names:  # 空集 = 发全部
            return self._definitions
        return [d for d in self._definitions if d["function"]["name"] in names]

    @property
    def tool_names(self) -> list[str]:
        return [d["function"]["name"] for d in self._definitions]

    @property
    def tool_categories(self) -> dict[str, list[str]]:
        """返回 {分类名: [工具名,...]}，按 TOOL_CATEGORIES 顺序归类。

        未匹配任何分类的工具归入「其他」。分类映射见模块级 TOOL_CATEGORIES。
        """
        result: dict[str, list[str]] = {}
        others: list[str] = []
        # 预初始化分类键（保持顺序）
        for cat_name, _, _ in TOOL_CATEGORIES:
            result[cat_name] = []

        for d in self._definitions:
            name = d["function"]["name"]
            mod = self._tool_modules.get(name, "")
            matched = False
            for cat_name, prefixes, explicit in TOOL_CATEGORIES:
                # 显式工具名优先匹配
                if name in explicit:
                    result[cat_name].append(name)
                    matched = True
                    break
                # 前缀匹配（空前缀跳过）
                if prefixes and prefixes != ("",) and any(mod.startswith(p) for p in prefixes):
                    result[cat_name].append(name)
                    matched = True
                    break
            if not matched:
                others.append(name)

        # 过滤空分类 + 追加「其他」
        result = {k: v for k, v in result.items() if v}
        if others:
            result["📦 其他"] = others
        return result

    def has(self, name: str) -> bool:
        return name in self._executors

    def schema(self, name: str) -> dict | None:
        """Return the JSON Schema for a registered tool."""
        for d in self.definitions:
            func = d.get("function", {})
            if func.get("name") == name:
                params = func.get("parameters")
                return {"parameters": params} if params else None
        return None

    # ── 执行 ──
    def execute(self, name: str, args: dict, validate_result: bool = True) -> str:
        """执行工具并返回结果文本（含轻量观测 + 错误自动恢复 #4）

        错误恢复策略（#4 新增）:
        - 未知工具 → TF-IDF 相似工具建议（而非裸错误）
        - 参数校验 → required 缺失/类型不匹配 → 带期望 schema 的错误字符串
        - 执行异常 → ErrorClassifier 分类 + 恢复建议（而非裸 raise）
        """
        try:
            from core.observability import TraceContext
            from core.observability import metrics as _m
        except ImportError:
            _m = None  # observability 不可用时静默降级
            TraceContext = None  # type: ignore[assignment]

        # 调用日志（可选，失败时静默降级）
        try:
            from core.tool_call_log import log_call as _log_call
        except ImportError:
            _log_call = None

        executor = self._executors.get(name)
        if not executor:
            # NEW (#4): 相似工具建议，帮助模型自我修正
            suggestion = _suggest_similar_tool(name, self._definitions)
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_suggestion_given")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "unknown_tool", 0.0, args)
            if suggestion:
                return f"[错误] 未知工具: {name}。你是否想用: {suggestion}？请检查工具名后重试。"
            return f"[错误] 未知工具: {name}。请检查工具名后重试。"

        # NEW (#4): 前置参数校验
        ok, detail = _validate_args(name, args, self._definitions)
        if not ok:
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_arg_validation_failed")
                _m.increment(f"tool_err.{name}")  # 按名分桶
                _m.increment(f"tool_arg_fail.{name}")  # 参数失败单独计数
            if _log_call:
                _log_call(name, "arg_validation_failed", 0.0, args)
            return detail

        try:
            ctx = TraceContext("registry_execute", tool_name=name) if _m else _noop_cm()  # type: ignore[operator]
            with ctx as span:
                result = executor(**args)
                elapsed_ms = span.duration_ms() if span is not None else 0.0
                if _m and span is not None:
                    span.set_attribute("result_chars", len(str(result)))
                    _m.increment("tool_executions")
                    _m.timing("tool_execute_ms", elapsed_ms)
                    _m.increment(f"tool_exec.{name}")  # 按名分桶
                    _m.timing(f"tool_ms.{name}", elapsed_ms)  # 按名耗时
            if _log_call:
                _log_call(name, "ok", elapsed_ms, args)

            # NEW: Qoder-style Semantic Return Validation
            result_str = str(result)
            if validate_result:
                result_str = self._validate_result(name, result_str, args)

            return result_str
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            # NEW (#4): 错误分类 + 恢复建议（让模型自我修正，而非裸 raise）
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            try:
                from core.resilience import ErrorClassifier

                etype = ErrorClassifier.classify(e)
                hint = ErrorClassifier.get_recovery_hint(e)
                return f"[错误 | {etype.value}] {e}。恢复建议: {hint}。请检查参数或方法后重试。"
            except ImportError:
                # resilience 不可用：退回原行为（raise）
                raise
        except Exception as e:
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")  # 按名分桶
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            return f"[错误] 工具 '{name}' 执行失败: {e}"

    # ── #2 Qoder-style: Semantic Return Validator ──
    @staticmethod
    def _validate_result(tool_name: str, result: str, args: dict) -> str:
        """Lightweight semantic validation of tool results.

        Qoder 理念：不只校验输入参数，还要嗅探结果质量——
        空结果、误判成功、格式异常都应标记，让 LLM 自行修正。

        Returns annotated result string with optional quality tags.
        """
        annotations: list[str] = []

        # 1. 空结果检测（写了文件/搜索了代码却返回空，大概率有问题）
        empty_sensitive_tools = {
            "read_file",
            "search_files",
            "glob_files",
            "find_symbol",
            "search_symbols",
            "find_references",
            "graph_neighbors",
            "graph_ancestors",
            "graph_descendants",
            "code_analyze",
            "web_search",
            "web_fetch",
            "github_search",
            "github_browse",
            "github_readme",
            "list_files",
            "tree_dir",
            "skill_search",
            "env_check",
            "run_test",
        }
        if tool_name in empty_sensitive_tools and (not result or not result.strip()):
            annotations.append("[语义警告] 结果为空——可能工具未找到目标，请检查参数或尝试其他工具")

        # 2. 读文件但内容是截断标记（说明读取范围可能不对）
        if tool_name == "read_file" and len(result) < 50 and result.strip():
            annotations.append("[语义提示] 返回内容很短，可能需要调整 offset/limit")

        # 3. 搜索返回 "no matches" / "not found" 模式
        if tool_name in ("search_files", "find_symbol", "search_symbols", "find_references") and (
            "no matches" in result.lower() or "not found" in result.lower()
        ):
            annotations.append("[语义提示] 未匹配到结果，建议放宽搜索条件或更换关键词")

        # 4. 编辑/写入操作返回空（正常：write_file/edit_file 成功时不返回值）
        if (
            tool_name
            in ("write_file", "edit_file", "safe_rewrite_file", "patch_file", "git_add_commit", "github_write_file")
            and not result.strip()
        ):
            # 这些工具成功时通常无输出，这是预期的
            return result  # 不加标记

        if annotations:
            sep = "\n\n" if "\n" in result else " | "
            return result + sep + " | ".join(annotations)

        return result


# ── 全局单例（线程安全双重检查锁） ──
_registry: ToolRegistry | None = None
_registry_lock = threading.Lock()


def _exec_self_heal(fix: bool = False, quick: bool = False) -> str:
    """Execute self_heal tool — audit + optionally fix the codebase."""
    from core.self_heal import SelfHealer

    healer = SelfHealer()
    if quick:
        healer.scan_syntax()
        healer.scan_config_drift()
    else:
        healer.run_all_scans()
    if fix:
        healer.fix_silent_exceptions()
    return healer.report()


def get_registry(config_path: Path | None = None) -> ToolRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ToolRegistry(config_path)
                _registry.load(mcp=True)
    return _registry


def reload_registry():
    global _registry
    with _registry_lock:
        _registry = None
    return get_registry()
