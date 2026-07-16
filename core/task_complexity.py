"""Canonical task complexity classification – single source of truth.

Replaces the duplicate classifiers that lived in:
  - core/runtime_orchestrator.py  (TaskGrade + classify_intent)
  - core/orchestration.py         (TaskComplexity + classify_complexity)

All routing decisions should flow through ``classify_task()`` here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class TaskComplexity(IntEnum):
    TRIVIAL = 0
    SIMPLE = 1
    MODERATE = 2
    COMPLEX = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class TaskClassification:
    complexity: TaskComplexity
    reason: str

    @property
    def requires_orchestration(self) -> bool:
        """Tasks MODERATE and above need the full orchestration pipeline."""
        return self.complexity >= TaskComplexity.MODERATE

    @property
    def is_trivial(self) -> bool:
        return self.complexity == TaskComplexity.TRIVIAL


# ── Keyword patterns (priority-ordered; no \b — Chinese chars need plain matching) ──

_CRITICAL_PATTERNS = [
    "production outage", "data loss", "credential leak", "security incident",
    "remote code execution", "rce", "corruption", "rollback production",
    "安全", "部署", "发布", "security", "deploy", "release", "migrate", "migration", "迁移",
]

_COMPLEX_PATTERNS = [
    "architecture", "architectural", "large refactor",
    "distributed system", "breaking change",
    "架构", "设计", "实现", "审计", "集成", "拆分", "重构",
    "refactor", "implement", "design", "audit", "integrate", "split",
]

_MODERATE_PATTERNS = [
    "failing test", "failing tests", "debug", "race condition", "deadlock",
    "implement feature", "performance regression", "integration", "thread safety",
    "修复", "添加", "更新", "删除", "优化",
    "bug", "add", "update", "delete", "optimize", "tweak", "调整",
]

# Feature/module context words — when present alongside a micro-task keyword,
# they indicate the micro-task is part of a larger feature change (MODERATE),
# e.g. "修复登录页拼写错误" contains both "拼写" (SIMPLE) and "页" (feature ctx).
_FEATURE_CONTEXT_PATTERNS = [
    "page", "module", "feature", "system", "component", "screen", "view",
    "页", "模块", "功能", "系统", "组件", "界面", "页面", "登录", "注册", "支付", "认证",
]

_SIMPLE_PATTERNS = [
    "typo", "spelling", "comment", "docstring", "formatting", "rename",
    "documentation", "readme", "log", "logging",
    "拼写", "注释", "格式化", "改名", "日志",
]

_TRIVIAL_RE = re.compile(
    r"^\s*(help|status|list commands?|show version|version)\s*[?.]?\s*$",
    re.IGNORECASE,
)


def _match_any(text_lower: str, keywords: list[str]) -> bool:
    """Plain substring match — works for both ASCII and CJK text."""
    for kw in keywords:
        if kw in text_lower:
            return True
    return False


_TRIVIAL_RE = re.compile(
    r"^\s*(help|status|list commands?|show version|version)\s*[?.]?\s*$",
    re.IGNORECASE,
)


def classify_task(goal: str) -> TaskClassification:
    """Classify a task goal into one of five complexity tiers.

    Returns a ``TaskClassification`` with the level and a human-readable reason.
    Use ``classification.requires_orchestration`` to decide whether to route
    through the full orchestration pipeline.
    """
    text = " ".join(goal.split())

    if not text:
        return TaskClassification(TaskComplexity.TRIVIAL, "Empty task")

    text_lower = text.lower()

    if _match_any(text_lower, _CRITICAL_PATTERNS):
        return TaskClassification(
            TaskComplexity.CRITICAL,
            "Critical production, security, or data-risk signal detected",
        )

    if _match_any(text_lower, _COMPLEX_PATTERNS):
        return TaskClassification(
            TaskComplexity.COMPLEX,
            "Repository-wide, architectural, or multi-module scope",
        )

    # A goal counts as a micro-task (SIMPLE) only when its signal is a pure
    # micro-task keyword WITHOUT any feature/module context. If the goal also
    # names a page/module/feature (e.g. "修复登录页拼写错误" = "拼写" SIMPLE
    # + "登录页" feature ctx), the micro-task is part of a feature change and
    # must be classified MODERATE.
    _has_simple = _match_any(text_lower, _SIMPLE_PATTERNS)
    _has_feature_ctx = _match_any(text_lower, _FEATURE_CONTEXT_PATTERNS)
    if _has_simple and not _has_feature_ctx:
        return TaskClassification(
            TaskComplexity.SIMPLE,
            "Small, locally scoped edit",
        )

    if _match_any(text_lower, _MODERATE_PATTERNS):
        return TaskClassification(
            TaskComplexity.MODERATE,
            "Debugging, integration, or feature implementation",
        )

    # Micro-task word appeared but was overridden by feature context above;
    # if no moderate signal matched, still treat as MODERATE (feature edit).
    if _has_simple and _has_feature_ctx:
        return TaskClassification(
            TaskComplexity.MODERATE,
            "Feature-scoped edit",
        )

    if _TRIVIAL_RE.match(text):
        return TaskClassification(
            TaskComplexity.TRIVIAL,
            "Read-only informational request",
        )

    return TaskClassification(
        TaskComplexity.SIMPLE,
        "No complex or critical scope signals detected",
    )
