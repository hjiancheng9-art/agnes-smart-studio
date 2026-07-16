"""Agent runtime loader — parse agent YAML frontmatter and enforce at runtime.

Before this module, agent .agent.md files were documentation-only:
  model / tools / permission / handoffs — all ignored.

Now they're the single source of truth for sub-agent behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


@dataclass
class AgentSpec:
    """Parsed agent specification from .agent.md frontmatter."""

    name: str
    description: str = ""
    model_ids: list[str] = field(default_factory=list)
    tools_whitelist: list[str] = field(default_factory=list)
    tools_blacklist: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
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

    return AgentSpec(
        name=meta.get("name", agent_name),
        description=meta.get("description", ""),
        model_ids=meta.get("model", []) or [],
        tools_whitelist=meta.get("tools", []) or [],
        tools_blacklist=meta.get("disallowedTools", []) or [],
        mcp_servers=meta.get("mcpServers", []) or [],
        permission=meta.get("permission", "read-only"),
        disable_model=meta.get("disable-model-invocation", False),
        handoffs=meta.get("handoffs", []) or [],
    )


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

    # Apply tool blacklist (disallowedTools) — higher priority than whitelist
    if tools is not None and spec.tools_blacklist:
        tools = _exclude_tools(tools, spec.tools_blacklist)

    # Apply MCP server whitelist
    if tools is not None and spec.mcp_servers:
        tools = _filter_mcp_servers(tools, spec.mcp_servers)

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
        "read_file",
        "search_files",
        "glob_files",
        "list_files",
        "web_search",
        "web_fetch",
        "web_read",
        "code_analyze",
        "find_symbol",
        "search_symbols",
        "find_references",
        "graph_neighbors",
        "graph_descendants",
        "graph_ancestors",
        "view_image",
        "count_lines",
    }
    return _filter_tools(tool_registry, list(READONLY_TOOLS))


def _exclude_tools(tool_registry, blacklist: list[str]):
    """Return a tool_registry copy with blacklisted tools removed.

    Blacklist has higher priority than whitelist — if a tool appears in
    both, it is excluded.
    """
    from core.tools import ToolRegistry

    filtered = ToolRegistry()
    blacklist_set = set(blacklist)

    for name, executor in getattr(tool_registry, "_executors", {}).items():
        if name not in blacklist_set:
            filtered._executors[name] = executor

    for name, mod in getattr(tool_registry, "_tool_modules", {}).items():
        if name not in blacklist_set:
            filtered._tool_modules[name] = mod

    for d in getattr(tool_registry, "_definitions", []):
        fn_name = d.get("function", {}).get("name", "")
        if fn_name not in blacklist_set:
            filtered._definitions.append(d)

    return filtered


# ── Auto-dispatch engine ─────────────────────────────────────────────────


def auto_route(task: str) -> str | None:
    """Automatically select the best agent for a task by matching descriptions.

    Scans all agent .agent.md files, tokenizes their descriptions, and
    scores them against the task text. Returns the name of the best match,
    or None if no agent matches above the threshold.

    This enables TRAE-style automatic sub-agent delegation without the
    caller needing to know which agent to use.

    Args:
        task: The user's task description.
    Returns:
        Agent name (e.g. "Debugger"), or None if no good match.
    """
    import os

    best_name = None
    best_match_count = 0

    task_lower = task.lower()

    for agent_file in sorted(os.listdir(AGENTS_DIR)):
        if not agent_file.endswith(".agent.md"):
            continue
        spec = load_agent_spec(agent_file.removesuffix(".agent.md"))
        if spec is None:
            continue

        desc = spec.description.lower()
        if not desc:
            continue

        # Tokenize description into keywords
        desc_clean = desc.replace(",", " ").replace("/", " ").replace("，", " ")
        desc_clean = desc_clean.replace("、", " ").replace("。", " ")
        desc_clean = desc_clean.replace("-", " ")  # Normalize hyphens
        keywords = []
        for w in desc_clean.split():
            w = w.strip("()[]{}'.:!?\"")
            if not w:
                continue
            has_cjk = any("一" <= c <= "鿿" for c in w)
            if (has_cjk and len(w) >= 2) or (not has_cjk and len(w) >= 3):
                keywords.append(w)

        if not keywords:
            continue

        # Normalize task text for matching (hyphens -> spaces)
        task_normalized = task_lower.replace("-", " ")

        # Score: what fraction of description keywords appear in the task?
        # For CJK: also check if individual CJK chars from keyword appear in task
        match_count = 0
        for kw in keywords:
            has_cjk = any("一" <= c <= "鿿" for c in kw)
            if has_cjk:
                cjk_chars = [c for c in kw if "一" <= c <= "鿿"]
                if cjk_chars:
                    char_matches = sum(1 for c in cjk_chars if c in task_normalized)
                    if char_matches / len(cjk_chars) >= 0.5:
                        match_count += 1
            elif kw in task_normalized:
                match_count += 1

        if match_count > best_match_count:
            best_match_count = match_count
            best_name = spec.name

    # Require at least 1 keyword match
    if best_match_count >= 1 and best_name:
        return best_name
    return None


# ── Handoff / chain-of-delegation ────────────────────────────────────────


def chain_run(
    client,
    task: str,
    agent_chain: list[str],
    tools: object | None = None,
) -> str:
    """Run a chain of agents, each receiving the previous agent's output.

    TRAE-style handoff: the first agent runs the task, its result is passed
    as context to the second agent, and so on. Each agent receives the
    previous result prefixed with "[Previous agent output]".

    Args:
        client: CruxClient instance.
        task: The original task description.
        agent_chain: Ordered list of agent names to execute.
        tools: Optional ToolRegistry shared across agents.
    Returns:
        The final agent's result string.
    """
    current_task = task
    final_result = ""

    for i, agent_name in enumerate(agent_chain):
        context = current_task
        if i > 0:
            context = (
                f"Previous agent ({agent_chain[i-1]}) completed. "
                f"Their output:\n---\n{final_result}\n---\n\n"
                f"Your task: {current_task}"
            )

        result = spawn_agent_from_spec(
            client=client,
            task=context,
            agent_name=agent_name,
            tools=tools,
        )
        final_result = result

    return final_result


def _filter_mcp_servers(tool_registry, server_whitelist: list[str]):
    """Return a tool_registry copy keeping only MCP tools from listed servers.

    Non-MCP tools (built-in tools) are kept as-is. Only MCP-prefixed tools
    (``mcp__<server>__<tool>``) are filtered by the whitelist.
    """
    from core.tools import ToolRegistry

    filtered = ToolRegistry()
    allowed = set(server_whitelist)

    for name, executor in getattr(tool_registry, "_executors", {}).items():
        if name.startswith("mcp__"):
            # Extract server name: "mcp__github__get_issue" → "github"
            parts = name.split("__", 2)
            if len(parts) >= 2 and parts[1] not in allowed:
                continue
        filtered._executors[name] = executor

    for name, mod in getattr(tool_registry, "_tool_modules", {}).items():
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            if len(parts) >= 2 and parts[1] not in allowed:
                continue
        filtered._tool_modules[name] = mod

    for d in getattr(tool_registry, "_definitions", []):
        fn_name = d.get("function", {}).get("name", "")
        if fn_name.startswith("mcp__"):
            parts = fn_name.split("__", 2)
            if len(parts) >= 2 and parts[1] not in allowed:
                continue
        filtered._definitions.append(d)

    return filtered
