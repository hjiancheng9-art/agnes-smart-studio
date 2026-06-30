"""Copilot Native Tools — 移植 Copilot CLI 核心能力到 CRUX。

将 Copilot CLI 验证通过的 AI 驱动能力注册为 CRUX 本地工具：
  - copilot_review: AI 代码审查（补充 code_review.py 的规则引擎）
  - copilot_security_review: AI 安全审计
  - copilot_research: AI 辅助研究搜索
  - copilot_agent: 子智能体委派

与 code_review.py 的关系：
  - code_review.py = 规则引擎（AST + 正则，快但浅）
  - copilot_tools.py = AI 审查（理解上下文，深但慢，需 15-25s）
  - 两者互补：规则引擎做第一道过滤，AI 做深度分析

架构：
  CRUX ToolRegistry → copilot_tools.py → copilot_proxy.py (11436) → Copilot CLI → GPT-5-mini
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

__all__ = [
    "COPILOT_TOOL_DEFS",
    "COPILOT_EXECUTOR_MAP",
    "run_copilot_review",
    "run_copilot_security_review",
    "run_copilot_research",
    "CopilotToolRunner",
]

ROOT = Path(__file__).resolve().parent.parent
COPILOT_BIN = (
    os.environ.get("COPILOT_BIN")
    or os.path.expanduser("~/AppData/Roaming/npm/copilot.CMD")
)

# 自动检测 copilot 路径
import shutil
from core.mcp_servers._mcp_utils import run_subprocess

if not os.path.isfile(COPILOT_BIN):
    found = shutil.which("copilot")
    if found:
        COPILOT_BIN = found

# 超时配置（秒）
REVIEW_TIMEOUT = int(os.environ.get("COPILOT_REVIEW_TIMEOUT", "300"))
RESEARCH_TIMEOUT = int(os.environ.get("COPILOT_RESEARCH_TIMEOUT", "60"))


def _find_copilot() -> str:
    """定位 copilot CLI 可执行文件。"""
    if os.path.isfile(COPILOT_BIN):
        return COPILOT_BIN
    raise FileNotFoundError(
        "Copilot CLI not found. Install: npm i -g @githubnext/github-copilot-cli\n"
        "Or set COPILOT_BIN env var."
    )


def _run_copilot(prompt: str, timeout: int = 120, cwd: str | None = None) -> dict:
    """调用 Copilot CLI 执行单次对话。

    返回 {"success": bool, "output": str, "error": str|None, "elapsed": float}
    """
    copilot = _find_copilot()
    start = time.time()

    try:
        r = run_subprocess([copilot, "-p", prompt, "--allow-all-tools", "--allow-all-paths"], timeout=timeout, cwd=cwd or str(ROOT))
        elapsed = time.time() - start
        output = r.stdout.strip()

        if r.returncode != 0 and not output:
            output = f"[Copilot Error] {r.stderr.strip()}" if r.stderr else "[Copilot returned empty]"

        return {
            "success": r.returncode == 0,
            "output": output,
            "error": r.stderr.strip() if r.stderr else None,
            "elapsed": round(elapsed, 1),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Timeout after {timeout}s",
            "elapsed": timeout,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": "",
            "error": f"Copilot CLI not found at {COPILOT_BIN}",
            "elapsed": 0,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "elapsed": time.time() - start,
        }


def _read_context_files(files: list[str], max_chars: int = 50000) -> str:
    """读取指定文件的内容，拼接为上下文字符串。

    超过 max_chars 则截断并标记。
    """
    chunks = []
    total = 0

    for fp in files:
        if not os.path.isfile(fp):
            chunks.append(f"[MISSING] {fp}")
            continue
        try:
            content = Path(fp).read_text(encoding="utf-8", errors="replace")
            if total + len(content) > max_chars:
                remaining = max_chars - total
                content = content[:remaining] + "\n... [TRUNCATED]"
            chunks.append(f"=== {fp} ===\n{content}")
            total += len(content)
            if total >= max_chars:
                chunks.append(f"[Total input truncated at {max_chars} chars]")
                break
        except Exception as e:
            chunks.append(f"[ERROR reading {fp}: {e}]")

    return "\n\n".join(chunks)


# ════════════════════════════════════════════════════════════════
# 工具 1: AI 代码审查 (copilot_review)
# ════════════════════════════════════════════════════════════════


def run_copilot_review(
    files: list[str] | None = None,
    focus: str = "all",
    diff_only: bool = False,
) -> dict:
    """通过 Copilot (GPT-5-mini) 执行 AI 驱动的代码审查。

    Args:
        files: 要审查的文件路径列表。None 时自动取 git diff 中的文件。
        focus: 审查焦点 — "bugs" | "security" | "style" | "performance" | "all"
        diff_only: 仅审查变更部分（读取 git diff 而非完整文件）

    Returns:
        {"success": bool, "review": str, "files": [...], "elapsed": float}
    """
    # 确定文件列表
    target_files = []
    if files:
        target_files = [f for f in files if os.path.isfile(f)]
    elif diff_only:
        try:
            r = run_subprocess(["git", "diff", "--name-only", "HEAD"], timeout=10, cwd=str(ROOT))
            target_files = [
                f.strip() for f in r.stdout.splitlines()
                if f.strip() and os.path.isfile(f.strip())
            ]
        except Exception:
            pass

    if not target_files:
        # 兜底：当前目录下的核心 Python 文件
        target_files = [
            str(p) for p in ROOT.glob("core/*.py")
            if p.is_file()
        ][:5]

    # 读取文件内容
    context = _read_context_files(target_files, max_chars=40000)

    # 构建审查提示词
    focus_map = {
        "bugs": "Focus ONLY on bugs, logic errors, edge cases, and potential crashes.",
        "security": "Focus ONLY on security vulnerabilities: injection risks, hardcoded secrets, unsafe deserialization, path traversal.",
        "style": "Focus ONLY on code style, naming, readability, and maintainability.",
        "performance": "Focus ONLY on performance issues, algorithmic complexity, and resource leaks.",
        "all": "Cover all aspects: bugs, security, style, and performance.",
    }
    focus_instruction = focus_map.get(focus, focus_map["all"])

    prompt = f"""[Code Review Request]
{focus_instruction}

