"""Phase 4: Reviewer Agent — ChatSession integration hooks.

Hooks into post-turn reflection to inject reviewer/debate checks.
Monkey-patches _trigger_reflection to add reviewer agent review.
"""

from __future__ import annotations

import logging
import types

logger = logging.getLogger(__name__)

_REVIEWER_HOOK_INJECTED = False


def inject_reviewer_hooks(session):
    """Add Phase 4 reviewer agent hooks to a ChatSession instance."""
    global _REVIEWER_HOOK_INJECTED
    if _REVIEWER_HOOK_INJECTED:
        return

    tvl = getattr(session, "tvl", None)
    if tvl is None:
        logger.warning("No tvl found, cannot inject reviewer hooks")
        return

    # Store original _trigger_reflection
    if not hasattr(session, "_orig_trigger_reflection"):
        session._orig_trigger_reflection = session._trigger_reflection

        def _trigger_reflection_with_review(self):
            """Enhanced reflection: run existing reflection + reviewer check."""
            # Run original reflection first
            result = self._orig_trigger_reflection()

            # Then run reviewer agent check
            try:
                tvl = getattr(self, "tvl", None)
                if tvl is None:
                    return result

                # Get the last user message and assistant response
                messages = getattr(self, "messages", [])
                if len(messages) < 2:
                    return result

                # Find last user turn and last assistant turn
                last_user = ""
                last_assistant = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user" and not last_user:
                        last_user = str(msg.get("content", ""))[:2000]
                    if msg.get("role") == "assistant" and not last_assistant:
                        content = str(msg.get("content", ""))
                        # Skip if it only contains tool_calls (no text)
                        if "<invoke" not in content[:200]:
                            last_assistant = content[:3000]

                if not last_user or not last_assistant:
                    return result

                # Get tool history
                tool_history = getattr(tvl, "_tool_history", [])

                # Run review
                report = tvl.review_turn(last_user, last_assistant, tool_history)
                if not report.passed and report.issues:
                    logger.info(f"Reviewer: {len(report.issues)} issues, score={report.score}")
                    # If critical issues, inject warning into messages.
                    # Replace any prior reviewer warning so at most one is kept —
                    # previously these accumulated one per turn and were never cleaned.
                    if report.has_critical:
                        warning = report.to_llm_prompt()
                        warning_marker = "[Reviewer Warning]"
                        self.messages = [
                            m for m in self.messages
                            if not (m.get("role") == "system"
                                    and str(m.get("content", "")).startswith(warning_marker))
                        ]
                        self.messages.append({
                            "role": "system",
                            "content": f"{warning_marker}\n{warning[:500]}",
                        })
                        # Set a flag for the UI to show
                        self._last_review_warning = warning[:200]

            except Exception as e:
                logger.debug(f"Reviewer check failed: {e}")

            return result

        session._trigger_reflection = types.MethodType(_trigger_reflection_with_review, session)

    _REVIEWER_HOOK_INJECTED = True
    logger.info("Phase 4 reviewer hooks injected")


def inject_llm_callback(session, callback):
    """Set the LLM callback for reviewer/debate/decompose agents."""
    tvl = getattr(session, "tvl", None)
    if tvl:
        tvl.set_llm_callback(callback)
