"""Command registry — /help auto-generates from this; dispatcher is table-driven.

Commands are defined as CommandDef dataclass instances. Each has:
  key       — internal identifier (used in dispatcher lookup)
  name      — slash command shown to user (/xxx)
  args      — parameter hint shown in /help
  desc      — one-liner description
  category  — group for /help rendering (创意生产/对话/任务工程/诊断配置)
  long_desc — detailed description for /all
  aliases   — extra keys that map to same handler (e.g. ["quit", "q"] for exit)
  handler   — method name on CruxCLI (without "self.") or None for inline handlers

To add a new command:
  1. Add a CommandDef to COMMANDS below (or call register()).
  2. Add command handler to crux_studio.py _chat_repl().
  3. Done. The dispatcher, /help, and /all auto-update.

History:
  v1 — tuple list, no handler binding; /help only.
  v2 — dataclass with handler_key + aliases; table-driven dispatcher replaces if-elif chain.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "COMMANDS",
    "CommandDef",
    "SKILL_ENTRIES",
    "auto_category",
    "build_dispatch_table",
    "get_all",
    "get_by_category",
    "register",
]


@dataclass
class CommandDef:
    """Single command definition."""

    key: str  # internal key (matches handler method: _chat_<key>)
    name: str  # display name (/xxx)
    args: str  # parameter hint
    desc: str  # one-liner
    category: str  # group for /help
    long_desc: str = ""  # detail for /all
    aliases: tuple[str, ...] = ()  # extra keys → same handler (e.g. quit, q → exit)
    handler: str | None = None  # cli method name, or None = use key


# ── 注册表 ──────────────────────────────────────────────────

COMMANDS: list[CommandDef] = [
    # ── 创意生产 ──
    CommandDef(
        "showrun",
        "/showrun",
        "<目标>",
        "Showrunner 全自动视频流水线（故事板→关键帧→动画→合成→音频）",
        "创意生产",
        "全自动：理解创意→拆解资产→分镜→生成→质检→导出",
        handler="_chat_showrun",
    ),
    CommandDef(
        "comfy",
        "/comfy",
        "<cmd>",
        "ComfyUI 工作流管理 (list/run/status/connect)",
        "创意生产",
        "远程/本地 ComfyUI 节点式生成，list=查看工作流，run=执行，status=状态",
        handler="_chat_comfy",
    ),
    CommandDef(
        "agnes",
        "/agnes",
        "<模式>",
        "Agnes 多模态生成 (t2i/i2i/t2v/i2v/pipeline)",
        "创意生产",
        "文生图/图生图/文生视频/图生视频/一键流水线，可选尺寸和时长",
        handler="_chat_agnes",
    ),
    CommandDef("video", "/video", "<描述>", "快速生成视频（支持图生视频，可 --size --duration）", "创意生产", handler="_chat_video_inline"),
    CommandDef("img", "/img", "<描述>", "快速生成图片（支持图生图，可 --size）", "创意生产", handler="_chat_img_inline"),
    CommandDef("vision", "/vision", "<图> <问>", "图片理解（智谱 GLM-4V-Flash 主视觉）", "创意生产"),
    # ── 对话 ──
    CommandDef(
        "help", "/help", "", "显示本帮助（/help /all 完整列表）", "对话", aliases=("all",), handler="_chat_help_inline"
    ),
    CommandDef("status", "/status", "", "系统健康状态", "对话", handler="_chat_status"),
    CommandDef(
        "vote", "/vote", "on|off", "多模型表决开关（复杂问题自动并行咨询多个AI）", "对话", handler="_chat_vote_toggle"
    ),
    CommandDef(
        "model",
        "/model",
        "<别名|ID>",
        "切换 AI 模型 (light/pro/deepseek/zhipu...)",
        "对话",
        handler="_chat_switch_model",
    ),
    CommandDef("thinking", "/thinking", "", "深度思考模式", "对话", handler="_inline_thinking"),
    CommandDef("code", "/code", "", "代码助手模式（再输退出）", "对话", handler="_inline_code"),
    CommandDef("agent", "/agent", "", "智能体模式（加载 tools.json 外部工具）", "对话", handler="_inline_agent"),
    CommandDef("tools", "/tools", "", "查看已注册的工具列表", "对话", handler="_inline_tools"),
    CommandDef("skill", "/skill", "<cmd>", "技能包管理 (list/load/mode/unload/create)", "对话", handler="_chat_skill"),
    CommandDef("clear", "/clear", "", "清空对话历史", "对话", handler="_inline_clear"),
    CommandDef("exit", "/exit", "", "退出聊天", "对话", aliases=("quit", "q")),
    # ── 任务工程 ──
    CommandDef("plan", "/plan", "<任务>", "先规划再执行（自动拆解步骤 + 用户审批）", "任务工程", handler="_chat_plan_mode"),
    CommandDef("sub", "/sub", "<任务>", "启动子智能体处理子任务", "任务工程", handler="_chat_subagent"),
    CommandDef("compress", "/compress", "", "压缩长对话历史为摘要", "任务工程"),
    CommandDef("team", "/team", "<类型>", "智能体团队 (review/debug/feature)", "任务工程"),
    CommandDef("project", "/project", "<cmd>", "项目管理 (new/save/load/analyze)", "任务工程"),
    CommandDef("deploy", "/deploy", "<目标>", "一键部署 (vercel/netlify/github)", "任务工程"),
    CommandDef("todo", "/todo", "[路径]", "扫描项目 TODO/FIXME/HACK", "任务工程"),
    CommandDef("commit", "/commit", "", "从 git diff 自动生成 commit 消息", "任务工程"),
    CommandDef("changelog", "/changelog", "", "从 git log 生成 CHANGELOG.md", "任务工程"),
    CommandDef("refactor", "/refactor", "<旧> <新>", "批量重命名/替换", "任务工程"),
    # ── 诊断配置 ──
    CommandDef("self", "/self", "<cmd>", "自诊断 (check/files/health/fix/audit)", "诊断配置", handler="_self_diagnose"),
    CommandDef("audit", "/audit", "<pip|npm>", "依赖安全审计 + 过期检测", "诊断配置"),
    CommandDef("rules", "/rules", "<cmd>", "编码规范管理 (list/enable/create)", "诊断配置"),
    CommandDef("automate", "/automate", "<cmd>", "自动化定时任务 (add/list/remove)", "诊断配置"),
    CommandDef("permission", "/permission", "<yolo|auto|manual>", "切换权限模式 (YOLO/自动/手动)", "诊断配置"),
    CommandDef("tasks", "/tasks", "", "查看后台任务状态", "诊断配置"),
    CommandDef("provider", "/provider", "<cmd>", "切换模型供应商 (list/switch)", "诊断配置"),
    CommandDef("evolve", "/evolve", "", "查看 Prompt 进化状态", "诊断配置"),
    CommandDef(
        "done", "/done", "[quick]", "完成前验证 (pytest+ruff+pyright+git diff)", "诊断配置",
        long_desc="跑完整验证清单确认任务完成。quick=跳过 pytest 只做 lint+diff。",
        handler="_chat_done",
    ),
    CommandDef(
        "method",
        "/method",
        "[reset]",
        "查看当前任务的方法论遵守状态 (A/B/C/D 分级 + Plan/基线/Worktree/TDD)",
        "诊断配置",
        long_desc="显示当前任务的 A/B/C/D 等级、Plan 状态、测试基线、Worktree 隔离、TDD 阶段。reset=重置状态。",
        handler="_chat_method",
    ),
    CommandDef(
        "know", "/know", "<cmd>", "浏览内置知识库 (methods/templates/domain)", "诊断配置", handler="_chat_knowledge"
    ),
    CommandDef("health", "/health", "", "工具质量评分 + 系统健康面板", "诊断配置", handler="_chat_health"),
    CommandDef("rollback", "/rollback", "", "回滚最近一次代码修改", "诊断配置", handler="_chat_rollback"),
    CommandDef("copy", "/copy", "[N]", "复制最近N条对话到剪贴板 (Ctrl+Y)", "对话", handler="_chat_copy"),
    CommandDef("trends", "/trends", "[cost|tools|quality]", "历史趋势分析（消费/工具健康/质量）", "诊断配置", handler="_chat_trends"),
    CommandDef("docs", "/docs", "[help|agents|manifest|all]", "从代码自动生成文档", "诊断配置", handler="_chat_docs"),
    CommandDef(
        "prompt_stats",
        "/prompt-stats",
        "",
        "Prompt Lab 实验统计",
        "诊断配置",
        long_desc="A/B 变体效果对比：满意度/完成度/修正率",
        handler="_chat_prompt_stats",
    ),
    CommandDef(
        "prompt_assign",
        "/prompt-assign",
        "<变体ID>",
        "指定 Prompt Lab 变体",
        "诊断配置",
        long_desc="手动分配变体到当前会话，替代随机分配",
        handler="_chat_prompt_assign",
    ),
    CommandDef(
        "cost",
        "/cost",
        "[budget <usd>|reset]",
        "查看花费统计 / 设日预算 / 清零",
        "诊断配置",
        long_desc="无参=汇总；budget <usd>=设日预算上限；reset=清零归档",
        handler="_chat_cost",
    ),
    CommandDef(
        "browser",
        "/browser",
        "",
        "Browser Companion 网页生成开关（8平台）",
        "对话",
        long_desc="toggle：切换 browser_generate 等 6 个网页生成工具。首次用需 browser_setup 登录。",
        handler="_inline_browser",
    ),
    CommandDef(
        "eval",
        "/eval",
        "[json]",
        "运行智能体质量基准测试",
        "诊断配置",
        long_desc="无参=表格展示；json=输出 JSON 报告。覆盖代码搜索/代码质量/理解能力。",
        handler="_chat_eval",
    ),
    CommandDef(
        "extend",
        "/extend",
        "<notebook|audio|browser|list>",
        "切换扩展工具集（notebook/audio/browser）",
        "诊断配置",
        long_desc="toggle：切换数据科学/音频/网页生成工具集。list：显示所有扩展状态。",
        handler="_chat_extend",
    ),
    CommandDef(
        "mcp",
        "/mcp",
        "<cmd>",
        "MCP 服务器管理 (list/add/remove/connect/disconnect/tools)",
        "诊断配置",
        long_desc="list：显示所有配置的服务器及连接状态；add <name> -- <cmd>：注册新服务器；"
        "remove <name>：移除；connect/disconnect <name>：启停连接；tools <name>：查看工具。",
        handler="_chat_mcp",
    ),
]

# Special skill-load entries for /help display
SKILL_ENTRIES = [
    
    ("/runs", "查看执行历史"),
    ("/summary", "查看指定执行摘要"),
    ("/providers", "查看 provider 健康状态"),
("/skill load video-pipeline", "输入理解→资产拆解→独立生成→分镜融合→质检→导出"),
    ("/skill load showrunner", "选模型-提取帧-制片"),
    ("/skill load storyboard-director", "简报→镜头列表→图像提示→运动→音频"),
    ("/skill load core-showrunner", "受控生产循环·诚实阻断·失败转修复"),
    ("/skill list", "查看所有可用技能 (63+)"),
    ("/skill load <名称>", "加载指定技能包"),
    ("/runs", "View execution history"),
    ("/summary", "View execution summary"),
    ("/providers", "View provider health"),
    ("/regression", "Run routing regression tests"),
    ("/replays", "List saved run replays"),
    ("/replay", "View run replay timeline"),
    ("/incidents", "View incident trends (24h)"),
    ("/playbook", "View remediation playbook"),
]


# ── 查询接口 ──────────────────────────────────────────────


def get_by_category() -> dict[str, list[tuple]]:
    """Returns {category: [(name, args, desc, long_desc), ...]}."""
    cats: dict[str, list[tuple]] = {}
    for cmd in COMMANDS:
        cats.setdefault(cmd.category, []).append((cmd.name, cmd.args, cmd.desc, cmd.long_desc))
    return cats


def auto_category(name: str, desc: str) -> str:
    """Guess command category from name + description keywords."""
    text = (name + " " + desc).lower()
    cats = {
        "创意生产": [
            "生成",
            "创建",
            "制作",
            "图片",
            "视频",
            "音频",
            "画",
            "拍",
            "渲染",
            "generate",
            "create",
            "img",
            "video",
            "image",
            "render",
            "showrun",
            "vision",
        ],
        "对话": [
            "帮助",
            "切换",
            "清空",
            "退出",
            "思考",
            "模式",
            "help",
            "model",
            "clear",
            "exit",
            "mode",
            "chat",
            "talk",
        ],
        "任务工程": [
            "规划",
            "任务",
            "部署",
            "项目",
            "提交",
            "日志",
            "重命名",
            "扫描",
            "plan",
            "task",
            "deploy",
            "project",
            "commit",
            "changelog",
            "refactor",
            "todo",
            "sub",
            "compress",
            "team",
        ],
        "诊断配置": [
            "诊断",
            "审计",
            "检查",
            "工具",
            "规范",
            "定时",
            "供应商",
            "进化",
            "知识",
            "self",
            "audit",
            "check",
            "tools",
            "rules",
            "automate",
            "provider",
            "evolve",
            "know",
        ],
    }
    scores = {cat: sum(1 for kw in kws if kw in text) for cat, kws in cats.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "诊断配置"


def register(
    key: str,
    name: str,
    args: str,
    desc: str,
    category: str = "",
    long_desc: str = "",
    aliases: tuple[str, ...] = (),
    handler: str | None = None,
):
    """Register or update a command. If key exists, update in-place; else append."""
    if not category:
        category = auto_category(name, desc)
    new_cmd = CommandDef(
        key=key,
        name=name,
        args=args,
        desc=desc,
        category=category,
        long_desc=long_desc,
        aliases=aliases,
        handler=handler,
    )
    for i, cmd in enumerate(COMMANDS):
        if cmd.key == key:
            COMMANDS[i] = new_cmd
            return
    COMMANDS.append(new_cmd)


register("palette", "/palette", "[filter]", "Command palette — fuzzy search all commands", "对话", handler="_chat_palette")

def get_all() -> list[CommandDef]:
    return list(COMMANDS)


# ── Dispatcher Table ───────────────────────────────────────
# 构建一次，返回 {cmd_key: (handler_method_name_or_None, CommandDef)}
# cli.py 的 _chat() 用这个表替代 if-elif 长链。


def build_dispatch_table() -> dict[str, tuple[str | None, CommandDef]]:
    """Build a lookup table: cmd_key → (handler_method_name, CommandDef).

    Each key from command.aliases also maps to the same entry.
    """
    table: dict[str, tuple[str | None, CommandDef]] = {}
    for cmd in COMMANDS:
        handler = cmd.handler or f"_chat_{cmd.key}"
        entry = (handler, cmd)
        table[cmd.key] = entry
        for alias in cmd.aliases:
            table[alias] = entry
    return table
