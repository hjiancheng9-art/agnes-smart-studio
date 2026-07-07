"""CRUX Studio 工程约束 — 全项目唯一真源。

四象融合净化：本项目不维护任何安全列表/规则集的副本。
所有模块从此处 import，修改一处即全局生效。

约束类型：
    SECURITY  — 高风险工具、危险参数
    DISK      — 跳过目录（搜索/审计/索引时忽略的路径）
    TOOL      — 工具语义分组（写工具、长耗时工具）
"""

import re

__all__ = [
    # SECURITY
    "HIGH_RISK_TOOLS",
    "DANGEROUS_ARGS_PATTERN",
    "is_tool_high_risk",
    # DISK
    "PROJECT_SKIP_DIRS",
    # TOOL
    "WRITE_TOOLS",
    "LONG_RUNNING_TOOLS",
    "READONLY_TOOLS",
    "CONFIRMABLE_TOOLS",
]

# ═══════════════════════════════════════════════════════════════════
# SECURITY — 高风险工具 + 危险参数匹配
# ═══════════════════════════════════════════════════════════════════

HIGH_RISK_TOOLS = frozenset(
    {
        "git_add_commit",  # 本地提交（可能误提交敏感内容）
        "git_push",  # 远程推送
        "git_pr_create",  # 创建 PR（含推送）
        "git_pr_merge",  # 合并 PR（不可逆）
        "git_tag",  # 创建/删除 tag（语义版本不可逆）
    }
)

DANGEROUS_ARGS_PATTERN = re.compile(
    r"\b(rm\s+-|del\s+[/-]|erase\s+[/-]|drop\s+(table|database)|truncate\s+(table|database)|format\s+[A-Za-z]:|mkfs\.)",
    re.IGNORECASE,
)


def is_tool_high_risk(name: str, args: dict) -> bool:
    """判断工具调用是否有高风险（单一入口，chat.py / async_chat.py 共用）。

    检查项：
    - 工具名是否在 HIGH_RISK_TOOLS 集合中
    - github_write_file 推默认分支（无 branch 参数）
    - git_push + force=True（即便用户绕过默认确认）
    - git_worktree remove + force=True（递归删目录）
    - git_branch delete（删分支）
    - run_bash 命令参数匹配 DANGEROUS_ARGS_PATTERN（精准锚定: rm -/del /erase / /drop table/format X: 等）
    """
    if name in HIGH_RISK_TOOLS:
        return True
    if name == "github_write_file" and not args.get("branch", "").strip():
        return True
    if name == "git_push" and bool(args.get("force", False)):
        return True
    if name == "git_worktree" and args.get("action", "") == "remove" and bool(args.get("force", False)):
        return True
    if name == "git_branch" and args.get("action", "") == "delete":
        return True
    return bool(name == "run_bash" and DANGEROUS_ARGS_PATTERN.search(args.get("command", "")))


# ═══════════════════════════════════════════════════════════════════
# DISK — 项目搜索/审计/索引时跳过的目录（多模块共用，取并集）
# ═══════════════════════════════════════════════════════════════════

PROJECT_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "browser_sessions",
        ".codebuddy",
        "node_modules",
        ".venv",
        "venv",
        "output",
    }
)


# ═══════════════════════════════════════════════════════════════════
# TOOL — 工具语义分组
# ═══════════════════════════════════════════════════════════════════

# 写操作类工具 — 不参与跨轮去重缓存，避免吞掉用户连续编辑意图
WRITE_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "patch_file",  # structured patch (PatchEngine.apply)
        "apply_patch",  # convenience alias
        "github_write_file",
        "git_add_commit",
        "git_push",
        "run_bash",
    }
)

# 耗时工具 — 执行前先发 info 提示，让用户知道正在干活
LONG_RUNNING_TOOLS = frozenset({"run_bash", "run_test", "run_python", "web_fetch", "web_search"})

# 只读工具 — Plan 模式下允许执行的工具集合
# 注意: "run_bash" 不在此列表中（Plan 模式禁止执行命令）
READONLY_TOOLS = frozenset(
    {
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
        "list_files",
        "tree_dir",
        "check_file_exists",
        "list_project_files",
        "fetch_url_content",
        "web_search",
        "web_fetch",
        "skill_search",
        "env_check",
        "health_check",
        "comfyui_status",
        "comfyui_list_models",
        "comfyui_get_node_info",
        "mcp_list_servers",
        "mcp_list_tools",
        "mcp_read_resource",
    }
)

# 确认类工具 — Manual 模式下需要用户确认的工具（写入操作超集）
# 基于 WRITE_TOOLS 扩展，包含所有会产生副作用的工具
CONFIRMABLE_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "patch_file",
        "apply_patch",
        "safe_rewrite_file",
        "github_write_file",
        "git_add_commit",
        "git_push",
        "git_pr_create",
        "git_pr_merge",
        "git_tag",
        "git_branch",
        "git_worktree",
        "git_stash",
        "run_bash",
        "run_test",
        "run_python",
        "generate_image",
        "generate_video",
        "comfyui_submit_workflow",
        "comfyui_create_custom_node",
        "comfyui_clear_queue",
        "schedule_add",
        "schedule_remove",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "execute_plan",
        "multi_agent",
    }
)

# ═══════════════════════════════════════════════════════════════════
# METHODOLOGY — 方法论禁区（来自 core/methodology.py）
# ═══════════════════════════════════════════════════════════════════
