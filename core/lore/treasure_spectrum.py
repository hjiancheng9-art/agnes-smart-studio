"""法宝谱 — 84 工具按五兽归属分类，注入系统提示词。

法宝 = Tool（可调用能力），按功能归属五兽：
  白虎·破限  → 自修/补丁/诊断/多智能体
  青龙·创生  → 文件操作/代码智能/执行/图分析
  朱雀·洞察  → 搜索/研究/审查/深度推理
  玄武·守卫  → Git/GitHub/MCP/部署/包管理
  麒麟·调和  → 生图/视频/ComfyUI/文档/浏览器/音频

来源:
  tools.json       — 56 个 python 工具
  BUILTIN_TOOLS    — 3 个内置 (generate_image/video + multi_agent)
  GIT_WORKFLOW     — 9 个 git 工作流工具
  MCP bridge       — 4 个 MCP 桥接工具
  PIPELINE_TOOL_DEFS — 6 个 Showrunner 管道工具
  COMFYUI_TOOL_DEFS — 6 个 ComfyUI toggle 工具

用法:
  from core.treasure_spectrum import get_treasure_prompt, get_treasure_summary
"""

from __future__ import annotations

TREASURE_PROMPT = """
[法宝谱 — 84 法宝·五兽归鞘]

## 白虎·破限 — 自修/补丁/诊断 (4件)
  `patch_file`       — 结构化补丁，多文件批量修改+自动备份+语法校验+失败回滚
  `patch_undo`       — 撤销最近补丁，幂等回退
  `execute_plan`     — 自主执行多步计划，依赖排序+语法校验+自动追踪
  `multi_agent`      — 多智能体协调，复杂目标分解→并行派发→结果汇总

## 青龙·创生 — 文件/代码/执行 (18件)
  **文件操作**: `read_file` `write_file` `edit_file` `search_files` `glob_files` `list_files` `tree_dir` `count_lines`
  **代码智能**: `code_analyze` `find_symbol` `search_symbols` `find_references`
  **知识图谱**: `graph_neighbors` `graph_ancestors` `graph_descendants`
  **执行引擎**: `run_python` `run_bash` `run_test` `js_eval` `think_deep`

## 朱雀·洞察 — 搜索/研究/审查 (5件)
  `web_fetch`        — 网页文本抓取，重定向+超时
  `web_search`       — DuckDuckGo HTML 搜索，前5条结果
  `skill_search`     — TF-IDF 语义代码搜索 (RAG)
  `browser_screenshot` — Playwright 网页截图
  `env_check`        — Python/包/git 环境诊断

## 玄武·守卫 — Git/GitHub/MCP/部署 (26件)
  **Git 读写**: `git_status` `git_diff` `git_log` `git_add_commit`
  **Git 分支**: `git_branch` `git_push` `git_pull` `git_stash` `git_tag` `git_worktree`
  **Git PR**: `git_pr_create` `git_pr_merge` `git_conflict_check`
  **GitHub**: `github_search` `github_repo_view` `github_repo_list` `github_browse` `github_readme` `github_release` `github_issue` `github_pr` `github_api` `github_write_file`
  **MCP**: `mcp_connect` `mcp_call` `mcp_list_servers` `mcp_list_tools` `mcp_call_tool` `mcp_read_resource`
  **部署**: `deploy_vercel` `pip_install` `download_file`

## 麒麟·调和 — 生图/视频/文档/浏览器/音频 (31件)
  **生图**: `generate_image` `imagegen`
  **生视频**: `generate_video`
  **ComfyUI**: `comfyui_status` `comfyui_list_models` `comfyui_submit_workflow` `comfyui_get_result` `comfyui_preview_workflow` `comfyui_clear_queue` `comfyui_get_node_info` `comfyui_build_custom_workflow` `comfyui_create_custom_node`
  **LoRA**: `comfyui_lora_prepare` `comfyui_lora_generate_config` `comfyui_lora_check_status`
  **文档**: `create_markdown` `create_html` `create_pdf`
  **音频**: `text_to_speech` `transcribe_audio`
  **浏览器**: `pw_navigate` `pw_screenshot` `desktop_screenshot`
  **管道**: `extract_video_keyframes` `save_project_manifest` `check_file_exists` `list_project_files` `decompose_to_storyboard` `regenerate_asset` `project_dependency_graph` `mark_asset_ok`
"""


def get_treasure_prompt() -> str:
    """Return the full treasure spectrum prompt for system injection."""
    return TREASURE_PROMPT


def get_treasure_summary() -> str:
    """Return a compact one-line summary of the treasure spectrum."""
    try:
        from core.tools import ToolRegistry

        reg = ToolRegistry()
        reg.load()
        names = reg.tool_names
        count = len(names)
    except Exception:
        count = 84
    return f"[法宝] {count} 工具 — 白虎4 · 青龙18 · 朱雀5 · 玄武26 · 麒麟31"
