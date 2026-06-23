# AGENTS.md instructions for C:\Users\huangjiancheng\agnes-smart-studio

<INSTRUCTIONS>
# Global Instructions

Agnes Smart Studio v5.0.0 — AI-native creative + coding platform

## Architecture
- Entry: launcher.py (menu) / agnes_studio.py -c (chat) / launch.bat (quick start)
- Core: core/chat.py (ChatSession), core/commands.py (COMMANDS registry), core/marketplace.py (skills), core/skills.py (SkillManager)
- UI: ui/cli.py (AgnesCLI — 多重继承 7 个 Mixin), ui/mixins/*.py (命令处理器按职责分组), ui/render.py (StreamingRenderer 流式渲染契约), ui/terminal_logo.py (ASCII logo)
- Engines: engines/text_to_image.py, engines/image_to_image.py, engines/video.py
- Knowledge: utils/memory.py (user memory), utils/history.py

## Extended Architecture (v5.0 新增子系统)
核心四件套之外，v5.0 引入了以下架构级子系统（均为 core/*.py 独立模块）：
- 编排/执行层: core/orchestra.py (多源能力协调), core/multi_agent.py (并行子智能体), core/executor.py (自主 plan-execute-verify 循环), core/showrunner.py (创意流水线导演)
- 智能体基础设施: core/sandbox.py (命令执行守卫，配合 core/tools.py 的 shell 执行点), core/hooks.py (生命周期钩子), core/provider.py (供应商自动 failover + 模型注册表), core/resilience.py + core/recovery.py (错误恢复 + 失败剧本)
- 代码智能: core/code_intel.py (AST/符号索引/语义搜索), core/rag.py (TF-IDF 语义检索), core/lsp.py (LSP 客户端)
- 记忆/会话: core/semantic_memory.py (跨会话语义记忆), core/session_mgr.py (命名持久化会话)
- 可观测/质量: core/observability.py (tracing/spans/metrics), core/cost_tracker.py (Token/预算追踪), core/audit_runner.py (统一诊断), core/eval_harness.py (智能体质量基准), core/self_audit.py (自审计)
- 持久化/调度: core/task_manager.py (持久任务), core/scheduler.py (内置定时), core/pipeline_state.py (流水线状态/质量门)
- 外部集成: core/browser_tools.py (网页生图生视频), core/git_tools.py + core/git_workflow.py (Git 自动化), core/mcp_client.py (MCP Client 桥接) + core/mcp_server.py (MCP Server stdio JSON-RPC), core/web_api.py (FastAPI REST 接口), core/codex_engines.py + core/codex_tools.py (Codex 引擎与工具集)

## MCP 四象融合架构
Agnes 同时作为 MCP **Server**（被外部调用）和 MCP **Client**（调用外部），双向可达：
- **Agnes → 外部**（MCP Client）: core/mcp_client.py 提供 MCPClient 单例 + 4 个 bridge tools（mcp_list_servers / mcp_list_tools / mcp_call_tool / mcp_read_resource），通过 ToolRegistry.load(mcp=True) 注入 runtime
- **外部 → Agnes**（MCP Server）: core/mcp_server.py 提供 stdio JSON-RPC server（`agnes mcp-serve`），暴露全量工具含 MCP bridge tools
- **REPL 管理**: /mcp <list|add|remove|connect|disconnect|tools> 命令，handler 在 ui/mixins/diag.py:_chat_mcp
- **接入点**: core/chat.py 中所有 tools.load() 调用均传 mcp=True（toggle_agent_mode / _reload_tools / load_skill / unload_skill），get_registry() 初始加载除外
- **配置持久化**: output/mcp_servers.json，auto-connect on first call，atexit cleanup

## Key Capabilities
- 33 Commands: auto-registered in core/commands.py (COMMANDS list), /help auto-generated
- Toggle-based feature switching (非 mode 架构):
  - code_mode / agent_mode: ChatSession.toggle_code_mode() / toggle_agent_mode()
  - Skill loading: ChatSession.load_skill() / unload_skill() (showrunner / comfyui-bridge)
  - 扩展工具集 toggle: /extend <notebook|audio|browser|list> 统一管理；/browser 快捷开关
  - 花费追踪: /cost [budget <usd>|reset] + send_stream 超预算提示
  - 质量基准: /eval [json] 跑 EvalEngine 基准集（表格/JSON 输出）
  - 每次切换通过 _build_system_prompt() 重建 system prompt
- Showrunner: /showrun <goal> full creative pipeline (plan->decompose->storyboard->generate->QC)
- Marketplace: 733 skills (45 local + 688 CodeBuddy), search/install/auto-discover
- Providers: Agnes AI / DeepSeek V4 Pro / SiliconFlow Kimi / Qwen3-Coder 30B (local CUDA)
- 52 Tools: code editing, git, testing, browser, ComfyUI, file ops, MCP bridge (4 tools)

## Rendering Contract (DNA — 输出不重复)
- ui/render.py:StreamingRenderer 是所有流式渲染的唯一合法网关（强制契约）
- 不变式: Live(transient=True) + _flushed_len 单一落盘点 + 副作用边界先 commit
- 守卫: tests/test_render.py (renderer 契约 + 仓库级禁止 ui/render.py 外 import Live)
- 真自检: core/capability.py:_quick_health() 的 rendering.invariants 字段（真反射检测，非写死）

## Rules System (规范注入)
- core/rules.py: RulesManager + Rule + get_rules()，扫描 rules/*.rules.md
- 规则名 = 文件名剥两层后缀 (.rules.md → 纯名，如 rendering)
- frontmatter `default-active: true` 标记的规则首次 discover 时自动激活（系统级契约默认生效）
- 接入点: core/chat.py:_build_system_prompt() 末尾追加 get_rules().inject_prompt()，所有 mode/skill 切换自动存活

## Important Files
- core/commands.py: COMMANDS list (line 55), register() (line 148), auto_category() (line 134)
- core/chat.py: ChatSession._build_system_prompt() (line 224), _current_base_prompt() (line 216)
- core/skills.py: SkillManager (line 53), get_manager() (line 280)
- core/skill_loader.py: SKILL_DIRS (line 22), 旧技能注入系统
- core/marketplace.py: MarketplaceClient (line 679), CodeBuddyAdapter (line 246)
- ui/cli.py: AgnesCLI 主壳，组合 7 个 Mixin
- ui/mixins/shared.py: SharedMixin._stream_chat() / _mode_hint() (line 193)
- ui/mixins/creative.py: _chat_showrun() handler (注意: 非 _chat_showrunner)
- ui/mixins/inline.py: _inline_browser handler (/browser 快捷开关)
- ui/mixins/diag.py: _chat_cost / _chat_eval / _chat_extend / _chat_mcp handlers (/cost /eval /extend /mcp)
- agnes_manifest.json: system evolution state snapshot
- assets/agnes_logo*.svg: terminal flat pixel logo, terminal_logo.py for CLI display

## How to Extend Agnes
- Add /command: 1 entry in core/commands.py COMMANDS + 1 handler 方法在对应 Mixin (ui/mixins/*.py)
- Register dynamically: core.commands.register('key', '/name', '<args>', '<desc>')
- Auto-category: leave category='' for auto-detection
- Install skills: from core.marketplace import get_marketplace; mkt.install('skill-name')
- 流式渲染: 必须用 ui.render.StreamingRenderer，禁止直接 import rich.live.Live（守卫测试会拦）

## Current State
- 33 commands, 52 tools, 45 local skills, 733 marketplace skills
- Core modules: 64 .py files in core/ (含 v5.0 新增编排/智能体/可观测子系统，见上方 Extended Architecture)
- Toggle-based: code_mode / agent_mode / skill (showrunner / comfyui-bridge) / extend (notebook/audio/browser)
- MCP 四象融合: MCP Client bridge (mcp_client.py) + MCP Server (mcp_server.py) 双向可达
- Terminal logo displays on startup via ui/terminal_logo.py
- llama-server with CUDA 13.3 on RTX 4060 Ti for local Qwen3-Coder 30B
- Test baseline: 1809 tests passing (数字随测试增减自动变化，不再硬编码)
</INSTRUCTIONS>

# currentDate
Today's date is 2026-06-22.

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
