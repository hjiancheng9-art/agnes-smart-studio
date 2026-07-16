"""PromptAssembler — builds compact system prompts from PromptPlan fragments.

Replaces the 85K/21K-token static system prompt with layered assembly:
  1. Core prompt (identity + safety, ~1K tokens)
  2. Task profile (debug/architecture/research, ~500 tokens)
  3. Selected tools (5-10 tool descriptions, ~1K tokens)
  4. Execution mode instruction (orchestrate/swarm/direct, ~200 tokens)

Target: 3-6K tokens for most tasks (vs current 21K).
"""

from __future__ import annotations

from domain.plans import PromptPlan

# ── Core prompt — always included, minimal identity + protocol ──

CORE_PROMPT = """You are CRUX Studio, an AI coding assistant running in a TUI.

Rules:
- Use tools to read/write files, search code, run commands.
- Report tool results concisely — no guessing, always verify with tools.
- If a task requires multiple stages, use `orchestrate` to plan and execute.
- If a task has independent sub-problems, use `agent_swarm` to parallelize.
- Always respond in Chinese unless the user asks for English.
- NEVER fabricate file contents or command outputs."""

# ── Task profiles ──

PROFILES = {
    "default": "",
    "architecture": "\n[Architecture Mode] Think about system design, module boundaries, and data flow before coding.",
    "debug": "\n[Debug Mode] Find root cause first. Write a failing test before fixing. Cite file:line.",
    "research": "\n[Research Mode] Be thorough. Cite sources. Present multiple options with tradeoffs.",
}


class PromptAssembler:
    """Assembles system prompt from PromptPlan fragments."""

    def build(self, plan: PromptPlan) -> str:
        parts = [CORE_PROMPT]

        # Task profile
        profile = PROFILES.get(plan.task_profile, "")
        if profile:
            parts.append(profile)

        # Tool list
        if plan.tool_names:
            tools = ", ".join(plan.tool_names)
            parts.append(f"\nAvailable tools: {tools}")

        # Mode instruction
        if "orchestrate" in plan.tool_names:
            parts.append(
                "\n[Orchestration] Use `orchestrate` tool for multi-stage tasks. Do NOT manually step through stages."
            )
        if "agent_swarm" in plan.tool_names:
            parts.append("\n[Swarm] Use `agent_swarm` to fan out independent sub-tasks to parallel agents.")

        return "\n".join(parts)
