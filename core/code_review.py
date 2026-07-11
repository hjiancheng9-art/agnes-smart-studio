"""Code Review & Security Review Tools — CRUX 内置代码审查。

借鉴 Copilot CLI 的 /review 和 /security-review 命令设计。
不依赖外部 CLI，直接基于本地 AST 分析 + 规则引擎。
"""

import ast
import json
import logging
import os
import re

logger = logging.getLogger("crux.code_review")
from dataclasses import dataclass, field
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "CODE_REVIEW_EXECUTOR_MAP",
    "CODE_REVIEW_TOOL_DEFS",
    "CodeReviewer",
    "SecurityReviewer",
    "run_review",
    "run_security_review",
]

# ── 审查结果模型 ──


@dataclass
class ReviewIssue:
    file: str
    line: int
    severity: str  # error | warning | info
    category: str  # style | logic | performance | security | maintainability
    message: str
    suggestion: str = ""
    rule: str = ""


@dataclass
class ReviewReport:
    issues: list[ReviewIssue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "issues": [
                {
                    "file": i.file,
                    "line": i.line,
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "rule": i.rule,
                }
                for i in self.issues
            ],
            "stats": self.stats,
        }

    def summary(self) -> str:
        s = self.stats
        lines = ["## Code Review Report", f"Files: {s.get('files', 0)} | Lines: {s.get('lines', 0)}"]
        lines.append(
            f"Issues: {s.get('total_issues', 0)} ({s.get('errors', 0)} errors, {s.get('warnings', 0)} warnings, {s.get('info', 0)} info)"
        )
        if self.issues:
            lines.append("")
            for i in self.issues[:20]:
                lines.append(f"- [{i.severity.upper()}] {i.file}:{i.line} — {i.message}")
            if len(self.issues) > 20:
                lines.append(f"  ... and {len(self.issues) - 20} more")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# 规则引擎
# ════════════════════════════════════════════════════════════════


class BaseRuleChecker:
    """规则检查基类。"""

    name: str = "base"
    category: str = "style"

    def check_file(self, filepath: str, content: str) -> list[ReviewIssue]:
        raise NotImplementedError


class PythonASTChecker(BaseRuleChecker):
    """基于 AST 的 Python 代码检查。"""

    def check_file(self, filepath: str, content: str) -> list[ReviewIssue]:
        issues = []
        try:
            tree = ast.parse(content, filename=filepath)
        except SyntaxError as e:
            issues.append(
                ReviewIssue(
                    file=filepath,
                    line=e.lineno or 1,
                    severity="error",
                    category="logic",
                    message=f"Syntax error: {e.msg}",
                    rule="python-syntax",
                )
            )
            return issues

        # 遍历 AST
        for node in ast.walk(tree):
            issues.extend(self._check_node(node, filepath, content))
        return issues

    def _check_node(self, node, filepath: str, content: str) -> list[ReviewIssue]:
        issues = []

        # 1. 过长的函数体 (> 200 行)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            end_line = node.body[-1].end_lineno or node.lineno
            length = end_line - node.lineno
            if length > 200:
                issues.append(
                    ReviewIssue(
                        file=filepath,
                        line=node.lineno,
                        severity="warning",
                        category="maintainability",
                        message=f"Function '{node.name}' is {length} lines long (threshold: 200)",
                        suggestion="Consider splitting into smaller functions",
                        rule="function-length",
                    )
                )

        # 2. 裸 except (可能吞掉重要异常)
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                ReviewIssue(
                    file=filepath,
                    line=node.lineno,
                    severity="warning",
                    category="maintainability",
                    message="Bare except clause — may hide unexpected errors",
                    suggestion="Catch specific exception types, or at minimum `except Exception`",
                    rule="bare-except",
                )
            )

        # 3. 循环中调用 .append()（可用列表推导式）
        # (简化检测：for 循环体中直接有 .append)

        return issues


