"""GitHub 工具集 — 基于 gh CLI，零限制访问 GitHub 全部能力。

CRUX DNA: AI-native platform, 不设外部能力边界。
所有工具通过 gh CLI 2.x 调用，token 由 gh 自行管理，CRUX 不碰。

9 个工具覆盖：搜索(5合1) / 仓库管理 / 文件浏览 / README / Release / Issue / PR / 万能 API。

用法：每个 execute_* 函数返回 json.dumps 字符串，供 ToolRegistry 的 python_executor 调用。
"""

import base64
import json
import re
import subprocess

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "execute_github_api",
    "execute_github_browse",
    "execute_github_issue",
    "execute_github_pr",
    "execute_github_readme",
    "execute_github_release",
    "execute_github_repo_list",
    "execute_github_repo_view",
    "execute_github_search",
    "execute_github_write_file",
    "_parse_repo_arg",
    "_run_gh",
]


# ======================================================================
# 底层：gh CLI 执行 + repo 参数解析
# ======================================================================


def _run_gh(args: list[str], timeout: int = 30) -> dict:
    """执行 gh CLI 命令，返回统一结果字典。

    补全 git_tools._run_gh 缺少的 TimeoutExpired 单独捕获。
    """
    cmd = ["gh"] + args
    try:
        r = run_subprocess(cmd, timeout=timeout)
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip() if r.stdout else "",
            "stderr": r.stderr.strip() if r.stderr else "",
            "exit_code": r.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "error": "gh CLI not found. Install from https://cli.github.com/"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"gh command timed out after {timeout}s"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"success": False, "error": str(e)}


def _parse_repo_arg(repo: str = "") -> str:
    """从各种格式提取 owner/repo slug。

    支持:
      https://github.com/owner/repo       → owner/repo
      https://github.com/owner/repo.git   → owner/repo
      https://github.com/owner/repo/tree/main → owner/repo
      git@github.com:owner/repo.git       → owner/repo
      owner/repo                          → owner/repo
      空                                  → git remote get-url origin 自动检测
    """
    if not repo:
        # 自动检测当前仓库
        r = _run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], timeout=5)
        if r.get("success"):
            return r["stdout"].strip()
        return ""

    repo = repo.strip()
    # 去掉末尾 .git 和 trailing slash
    repo = re.sub(r"\.git\s*$", "", repo).rstrip("/")

    # GitHub URL → 提取 owner/repo
    patterns = [
        r"github\.com[/:]([^/\s]+/[^/\s?#]+)",
    ]
    for pat in patterns:
        m = re.search(pat, repo)
        if m:
            slug = m.group(1)
            # 去掉 URL path 中 tree/main 等后缀
            slug = slug.split("/")[0] + "/" + slug.split("/")[1]
            return slug

    # 已经是 owner/repo 格式
    if "/" in repo and len(repo.split("/")) == 2:
        return repo

    return repo


# ======================================================================
# 9 个工具 executor（统一返回 json.dumps）
# ======================================================================

# ── 1. github_search: 5 合 1 搜索 ──


def execute_github_search(
    query: str = "",
    search_type: str = "repos",
    language: str = "",
    owner: str = "",
    repo: str = "",
    sort: str = "",
    limit: int = 10,
    state: str = "",
    label: str = "",
) -> str:
    """搜索 GitHub: repos / issues / PRs / code / commits，5 合 1。"""
    if not query:
        return json.dumps({"error": "query required"}, ensure_ascii=False)

    valid_types = {"repos", "issues", "prs", "code", "commits"}
    if search_type not in valid_types:
        return json.dumps(
            {"error": f"search_type must be one of: {', '.join(sorted(valid_types))}"}, ensure_ascii=False
        )

    args = ["search", search_type, query, "--limit", str(min(limit, 100))]

    # 通用过滤参数
    if language:
        args += ["--language", language]
    if owner:
        args += ["--owner", owner]
    if repo:
        args += ["--repo", repo]
    if sort:
        args += ["--sort", sort]

    # issues/prs 专用
    if search_type in ("issues", "prs"):
        if state:
            args += ["--state", state]
        if label:
            args += ["--label", label]

    r = _run_gh(args)
    if not r.get("success"):
        return json.dumps(
            {"error": r.get("stderr", r.get("error", "unknown error")), "query": query, "search_type": search_type},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "query": query,
            "search_type": search_type,
            "results": r["stdout"],
            "raw_output": r["stdout"][:5000],
        },
        ensure_ascii=False,
        indent=2,
    )


