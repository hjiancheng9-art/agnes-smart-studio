"""Model Router — re-exports from core.agent (canonical location).

Backward-compatibility shim.  All routing logic now lives in core.agent.ModelRouter.
"""

from core.agent import ModelRouter, classify_prompt

__all__ = ["ModelRouter", "classify_prompt"]
