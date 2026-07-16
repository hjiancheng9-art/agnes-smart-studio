# core/intelligence/signals.py
"""TaskSignals — extract task characteristics from user input for policy routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Keywords that indicate different task characteristics
_DANGER_KEYWORDS = [
    "delete",
    "remove",
    "rm ",
    "rmdir",
    "del ",
    "wipe",
    "clear",
    "truncate",
    "覆盖",
    "删除",
    "清空",
]

_SHELL_KEYWORDS = [
    "run ",
    "exec",
    "bash",
    "shell",
    "command",
    "cmd ",
    "terminal",
    "执行",
    "运行",
]

_ARCH_KEYWORDS = [
    "architecture",
    "design",
    "refactor",
    "restructur",
    "migrate",
    "pattern",
    "strategy",
    "trade-off",
    "decision",
    "架构",
    "设计",
    "重构",
]

_MULTI_STEP_KEYWORDS = [
    "first",
    "then",
    "after that",
    "step",
    "phase",
    "stage",
    "先",
    "然后",
    "之后",
    "步骤",
]

_FAILURE_KEYWORDS = [
    "still not",
    "doesn't work",
    "broken",
    "failed",
    "error",
    "不对",
    "不行",
    "炸了",
    "失败了",
    "还是不行",
]


@dataclass(frozen=True)
class TaskSignals:
    """Signals extracted from user input for policy routing."""

    user_message_length: int = 0
    estimated_task_complexity: float = 0.0  # 0.0 - 1.0
    estimated_risk: float = 0.0  # 0.0 - 1.0
    requires_tools: bool = False
    requires_file_write: bool = False
    requires_shell: bool = False
    requires_multi_step: bool = False
    requires_architecture_reasoning: bool = False
    token_pressure: float = 0.0  # 0.0 - 1.0
    prior_failure_score: float = 0.0  # 0.0 - 1.0
    has_danger_keywords: bool = False
    has_failure_indicator: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_message_length": self.user_message_length,
            "estimated_task_complexity": round(self.estimated_task_complexity, 2),
            "estimated_risk": round(self.estimated_risk, 2),
            "requires_tools": self.requires_tools,
            "requires_file_write": self.requires_file_write,
            "requires_shell": self.requires_shell,
            "requires_multi_step": self.requires_multi_step,
            "requires_architecture_reasoning": self.requires_architecture_reasoning,
            "token_pressure": round(self.token_pressure, 2),
            "prior_failure_score": round(self.prior_failure_score, 2),
            "has_danger_keywords": self.has_danger_keywords,
            "has_failure_indicator": self.has_failure_indicator,
        }


class SignalExtractor:
    """Extract TaskSignals from user input and conversation context."""

    def extract(
        self,
        user_message: str,
        message_history: list[dict] | None = None,
        prior_failures: int = 0,
        prior_total_turns: int = 0,
        current_tokens: int = 0,
        max_tokens: int = 64000,
    ) -> TaskSignals:
        """Analyze user input and context to produce routing signals.

        Args:
            user_message: The current user input text.
            message_history: Previous messages (for context).
            prior_failures: Number of prior failed tool calls in session.
            prior_total_turns: Total turns so far in session.
            current_tokens: Current approximate token usage.
            max_tokens: Maximum tokens allowed.
        """
        text = user_message.lower()
        text_len = len(user_message)

        # Requires tools: any invocation-like pattern, or code blocks
        requires_tools = (
            bool(re.search(r"<invoke\b", user_message))
            or bool(re.search(r"read_file|write_file|run_bash|run_python|edit_file", user_message))
            or bool(re.search(r"```(?:python|bash|js|ts|go|rust)", user_message))
            or text_len > 200
        )

        # Danger keywords
        has_danger = any(kw in text for kw in _DANGER_KEYWORDS)

        # Shell commands
        requires_shell = any(kw in text for kw in _SHELL_KEYWORDS)

        # Architecture reasoning
        requires_arch = any(kw in text for kw in _ARCH_KEYWORDS)

        # Multi-step
        requires_multi = any(kw in text for kw in _MULTI_STEP_KEYWORDS)

        # Failure indicator
        has_failure = any(kw in text for kw in _FAILURE_KEYWORDS)

        # Complexity: based on message length + key characteristics
        length_factor = min(text_len / 1000, 1.0)
        complexity_factors = [
            length_factor * 0.4,
            (0.3 if requires_arch else 0.0),
            (0.2 if requires_multi else 0.0),
            (0.1 if requires_tools else 0.0),
        ]
        estimated_complexity = min(sum(complexity_factors), 1.0)

        # Risk: danger + shell + write operations
        risk = 0.0
        if has_danger:
            risk += 0.5
        if requires_shell:
            risk += 0.3
        risk += length_factor * 0.2
        estimated_risk = min(risk, 1.0)

        # Token pressure
        token_pressure = min(current_tokens / max(max_tokens, 1), 1.0)

        # Prior failure score
        prior_failure_score = (
            min(
                prior_failures / max(prior_total_turns, 1) * 2,
                1.0,
            )
            if prior_total_turns > 0
            else 0.0
        )

        return TaskSignals(
            user_message_length=text_len,
            estimated_task_complexity=round(estimated_complexity, 2),
            estimated_risk=round(estimated_risk, 2),
            requires_tools=requires_tools,
            requires_file_write=any(kw in text for kw in ["write_file", "edit_file", "patch_file"]),
            requires_shell=requires_shell,
            requires_multi_step=requires_multi,
            requires_architecture_reasoning=requires_arch,
            token_pressure=round(token_pressure, 2),
            prior_failure_score=round(prior_failure_score, 2),
            has_danger_keywords=has_danger,
            has_failure_indicator=has_failure,
        )
