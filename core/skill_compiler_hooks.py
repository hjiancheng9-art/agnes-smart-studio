"""Phase 5: Skill/Prompt Compiler — ChatSession integration hooks.

Replaces _build_system_prompt with a compiled version that:
1. Uses the PromptCompiler to dynamically assemble skills
2. Injects context memory from Phase 3
3. Respects token budgets
"""

from __future__ import annotations

import logging
import types

logger = logging.getLogger(__name__)


def inject_skill_compiler_hooks(session):
    """Add Phase 5 skill/prompt compiler hooks to a ChatSession instance.

    Injection is per-session — each ChatSession gets its own compiler hook.
    """
    # Per-session guard: skip if this session already has compiler hooks
    if getattr(session, "_skill_compiler_hooked", False):
        return

    tvl = getattr(session, "tvl", None)
    if tvl is None:
        logger.warning("No tvl found, cannot inject skill compiler hooks")
        return

    # Store original _build_system_prompt (may already be replaced by Phase 3)
    original = getattr(session, "_orig_build_system_prompt", None)
    if original is None:
        original = session._build_system_prompt

    if not hasattr(session, "_phase3_build_system_prompt"):
        session._orig_build_system_prompt = original

        def _build_system_prompt_with_compiler(self):
            """Enhanced: use PromptCompiler to assemble system prompt."""
            base = self._orig_build_system_prompt()
            tvl = getattr(self, "tvl", None)
            if tvl is None:
                return base

            try:
                # Get current context memory
                messages = getattr(self, "messages", [])
                total_chars = sum(len(str(m.get("content", ""))) for m in messages)
                current_tokens = total_chars // 4

                # Get context from memory tier
                ctx = tvl.compile_context(current_tokens=current_tokens)
                context_memory = ctx.assemble() if ctx.has_content else ""

                # Determine task target from first user message
                task_target = "general"
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        content = str(msg.get("content", ""))[:500].lower()
                        # Simple heuristic target detection
                        if any(
                            kw in content
                            for kw in [
                                "render",
                                "generate",
                                "image",
                                "video",
                                "picture",
                                "draw",
                                "create",
                                "生图",
                                "画",
                            ]
                        ):
                            task_target = "media"
                        elif any(
                            kw in content
                            for kw in [
                                "code",
                                "function",
                                "class",
                                "def ",
                                "implement",
                                "fix",
                                "debug",
                                "refactor",
                                "写代码",
                            ]
                        ):
                            task_target = "code"
                        break

                # Get active skills
                active_skills = list(getattr(self, "_loaded_skills", set()))

                # Compile via PromptCompiler
                token_budget = 32000  # conservative
                return tvl.compile_prompt(
                    task_target=task_target,
                    active_skills=active_skills,
                    context_memory=context_memory,
                    token_budget=token_budget,
                    existing_prompt=base,
                )
            except Exception as e:
                logger.debug(f"Prompt compiler failed: {e}")
                return base

        # Only replace if Phase 3 hasn't already overridden
        if (
            hasattr(session, "_orig_build_system_prompt")
            and getattr(session, "_build_system_prompt", None) is not session._orig_build_system_prompt
        ):
            # Phase 3 already replaced it; we chain through
            # Store the phase 3 version as original
            pass
        else:
            session._build_system_prompt = types.MethodType(_build_system_prompt_with_compiler, session)

    session._skill_compiler_hooked = True
    logger.debug("Phase 5 skill compiler hooks injected for session %s", id(session))


def print_skill_report(session) -> str:
    """Print a report of all compiled skills."""
    tvl = getattr(session, "tvl", None)
    if tvl and hasattr(tvl, "skill_report"):
        return tvl.skill_report
    return "Skill compiler not available"
