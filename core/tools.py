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
import logging
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

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


def _exec_grep(**kwargs) -> str:
    """grep 别名 — 重定向到 search_files。"""
    from core.file_tools import search_files

    pattern = kwargs.get("pattern", kwargs.get("query", ""))
    return search_files(pattern)


def _exec_skill_load(**kwargs) -> str:
    """模型调用 skill_load 时执行：动态加载技能到当前会话。"""
    name = kwargs.get("name", "").strip()
    if not name:
        return "用法: skill_load <技能名>。"
    from core.skills import get_manager

    mgr = get_manager()
    # Skill 反馈: 记录加载事件供后续效果评估
    try:
        if not hasattr(mgr, "_skill_usage_log"):
            mgr._skill_usage_log = []
        import time as _time

        mgr._skill_usage_log.append(
            {
                "skill": name,
                "timestamp": _time.time(),
            }
        )
        # Cap at 500 entries to prevent unbounded memory growth
        if len(mgr._skill_usage_log) > 500:
            mgr._skill_usage_log = mgr._skill_usage_log[-250:]
    except Exception:
        logger.debug("Exception in tools", exc_info=True)
    skill = mgr.load(name)
    if skill is None:
        available = list(mgr._available.keys())[:15]
        return f"技能 '{name}' 未找到。可用: {', '.join(available)}"
    return f"技能 '{name}' 已加载: {skill.description}\n{skill.prompt[:500]}"


def _exec_skill_install(**kwargs) -> str:
    """模型调用 skill_install 时执行：从市场安装技能。"""
    name = kwargs.get("name", "").strip()
    if not name:
        return "用法: skill_install <技能名>。先用 skill_search 搜索可用技能。"
    try:
        from core.marketplace import get_marketplace

        mkt = get_marketplace()
        result = mkt.install(name)
        if result:
            return f"技能 '{name}' 安装成功。用 skill_load('{name}') 加载。"
        return f"技能 '{name}' 安装失败。用 skill_search 确认名称正确。"
    except Exception as e:
        return f"安装失败: {e}"


# ── Stable tool wrappers for tools.json entries that need canonical paths ──


def view_image(**kwargs) -> str:
    """Stable tool entry point for displaying an image.
    Wraps ui.display._view_image to avoid fragile private-path references in tools.json.
    """
    from ui.display import _view_image

    return _view_image(**kwargs)


def update_plan(**kwargs) -> str:
    """Stable tool entry point for updating the displayed plan.
    Wraps ui.display._update_plan to avoid fragile private-path references in tools.json.
    """
    from ui.display import _update_plan

    return _update_plan(**kwargs)


def _exec_skill_list(**kwargs) -> str:
    """列出所有已安装技能。"""
    from core.skills import get_manager

    mgr = get_manager()
    mgr.discover()
    lines = []
    for name in sorted(mgr._available.keys()):
        s = mgr._available[name]
        trigger = mgr.get_trigger(name)
        tag = "[auto]" if trigger == "auto" else "[manual]"
        lines.append(f"  {tag} {name}: {s.description[:80]}")
    return f"已安装 {len(lines)} 个技能:\n" + "\n".join(lines)


def _exec_plugin_list(**kwargs) -> str:
    """列出 output/plugins/ 中可用插件。"""
    import json
    import os

    plugin_dir = os.path.join(os.path.dirname(__file__), "..", "output", "plugins")
    if not os.path.exists(plugin_dir):
        return "插件目录不存在。"
    lines = []
    for name in sorted(os.listdir(plugin_dir)):
        cfg_path = os.path.join(plugin_dir, name, "plugin.json")
        desc = ""
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    desc = json.load(f).get("description", "")
            except (OSError, json.JSONDecodeError):
                pass
        lines.append(f"  {name}: {desc[:100]}")
    return f"可用插件 {len(lines)} 个:\n" + "\n".join(lines)


