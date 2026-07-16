"""RoutingState — session-scoped provider/model selection.

Extracted from ProviderManager global mutable state (God Object refactoring, Phase 2).
Each session owns its RoutingState; sessions do not interfere with each other.

Integrates with:
- ChatSession (owner)
- TurnOrchestrator (consumer)
- ProviderManager.create_client() (reads provider/model from here)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutingState:
    """Per-session provider and model selection. Owned by ChatSession."""

    active_provider: str = "deepseek"
    active_model: str = ""
    pinned: bool = False
    fallback_count: int = 0

    # Cost/quality guardrails
    max_cost_tier: str = "balanced"  # save | balanced | premium
    allow_cross_provider_fallback: bool = False  # default: no silent cross-provider switch

    def select(self, provider: str, model: str, *, pin: bool = False) -> None:
        """Set active provider and model for this session."""
        if not provider or not isinstance(provider, str):
            raise ValueError(f"Invalid provider: {provider!r}")
        if not model or not isinstance(model, str):
            raise ValueError(f"Invalid model: {model!r}")
        self.active_provider = provider
        self.active_model = model
        if pin:
            self.pinned = True

    def record_fallback(self) -> None:
        """Called when a same-provider fallback occurs."""
        self.fallback_count += 1

    def can_fallback(self, to_provider: str) -> bool:
        """Check if cross-provider fallback is allowed."""
        if to_provider == self.active_provider:
            return True  # same-provider always OK
        return self.allow_cross_provider_fallback
