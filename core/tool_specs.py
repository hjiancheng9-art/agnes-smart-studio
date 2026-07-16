"""ToolSpec registry — declares execution metadata per tool for the async ToolExecutor.

Tools NOT listed here use ToolSpec.for_tool() heuristic defaults.
Add entries as tools are audited and migrated.
"""

from core.tool_executor import ToolSpec

# ── Write tools (side-effect: WRITE) — max 1 attempt, non-idempotent ──
WRITE_TOOLS: list[ToolSpec] = [
    ToolSpec(name="write_file", timeout_s=30, idempotent=False),
    ToolSpec(name="edit_file", timeout_s=30, idempotent=False),
    ToolSpec(name="patch_file", timeout_s=60, idempotent=False),
    ToolSpec(name="git_add_commit", timeout_s=30, idempotent=False),
    ToolSpec(name="git_push", timeout_s=60, idempotent=False),
    ToolSpec(name="git_pr_create", timeout_s=60, idempotent=False),
    ToolSpec(name="git_pr_merge", timeout_s=60, idempotent=False),
    ToolSpec(name="pip_install", timeout_s=120, idempotent=False, slow=True),
    ToolSpec(name="github_write_file", timeout_s=30, idempotent=False),
]

# ── Read-only tools (side-effect: NONE) — idempotent, can retry ──
READ_TOOLS: list[ToolSpec] = [
    ToolSpec(name="read_file", timeout_s=10, idempotent=True),
    ToolSpec(name="search_files", timeout_s=30, idempotent=True),
    ToolSpec(name="glob_files", timeout_s=15, idempotent=True),
    ToolSpec(name="list_files", timeout_s=10, idempotent=True),
    ToolSpec(name="find_symbol", timeout_s=15, idempotent=True),
    ToolSpec(name="find_references", timeout_s=15, idempotent=True),
    ToolSpec(name="code_analyze", timeout_s=15, idempotent=True),
    ToolSpec(name="graph_neighbors", timeout_s=15, idempotent=True),
    ToolSpec(name="graph_ancestors", timeout_s=15, idempotent=True),
    ToolSpec(name="graph_descendants", timeout_s=15, idempotent=True),
    ToolSpec(name="web_fetch", timeout_s=30, idempotent=True),
    ToolSpec(name="web_search", timeout_s=20, idempotent=True),
    ToolSpec(name="search_symbols", timeout_s=15, idempotent=True),
    ToolSpec(name="git_status", timeout_s=10, idempotent=True),
    ToolSpec(name="git_diff", timeout_s=10, idempotent=True),
    ToolSpec(name="git_log", timeout_s=10, idempotent=True),
    ToolSpec(name="github_search", timeout_s=20, idempotent=True),
    ToolSpec(name="github_repo_view", timeout_s=15, idempotent=True),
    ToolSpec(name="github_repo_list", timeout_s=15, idempotent=True),
    ToolSpec(name="github_browse", timeout_s=15, idempotent=True),
    ToolSpec(name="github_readme", timeout_s=15, idempotent=True),
    ToolSpec(name="github_release", timeout_s=15, idempotent=True),
    ToolSpec(name="github_issue", timeout_s=15, idempotent=True),
    ToolSpec(name="github_pr", timeout_s=15, idempotent=True),
    ToolSpec(name="github_api", timeout_s=20, idempotent=True),
    ToolSpec(name="lsp_goto_definition", timeout_s=15, idempotent=True),
    ToolSpec(name="lsp_hover", timeout_s=10, idempotent=True),
    ToolSpec(name="lsp_diagnostics", timeout_s=10, idempotent=True),
    ToolSpec(name="lsp_find_references", timeout_s=15, idempotent=True),
    ToolSpec(name="lsp_completion", timeout_s=10, idempotent=True),
    ToolSpec(name="code_review", timeout_s=120, idempotent=True, slow=True),
    ToolSpec(name="security_review", timeout_s=120, idempotent=True, slow=True),
]

# ── Generation / external tools — slow, non-idempotent, side effects ──
SLOW_TOOLS: list[ToolSpec] = [
    ToolSpec(name="generate_image", timeout_s=180, idempotent=False, slow=True),
    ToolSpec(name="generate_video", timeout_s=600, idempotent=False, slow=True),
    ToolSpec(name="run_bash", timeout_s=120, idempotent=False, slow=True),
    ToolSpec(name="run_test", timeout_s=1800, idempotent=False, slow=True),
    ToolSpec(name="run_python", timeout_s=30, idempotent=False),
    ToolSpec(name="debug_inspect", timeout_s=120, idempotent=True, slow=True),
    ToolSpec(name="orchestrate", timeout_s=1200, idempotent=False, slow=True),
    ToolSpec(name="execute_plan", timeout_s=600, idempotent=False, slow=True),
    ToolSpec(name="transcribe_audio", timeout_s=120, idempotent=True, slow=True),
    ToolSpec(name="text_to_speech", timeout_s=60, idempotent=True),
    ToolSpec(name="deploy_vercel", timeout_s=120, idempotent=False, slow=True),
    ToolSpec(name="db_query", timeout_s=30, idempotent=True),
    ToolSpec(name="download_file", timeout_s=300, idempotent=False, slow=True),
]

# ── Browser tools — slow, side-effect: EXTERNAL ──
BROWSER_TOOLS: list[ToolSpec] = [
    ToolSpec(name="pw_navigate", timeout_s=30, idempotent=True),
    ToolSpec(name="cdp_ask_chatgpt", timeout_s=240, idempotent=False, slow=True),
    ToolSpec(name="pw_navigate_v2", timeout_s=30, idempotent=True),
]

# ── UI / display tools — fast, read-only ──
UI_TOOLS: list[ToolSpec] = [
    ToolSpec(name="view_image", timeout_s=10, idempotent=True),
    ToolSpec(name="create_markdown", timeout_s=10, idempotent=True),
    ToolSpec(name="create_html", timeout_s=10, idempotent=True),
    ToolSpec(name="create_pdf", timeout_s=30, idempotent=True),
    ToolSpec(name="estimate_tokens", timeout_s=5, idempotent=True),
    ToolSpec(name="tool_search", timeout_s=5, idempotent=True),
    ToolSpec(name="request_user_input", timeout_s=300, idempotent=False, slow=True),
    ToolSpec(name="notebook_open", timeout_s=10, idempotent=True),
    ToolSpec(name="notebook_edit_cell", timeout_s=10, idempotent=False),
    ToolSpec(name="notebook_add_cell", timeout_s=10, idempotent=False),
    ToolSpec(name="notebook_run_cell", timeout_s=60, idempotent=False),
    ToolSpec(name="notebook_save", timeout_s=10, idempotent=False),
    ToolSpec(name="env_check", timeout_s=10, idempotent=True),
    ToolSpec(name="count_lines", timeout_s=10, idempotent=True),
    ToolSpec(name="tree_dir", timeout_s=10, idempotent=True),
]

_ALL_SPECS: dict[str, ToolSpec] = {}
for _group in (WRITE_TOOLS, READ_TOOLS, SLOW_TOOLS, BROWSER_TOOLS, UI_TOOLS):
    for _s in _group:
        _ALL_SPECS[_s.name] = _s


def get_spec(name: str) -> ToolSpec:
    """Get ToolSpec for a tool. Falls back to heuristic if not explicitly declared."""
    if name in _ALL_SPECS:
        return _ALL_SPECS[name]
    return ToolSpec.for_tool(name)
