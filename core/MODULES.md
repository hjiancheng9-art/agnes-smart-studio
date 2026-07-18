# CRUX Core Modules — Layered Index

**265 modules organized into 12 logical layers.** All files live flat in `core/`.  
This document is the navigation map — use it to find modules by function.

---

## TOOLS (43 modules)
Tool registry, routing, browser automation, file/code tools, infrastructure integrations.

| File | Description |
|---|---|
| `tools.py` | Main tool registry (ToolRegistry) |
| `tools_defs.py` | Tool schema definitions (OpenAI format) |
| `tool_router.py` | Unified internal + MCP tool routing |
| `tool_registry_mesh.py` | TRM — multi-source tool index |
| `tool_interceptor.py` | Pre/post call hooks and validation |
| `tool_scorecard.py` | Tool quality scoring and ranking |
| `tool_cache.py` | Tool result LRU caching |
| `tool_call_parser.py` | Parse and validate tool call JSON |
| `tool_call_validator.py` | Validate tool call before execution |
| `tool_call_log.py` | Structured logging of all tool calls |
| `tool_executor.py` | Async tool execution engine |
| `tool_outcome.py` | Structured tool outcome records |
| `tool_result.py` | Tool result normalization |
| `tool_specs.py` | Tool parameter specs and schemas |
| `tool_validation_integration.py` | Integration tests for validation |
| `browser_tools.py` | Browser automation (Playwright) |
| `browser_control.py` | Browser control for AI websites |
| `browser_control_cli.py` | CLI interface for browser control |
| `browser_runtime.py` | Browser runtime management |
| `cdp_browser.py` | Chrome DevTools Protocol browser |
| `pw_tools.py` | Playwright worker tools |
| `pw_worker.py` | Playwright worker process |
| `codex_tools.py` | Codex agent bridge tools |
| `codex_engines.py` | Codex engine backends |
| `context_tools.py` | Context window management |
| `file_tools.py` | File read/write/edit |
| `format_tools.py` | Code formatting |
| `git_tools.py` | Git operations |
| `github_tools.py` | GitHub API/PR/issues |
| `image_tools.py` | Image generation and manipulation |
| `audio_tools.py` | Speech-to-text and TTS |
| `notebook.py` | Jupyter notebook tools |
| `pytest_runner.py` | Test execution |
| `pipeline_tools.py` | Pipeline tools (create_project, etc.) |
| `clipboard_tools.py` | Cross-platform clipboard read/write |
| `notification_tools.py` | Desktop notifications |
| `fs_watcher.py` | Polling-based directory monitoring |
| `package_tools.py` | pip/npm package management |
| `redis_tools.py` | Redis command execution |
| `sql_tools.py` | SQLite/MySQL/PostgreSQL query |
| `ssh_tools.py` | SSH remote execution and file transfer |
| `webhook_server.py` | Local HTTP webhook listener |
| `ws_server.py` | WebSocket broadcast server |

## PROVIDER (18 modules)
API clients, streaming, model routing, and fallback chains.

| File | Description |
|---|---|
| `provider.py` | Provider manager — load, switch, create clients |
| `provider_adapter.py` | Adapter layer for provider API differences |
| `provider_history.py` | Track provider switching for analytics |
| `provider_policy.py` | Policy-driven provider selection |
| `client.py` | Synchronous CruxClient (HTTP + SSE streaming) |
| `async_client.py` | Async CruxClient (aiohttp) |
| `async_runtime.py` | Async runtime helpers |
| `async_render.py` | Async rendering helpers |
| `stream_adapter.py` | Unified stream consumption/transformation |
| `stream_protocol.py` | Stream event type contracts |
| `streaming_executor.py` | Tool execution during streaming |
| `model_router.py` | Tier-based model selection (light/pro/heavy) |
| `model_worker.py` | Worker pool for model inference |
| `routing_service.py` | Fallback chain builder and routing decisions |
| `routing_signals.py` | Signals that influence routing |
| `routing_state.py` | Persistent routing state |
| `router.py` | Unified router (commands + NL classification) |
| `router_replay.py` | Replay router decisions for debugging |

