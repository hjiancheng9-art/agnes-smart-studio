"""Plan-Execute fusion: GPT gives the plan, local model executes with tools.

Replaces the old core/fusion.py prefix-injection approach. Instead of truncating
GPT's reply to 2000 chars and concatenating, this module:

1. Builds a structured "plan context" from GPT's full reply
2. Injects it as system context (not as a user-message prefix)
3. Tells the local model to execute the plan using its tool capabilities

The local model gets GPT's full reasoning + code, and uses its own tool-calling
ability to actually implement/verify/extend the plan. This leverages GPT's
reasoning strength and the local model's execution capability.

When the user mentions file paths, those files are uploaded to GPT alongside
the plan request, so GPT can analyze actual file content.
"""

from __future__ import annotations

import os
import re

# ── File path detection ────────────────────────────────────

# Broader than router.py's _FILE_PATH_RE — includes image, doc, and code extensions
_FILE_PATH_RE = re.compile(
    r"(?:"
    r'[A-Za-z]:[\\/][^\s:?*"<>|]+'
    r'|[~/][^\s:?*"<>|]+'
    r")"
    r"\.(?:py|js|ts|tsx|jsx|md|json|yaml|yml|toml|cfg|ini|sh|bat|ps1|"
    r"txt|csv|xml|html|css|scss|less|"
    r"c|cpp|cc|h|hpp|java|go|rs|rb|php|swift|kt|scala|lua|r|"
    r"png|jpg|jpeg|gif|webp|bmp|svg|ico|tiff|"
    r"pdf|doc|docx|xls|xlsx|ppt|pptx|zip|tar|gz|rar|7z|"
    r"mp4|mov|avi|mkv|webm|flv|wmv|m4v|mpg|mpeg|3gp)",
    re.IGNORECASE,
)

# Cap to avoid overwhelming CDP upload
_MAX_FILES = 5


def extract_file_paths(text: str) -> list[str]:
    """Extract existing file paths from user text.

    Returns a de-duplicated list of paths that actually exist on disk,
    capped at _MAX_FILES entries.
    """
    matches = _FILE_PATH_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        # Normalize forward slashes for cross-platform consistency
        path = os.path.normpath(m)
        if path in seen:
            continue
        if os.path.isfile(path):
            seen.add(path)
            result.append(path)
            if len(result) >= _MAX_FILES:
                break
    return result


# ── Plan prompt for GPT advisor (text only) ────────────────

PLAN_ADVISOR_PROMPT = """You are a senior software architect advising a local coding agent.

The local agent has these tools: read_file, search_files, glob_files, edit_file, write_file, \
run_bash, run_test, web_search, github_search. It can execute code and edit files directly.

For the user's request below, provide a CONCRETE implementation plan:
1. Brief analysis of what needs to be done
2. Specific files to read/modify/create (with paths if you can guess)
3. Code snippets for key changes (full functions, not pseudocode)
4. Verification steps (tests to run, commands to check)

Be direct and concrete. The local agent will execute your plan with real tools.
Do NOT hedge or say "you should" — give the actual code and commands.

User request:
{query}
"""

# ── Plan prompt for GPT advisor (with files attached) ──────

PLAN_ADVISOR_PROMPT_WITH_FILES = """You are a senior software architect advising a local coding agent.

The local agent has these tools: read_file, search_files, glob_files, edit_file, write_file, \
run_bash, run_test, web_search, github_search. It can execute code and edit files directly.

I have attached {file_count} file(s) for your reference. Analyze them carefully before planning.

For the user's request below, provide a CONCRETE implementation plan:
1. Analysis based on the attached file(s) — reference specific lines/sections
2. Specific changes to make (with exact file paths from the attachments)
3. Code snippets for key changes (full functions, not pseudocode)
4. Verification steps (tests to run, commands to check)

Be direct and concrete. The local agent will execute your plan with real tools.
Do NOT hedge or say "you should" — give the actual code and commands.

User request:
{query}
"""

# ── Execution context for local model ──────────────────────

_EXECUTE_PREFIX = """[GPT Advisor 方案]
GPT 给出了以下方案，请用你的工具能力执行：
- 理解方案思路，用工具调用实现
- 如果方案中的代码可以直接用，用 edit_file/write_file 写入
- 如果方案有问题或不完整，自行修正和补充
- 执行完毕后运行测试验证

"""

_EXECUTE_SUFFIX = """
[方案结束]

现在请执行上述方案。优先使用工具调用（edit_file / write_file / run_bash / run_test）落地实现。"""


def build_advisor_query(user_query: str, file_paths: list[str] | None = None) -> str:
    """Build the query to send to GPT advisor.

    If file_paths is non-empty, uses the file-aware prompt variant.
    """
    if file_paths:
        return PLAN_ADVISOR_PROMPT_WITH_FILES.format(
            query=user_query,
            file_count=len(file_paths),
        )
    return PLAN_ADVISOR_PROMPT.format(query=user_query)


def build_execution_context(user_query: str, gpt_plan: str, file_paths: list[str] | None = None) -> str:
    """Build the text to inject into the local model's context.

    Includes GPT's full plan (no truncation) + execution instructions.
    If file_paths were uploaded to GPT, mentions them so the local model
    knows which files are relevant.
    """
    file_hint = ""
    if file_paths:
        file_list = "\n".join(f"  - {p}" for p in file_paths)
        file_hint = f"\n[GPT 已分析的文件]\n{file_list}\n"

    return f"{_EXECUTE_PREFIX}{gpt_plan}{_EXECUTE_SUFFIX}{file_hint}\n[用户原始请求]\n{user_query}"


def should_consult_gpt(profile_str: str) -> bool:
    """Decide whether a task profile warrants consulting GPT advisor.

    DEEP tasks (architecture, complex analysis) always consult GPT.
    CODING tasks consult GPT only if the query is complex enough.
    CHAT / QUICK_FIX / SKIP never consult GPT (local model is sufficient).
    """
    return profile_str in ("deep", "coding")
