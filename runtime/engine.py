"""RuntimeEngine — turn preparation only (prompt enhancement).

The model-flow stage that previously tried to replace _consume_stream_delta
has been removed. RuntimeEngine now only prepares a domain-aware system prompt
for orchestrate/swarm turns. The proven legacy stream loop handles all model I/O.

Opt-in via CRUX_ENABLE_NEW_RUNTIME=1 (default: off, old prompt used).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreparedTurn:
    plan: object  # accepts both old core.runtime_types.ExecutionPlan and new domain.plans.ExecutionPlan
    system_prompt: str
    tool_defs: tuple = ()


class RuntimeEngine:
    """Prepares a turn: plan + prompt + tools. Model flow stays in old send_stream."""

    def __init__(self, planner=None, tool_kernel=None):
        self._planner = planner
        self._tools = tool_kernel

    def prepare_turn(self, old_plan=None):
        """Return PreparedTurn or None if old loop should handle everything."""
        plan = old_plan
        if plan is None or getattr(plan, "mode", "direct") == "direct":
            return None

        # Handle both old (core.runtime_types) and new (domain.plans) plan formats
        tool_names = (
            getattr(plan, "tool_names", ()) or getattr(getattr(plan, "prompt_plan", None), "tool_names", ()) or ()
        )

        # Build short system prompt
        try:
            from domain.plans import PromptPlan
            from prompts.assembler import PromptAssembler

            assembler = PromptAssembler()
            pp = PromptPlan(task_profile="architecture", tool_names=tool_names)
            system_prompt = assembler.build(pp)
        except ImportError:
            system_prompt = ""

        return PreparedTurn(plan=plan, system_prompt=system_prompt, tool_defs=())