Files to review:
{context}

Output a structured code review with these sections:
1. Summary (2-3 sentences)
2. Critical Issues (if any — with file:line references)
3. Warnings (potential problems)
4. Suggestions (concrete improvements)

Be specific. Reference line numbers where possible. Be concise."""

    result = _run_copilot(prompt, timeout=REVIEW_TIMEOUT, cwd=str(ROOT))

    return {
        "success": result["success"],
        "review": result["output"],
        "files": target_files,
        "elapsed": result["elapsed"],
        "error": result["error"],
        "engine": "copilot-gpt-5-mini",
        "mode": "ai-powered",
    }


def _exec_copilot_review(args: dict) -> str:
    """ToolRegistry 执行器接口。"""
    r = run_copilot_review(
        files=args.get("files"),
        focus=args.get("focus", "all"),
        diff_only=args.get("diff_only", False),
    )
    return json.dumps(r, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════
# 工具 2: AI 安全审计 (copilot_security_review)
# ════════════════════════════════════════════════════════════════


def run_copilot_security_review(
    files: list[str] | None = None,
    threat_model: str = "web-app",
) -> dict:
    """通过 Copilot 执行 AI 驱动的安全审计。

    Args:
        files: 要审计的文件列表。None 时自动发现。
        threat_model: 威胁模型 — "web-app" | "cli-tool" | "api-service" | "library"

    Returns:
        {"success": bool, "audit": str, "files": [...], "elapsed": float}
    """
    target_files = []
    if files:
        target_files = [f for f in files if os.path.isfile(f)]
    else:
        # 自动发现核心 Python 文件
        target_files = sorted(
            [str(p) for p in ROOT.glob("core/*.py") if p.is_file()],
            key=lambda x: os.path.getsize(x),
            reverse=True,
        )[:8]

    context = _read_context_files(target_files, max_chars=50000)

    threat_context = {
        "web-app": "Web application: consider XSS, CSRF, SQL injection, auth bypass, session hijacking.",
        "cli-tool": "CLI tool: consider shell injection, argument injection, privilege escalation, path traversal.",
        "api-service": "API service: consider JWT flaws, rate limiting bypass, IDOR, mass assignment, SSRF.",
        "library": "Library/SDK: consider dependency confusion, prototype pollution, deserialization attacks.",
    }
    threat_instruction = threat_context.get(threat_model, threat_context["web-app"])

    prompt = f"""[Security Audit Request]
Threat model: {threat_model} — {threat_instruction}

Files to audit:
{context}

Output a structured security audit with:
1. Threat Summary (overall risk level + top threats)
2. Critical Vulnerabilities (CVE-worthy issues with file:line)
3. Medium/Low Risks
4. Remediation Plan (concrete steps, priority order)

Use OWASP Top 10 terminology. Reference specific line numbers. Be thorough."""

    result = _run_copilot(prompt, timeout=REVIEW_TIMEOUT, cwd=str(ROOT))

    return {
        "success": result["success"],
        "audit": result["output"],
        "files": target_files,
        "elapsed": result["elapsed"],
        "error": result["error"],
        "engine": "copilot-gpt-5-mini",
        "threat_model": threat_model,
    }


def _exec_copilot_security_review(args: dict) -> str:
    """ToolRegistry 执行器接口。"""
    r = run_copilot_security_review(
        files=args.get("files"),
        threat_model=args.get("threat_model", "web-app"),
    )
    return json.dumps(r, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════
# 工具 3: AI 研究搜索 (copilot_research)
# ════════════════════════════════════════════════════════════════


def run_copilot_research(
    query: str,
    depth: str = "quick",
    max_sources: int = 5,
) -> dict:
    """通过 Copilot 执行 AI 驱动的研究搜索。

    利用 Copilot 的网页搜索能力获取最新信息。

    Args:
        query: 研究问题
        depth: "quick"（快速概要）| "deep"（深度分析）
        max_sources: 最多引用来源数

    Returns:
        {"success": bool, "findings": str, "sources": [...], "elapsed": float}
    """
    depth_instruction = {
        "quick": "Give a concise answer in 3-5 bullet points. Cite sources.",
        "deep": "Do a thorough analysis. Include multiple perspectives, cite sources, and note any disagreements in the field.",
    }
    instruction = depth_instruction.get(depth, depth_instruction["quick"])

    prompt = f"""[Research Request]
{instruction}

