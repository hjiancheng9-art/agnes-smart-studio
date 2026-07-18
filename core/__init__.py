"""CRUX Studio v6.1 core — 265 modules organized into logical layers.

All modules live flat in core/. Import paths:

    from core.chat import ChatSession
    from core.tool_router import get_tool_router

─────────────────────────────────────────────────────────────────
Layer map (logical grouping — not subpackage directories):
─────────────────────────────────────────────────────────────────

TOOLS (35 modules): tool_router, tool_registry_mesh, tool_interceptor,
  tool_scorecard, tool_cache, tool_call_parser, tool_call_validator,
  tool_call_log, tool_executor, tool_outcome, tool_result, tool_specs,
  tool_validation_integration, tools, tools_defs, browser_tools,
  codex_tools, context_tools, file_tools, format_tools, git_tools,
  github_tools, image_tools, audio_tools, pw_tools, pytest_runner,
  clipboard_tools, notification_tools, fs_watcher, package_tools,
  redis_tools, sql_tools, ssh_tools, webhook_server, ws_server

PROVIDER (17 modules): provider, provider_adapter, provider_history,
  provider_policy, client, async_client, async_runtime, stream_adapter,
  stream_protocol, streaming_executor, model_router, model_worker,
  routing_service, routing_signals, routing_state, router, router_replay

CHAT (19 modules): chat, chat_prompt, chat_routing, chat_model_helpers,
  chat_toggle_mixin, chat_tool_dispatch, chat_tool_helpers, chat_vision,
  chat_history, chat_hooks_setup, session_config, session_lifecycle,
  session_mgr, session_tracker, session_wire, gpt_tool_result,
  cost_tracker, context_memory, context_memory_hooks

AGENTS (11 modules): agent, agent_cache, agent_loader, critic_agent,
  reviewer_agent, cognitive_orchestrator, multi_agent,
  multi_agent_decompose, multi_agent_models, multi_agent_modes,
  multi_agent_swarm

ORCHESTRATION (20 modules): runtime_orchestrator, runtime_types,
  runtime_result, runtime_guard, runtime_inspect, orchestra, orchestration,
  task_manager, task_complexity, task_governor, task_spec_builder,
  execution_policy, executor, executor_models, plan_executor, plan_mode,
  deliberate_workflow, pipeline_dag, pipeline_tools, pipeline_state

INTEL (9 modules): code_intel, lsp, repo_map, repo_understanding,
  repo_wiki, semantic_memory, awareness_graph, memory_bridge, rag

SELF_HEAL (16 modules): self_audit, self_heal, self_evolve, self_tool,
  incident_classifier, incident_playbook, incident_store,
  remediation_executor, reflection, reflection_loop, failure_learning,
  rollback_manager, rollback_engine, rollback_orchestrator, recovery,
  healing

CROSS-CUTTING (138 modules): config, commands, hooks, marketplace,
  skills, skill_compiler, rules, permission, policy, validation, event_bus,
  cleanup, daemon, watchdog, sandbox, crash_guard, defense, bootstrap,
  startup_checks, observability, crux_telemetry, evaluation, trends,
  encoding, secret_redactor, workflow, export, background, cron, etc.
"""