# ── 2. github_repo_view: 仓库信息 ──


def execute_github_repo_view(repo: str = "") -> str:
    """查看仓库信息：描述、星标、语言、README 等。"""
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    r = _run_gh(
        [
            "repo",
            "view",
            slug,
            "--json",
            "name,description,url,stargazerCount,forkCount,primaryLanguage,"
            "licenseInfo,createdAt,updatedAt,isPrivate,isArchived,defaultBranchRef",
            "-q",
            ".",
        ]
    )
    if not r.get("success"):
        return json.dumps({"error": r.get("stderr", r.get("error", "unknown")), "repo": slug}, ensure_ascii=False)

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    data["repo"] = slug
    return json.dumps(data, ensure_ascii=False, indent=2)


# ── 3. github_repo_list: 列出仓库 ──


def execute_github_repo_list(owner: str = "", limit: int = 20) -> str:
    """列出仓库（默认当前用户，可指定 owner）。"""
    args = [
        "repo",
        "list",
        "--limit",
        str(min(limit, 100)),
        "--json",
        "name,description,url,stargazerCount,isPrivate,updatedAt",
    ]
    if owner:
        args.append(owner)

    r = _run_gh(args)
    if not r.get("success"):
        return json.dumps({"error": r.get("stderr", r.get("error", "unknown"))}, ensure_ascii=False)

    try:
        repos = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    return json.dumps(
        {"owner": owner or "current user", "count": len(repos), "repos": repos}, ensure_ascii=False, indent=2
    )


# ── 4. github_browse: 读文件/目录（无 5000 字限制）──


