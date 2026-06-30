def spawn_subagent(client, task: str, model: str = "", task_type: str = "search") -> str:
    """Spawn a sub-agent with a real tool-calling loop.

    Args:
        client: CruxClient instance
        task: Task description for the sub-agent
        model: Explicit model ID (empty = auto-route by task_type)
        task_type: Task type for auto-routing ("search"/"read_file"/"code"/"planning" etc.)
                   Default "search" since most sub-agents do exploration.
    """
    from core.tools import get_registry

    tools = get_registry()
    if model:
        agent = SubAgent(client, tools=tools, model=model)
    else:
        agent = SubAgent(client, tools=tools, tier="auto", task_type=task_type)
    return agent.run(task)


COMPRESS_PROMPT = """Summarize the following conversation, preserving:
- User's requirements and preferences
- Completed steps and results
- Important decisions and corrections
- Pending items

Output a concise summary (max 300 words):"""

