# core/intelligence/router.py
"""IntelligencePolicyRouter — routes user tasks to the optimal ExecutionPolicy."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.intelligence.profiles import load_profile
from core.intelligence.signals import SignalExtractor, TaskSignals

if TYPE_CHECKING:
    from core.intelligence.policy import ExecutionPolicy

logger = logging.getLogger(__name__)


class IntelligencePolicyRouter:
    """Routes tasks to the optimal execution policy based on task signals.

    The routing logic uses a priority chain:
    SAFE (high risk) > DEBUG (high prior failure) > DEEP (high complexity) > FAST (simple) > BALANCED (default)
    """

    def __init__(self):
        self.extractor = SignalExtractor()
        self._last_policy: ExecutionPolicy | None = None
        self._last_signals: TaskSignals | None = None

    def route(
        self,
        user_message: str,
        message_history: list[dict] | None = None,
        prior_failures: int = 0,
        prior_total_turns: int = 0,
        current_tokens: int = 0,
        max_tokens: int = 64000,
        force_mode: str | None = None,
    ) -> ExecutionPolicy:
        """Determine the optimal execution policy for a user message.

        Args:
            user_message: The current user input.
            message_history: Previous conversation turns.
            prior_failures: Number of failed tool calls in this session.
            prior_total_turns: Total tool call turns in this session.
            current_tokens: Estimated current token usage.
            max_tokens: Token budget limit.
            force_mode: If set, bypass routing and use this mode directly.

        Returns:
            An ExecutionPolicy appropriate for this task.
        """
        # Force mode bypass
        if force_mode is not None and force_mode in ("fast", "balanced", "deep", "safe", "debug"):
            self._last_policy = load_profile(force_mode)
            self._last_signals = None
            return self._last_policy

        # Extract signals
        signals = self.extractor.extract(
            user_message=user_message,
            message_history=message_history,
            prior_failures=prior_failures,
            prior_total_turns=prior_total_turns,
            current_tokens=current_tokens,
            max_tokens=max_tokens,
        )
        self._last_signals = signals

        # Routing decision chain (highest priority first)
        policy = self._decide(signals)
        self._last_policy = policy

        logger.debug(
            "Policy route: mode=%s complexity=%.2f risk=%.2f tools=%s danger=%s fail=%s",
            policy.mode.value,
            signals.estimated_task_complexity,
            signals.estimated_risk,
            signals.requires_tools,
            signals.has_danger_keywords,
            signals.has_failure_indicator,
        )
        return policy

    def _decide(self, s: TaskSignals) -> ExecutionPolicy:
        """Core routing decision logic."""
        # SAFE: high-risk operations
        if s.estimated_risk >= 0.5:
            return load_profile("safe")

        # DEBUG: prior failures or failure keywords
        if s.prior_failure_score >= 0.4 or s.has_failure_indicator:
            return load_profile("debug")

        # DEEP: complex engineering or architecture tasks
        if s.estimated_task_complexity >= 0.5 or s.requires_architecture_reasoning or s.requires_multi_step:
            return load_profile("deep")

        # FAST: simple, no tools needed
        if not s.requires_tools and s.estimated_task_complexity < 0.25:
            return load_profile("fast")

        # Default: BALANCED
        return load_profile("balanced")

    @property
    def last_policy(self) -> ExecutionPolicy | None:
        return self._last_policy

    @property
    def last_signals(self) -> TaskSignals | None:
        return self._last_signals

    def explain_last(self) -> str:
        """Explain the last routing decision."""
        if self._last_policy is None:
            return "No routing decision made yet"
        lines = [f"📋 Routing Decision: {self._last_policy.mode.value.upper()}"]
        if self._last_signals:
            sig = self._last_signals
            lines.append(f"   Complexity: {sig.estimated_task_complexity:.2f}")
            lines.append(f"   Risk: {sig.estimated_risk:.2f}")
            lines.append(f"   Tools: {sig.requires_tools}")
            lines.append(f"   Multi-step: {sig.requires_multi_step}")
            lines.append(f"   Architecture: {sig.requires_architecture_reasoning}")
            lines.append(f"   Danger keywords: {sig.has_danger_keywords}")
            lines.append(f"   Failure indicator: {sig.has_failure_indicator}")
            lines.append(f"   Prior failure score: {sig.prior_failure_score:.2f}")
        lines.append(f"\n{self._last_policy.summary()}")
        return "\n".join(lines)