def execute_github_browse(repo: str = "", path: str = "", ref: str = "") -> str:
    """读取仓库文件或目录树。突破 web_fetch 5000 字限制。

    path 为空时列出仓库根目录；指定 path 时返回文件内容（Base64 解码）。
    """
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    api_path = f"repos/{slug}/contents/{path}".rstrip("/") if path else f"repos/{slug}/contents"
    args = ["api", api_path]
    if ref:
        args += ["--jq", "--ref", ref]
        # gh api 的 --ref 需要通过 query param 或 header，用 -f 更可靠
        args = ["api", api_path, "-f", f"ref={ref}"]

    r = _run_gh(args, timeout=15)
    if not r.get("success"):
        return json.dumps(
            {"error": r.get("stderr", r.get("error", "unknown")), "repo": slug, "path": path}, ensure_ascii=False
        )

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    # 目录：返回文件列表
    if isinstance(data, list):
        items = [
            {"name": item["name"], "type": item["type"], "path": item["path"], "size": item.get("size", 0)}
            for item in data
        ]
        return json.dumps(
            {"repo": slug, "path": path or "/", "type": "directory", "items": items, "count": len(items)},
            ensure_ascii=False,
            indent=2,
        )

    # 文件：Base64 解码内容
    if isinstance(data, dict) and data.get("type") == "file":
        content_b64 = data.get("content", "")
        try:
            content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            content = content_b64  # fallback
        result = {
            "repo": slug,
            "path": data.get("path", path),
            "type": "file",
            "size": data.get("size", 0),
            "sha": data.get("sha", ""),
            "content": content,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    return json.dumps(data, ensure_ascii=False, indent=2)


# ── 5. github_readme: 一键读 README ──


def execute_github_readme(repo: str = "") -> str:
    """读取任意仓库的 README。"""
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    r = _run_gh(["api", f"repos/{slug}/readme", "-q", "."], timeout=15)
    if not r.get("success"):
        return json.dumps({"error": r.get("stderr", r.get("error", "unknown")), "repo": slug}, ensure_ascii=False)

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    content_b64 = data.get("content", "")
    try:
        content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        content = content_b64

    return json.dumps(
        {
            "repo": slug,
            "name": data.get("name", ""),
            "path": data.get("path", ""),
            "size": data.get("size", 0),
            "content": content,
        },
        ensure_ascii=False,
        indent=2,
    )


# ── 6. github_release: 列出/查看 releases ──


def execute_github_release(repo: str = "", tag: str = "", limit: int = 10) -> str:
    """列出 releases（指定 tag 则查看详情）。"""
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    if tag:
        r = _run_gh(
            [
                "release",
                "view",
                tag,
                "--repo",
                slug,
                "--json",
                "tagName,name,body,createdAt,isDraft,isPrerelease,assets",
            ],
            timeout=15,
        )
    else:
        r = _run_gh(
            [
                "release",
                "list",
                "--repo",
                slug,
                "--limit",
                str(min(limit, 30)),
                "--json",
                "tagName,name,createdAt,isDraft,isPrerelease",
            ],
            timeout=15,
        )

    if not r.get("success"):
        return json.dumps({"error": r.get("stderr", r.get("error", "unknown")), "repo": slug}, ensure_ascii=False)

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    return json.dumps({"repo": slug, "tag": tag, "releases": data}, ensure_ascii=False, indent=2)


# ── 7. github_issue: 创建/列出/查看 issues ──


def execute_github_issue(
    repo: str = "",
    action: str = "list",
    title: str = "",
    body: str = "",
    state: str = "open",
    limit: int = 20,
) -> str:
    """GitHub Issues: list / view（create 由 git_tools.git_pr_create 间接覆盖）。

    action: list | create
    """
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    if action == "list":
        args = [
            "issue",
            "list",
            "--repo",
            slug,
            "--state",
            state,
            "--limit",
            str(min(limit, 50)),
            "--json",
            "number,title,state,createdAt,author,labels",
        ]
        r = _run_gh(args)
    elif action == "create":
        if not title:
            return json.dumps({"error": "title required for create"}, ensure_ascii=False)
        args = ["issue", "create", "--repo", slug, "--title", title, "--body", body or ""]
        r = _run_gh(args)
    else:
        return json.dumps({"error": f"action must be 'list' or 'create', got '{action}'"}, ensure_ascii=False)

    if not r.get("success"):
        return json.dumps(
            {"error": r.get("stderr", r.get("error", "unknown")), "repo": slug, "action": action}, ensure_ascii=False
        )

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    return json.dumps({"repo": slug, "action": action, "results": data}, ensure_ascii=False, indent=2)


# ── 8. github_pr: 列出/查看 PRs ──


def execute_github_pr(
    repo: str = "",
    state: str = "open",
    limit: int = 20,
    number: int = 0,
) -> str:
    """GitHub PRs: list / view（create/merge 由 git_tools 覆盖）。"""
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)

    if number:
        r = _run_gh(
            [
                "pr",
                "view",
                str(number),
                "--repo",
                slug,
                "--json",
                "number,title,state,body,author,createdAt,headRefName,baseRefName,"
                "reviewDecision,mergeable,additions,deletions,changedFiles",
            ],
            timeout=15,
        )
    else:
        r = _run_gh(
            [
                "pr",
                "list",
                "--repo",
                slug,
                "--state",
                state,
                "--limit",
                str(min(limit, 50)),
                "--json",
                "number,title,state,createdAt,headRefName,baseRefName,reviewDecision",
            ]
        )

    if not r.get("success"):
        return json.dumps({"error": r.get("stderr", r.get("error", "unknown")), "repo": slug}, ensure_ascii=False)

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    return json.dumps({"repo": slug, "state": state, "results": data}, ensure_ascii=False, indent=2)


# ── 9. github_api: 万能钥匙（零限制）──


