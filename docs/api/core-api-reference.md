# CRUX Studio Core API Reference

> Auto-generated from docstrings. Last updated: 2026-07-20

---

## `core.chat` — Chat Session

### `class ChatSession(ChatToggleMixin)`

Multi-turn chat session maintaining history and hybrid dispatch.

**Constructor:**
```python
ChatSession(
    client: CruxClient,
    default_model: str = "",
    vision_client: CruxClient | None = None,
    vision_model: str = "",
)
```

**Key Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `model` | `str` | Active model ID (delegates to `SessionConfig`) |
| `code_mode` | `bool` | Code-optimized mode toggle |
| `agent_mode` | `AgentMode` | Agent operation mode |
| `browser_enabled` | `bool` | Browser tools toggle |
| `supports_tools` | `bool` | Whether current model supports tool calling |
| `brain` | `SmartBrain` | Lazy-loaded creative generation brain |
| `ctx_mgr` | `ContextManager` | Lazy-loaded context window manager |

**Key Methods:**

```python
send_stream(user_text: str, image_url: str | None = None) -> Generator
```
Core entry point. Streams `(kind, payload)` tuples:
- `("text", str)` — text increment
- `("info", str)` — intermediate hint
- `("image", dict)` — generated image result
- `("video", dict)` — generated video result
- `("confirm", dict)` — high-risk tool confirmation

```python
load_skill(name: str) -> str | None
```
Activate a skill by name. Returns loaded skill name or `None`.

```python
reset()
```
Reset conversation history to system message only.

---

## `core.runtime_orchestrator` — Runtime Orchestrator

Full-featured runtime orchestration engine with six-phase closed loop.

### Enums

**`class TaskComplexity`**
- `MICRO` — trivial one-shot tasks
- `NORMAL` — standard development tasks
- `COMPLEX` — multi-file, multi-step
- `HIGH_RISK` — destructive, requires confirmation

**`class DNAProfile`**
- `CRUX`, `CLAUDE`, `CODEBUDDY`, `CODEX`, `KIMI`, `ZCODE`

**`class BeastRole`**
Seven beasts: `BAIHU`, `XUANWU`, `QINGLONG`, `ZHUQUE`, `QILIN`, `TENGSHE`, `YINGLONG`

### Key Functions

```python
classify_task(intent: str) -> TaskComplexity
```
Classify task complexity from natural language intent.

```python
execute(goal: str) -> dict
```
Synchronous execution with full pipeline.

```python
execute_stream(goal: str) -> Generator[OrchEvent, None, None]
```
Streaming execution with progress events.

```python
preview(goal: str) -> list[Step]
```
Dry-run: generate plan without executing.

---

## `core.tools` — Tool Registry

Agent tool registration and execution system.

### `class ToolRegistry`

Manages tool definitions from `tools.json` and dynamic registration.

```python
get_registry() -> ToolRegistry
```
Get the global tool registry singleton.

```python
reload_registry() -> ToolRegistry
```
Force reload from disk.

### Tool Types

| Type | Description |
|------|-------------|
| `shell` | Execute local commands, return stdout |
| `http` | Call HTTP API, return response |
| `python` | Call Python function via import path |
| `pipeline` | One-shot video pipeline (Showrunner) |

### Built-in Constants

- `CORE_TOOL_NAMES: frozenset[str]` — 24 default visible tools
- `TOOL_EXPANSION_CATEGORIES: dict` — category mapping for progressive disclosure
- `AGENT_SYSTEM_PROMPT: str` — agent mode system prompt

---

## `core.agent` — Agent Infrastructure

"Thinking brain" behind crux-studio.

### `class ContextManager`

Token counting + layered auto-compression for conversation history.

```python
ContextManager(
    max_tokens: int = 60000,
    preserve_recent: int = 10,
    preserve_system: bool = True,
)
```

```python
compress(messages: list[dict], client, model: str) -> list[dict]
```
Compress conversation history when over threshold.

```python
needs_compression(messages: list[dict]) -> bool
```
Check if compression is needed.

### `class ModelRouter`

Intelligent model selection based on task type and cost.

```python
classify_prompt(prompt: str) -> str
```
Heuristic classification: returns `"light"`, `"pro"`, or `"reasoner"`.

### `class PlanExecutor`

Step-by-step task execution with state machine.

### `class SubAgent`

Independent agent with its own tool-calling loop and session history.

```python
spawn_subagent(task: str, tools: list, model: str = "") -> SubAgentResult
```

---

## `core.chat_stream` — Stream Pipeline

Extracted `send_stream` implementation. Module-level generator function.

```python
_send_stream_impl(self, user_text: str, image_url: str | None = None) -> Generator
```
Core pipeline stages: accepted → plan → context → model → tools → finalize.

---

## `core.chat_stream_tools` — Tool Execution Loop

Extracted `_run_tool_calls` implementation. Module-level generator function.

