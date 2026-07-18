"""CRUX Studio v6.1 core — 265 modules organized into 7 logical namespaces.

Layered structure (all modules remain flat in core/; namespaces are for discovery):

    core/tools/          — 34  tool system (registry, routing, infra tools)
    core/provider/       — 17  API clients, streaming, model routing
    core/chat/           — 19  conversation engine, session, prompts
    core/agents/         — 11  single + multi-agent orchestration
    core/orchestration/  — 20  task planning, execution, pipelines
    core/intel/          —  9  LSP, semantic search, knowledge graph
    core/self_heal/      — 16  self-audit, healing, rollback, recovery

    core/                — 139  cross-cutting: config, events, skills,
                               marketplace, hooks, security, etc.

Import paths are unchanged — use flat imports as before:

    from core.chat import ChatSession
    from core.tool_router import get_tool_router

To explore a namespace, import the sub-package and read its __all__:

    import core.tools; print(core.tools.__all__)
"""