def _exec_mcp_get_tool_description(**kwargs) -> str:
    """模拟 mcp_get_tool_description — 返回 CRUX 可用工具列表。"""
    from core.tools import get_registry

    r = get_registry()
    r.load()
    tools = sorted(r._executors.keys())
    return f"CRUX 可用工具 ({len(tools)} 个):\n" + "\n".join(f"  {t}" for t in tools[:80])


def _build_shell_strategies(cmd: str, sys_module) -> list[tuple[str, str]]:
    """构建多策略 shell 执行降级链。

    策略按优先级排列：主策略 → 平台适配 → 裸命令 → 最简执行。
    任一策略成功即停止，全部失败才报错。
    """
    import shutil

    strategies: list[tuple[str, str]] = []
    is_win = sys_module.platform == "win32"
    has_bash = bool(shutil.which("bash"))

    # 策略 0：原始命令（主策略）
    strategies.append(("primary", cmd))

    # 策略 1：剥离 bash -c 包装，直接执行（修复双重 shell 问题）
    import re as _re

    bash_wrapped = _re.match(r'^bash\s+-c\s+["\'](.+)["\']\s*$', cmd.strip())
    if bash_wrapped:
        inner = bash_wrapped.group(1)
        strategies.append(("unwrap_bash", inner))

    # 策略 2：Windows 上用 cmd.exe /c 直接执行
    if is_win:
        clean = _re.sub(r"^bash\s+-c\s+", "", cmd.strip())
        strategies.append(("cmd_exe", f'cmd.exe /c "{clean}"'))

    # 策略 3：如果有 bash，尝试 bash 登录 shell
    if has_bash and not cmd.strip().startswith("bash"):
        strategies.append(("bash_login", f'bash -l -c "{cmd}"'))

    # 策略 4：裸命令（无 shell 包装），仅当命令简单时
    if not any(c in cmd for c in ('"', "'", "&&", "||", "|", ">", "<", ";")):
        strategies.append(("raw_no_shell", cmd))

    # 策略 5：Windows 上 POSIX 命令 → PowerShell 转换
    if is_win:
        cmd_name = cmd.strip().split()[0].lower() if cmd.strip() else ""
        if cmd_name in _POSIX_TO_POWERSHELL:
            try:
                pwsh_cmd = _POSIX_TO_POWERSHELL[cmd_name](cmd)
                strategies.append(("powershell_fallback", pwsh_cmd))
            except Exception:
                pass  # 转换失败静默跳过

    # 去重
    seen = set()
    unique = []
    for label, c in strategies:
        if c not in seen:
            seen.add(c)
            unique.append((label, c))
    return unique


def _diagnose_shell_failure(cmd: str, errors: list[str], sys_module) -> str:
    """诊断 shell 执行失败原因，给出可操作的修复建议。"""
    import shutil

    is_win = sys_module.platform == "win32"
    has_bash = bool(shutil.which("bash"))
    has_pwsh = bool(shutil.which("powershell"))

    suggestions = []
    if is_win and has_bash:
        suggestions.append("Windows + Git Bash 环境: bash -c 嵌套可能导致转义问题，已自动尝试剥离")
    if is_win and not has_bash:
        suggestions.append("Windows 无 bash: 请使用 cmd 兼容语法（如 dir 而非 ls，type 而非 cat）")
    if any("TimeoutExpired" in e or "超时" in e for e in errors):
        suggestions.append("命令超时: 考虑拆分任务、增加 timeout 参数，或使用 run_in_background=true")
    if any("Permission" in e or "denied" in e.lower() for e in errors):
        suggestions.append("权限不足: 需要管理员权限或调整文件权限")

    # ── POSIX → Windows 命令映射 ──
    if is_win and any("not found" in e.lower() or "not recognized" in e.lower() for e in errors):
        # 提取命令名（去掉参数和路径）
        cmd_name = cmd.strip().split()[0] if cmd.strip() else ""
        win_alt = _POSIX_TO_WINDOWS.get(cmd_name.lower())
        if win_alt:
            suggestions.append(f"'{cmd_name}' 是 Linux 命令，Windows 等价: {win_alt}")
            if has_pwsh and cmd_name.lower() in _POSIX_TO_POWERSHELL:
                pwsh_cmd = _POSIX_TO_POWERSHELL[cmd_name.lower()](cmd)
                suggestions.append(f"PowerShell 替代: {pwsh_cmd}")
        else:
            suggestions.append(
                "命令未找到: 检查工具是否已安装或在 PATH 中"
                + ("（提示: 你正在 Windows 上，ls→dir, cat→type, grep→findstr）" if is_win else "")
            )
    elif not is_win and any("not found" in e.lower() or "not recognized" in e.lower() for e in errors):
        suggestions.append("命令未找到: 检查工具是否已安装或在 PATH 中")

    if not suggestions:
        suggestions.append("未知原因: 请检查命令语法和参数是否正确")

    return "💡 修复建议:\n" + "\n".join(f"  → {s}" for s in suggestions)


