"""Agent runtime loader — parse agent YAML frontmatter and enforce at runtime.

Before this module, agent .agent.md files were documentation-only:
  model / tools / permission / handoffs — all ignored.

Now they're the single source of truth for sub-agent behavior.
"""

from __future__ import annotations

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent import SubAgent

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


@dataclass
class AgentSpec:
    """Parsed agent specification from .agent.md frontmatter."""
    name: str
    description: str = ""
    model_ids: list[str] = field(default_factory=list)
    tools_whitelist: list[str] = field(default_factory=list)
    permission: str = "read-only"  # read-only | write | elevated
    disable_model: bool = False
    handoffs: list[dict] = field(default_factory=list)


def load_agent_spec(agent_name: str) -> AgentSpec | None:
    """Load agent specification from agents/<name>.agent.md.

    Returns None if the file doesn't exist or can't be parsed.
    """
    agent_file = AGENTS_DIR / f"{agent_name}.agent.md"
    if not agent_file.exists():
        return None

    try:
        content = agent_file.read_text(encoding="utf-8")
    except OSError:
        return None

    # Parse YAML frontmatter
    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    spec = AgentSpec(
        name=meta.get("name", agent_name),
        description=meta.get("description", ""),
        model_ids=meta.get("model", []) or [],
        tools_whitelist=meta.get("tools", []) or [],
        permission=meta.get("permission", "read-only"),
        disable_model=meta.get("disable-model-invocation", False),
        handoffs=meta.get("handoffs", []) or [],
    )

    return spec


def resolve_agent_model(spec: AgentSpec) -> str:
    """Resolve the model for an agent spec.

    Returns empty string if model should be auto-routed via tier/task_type.
    """
    if spec.disable_model:
        return ""

    if spec.model_ids:
        has_auto = "auto" in spec.model_ids
        real_models = [m for m in spec.model_ids if m != "auto"]

        # If "auto" is present: use tier-based routing (empty model = auto)
        if has_auto:
            return ""

        # Explicit model only → use it
        if real_models:
            return real_models[0]

    return ""


def resolve_agent_tier(spec: AgentSpec) -> str:
    """Map agent permission/name to a model tier for routing."""
    if spec.disable_model:
        return ""

    # Read-only agents → light tier (cheap)
    if spec.permission == "read-only":
        return "light"

    # Write agents → pro tier
    if spec.permission == "write":
        return "pro"

    return "pro"


def resolve_agent_task_type(spec: AgentSpec) -> str:
    """Map agent name to a task type for ModelRouter.select()."""
    name_lower = spec.name.lower()

    if "explore" in name_lower or "ask" in name_lower:
        return "search"
    if "plan" in name_lower:
        return "planning"
    if "implement" in name_lower or "backend" in name_lower or "frontend" in name_lower:
        return "code"
    if "test" in name_lower:
        return "code"
    if "refactor" in name_lower:
        return "code"

    return "chat"


def spawn_agent_from_spec(
    client,
    task: str,
    agent_name: str,
    tools: object | None = None,
) -> str:
    """Spawn a sub-agent using its .agent.md specification.

    This is the main entry point — replaces direct SubAgent() calls with
    spec-aware spawning.

    Args:
        client: CruxClient (or None for disable-model agents)
        task: Task description
        agent_name: Name matching agents/<name>.agent.md
        tools: Optional ToolRegistry (filtered by whitelist)

    Returns:
        Agent result string.
    """
    from core.agent import SubAgent

    spec = load_agent_spec(agent_name)
    if spec is None:
        # Fallback: spawn with defaults
        agent = SubAgent(client, tools=tools, tier="auto", task_type="search")
        return agent.run(task)

    # Resolve model
    model = resolve_agent_model(spec)
    tier = resolve_agent_tier(spec)
    task_type = resolve_agent_task_type(spec)

    # Apply tool whitelist if specified
    if tools is not None and spec.tools_whitelist:
        tools = _filter_tools(tools, spec.tools_whitelist)
    elif spec.permission == "read-only" and tools is not None:
        tools = _filter_readonly(tools)

    # Handle disable-model agents
    if spec.disable_model:
        agent = SubAgent(None, tools=tools, model="", tier="", task_type="")
        agent.client = None  # Prevent any API calls
        return agent.run(task)

    # Spawn with spec-aware configuration
    if model:
        agent = SubAgent(client, tools=tools, model=model)
    else:
        agent = SubAgent(client, tools=tools, tier=tier, task_type=task_type)

    return agent.run(task)


def _filter_tools(tool_registry, whitelist: list[str]):
    """Return a copy of tool_registry with only whitelisted tools."""
    try:
        from core.tools import ToolRegistry

        filtered = ToolRegistry()
        for name in whitelist:
            if name in tool_registry._executors:
                filtered._executors[name] = tool_registry._executors[name]
            if name in tool_registry._tool_modules:
                filtered._tool_modules[name] = tool_registry._tool_modules[name]
        # Copy matching definitions
        for d in tool_registry._definitions:
            if d.get("function", {}).get("name") in whitelist:
                filtered._definitions.append(d)
        return filtered
    except Exception:
        return tool_registry  # Fallback: return unfiltered


def _filter_readonly(tool_registry):
    """Return a tool_registry copy with only read-only tools."""
    READONLY_TOOLS = {
        "read_file", "search_files", "glob_files", "list_files",
        "web_search", "web_fetch", "web_read",
        "code_analyze", "find_symbol", "search_symbols", "find_references",
        "graph_neighbors", "graph_descendants", "graph_ancestors",
        "view_image", "count_lines",
    }
    return _filter_tools(tool_registry, list(READONLY_TOOLS))