class TextPatternChecker(BaseRuleChecker):
    """基于文本模式的通用检查（适用于所有语言）。"""

    # (pattern, severity, category, message, suggestion, rule_name)
    PATTERNS = [
        # ⚠ 安全
        (
            r'\bpassword\s*=\s*["\'][^"\']+["\']',
            "error",
            "security",
            "Hardcoded password found",
            "Use environment variables or secret manager",
            "hardcoded-password",
        ),
        (
            r'\bsecret\s*=\s*["\'][^"\']+["\']',
            "error",
            "security",
            "Hardcoded secret/token found",
            "Use environment variables",
            "hardcoded-secret",
        ),
        (
            r'\bapi[_-]?key\s*=\s*["\'][^"\']+["\']',
            "error",
            "security",
            "Hardcoded API key",
            "Move to .env or config",
            "hardcoded-api-key",
        ),
        (
            r'\baws_access_key_id\s*=\s*["\'][^"\']+["\']',
            "error",
            "security",
            "Hardcoded AWS credential",
            "Use IAM roles or ~/.aws/credentials",
            "hardcoded-aws-key",
        ),
        (
            r"\beval\s*\(",
            "warning",
            "security",
            "eval() usage — potential code injection",
            "Use ast.literal_eval() or avoid eval",
            "dangerous-eval",
        ),
        (
            r"\bexec\s*\(",
            "error",
            "security",
            "exec() usage — arbitrary code execution risk",
            "Avoid exec entirely",
            "dangerous-exec",
        ),
        (
            r"\bos\.system\s*\(",
            "warning",
            "security",
            "os.system() — shell injection risk",
            "Use subprocess.run() with list args",
            "shell-injection",
        ),
        (
            r'\bsubprocess\.call\s*\(\s*["\'].*\$',
            "warning",
            "security",
            "Subprocess call with shell variable expansion",
            "Pass args as list, not string",
            "shell-injection-subprocess",
        ),
        (
            r"pickle\.(loads?|dumps?)\s*\(",
            "warning",
            "security",
            "pickle usage — arbitrary code execution on deserialization",
            "Use JSON or safer serialization",
            "dangerous-pickle",
        ),
        # ⚠ 质量
        (
            r"TODO|FIXME|HACK|XXX",
            "info",
            "maintainability",
            "TODO/FIXME/HACK comment found",
            "Address or track in issue tracker",
            "todo-comment",
        ),
        (
            r"print\s*\(",
            "info",
            "style",
            "print() statement found — consider logging",
            "Use logging.getLogger() for production code",
            "debug-print",
        ),
        # ⚠ 依赖
        (
            r"requirements\.txt",
            "info",
            "maintainability",
            "requirements.txt found (consider pyproject.toml)",
            "Migrate to pyproject.toml for modern packaging",
            "old-requirements",
        ),
        # ⚠ 文件操作
        (
            r"open\s*\([^)]*\)\s*\.(read|write)",
            "info",
            "maintainability",
            "File operation without context manager",
            "Use 'with open(...) as f:' pattern",
            "file-no-context",
        ),
    ]

    def check_file(self, filepath: str, content: str) -> list[ReviewIssue]:
        issues = []
        lines = content.splitlines()
        for pat, sev, cat, msg, sug, rule in self.PATTERNS:
            for m in re.finditer(pat, content, re.IGNORECASE):
                # 计算行号
                pos = m.start()
                line_no = content[:pos].count("\n") + 1
                # 过滤假阳性：在注释中的 TODO 不报告为打印
                if rule == "debug-print":
                    line_text = lines[line_no - 1] if line_no <= len(lines) else ""
                    if line_text.strip().startswith("#"):
                        continue
                issues.append(
                    ReviewIssue(
                        file=filepath,
                        line=line_no,
                        severity=sev,
                        category=cat,
                        message=msg,
                        suggestion=sug,
                        rule=rule,
                    )
                )
        return issues


class SecurityRuleChecker(BaseRuleChecker):
    """安全专项检查规则。"""

    SECURITY_PATTERNS = [
        # SQL 注入
        (
            r'(?:execute|cursor)\s*\(\s*f["\']',
            "error",
            "SQL injection risk — f-string in query",
            "Use parameterized queries",
            "sql-injection-fstring",
        ),
        (
            r'(?:execute|cursor)\s*\(\s*["\'].*%\s*\(',
            "warning",
            "SQL injection risk — % formatting in query",
            "Use parameterized queries",
            "sql-injection-percent",
        ),
        # XSS
        (
            r"innerHTML\s*=",
            "error",
            "XSS risk — innerHTML assignment",
            "Use textContent or sanitize with DOMPurify",
            "xss-innerhtml",
        ),
        # 路径遍历
        (
            r"os\.path\.join\s*\(\s*.*request\.",
            "warning",
            "Path traversal risk — user input in file path",
            "Validate and sanitize user input paths",
            "path-traversal",
        ),
        # 不安全的反序列化
        (
            r"yaml\.load\s*\(",
            "error",
            "Unsafe YAML load — arbitrary code execution",
            "Use yaml.safe_load()",
            "unsafe-yaml",
        ),
        # 弱加密
        (r"\bmd5\s*\(", "warning", "MD5 is cryptographically broken", "Use SHA-256 or better", "weak-crypto-md5"),
        (r"\bsha1\s*\(", "info", "SHA-1 is deprecated", "Use SHA-256 or better", "weak-crypto-sha1"),
        # 硬编码证书/密钥
        (
            r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----",
            "error",
            "Private key in source code",
            "Remove immediately, rotate key",
            "private-key-in-code",
        ),
        # 调试模式
        (
            r"DEBUG\s*=\s*True",
            "warning",
            "DEBUG=True in production-like config",
            "Ensure DEBUG is False in production",
            "debug-enabled",
        ),
        # 允许所有主机
        (
            r'ALLOWED_HOSTS\s*=\s*\[\s*["\']?\*["\']?\s*\]',
            "error",
            "ALLOWED_HOSTS = ['*'] — host header attack risk",
            "Restrict to specific hosts",
            "allowed-hosts-wildcard",
        ),
    ]

    def check_file(self, filepath: str, content: str) -> list[ReviewIssue]:
        issues = []
        for pat, sev, msg, sug, rule in self.SECURITY_PATTERNS:
            for m in re.finditer(pat, content, re.IGNORECASE):
                line_no = content[: m.start()].count("\n") + 1
                issues.append(
                    ReviewIssue(
                        file=filepath,
                        line=line_no,
                        severity=sev,
                        category="security",
                        message=msg,
                        suggestion=sug,
                        rule=rule,
                    )
                )
        return issues