## CHAT (26 modules)
Conversation engine, system prompts, session management, skills, cost tracking.

| File | Description |
|---|---|
| `chat.py` | ChatSession — the main conversation engine |
| `chat_prompt.py` | System prompt builder |
| `chat_routing.py` | Routing decisions during chat |
| `chat_model_helpers.py` | Model-specific prompt adjustment |
| `chat_toggle_mixin.py` | Feature toggle support (code_mode, agent_mode) |
| `chat_tool_dispatch.py` | Tool call dispatch during chat |
| `chat_tool_helpers.py` | Tool helper functions |
| `chat_vision.py` | Vision model integration |
| `chat_history.py` | Conversation history management |
| `chat_hooks_setup.py` | Hook registration for chat lifecycle |
| `session_config.py` | SessionConfig — extracted session state |
| `session_lifecycle.py` | Session creation, activation, teardown |
| `session_mgr.py` | Multi-session management |
| `session_tracker.py` | Session activity tracking |
| `session_wire.py` | Session wiring/injection |
| `gpt_tool_result.py` | GPT/OpenAI tool result handling |
| `cost_tracker.py` | Token cost tracking and budgeting |
| `context_memory.py` | Conversation context memory |
| `context_memory_hooks.py` | Hook integration for context memory |
| `skills.py` | SkillManager — skill lifecycle |
| `skill_compiler.py` | Compile skill definitions |
| `skill_compiler_hooks.py` | Hook integration for skill compilation |
| `skill_loader.py` | Dynamic skill loading |
| `skill_manifest.py` | Skill manifest parsing |
| `skill_recommender.py` | Skill recommendation engine |
| `marketplace.py` | Skill marketplace (search, install, discover) |

## AGENTS (13 modules)
Single agent lifecycle + multi-agent orchestration + specialized agents.

| File | Description |
|---|---|
| `agent.py` | Agent — core agent class |
| `agent_cache.py` | Agent result caching |
| `agent_loader.py` | Load agents from .agent.md files |
| `multi_agent.py` | Multi-agent core — launch and coordinate |
| `multi_agent_decompose.py` | Task decomposition for multi-agent |
| `multi_agent_models.py` | Data models for multi-agent |
| `multi_agent_modes.py` | Execution modes (plan_execute, review_pair, etc.) |
| `multi_agent_swarm.py` | agent_swarm — parallel fan-out execution |
| `critic_agent.py` | Critic agent for self-review |
| `reviewer_agent.py` | Reviewer agent for code review |
| `cognitive_orchestrator.py` | Cognitive task decomposition |
| `showrunner.py` | Showrunner agent for creative pipelines |
| `showrunner_pipeline.py` | Showrunner pipeline execution |

## ORCHESTRATION (21 modules)
Task planning, execution, pipelines, goal management.

| File | Description |
|---|---|
| `runtime_orchestrator.py` | RuntimeOrchestrator — main execution engine |
| `runtime_types.py` | ExecutionPlan, ExecutionMode, TaskComplexity |
| `runtime_result.py` | Runtime result types |
| `runtime_guard.py` | Sandbox and safety guard |
| `runtime_inspect.py` | Runtime introspection |
| `orchestra.py` | Orchestration presets and launchers |
| `orchestration.py` | Low-level orchestration primitives |
| `execution_policy.py` | choose_policy() — task classification |
| `executor.py` | Executor core |
| `executor_models.py` | Executor data models |
| `plan_executor.py` | Multi-step plan execution |
| `plan_mode.py` | Plan mode workflow |
| `deliberate_workflow.py` | Deliberate execution workflow |
| `task_manager.py` | Task lifecycle management |
| `task_complexity.py` | Task complexity estimation |
| `task_governor.py` | Task budget and rate limiting |
| `task_spec_builder.py` | Build task specs from user intent |
| `pipeline_dag.py` | DAG-based pipeline execution |
| `pipeline_state.py` | Pipeline state persistence |
| `goal_manager.py` | Goal lifecycle management |
| `goal_evaluator.py` | Goal completion evaluation |