Question: {query}

Format:
- Key Findings (numbered list)
- Sources (where you got the info)
- Confidence (high/medium/low with brief reason)"""

    result = _run_copilot(prompt, timeout=RESEARCH_TIMEOUT)

    # 尝试提取来源
    sources = []
    output = result["output"]
    if "Sources:" in output or "sources:" in output:
        # 简单提取 URL
        import re

        urls = re.findall(r"https?://[^\s\)\]>]+", output)
        sources = urls[:max_sources]

    return {
        "success": result["success"],
        "findings": output,
        "sources": sources,
        "elapsed": result["elapsed"],
        "error": result["error"],
        "engine": "copilot-gpt-5-mini",
        "depth": depth,
    }


def _exec_copilot_research(args: dict) -> str:
    """ToolRegistry 执行器接口。"""
    r = run_copilot_research(
        query=args.get("query", ""),
        depth=args.get("depth", "quick"),
        max_sources=args.get("max_sources", 5),
    )
    return json.dumps(r, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════
# ToolRegistry 兼容定义
# ════════════════════════════════════════════════════════════════

COPILOT_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "copilot_review",
            "description": "AI 代码审查：通过 Copilot (GPT-5-mini) 深度分析代码，发现 bugs/安全/风格/性能问题。比规则引擎更深入，能理解上下文。适合审查核心模块和复杂逻辑。",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要审查的文件路径列表（空=自动取核心 .py 文件）",
                    },
                    "focus": {
                        "type": "string",
                        "enum": ["bugs", "security", "style", "performance", "all"],
                        "description": "审查焦点（默认 all）",
                    },
                    "diff_only": {
                        "type": "boolean",
                        "description": "仅审查 git diff 中的变更文件（默认 false）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copilot_security_review",
            "description": "AI 安全审计：通过 Copilot (GPT-5-mini) 深度扫描代码中的安全漏洞。比 rule-based 安全审查更全面，能识别逻辑漏洞和 OWASP Top 10 模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要审计的文件列表（空=自动取核心文件）",
                    },
                    "threat_model": {
                        "type": "string",
                        "enum": ["web-app", "cli-tool", "api-service", "library"],
                        "description": "威胁模型（默认 web-app）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copilot_research",
            "description": "AI 研究搜索：通过 Copilot 搜索最新技术信息/文档/最佳实践。适合查询 API 用法、版本变更、技术对比等需要外部知识的场景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "研究问题或搜索查询",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "deep"],
                        "description": "研究深度：quick=快速概要, deep=深度分析（默认 quick）",
                    },
                    "max_sources": {
                        "type": "integer",
                        "description": "最多引用的来源数（默认 5）",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

COPILOT_EXECUTOR_MAP = {
    "copilot_review": _exec_copilot_review,
    "copilot_security_review": _exec_copilot_security_review,
    "copilot_research": _exec_copilot_research,
}


# ════════════════════════════════════════════════════════════════
# 便捷类：程序化调用
# ════════════════════════════════════════════════════════════════


class CopilotToolRunner:
    """程序化调用 Copilot 工具的统一入口。

    使用示例:
        runner = CopilotToolRunner()
        result = runner.review(["core/copilot_proxy.py"])
        result = runner.security_review(["core/copilot_proxy.py"])
        result = runner.research("Python 3.13 new features")
    """

    def __init__(self):
        import shutil

        self.copilot_bin = shutil.which("copilot") or COPILOT_BIN
        self.available = os.path.isfile(self.copilot_bin) if self.copilot_bin else False

    def review(self, files: list[str] | None = None, **kwargs) -> dict:
        return run_copilot_review(files=files, **kwargs)

    def security_review(self, files: list[str] | None = None, **kwargs) -> dict:
        return run_copilot_security_review(files=files, **kwargs)

    def research(self, query: str, **kwargs) -> dict:
        return run_copilot_research(query=query, **kwargs)

    def ping(self) -> bool:
        """快速检查 Copilot CLI 是否可用。"""
        try:
            r = run_subprocess([self.copilot_bin, "--version"], timeout=5)
            return r.returncode == 0
        except Exception:
            return False