# ════════════════════════════════════════════════════════════════
# 审查引擎
# ════════════════════════════════════════════════════════════════


class CodeReviewer:
    """代码审查引擎：收集文件 → 运行规则 → 生成报告。"""

    def __init__(self, rules: list[BaseRuleChecker] | None = None):
        self.rules = rules or [
            PythonASTChecker(),
            TextPatternChecker(),
        ]

    def review_files(self, filepaths: list[str]) -> ReviewReport:
        """审查指定文件列表。"""
        all_issues = []
        total_lines = 0
        for fp in filepaths:
            if not os.path.isfile(fp):
                continue
            try:
                content = Path(fp).read_text(encoding="utf-8", errors="replace")
            except Exception:
                self._log_debug("跳过不可读文件") if hasattr(self, "_log_debug") else None
                continue
            total_lines += content.count("\n") + 1
            for rule in self.rules:
                try:
                    all_issues.extend(rule.check_file(fp, content))
                except Exception as e:
                    logger.debug("file review skipped: %s", e)
                    continue

        stats = {
            "files": len(filepaths),
            "lines": total_lines,
            "total_issues": len(all_issues),
            "errors": sum(1 for i in all_issues if i.severity == "error"),
            "warnings": sum(1 for i in all_issues if i.severity == "warning"),
            "info": sum(1 for i in all_issues if i.severity == "info"),
            "categories": {},
        }
        for i in all_issues:
            stats["categories"][i.category] = stats["categories"].get(i.category, 0) + 1

        return ReviewReport(issues=all_issues, stats=stats)

    def review_changes(self, diff_files: list[str] | None = None) -> ReviewReport:
        """审查 git diff 中的变更文件。"""
        if diff_files:
            return self.review_files(diff_files)

        # 自动获取 git diff 中的文件
        try:
            r = run_subprocess(["git", "diff", "--name-only", "HEAD"], cwd=os.getcwd(), timeout=10)
            files = [f.strip() for f in r.stdout.splitlines() if f.strip().endswith(".py")]
        except Exception:
            files = []
        return self.review_files(files)


class SecurityReviewer(CodeReviewer):
    """安全审查引擎：额外加载安全规则。"""

    def __init__(self):
        super().__init__(
            rules=[
                PythonASTChecker(),
                TextPatternChecker(),
                SecurityRuleChecker(),
            ]
        )


# ════════════════════════════════════════════════════════════════
# 执行入口（供 ToolRegistry 调用）
# ════════════════════════════════════════════════════════════════


def run_review(files: list[str] | None = None, mode: str = "code") -> dict:
    """执行代码审查或安全审查。

    Args:
        files: 要审查的文件列表（None = git diff 中的 .py 文件）
        mode: "code" 或 "security"
    """
    try:
        reviewer = SecurityReviewer() if mode == "security" else CodeReviewer()

        report = reviewer.review_files(files) if files else reviewer.review_changes()

        return {
            "success": True,
            "report": report.to_dict(),
            "summary": report.summary(),
            "mode": mode,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "summary": f"Review failed: {e}"}


def run_security_review(files: list[str] | None = None) -> dict:
    """执行安全审查。"""
    return run_review(files=files, mode="security")


# ── ToolRegistry 兼容定义 ──


def _exec_code_review(files: list[str] | None = None, mode: str = "code") -> str:
    result = run_review(files=files, mode=mode)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _exec_security_review(files: list[str] | None = None) -> str:
    result = run_security_review(files=files)
    return json.dumps(result, ensure_ascii=False, indent=2)


CODE_REVIEW_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "code_review",
            "description": "审查代码质量：检查变更文件的风格/逻辑/性能/可维护性问题。借鉴 Copilot CLI 的 /review 命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要审查的文件路径列表（空=自动取 git diff 中的 .py 文件）",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["code", "security"],
                        "description": "审查模式：code=代码质量, security=安全审查（默认 code）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "security_review",
            "description": "审查安全漏洞：检查硬编码凭据/SQL注入/XSS/路径遍历/不安全反序列化等。借鉴 Copilot CLI 的 /security-review 命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要审查的文件路径列表（空=自动取 git diff 中的 .py 文件）",
                    },
                },
            },
        },
    },
]

CODE_REVIEW_EXECUTOR_MAP = {
    "code_review": _exec_code_review,
    "security_review": _exec_security_review,
}