## SELF_HEAL (18 modules)
Self-audit, auto-fix, incident response, rollback, failure learning.

| File | Description |
|---|---|
| `self_audit.py` | Comprehensive self-audit |
| `self_heal.py` | Self-healing engine |
| `self_evolve.py` | Self-improvement and learning |
| `self_tool.py` | Self-inspection tools |
| `incident_classifier.py` | Classify incidents by severity |
| `incident_playbook.py` | Incident response playbooks |
| `incident_store.py` | Persistent incident tracking |
| `remediation_executor.py` | Execute remediation plans |
| `reflection.py` | Reflection on past actions |
| `reflection_loop.py` | Continuous reflection cycle |
| `failure_learning.py` | Learn from failures |
| `rollback_manager.py` | Manage rollback operations |
| `rollback_engine.py` | Rollback execution engine |
| `rollback_orchestrator.py` | Orchestrate multi-step rollback |
| `recovery.py` | Recovery procedures |
| `crash_guard.py` | Crash protection guard |
| `fake_fix_detector.py` | Detect fake fixes |
| `fixability_estimator.py` | Estimate fix difficulty |

## INTEL (9 modules)
Code intelligence: LSP, semantic search, knowledge graphs, repo understanding.

| File | Description |
|---|---|
| `code_intel.py` | Code intelligence core |
| `lsp.py` | Language Server Protocol client |
| `repo_map.py` | Generate repo structure maps |
| `repo_understanding.py` | Deep codebase comprehension |
| `repo_wiki.py` | Project knowledge wiki |
| `semantic_memory.py` | Semantic embedding and retrieval |
| `awareness_graph.py` | Context awareness graph |
| `memory_bridge.py` | Bridge between memory systems |
| `rag.py` | Retrieval-augmented generation |

## CREATIVE (20 modules)
Creative/media generation: image, video, aesthetics, theming.

| File | Description |
|---|---|
| `brain.py` | Central creative brain |
| `brain_aesthetics.py` | Aesthetics analysis |
| `brain_combat.py` | Combat/challenge generation |
| `brain_creative.py` | Creative generation orchestration |
| `brain_vision.py` | Vision analysis |
| `beast_wiring.py` | Seven beasts wiring |
| `seven_beasts_fusion.py` | Seven beasts fusion engine |
| `agnes_models.py` | Agnes model definitions |
| `agnes_multimodal.py` | Agnes multimodal integration |
| `comfyflow_client.py` | ComfyFlow client for image generation |
| `aria2_bridge.py` | Aria2 download bridge |
| `artifact_activation.py` | Artifact activation |
| `artifact_pipeline.py` | Artifact pipeline |
| `field_arena.py` | Field/arena generation |
| `golden_finger.py` | Golden finger creative tool |
| `image_compare.py` | Image comparison |
| `skin.py` | UI skinning |
| `theme.py` | UI theming |
| `sound_ux.py` | Sound UX |
| `vision_context.py` | Vision context management |

## MCP (4 modules)
Model Context Protocol bridges.

| File | Description |
|---|---|
| `mcp_client.py` | MCP client — connect to MCP servers |
| `mcp_server.py` | MCP server implementation |
| `mcp_context.py` | MCP context management |
| `claude_mcp_bridge.py` | Claude MCP bridge |

## QA (14 modules)
Code review, CI pipeline, diff review, pre-commit, patch/repair.

| File | Description |
|---|---|
| `code_review.py` | Code review engine |
| `diff_review.py` | Diff-based review |
| `diff_context.py` | Diff context extraction |
| `ci_pipeline.py` | CI pipeline execution |
| `pre_commit.py` | Pre-commit quality gates |
| `confirm_manager.py` | Confirmation dialog manager |
| `confirm_checkpoint.py` | Confirmation checkpoints |
| `evidence_gate.py` | Evidence-based gating |
| `quality_gate.py` | Quality gate engine |
| `pr_description.py` | PR description generation |
| `edit_pipeline.py` | Edit pipeline |
| `patch.py` | Patch application |
| `run_replay.py` | Run replay for debugging |
| `run_summary.py` | Run summary generation |