```python
_run_tool_calls_impl(self, tool_calls, executed_sigs, executed_cache, loop_idx=0) -> Generator
```
Executes one round of tool calls with:
- Cross-turn deduplication
- Tool validation (Phase 1)
- Dispatch + result normalization (Phase 2)
- Adaptive loop limit adjustment
- Confirmation flow for high-risk tools

---

## `core.tool_registry_mesh` — Tool Registry Mesh (TRM)

Three-layer tool discovery, routing, and caching over the nine-beast MCP mesh.

### `class ToolTier`

| Tier | Level | Description |
|------|-------|-------------|
| `CORE` | 1 | High-frequency tools (read, search, commit) |
| `COMMON` | 2 | Common tools (code review, web fetch) |
| `SPECIALIZED` | 3 | Specialized (ComfyUI, CDP) |
| `EXPERIMENTAL` | 4 | Experimental tools |

### `class ToolRegistryMesh`

```python
trm = ToolRegistryMesh()
trm.discover_all()           # Pull tools from all bridges
trm.route("search", query="payment module")  # Auto-select + call
trm.print_catalog()          # Show full index
```

### Tool Categories

| Category | Examples |
|----------|----------|
| `infra` | read_file, write_file, run_bash, search_files |
| `creative` | generate_image, generate_video, text_to_speech |
| `code` | run_test, code_review, git_add_commit, run_lint |
| `web` | web_search, web_fetch, github_search |
| `data` | db_query |
| `ai` | multi_agent, agent_swarm, skill_search |

---

## `core.beast_wiring` — Seven-Beast Neural Wiring

Event-driven coordination of the seven beasts.

```python
wire_all() -> bool
```
Wire all beast event handlers. Called once in `ChatSession.__init__`.

| Beast | Role | Event |
|-------|------|-------|
| **Xuanwu** | Capability guard | `tool:before` — blocks unauthorized tools |
| **Baihu** | Disaster recovery | `tool:error` — self-healing on failures |
| **Qinglong** | Pipeline DAG | Pipeline dependency orchestration |
| **Zhuque** | Event emission | Event bus publish/subscribe |
| **Qilin** | Plugin ecosystem | Hot-load plugins |
| **Tengshe** | Long-term memory | Knowledge persistence |
| **Yinglong** | Top-level orchestration | Master scheduling |

---

## `core.brain` — Smart Brain

Intent recognition, prompt enhancement, storyboard generation.

### `class SmartBrain`

Multi-mixin composition:
- `CombatMixin` — adversarial combat strategies
- `CreativeMixin` — creative generation prompts
- `AestheticsMixin` — beauty/portrait aesthetics
- `VisionMixin` — vision model integration

```python
brain.enhance_prompt(user_input: str, intent: str) -> str
brain.generate_storyboard(concept: str) -> list[dict]
```

---

## `core.executor` — Autonomous Task Executor

Plan → Execute → Verify → Report lifecycle.

### `class TaskExecutor`

```python
executor = TaskExecutor(tool_executor: Callable)
result = executor.run(task: Task) -> dict
```

### `class AsyncTaskExecutor`

```python
async_executor = AsyncTaskExecutor(tool_executor: Callable)
result = await async_executor.arun(task: Task) -> dict
```

### Data Classes

- **`Goal`**: finish_line + boundaries + budget
- **`Step`**: id, description, tool, args, depends_on, verify
- **`Task`**: steps with dependency graph

---

## Testing: Reset Functions

For test isolation, the following reset functions clear module-level state:

| Module | Function | Clears |
|--------|----------|--------|
| `core.defense` | `reset_defense_state()` | `_circuits`, `_file_snapshots`, `_operation_hashes` |
| `core.fake_fix_detector` | `reset_fake_fix_detector()` | `_quarantine` |
| `core.patch` | `reset_patch_state()` | `_LAST_BACKUPS`, `_LAST_ADDED` |
| `core.adversarial_bypass` | `reset_adversarial_bypass_stats()` | `_stats` |
| `core.chat_prompt` | `reset_prompt_cache()` | `_cache`, `_COLD_LORE_LOADED` |
| `core.tool_router` | `reset_tool_router()` | `_internal_tools`, `_mcp_tools` |
| `core.background` | `reset_background_manager()` | `_bg_manager` |
| `core.tool_cache` | `reset_tool_cache()` | `_cache_singleton` |
| `core.agent_cache` | `reset_agent_cache()` | `_cache` |
| `core.workspace_guard` | `reset_workspace_guard()` | `_cached_workspace` |
| `core.secret_redactor` | `reset_secret_redactor()` | `_cached_keys` |
| `core.pipeline_tools` | `reset_pipeline_globals()` | `OUTPUT_ROOT`, `MANIFEST_DIR` |

All called by `conftest.py:_reset_shared_state` before each test module.
