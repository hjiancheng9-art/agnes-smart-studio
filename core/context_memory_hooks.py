"""Phase 3: Context Memory — ChatSession integration hooks.

Injected into chat.py via monkey-patch-safe extension methods.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Sentinels to track if injected
_CONTEXT_HOOK_INJECTED = False


def inject_context_hooks(session):
    """Add Phase 3 context memory methods to a ChatSession instance."""
    global _CONTEXT_HOOK_INJECTED
    if _CONTEXT_HOOK_INJECTED:
        return

    # Check if tvl exists
    tvl = getattr(session, "tvl", None)
    if tvl is None:
        logger.warning("No tvl (ValidationLayer) found, cannot inject context memory")
        return

    # Store original _build_system_prompt
    if not hasattr(session, "_orig_build_system_prompt"):
        session._orig_build_system_prompt = session._build_system_prompt

        # Replace _build_system_prompt with context-enhanced version
        def _build_system_prompt_with_context(self):
            base = self._orig_build_system_prompt()
            tvl = getattr(self, "tvl", None)
            if tvl:
                # Estimate current token usage
                total = sum(len(str(m.get("content", ""))) for m in getattr(self, "messages", []))
                # Inject context memory
                enhanced = tvl.inject_context_into_prompt(
                    base,
                    current_tokens=total // 4,  # rough char->token estimate
                )
                return enhanced
            return base

        # Bind the method
        import types

        session._build_system_prompt = types.MethodType(_build_system_prompt_with_context, session)

    _CONTEXT_HOOK_INJECTED = True
    logger.debug("Phase 3 context memory hooks injected")


def record_turn(session, user_msg: str, assistant_msg: str, tool_calls: list | None = None):
    """Record a conversation turn in context memory."""
    tvl = getattr(session, "tvl", None)
    if tvl:
        try:
            tvl.record_turn(user_msg, assistant_msg, tool_calls)
        except Exception as e:
            logger.debug(f"record_turn failed: {e}")


def track_tool(session, tool_name: str, args: dict, result: str, success: bool):
    """Track a tool call in context memory."""
    tvl = getattr(session, "tvl", None)
    if tvl:
        try:
            tvl.track_tool_use_v2(tool_name, args, result, success)
        except Exception as e:
            logger.debug(f"track_tool failed: {e}")


def set_task(session, task: str):
    """Set current task in working memory."""
    tvl = getattr(session, "tvl", None)
    if tvl:
        try:
            tvl.set_current_task(task)
        except Exception:
            logger.debug("Exception in context_memory_hooks", exc_info=True)