## INFRA (44 modules)
Cross-cutting: config, events, hooks, security, telemetry, daemons, registry.

| File | Description |
|---|---|
| `config.py` | Application configuration |
| `bootstrap.py` | Application bootstrap |
| `startup_checks.py` | Startup health checks |
| `settings_watcher.py` | Watch config files for changes |
| `toml_config.py` | TOML config parser |
| `version.py` | Version module (single source of truth) |
| `commands.py` | Slash command registry |
| `cli_handlers.py` | CLI command handlers |
| `capability.py` | Capability definitions |
| `capability_registry.py` | Capability registry |
| `hooks.py` | Hook system |
| `intelligence_hook.py` | Intelligence hook |
| `reviewer_hooks.py` | Reviewer hooks |
| `event_bus.py` | Event bus |
| `event_log.py` | Event log |
| `event_log_bridge.py` | Event log bridge |
| `event_system.py` | Event system |
| `permission.py` | Permission management |
| `rules.py` | Rules engine |
| `policy_gate.py` | Policy gating |
| `policy_memory.py` | Policy memory |
| `policy_regression.py` | Policy regression testing |
| `constraints.py` | Execution constraints |
| `validation_errors.py` | Validation error types |
| `validator.py` | Input validation |
| `defense.py` | Defense/security layer |
| `sandbox.py` | Sandbox execution |
| `secret_redactor.py` | Secret redaction |
| `observability.py` | Observability core |
| `crux_telemetry.py` | CRUX telemetry |
| `evaluation.py` | Evaluation engine |
| `eval_harness.py` | Eval harness |
| `trends.py` | Trend analysis |
| `learning_store.py` | Learning data storage |
| `background.py` | Background task manager |
| `cron.py` | Cron scheduler |
| `daemon.py` | Daemon management |
| `watchdog.py` | Watchdog monitor |
| `cleanup_manager.py` | Cleanup manager |
| `tidy_up.py` | Tidy up utilities |
| `export.py` | Data export |
| `scheduler.py` | Task scheduler |
| `encoding.py` | Encoding utilities |
| `encoding_fix.py` | Encoding fix utilities |

## UNSORTED (34 modules)
Cross-cutting utilities that don't fit neatly into one layer.

| File | Likely Layer |
|---|---|
| `adaptive_learner.py` | SELF_HEAL |
| `adr_engine.py` | INTEL |
| `adversarial_bypass.py` | SELF_HEAL |
| `audit_runner.py` | SELF_HEAL |
| `cancellation.py` | ORCHESTRATION |
| `control_plane.py` | ORCHESTRATION |
| `docs_engine.py` | QA |
| `error_sink.py` | INFRA |
| `exceptions.py` | INFRA |
| `fake_fix_seed_policy.py` | SELF_HEAL |
| `fast_scanner.py` | QA |
| `feedback_loop.py` | SELF_HEAL |
| `git_workflow.py` | TOOLS |
| `growth_engine.py` | INFRA |
| `intelligence_eval.py` | INTEL |
| `intelligence_policy.py` | INTEL |
| `intelligence_trace.py` | INTEL |
| `methodology.py` | INFRA |
| `onboarding.py` | INFRA |
| `plugin_system.py` | INFRA |
| `project.py` | INFRA |
| `prompt_bypass.py` | CHAT |
| `prompt_lab.py` | CHAT |
| `protocol.py` | PROVIDER |
| `quest_engine.py` | ORCHESTRATION |
| `resilience.py` | SELF_HEAL |
| `resource_budget.py` | INFRA |
| `result_validator.py` | QA |
| `retro_engine.py` | QA |
| `retry_budget.py` | INFRA |
| `tdd_workflow.py` | QA |
| `trace_debugger.py` | QA |
| `workbuddy.py` | INFRA |
| `workspace_guard.py` | INFRA |
