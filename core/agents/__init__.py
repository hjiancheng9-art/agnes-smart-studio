"""Agent & multi-agent system (11 modules).

Implements agent lifecycle, multi-agent orchestration, and swarm execution.
"""

__all__ = [
    # Single agent
    "agent",  # Agent — core agent class
    "agent_cache",  # agent result caching
    "agent_loader",  # load agents from .agent.md files
    "critic_agent",  # critic agent for self-review
    "reviewer_agent",  # reviewer agent for code review
    "cognitive_orchestrator",  # cognitive task decomposition
    # Multi-agent
    "multi_agent",  # multi-agent core — launch and coordinate
    "multi_agent_decompose",  # task decomposition for multi-agent
    "multi_agent_models",  # data models for multi-agent
    "multi_agent_modes",  # execution modes (plan_execute, review_pair, etc.)
    "multi_agent_swarm",  # agent_swarm — parallel fan-out execution
]
