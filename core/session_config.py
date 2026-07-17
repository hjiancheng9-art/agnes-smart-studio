"""SessionConfig — session-level mode flags and configuration.

Extracted from ChatSession per GPT v6.2 plan.
ChatSession should only hold runtime state, not configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionConfig:
    """Mutable session configuration — modes, flags, budget settings."""

    model: str = ""
    auto_model: bool = True
    vision_model: str = ""
    enable_thinking: bool = True
    code_mode: bool = False
    mode: str = "chat"
    unlimited_tools: bool = False
    agent_mode: bool = False
    browser_enabled: bool = False
    notebook_enabled: bool = False
    audio_enabled: bool = False

    # Tier preferences
    auto_tier_order: list[str] = field(default_factory=lambda: ["reasoner", "pro", "light"])
    consecutive_skips: int = 0

    # Intelligence analysis (set per-turn by _auto_route)
    intel_mode: str = "BALANCED"
    intel_analysis: dict = field(default_factory=dict)
    intel_config: dict = field(default_factory=dict)

    def reset_skips(self) -> None:
        self.consecutive_skips = 0

    def set_deep(self) -> None:
        self.enable_thinking = True

    def set_fast(self) -> None:
        self.enable_thinking = False