def execute_github_api(
    endpoint: str = "",
    method: str = "",
    fields: str = "",
    jq_filter: str = "",
    paginate: bool = False,
    raw_input: str = "",
) -> str:
    """万能钥匙：调用任意 GitHub REST/GraphQL endpoint。

    AI 可以用这个做 GitHub 上的一切。零限制。

    Examples:
      endpoint: "repos/owner/repo/releases/latest"
      endpoint: "graphql"  +  raw_input: '{"query":"{ viewer { login } }"}'
      endpoint: "search/code?q=hello+language:python"
      method: "POST"
      fields: "title=My Title" (多个用换行分隔，如 "title=T1\\nbody=B2")
    """
    if not endpoint:
        return json.dumps({"error": "endpoint required"}, ensure_ascii=False)

    args = ["api", endpoint]

    if method:
        args += ["--method", method.upper()]

    # 解析 fields（换行分隔的 key=value 对）
    if fields:
        for field_line in fields.strip().split("\n"):
            field_line = field_line.strip()
            if "=" in field_line:
                args += ["-f", field_line]

    if jq_filter:
        args += ["--jq", jq_filter]

    if paginate:
        args.append("--paginate")

    if raw_input:
        # 用 --input 传入 JSON body（适合 GraphQL）
        args += ["--input", "-", "--method", "POST"]
        r = run_subprocess(["gh"] + args, input_data=raw_input, timeout=30)
        result = {
            "success": r.returncode == 0,
            "stdout": r.stdout.strip() if r.stdout else "",
            "stderr": r.stderr.strip() if r.stderr else "",
            "exit_code": r.returncode,
        }
    else:
        result = _run_gh(args)

    if not result.get("success"):
        return json.dumps(
            {"error": result.get("stderr", result.get("error", "unknown")), "endpoint": endpoint}, ensure_ascii=False
        )

    return json.dumps(
        {
            "endpoint": endpoint,
            "method": method or "GET",
            "result": result["stdout"],
        },
        ensure_ascii=False,
        indent=2,
    )


# ── 10. github_write_file: 远端写文件（自动 commit）──


def execute_github_write_file(
    repo: str = "",
    path: str = "",
    content: str = "",
    message: str = "",
    branch: str = "",
    sha: str = "",
) -> str:
    """通过 Contents API 在远端创建或更新文件，自动 commit。

    创建新文件：sha 留空。
    更新已有文件：需要先通过 github_browse 获取该文件的 sha。
    所有内容会自动 Base64 编码，gh api 原生支持 -f content=@- 通过 stdin 传入。

    典型工作流：
      1. github_browse 获取 sha（更新时）
      2. github_write_file 写入新内容
      3. git_pr_create 创建 PR（可选）
    """
    slug = _parse_repo_arg(repo)
    if not slug:
        return json.dumps({"error": "repo required (format: owner/repo or URL)"}, ensure_ascii=False)
    if not path:
        return json.dumps({"error": "path required"}, ensure_ascii=False)
    if not content:
        return json.dumps({"error": "content required"}, ensure_ascii=False)

    endpoint = f"repos/{slug}/contents/{path}"
    args = ["api", endpoint, "--method", "PUT"]

    # Base64 编码内容
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    args += ["-f", f"message={message or f'Update {path}'}"]
    args += ["-f", f"content={encoded}"]

    if branch:
        args += ["-f", f"branch={branch}"]
    if sha:
        args += ["-f", f"sha={sha}"]

    r = _run_gh(args, timeout=30)
    if not r.get("success"):
        return json.dumps(
            {"error": r.get("stderr", r.get("error", "unknown")), "repo": slug, "path": path}, ensure_ascii=False
        )

    try:
        data = json.loads(r["stdout"])
    except json.JSONDecodeError:
        return json.dumps({"error": "failed to parse gh output", "raw": r["stdout"][:1000]}, ensure_ascii=False)

    result = {
        "repo": slug,
        "path": path,
        "commit": {
            "sha": data.get("commit", {}).get("sha", ""),
            "message": data.get("commit", {}).get("message", ""),
            "url": data.get("commit", {}).get("html_url", ""),
        },
        "content": {
            "sha": data.get("content", {}).get("sha", ""),
            "path": data.get("content", {}).get("path", ""),
        },
    }
    if data.get("commit", {}).get("html_url"):
        result["url"] = data["commit"]["html_url"]

    return json.dumps(result, ensure_ascii=False, indent=2)
