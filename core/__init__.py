"""CRUX Studio v6.1 core — 265 modules, 7 layered packages (mod_*), 0 file moves.

    from core.chat import ChatSession        # flat (always works)
    from core.mod_chat import ChatSession    # layered (recommended)

=================================================================
Layered packages (thin re-export wrappers, no file moves):
=================================================================

    core.mod_tools/          — 43  tool registry, routing, browser, infra tools
    core.mod_provider/       — 18  API clients, streaming, model routing
    core.mod_chat/           — 26  conversation engine, session, skills
    core.mod_agents/         — 13  single + multi-agent orchestration
    core.mod_orchestration/  — 21  task planning, execution, pipelines
    core.mod_self_heal/      — 18  self-audit, healing, rollback, recovery
    core.mod_intel/          —  9  LSP, semantic search, knowledge graph

See core/MODULES.md for full 265-module index.
"""
