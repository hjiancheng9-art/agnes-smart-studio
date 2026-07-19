"""Token budget monitor — warns when conversation approaches context window limit.

Usage in ChatSession:
    from core.token_budget import TokenBudget
    self._budget = TokenBudget(context_window=128000)

    # After each turn
    self._budget.count(self.messages)
    if self._budget.should_warn():
        print(self._budget.warning())
"""

from __future__ import annotations

import re

# Default context window for deepseek-v4 models
DEFAULT_WINDOW = 128000


class TokenBudget:
    """Lightweight token estimator. Character-based heuristic:
    1 token ≈ 4 chars (English) or 1.5 chars (CJK).
    """

    def __init__(self, context_window: int = DEFAULT_WINDOW, warn_at: float = 0.8):
        self.context_window = context_window
        self.warn_at = warn_at
        self._current: int = 0
        self._turns: int = 0

    def estimate(self, text: str) -> int:
        """Estimate token count from text. Heuristic: 4 chars/token, 1.5 for CJK."""
        if not text:
            return 0
        cjk = len(re.findall(r"[一-鿿㐀-䶿]", text))
        other = len(text) - cjk
        return max(1, int(cjk / 1.5 + other / 4))

    def count(self, messages: list[dict]) -> int:
        """Count total tokens in a list of messages. Updates internal counter."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.estimate(part["text"])
        self._current = total
        return total

    @property
    def usage_pct(self) -> float:
        return self._current / self.context_window if self.context_window > 0 else 0

    @property
    def remaining(self) -> int:
        return max(0, self.context_window - self._current)

    def should_warn(self) -> bool:
        return self.usage_pct >= self.warn_at

    def should_compress(self) -> bool:
        return self.usage_pct >= 0.9

    def warning(self) -> str:
        """Generate a user-visible warning string."""
        pct = int(self.usage_pct * 100)
        return (
            f"\n  Context: {pct}% used ({self._current:,}/{self.context_window:,} tokens).\n"
            f"  Tip: use /compress to summarize, or /clear to reset.\n"
        )

    def system_prompt_footer(self) -> str:
        """Generate a system prompt footer warning the LLM to be concise."""
        if self.should_compress():
            return (
                f"[CRITICAL: Context window {int(self.usage_pct * 100)}% full ({self.remaining:,} tokens remaining). "
                f"Respond as concisely as possible. Do not generate long code or explanations.]"
            )
        if self.should_warn():
            return (
                f"[Note: Context window {int(self.usage_pct * 100)}% used. "
                f"Consider summarizing the conversation with /compress.]"
            )
        return ""
