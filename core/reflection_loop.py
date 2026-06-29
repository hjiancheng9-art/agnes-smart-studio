"""Reflection loop — post-turn lightweight review for output quality.

After each chat turn, a cheap light model reviews the last assistant response
for factual errors, omissions, and better alternatives. If issues are found,
a correction is appended to the conversation history.

Activated by CHAT_TURN_END hook (via register_reflection_hook).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.chat import ChatSession

logger = logging.getLogger("crux.reflection")

REVIEW_PROMPT = """Review this assistant response critically. Answer ONLY in this format:

FACTS: [any factual errors? "none" if clean]
MISSING: [anything the user asked that was not addressed? "none" if complete]
BETTER: [is there a simpler/better approach? "none" if optimal]

User asked: {user}
Assistant said: {assistant}

If everything is fine, reply with just "OK". Otherwise give a 1-2 sentence correction."""


class ReflectionLoop:
    """Post-turn quality reviewer using a lightweight model."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.review_count = 0
        self.correction_count = 0

    def review(self, session: ChatSession) -> None:
        """Review the last assistant response and append correction if needed."""
        if not self.enabled:
            return
        # Get last user message and last assistant response
        msgs = session.messages
        user_msg = ""
        assistant_msg = ""
        for m in reversed(msgs):
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "assistant" and not assistant_msg:
                assistant_msg = str(content)
            elif role == "user" and not user_msg:
                user_msg = str(content)
            if user_msg and assistant_msg:
                break
        if not assistant_msg or len(assistant_msg) < 50:
            return  # too short to review

        # Use a light model for cheap review
        try:
            review_prompt = REVIEW_PROMPT.format(user=user_msg[:500], assistant=assistant_msg[:1500])
            client = session.client
            resp = client.chat(
                "deepseek-v4-flash",
                messages=[{"role": "user", "content": review_prompt}],
                temperature=0.1,
                max_tokens=256,
            )
            review_text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception:
            return  # review failure is silent — don't block the user

        self.review_count += 1

        if not review_text or review_text.strip() == "OK":
            return

        # Found issues — append correction
        correction = f"[🔍 Review] {review_text.strip()[:300]}"
        session.messages.append({"role": "assistant", "content": correction})
        self.correction_count += 1
