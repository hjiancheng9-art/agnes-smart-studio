"""RoutingService — model selection and provider fallback logic.

Extracted from ChatSession._auto_route and _text_fallback_chain
per GPT v6.2 plan.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.client import CruxClient

logger = logging.getLogger("crux.routing")


def build_fallback_chain(
    current_model: str,
    current_client: CruxClient,
) -> list[tuple[str, CruxClient]]:
    """Build fallback chain: [(model, client), ...].

    Order: current → fallback provider → same-provider light model.
    """
    from core.provider import get_provider_manager

    chain: list[tuple[str, CruxClient]] = [(current_model, current_client)]
    try:
        mgr = get_provider_manager()
        # Fallback providers (cross-provider)
        for pid in mgr.fallback_priority:
            if mgr.state.is_down(pid) or not mgr.state.circuit_can_try(pid):
                continue
            provider = mgr.providers.get(pid, {})
            mid = provider.get("models", {}).get("pro")
            if mid and mid != current_model:
                try:
                    fb = mgr.create_client(pid)
                    chain.append((mid, fb))
                except (OSError, RuntimeError):
                    pass
        # Same-provider light model (e.g. pro → flash)
        for _pid, pdata in mgr.providers.items():
            if current_model in pdata.get("models", {}).values():
                light_mid = pdata.get("models", {}).get("light")
                if light_mid and light_mid != current_model:
                    chain.append((light_mid, current_client))
                break
    except (ImportError, OSError, RuntimeError):
        pass
    return chain