def _safe_decode(raw: bytes) -> str:
    """安全解码子进程输出：尝试 UTF-8 → GBK → Latin-1 回退。

    Windows cmd.exe 输出可能为系统 ANSI 编码（如 GBK/CP936），
    UTF-8 解码会损坏中文字符。逐编码尝试确保诊断关键词可匹配。
    """
    for enc in ("utf-8", "gbk", "cp936", "gb2312", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


# ── POSIX → Windows 命令映射表 ──
_POSIX_TO_WINDOWS: dict[str, str] = {
    "ls": "dir",
    "cat": "type",
    "grep": "findstr",
    "head": "more /p (或 PowerShell: Get-Content | Select -First N)",
    "tail": "more +N (或 PowerShell: Get-Content | Select -Last N)",
    "cp": "copy",
    "mv": "move",
    "rm": "del /f",
    "touch": "type nul >",
    "wc": "find /c",
    "chmod": "icacls",
    "clear": "cls",
    "pwd": "cd",
    "whoami": "whoami",
    "which": "where",
    "uname": "ver",
    "sudo": "runas",
    "nohup": "start /b",
    "kill": "taskkill /f /pid",
    "ps": "tasklist",
    "top": "taskmgr",
    "df": "wmic logicaldisk get size,freespace,caption",
    "du": "dir /s",
    "ln": "mklink",
    "sort": "sort",
    "uniq": "PowerShell: ... | Get-Unique",
    "cut": "PowerShell: ($line -split '\\t')[N]",
    "sed": "PowerShell: (Get-Content f) -replace 'old','new'",
    "awk": "PowerShell: ($line -split ' ')[N]",
    "tr": "PowerShell: $s -replace 'a','b'",
    "xargs": "PowerShell: ... | ForEach-Object { cmd $_ }",
    "tee": "PowerShell: ... | Tee-Object -FilePath out.txt",
    "watch": "PowerShell: while ($true) { cmd; Start-Sleep 1 }",
    "ssh": "ssh",
    "scp": "scp",
}

_POSIX_TO_POWERSHELL: dict = {
    "head": lambda cmd: (
        f'powershell -Command "Get-Content {cmd[5:].strip()} | Select-Object -First 10"'
        if len(cmd.split()) > 1
        else 'powershell -Command "$input | Select-Object -First 10"'
    ),
    "tail": lambda cmd: (
        f'powershell -Command "Get-Content {cmd[5:].strip()} | Select-Object -Last 10"'
        if len(cmd.split()) > 1
        else 'powershell -Command "$input | Select-Object -Last 10"'
    ),
    "grep": lambda cmd: cmd.replace("grep", "findstr", 1) if cmd.startswith("grep") else cmd,
    "cat": lambda cmd: cmd.replace("cat", "type", 1) if cmd.startswith("cat") else cmd,
    "wc": lambda cmd: (
        f'powershell -Command "{cmd.replace("wc", "Measure-Object", 1)}"' if cmd.startswith("wc") else cmd
    ),
}


class ToolRegistry:
    """工具注册表：加载配置、管理定义、执行调度"""

    # Tool aliases: LLMs use shorthand names; map to registered canonical names
    ALIASES: dict[str, str] = {
        "bash": "run_bash",
        "shell": "run_bash",
        "terminal": "run_bash",
        "cmd": "run_bash",
        "sh": "run_bash",
        "python": "run_python",
        "orchestrator": "orchestrate",
        "orchestration": "orchestrate",
        "run": "run_bash",
        "execute": "run_bash",
        "exec": "run_bash",
    }

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or TOOLS_CONFIG
        self._definitions: list[dict] = []  # OpenAI function 格式
        self._executors: dict[str, Callable[..., str]] = {}  # name → 执行函数
        self._tool_modules: dict[str, str] = {}  # name → 模块路径（分类用）
        self._tool_config: dict[str, dict] = {}  # name → tools.json 原始配置（读 timeout 等）
        self.model_router = None  # Optional ModelRouter for sub-agent dispatch

    def resolve_name(self, raw_name: str) -> str:
        """Resolve tool name aliases. LLMs often use 'bash' instead of 'run_bash'."""
        return self.ALIASES.get(raw_name.strip().lower(), raw_name)

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
        self._tool_config.clear()
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
            self._tool_modules[name] = "core.retro_engine"

        # ── Agent Swarm 工具（常驻加载）──
        from core.multi_agent import AGENT_SWARM_TOOL_DEF, _exec_agent_swarm

        self._definitions.append(AGENT_SWARM_TOOL_DEF)
        self._executors["agent_swarm"] = _exec_agent_swarm
        self._tool_modules["agent_swarm"] = "core.multi_agent"

        # ── Skill 管理工具（chat_tool_dispatch 处理，此处仅注册定义）──
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "load_skill",
                    "description": "加载一个技能包。加载后技能的系统提示词和工具会注入当前会话。用 list_skills 查看可用技能。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "要加载的技能名称",
                            }
                        },
                        "required": ["name"],
                    },
                },
            }
        )
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "list_skills",
                    "description": "列出所有可用技能包及其触发模式（auto=自动激活, manual=手动加载, off=已禁用）。",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        )

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

        # ── grep 别名 (模型常用名 → search_files) ──
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "搜索文件内容（等同于 search_files）。用正则表达式在项目中搜索代码。",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern": {"type": "string", "description": "正则搜索模式"}},
                        "required": ["pattern"],
                    },
                },
            }
        )
        self._executors["grep"] = _exec_grep

        # ── 技能动态加载（常驻加载）──
        # skill_load: 模型遇到特定领域问题时自行加载对应技能
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "skill_load",
                    "description": (
                        "加载一个专业技能到当前会话。在以下场景**必须调用**：\n"
                        "- 用户要求调试/排查错误 → 加载 debug-master\n"
                        "- 用户要求代码审查/review → 加载 code-review\n"
                        "- 用户要求安全审计/加固 → 加载 security-hardening\n"
                        "- 用户要求写复杂Python → 加载 python-expert\n"
                        "- 用户要求写Shell脚本 → 加载 shell-master\n"
                        "- 用户要求API设计 → 加载 api-designer\n"
                        "- 用户要求项目全量审计 → 加载 self-audit\n"
                        "加载后技能规则自动生效，提升该领域的输出质量。不确定时先用 skill_search 搜索。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "技能名称，如 tdd-workflow、code-review 等"}
                        },
                        "required": ["name"],
                    },
                },
            }
        )
        self._executors["skill_load"] = _exec_skill_load

        # skill_install: 从市场安装技能
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "skill_install",
                    "description": (
                        "从技能市场安装新技能。先用 skill_search 搜索找到合适的技能名，"
                        "再调用此工具安装。安装后可用 skill_load 加载到当前会话。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "description": "要安装的技能名称"}},
                        "required": ["name"],
                    },
                },
            }
        )
        self._executors["skill_install"] = _exec_skill_install

        # skill_list: 列出已安装技能
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "skill_list",
                    "description": "列出所有已安装的技能及其触发模式。用于了解当前可用的技能。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        )
        self._executors["skill_list"] = _exec_skill_list

        # plugin_list: 列出可用插件
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "plugin_list",
                    "description": "列出 output/plugins/ 中所有可用插件及描述。",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        )
        self._executors["plugin_list"] = _exec_plugin_list

        # mcp_get_tool_description: 兼容 ZCode 习惯，返回工具列表
        self._definitions.append(
            {
                "type": "function",
                "function": {
                    "name": "mcp_get_tool_description",
                    "description": "列出所有可用工具的请求描述。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_requests": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}
                        },
                        "required": [],
                    },
                },
            }
        )
        self._executors["mcp_get_tool_description"] = _exec_mcp_get_tool_description

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
            self._tool_config[name] = tool_cfg

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
            import subprocess as _sp
            import sys

            # ── 提取 shell 控制参数（Copilot CLI 三模式）──
            run_in_background = kwargs.pop("run_in_background", False)
            detach = kwargs.pop("detach", False)
            description = kwargs.pop("description", "")

            safe_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, str):
                    # Windows: 不用 shlex.quote，POSIX 引号 cmd.exe 不认
                    # 安全由 sandbox_restrict 保证，自愈链有 bash 策略兜底
                    if sys.platform == "win32":
                        safe_kwargs[k] = v
                    else:
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
                proc = _sp.Popen(
                    cmd,
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
                _timeout = max(_timeout, 300)

            # ── 自愈多策略 shell 执行 ──
            # 构建降级策略链：主策略失败后自动尝试备选方案，而非直接报错/崩溃
            strategies = _build_shell_strategies(cmd, sys)
            errors = []
            for strategy_label, strategy_cmd in strategies:
                try:
                    # 用 Popen + communicate 替代 run(capture_output=True)
                    # capture_output 内部用后台线程读管道，高并发下 _readerthread 会崩溃
                    proc = _sp.Popen(
                        strategy_cmd,
                        shell=True,
                        stdout=_sp.PIPE,
                        stderr=_sp.PIPE,
                    )
                    try:
                        _raw_stdout, _raw_stderr = proc.communicate(timeout=_timeout)
                        _rc = proc.returncode
                    except _sp.TimeoutExpired:
                        # Kill the ENTIRE process tree, not just the shell.
                        try:
                            from core.mcp_servers._mcp_utils import _kill_process_tree

                            _kill_process_tree(proc)
                        except ImportError:
                            proc.kill()
                        # Drain pipes with a deadline (5s max).
                        try:
                            _raw_stdout, _raw_stderr = proc.communicate(timeout=5)
                        except _sp.TimeoutExpired:
                            _raw_stdout, _raw_stderr = b"", b""
                        # Timeout is FATAL — do NOT retry other strategies.
                        # Each strategy shares the same timeout; retrying would
                        # compound N×120s instead of failing fast.
                        errors.append(f"[{strategy_label}] 超时 ({_timeout}s)")
                        break
                    # 多编码尝试解码（Windows cmd.exe 输出可能是 GBK）
                    _stdout = _safe_decode(_raw_stdout) if _raw_stdout else ""
                    _stderr = _safe_decode(_raw_stderr) if _raw_stderr else ""
                    output = _stdout.strip() or _stderr.strip() or f"[exit: {_rc}]"
                    if _rc == 0:
                        if strategy_label != "primary":
                            try:
                                import logging

                                logging.getLogger("crux").info(
                                    "shell_executor self-healed: strategy=%s, cmd=%s",
                                    strategy_label,
                                    cmd[:120],
                                )
                            except Exception:
                                logger.debug("Exception in tools", exc_info=True)
                        return output
                    # 非零退出码：区分 shell 级错误 vs 应用级错误
                    # 核心原则：有实质输出且不像 shell 报错 → 应用层结果，直接返回
                    # 无输出或输出像 shell 报错 → 尝试下一个策略
                    _has_output = bool(_stdout.strip() or _stderr.strip())
                    _stderr_lower = _stderr.lower()
                    _SHELL_EXIT_CODES = {9009}  # Windows: 命令未找到
                    _SHELL_ERR_KEYWORDS = (
                        "not recognized",
                        "command not found",
                        "no such file",
                        "cannot find",
                        "could not find",
                        "the syntax of the command is incorrect",
                    )
                    # 中文 Windows 错误消息编码检测：用原始字节
                    _has_chinese_err = (
                        b"\xb2\xbb\xca\xc7" in (_raw_stderr or b"")  # "不是" GBK
                        or b"\xc4\xda\xb2\xbf" in (_raw_stderr or b"")  # "内部" GBK
                        or b"\xcd\xe2\xb2\xbf" in (_raw_stderr or b"")  # "外部" GBK
                    )
                    _looks_like_shell_err = (
                        _rc in _SHELL_EXIT_CODES
                        or _has_chinese_err
                        or any(p in _stderr_lower for p in _SHELL_ERR_KEYWORDS)
                    )
                    if _looks_like_shell_err:
                        # Only retry for shell-level errors (command not found, syntax).
                        # Never retry application errors (non-zero exit with actual output
                        # like pytest failures, git merge conflicts, etc.) — retrying
                        # would execute side-effecting commands multiple times.
                        errors.append(
                            f"[{strategy_label}] exit={_rc}: {_stderr.strip()[:200] or _stdout.strip()[:200] or '(no output)'}"
                        )
                    else:
                        # 应用层有实际输出（pytest/编译器等），直接返回
                        return output
                except _sp.TimeoutExpired:
                    errors.append(f"[{strategy_label}] 超时 ({_timeout}s)")
                except _sp.SubprocessError as e:
                    errors.append(f"[{strategy_label}] 子进程错误: {e}")
                except OSError as e:
                    errors.append(f"[{strategy_label}] 系统错误: {e}")

            # 所有策略均失败 → 返回结构化错误（含诊断信息，帮助 CRUX 自我修正）
            diagnosis = _diagnose_shell_failure(cmd, errors, sys)
            return (
                f"[自愈失败] 所有 {len(strategies)} 个执行策略均失败:\n"
                + "\n".join(f"  • {e}" for e in errors)
                + f"\n\n{diagnosis}"
            )

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
        if t in ("python", "function"):
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

    def get_definitions_for_names(self, names: set[str]) -> list[dict]:
        """Return definitions for a specific set of tool names.

        Used by the tool-loop to send only the initially filtered tools plus any
        tools the model has actually called, instead of expanding to the full
        97-tool set (14K tokens) on every subsequent loop iteration.
        """
        if not names:
            return []
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
        """执行工具并返回结果文本（自愈执行 + 观测 + 错误恢复）

        自愈策略（三层防护）:
        - 第一层: shell 工具内置多策略降级链（_build_shell_strategies）
        - 第二层: SafeExecutor 超时/大小保护
        - 第三层: ErrorClassifier 分类 + 恢复建议（而非裸 raise）
        """
        try:
            from core.observability import TraceContext
            from core.observability import metrics as _m
        except ImportError:
            _m = None
            TraceContext = None  # type: ignore[assignment]

        # 调用日志（可选，失败时静默降级）
        try:
            from core.tool_call_log import log_call as _log_call
        except ImportError:
            _log_call = None

        executor = self._executors.get(name)
        if not executor:
            suggestion = _suggest_similar_tool(name, self._definitions)
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_suggestion_given")
                _m.increment(f"tool_err.{name}")
            if _log_call:
                _log_call(name, "unknown_tool", 0.0, args)
            if suggestion:
                return f"[错误] 未知工具: {name}。你是否想用: {suggestion}？请检查工具名后重试。"
            return f"[错误] 未知工具: {name}。请检查工具名后重试。"

        # 前置参数校验
        ok, detail = _validate_args(name, args, self._definitions)
        if not ok:
            if _m:
                _m.increment("tool_errors")
                _m.increment("tool_arg_validation_failed")
                _m.increment(f"tool_err.{name}")
                _m.increment(f"tool_arg_fail.{name}")
            if _log_call:
                _log_call(name, "arg_validation_failed", 0.0, args)
            return detail

        # ── SafeExecutor 包装：超时/大小/审计保护 ──
        # 硬超时预算 = 该工具在 tools.json 声明的 timeout + 余量；无声明则用默认。
        # 保证：短工具不会占用满 300s，长任务(如 run_test=1800)也不会被 300s 误杀。
        try:
            from core.resilience import SafeExecutor

            _tool_cfg = self._tool_config.get(name, {}) if hasattr(self, "_tool_config") else {}
            _tool_to = _tool_cfg.get("timeout")
            if not isinstance(_tool_to, (int, float)) or _tool_to <= 0:
                _tool_to = 120  # 与多数执行类工具一致的稳妥默认
            _safe_to = float(_tool_to) + 60.0  # 余量：容纳进程树 kill/回收
            safe = SafeExecutor(timeout=_safe_to)
        except ImportError:
            safe = None

        try:
            ctx = TraceContext("registry_execute", tool_name=name) if _m else _noop_cm()
            with ctx as span:
                if safe:
                    safe_result = safe.execute(name, executor, args)
                    if not safe_result.get("success", False):
                        _err = safe_result.get("error") or "unknown error"
                        _hint = safe_result.get("recovery_hint") or ""
                        result = f"[错误] {_err}" + (f"\n恢复建议: {_hint}" if _hint else "")
                    else:
                        result = safe_result.get("result", "")
                else:
                    result = executor(**args)
                elapsed_ms = span.duration_ms() if span is not None else 0.0
                if _m and span is not None:
                    span.set_attribute("result_chars", len(str(result)))
                    _m.increment("tool_executions")
                    _m.timing("tool_execute_ms", elapsed_ms)
                    _m.increment(f"tool_exec.{name}")
                    _m.timing(f"tool_ms.{name}", elapsed_ms)
            if _log_call:
                _log_call(name, "ok", elapsed_ms, args)

            result_str = str(result)
            # 自愈结果检测：如果 shell 工具返回了自愈成功的结果，记录指标
            if name in ("run_bash", "run_test") and "self-healed" not in result_str.lower():
                # 检测结果中是否有自愈标记
                pass

            if validate_result:
                result_str = self._validate_result(name, result_str, args)
            # Protocol guard: never return None — tools must always return strings
            if result_str is None:
                result_str = f"[错误] 工具 '{name}' 返回了空结果"
            return result_str

        except (RuntimeError, OSError, ValueError, TypeError) as e:
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            try:
                from core.resilience import ErrorClassifier

                etype = ErrorClassifier.classify(e)
                hint = ErrorClassifier.get_recovery_hint(e)
                # 增强错误消息：包含诊断信息，让 CRUX 能够自修正
                return (
                    f"[错误 | {etype.value}] {e}\n"
                    f"恢复建议: {hint}\n"
                    f"请检查参数或方法后重试。若持续失败，考虑使用替代工具或简化命令。"
                )
            except ImportError:
                raise
        except Exception as e:
            if _m:
                _m.increment("tool_errors")
                _m.increment(f"tool_err.{name}")
            if _log_call:
                _log_call(name, "exception", 0.0, args)
            # 记录到 error_sink 供后续诊断
            try:
                from core.error_sink import capture

                capture(f"tool.{name}", str(e), context=str(args)[:500])
            except ImportError:
                pass
            return f"[错误] 工具 '{name}' 执行失败: {type(e).__name__}: {e}"

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
        # 1. Narrow fix: replace bare except:pass with logging
        healer.fix_silent_exceptions()
        # 2. Broad fix: ruff check --fix (auto-fix lint issues)
        qf = healer.quick_fix()
        # 3. Re-scan to show post-fix state (clear duplicates)
        healer.findings.clear()
        healer.run_all_scans()

    parts = [healer.report()]
    if fix:
        parts.append(f"Auto-fix applied: ruff={qf.get('ruff_fixed', 0)} patches={qf.get('patches', 0)}")
    return "\n".join(parts)


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
