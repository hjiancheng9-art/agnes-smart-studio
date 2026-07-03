# AGENTS.md instructions for C:\Users\huangjiancheng\agnes-smart-studio

<INSTRUCTIONS>
# Global Instructions

CRUX Studio v5.0.0 — AI-native creative + coding platform

> 项目命名：Agnes Smart Studio 是产品/仓库名称，CRUX Studio 是 TUI/工程系统名称。
> 本文中 CRUX 与 Agnes 指同一项目的不同层级。

## 流程强度说明

本文件定义通用铁律，但具体执行强度由 `METHODOLOGY.md` 的 A/B/C/D 任务分级决定：

- **A 级微任务**：可跳过 Plan / TDD / Worktree，但必须看 diff，必要时跑相关验证。
- **B 级普通开发**：需要简短计划和验证；Bug 修复必须补回归测试。
- **C 级复杂工程**：执行完整 Plan + 分阶段实现 + 测试 + Review。
- **D 级高风险任务**：必须 Spec + 风险评估 + 人工确认 + 隔离 + CI。

---

## 工作方法论：Codex × Claude Code × ZCode 融合方法论（强制）

> 最高原则：**没有上下文，不行动；没有计划，不大改；没有测试，不实现；没有验证，不宣布完成；没有资源收敛，不算完成。**

### 七大铁律
1. **没有上下文，不行动** — 改代码前必须知道目标、相关文件、当前行为、不能破坏什么、如何验证
2. **复杂任务必须先 Plan** — 3+ 文件 / 架构 / 数据库 / 重构 / 需求模糊 → 先出方案再动手
3. **没有失败测试，不修 bug** — `NO BUG FIX WITHOUT A FAILING TEST FIRST`
4. **没有新鲜验证，不声明完成** — 禁止"应该好了""看起来可以""理论上没问题"
5. **报告不是证据** — 命令输出、测试结果、构建结果才算证据。Agent 总结、子代理报告不算
6. **读可以并行，写必须隔离** — 多 Agent 不能同时写同一文件
7. **没有资源收敛，不算完成** — 退出码 0 ≠ 资源已释放。测试后必须检查残留进程

### 强制工作流（7 步法）

> 适用范围：该完整流程默认适用于 C/D 级任务；A/B 级任务按 METHODOLOGY.md 的轻量流程执行。
1. **头脑风暴** — 写代码前先设计推敲，提出 2-3 种方案。**硬性门禁：设计未获批准前不得实施。**
2. **Git Worktree 隔离** — 新分支上隔离工作，建立干净测试基线。
3. **编写计划** — 拆解为 2-5 分钟小任务，每任务含精确文件路径、完整代码、验证步骤。
4. **子代理驱动开发** — 每任务全新子代理，两阶段审查：需求合规性 → 代码质量。持续执行，不问"是否继续"。
5. **TDD** — RED → GREEN → REFACTOR。**铁律：没有失败的测试，绝不写生产代码。测试之前写的代码必须删除。**
6. **代码审查** — 任务间审查，关键问题阻塞进度。
7. **收尾** — 验证测试、合并/PR/保留/丢弃、清理 worktree。

### 系统化调试
1. **根因调查** — 铁律：未做根因调查前不得修复
2. **模式分析**
3. **假设与测试** — 一次只验证一个假设
4. **实施** — 三次修复失败后，停下来质疑架构

### 资源纪律（硬约束）
```
全量测试必须限并发（-n 4，禁止 -n auto）。
长命令必须有 timeout。
失败后不能无脑重跑。
通过后必须查残留。
多 Agent 不能抢资源锁。
退出码 0 不等于资源释放。
```

测试后清理：

> 具体清理命令以 `METHODOLOGY.md` 的安全清理流程为准：先列进程 → 确认无重要任务 → 再清理。以下是快速参考。

```bash
tasklist /FI "IMAGENAME eq python.exe"                   # Windows: 先列进程
taskkill //F //FI "MEMUSAGE gt 40000" //IM "python.exe"   # Windows: 确认后清理
pkill -f pytest                                           # Linux/Mac
```

### 完成前验证
完成声明前必须：
- 运行相关测试，确认 0 failed
- 如项目配置了 lint/typecheck，则必须运行
- git diff 无无关改动
- 检查残留进程
- 验证原始问题已解决

### 红旗警示
"这很简单" → 也需要验证 | "我先改一下" → 先收集上下文 | "子代理说完成了" → 报告不是证据 | "顺便重构一下" → 不扩大范围 | "pytest -n auto 最快" → 限制并发 | "测试 exit 0 了" → 还要查残留进程

### 一句话总结
**先设计再编码，先写测试再实现，小步快跑，每步独立验证，全程系统化而非拍脑袋。**

## Architecture
- Entry: launcher.py (menu) / crux_studio.py -c (chat) / launch.bat (quick start)
- Core: core/chat.py (ChatSession), core/commands.py (COMMANDS registry), core/marketplace.py (skills), core/skills.py (SkillManager)
- UI: ui/tui_app.py (TuiApp — prompt_toolkit 全屏 TUI), ui/theme.py (暗夜工坊配色)
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
- 安全/约束: core/constraints.py (高风险工具确认 + 危险参数匹配 + 写入/长运行工具白名单，单一真源)
- 事件/插件: core/event_bus.py (发布/订阅事件总线), core/plugin_system.py (外部插件加载), core/capability_registry.py (工具能力守卫/白名单)
- 守护/后台: core/watchdog.py (供应商健康探针), core/daemon.py (后台守护进程), core/pipeline_dag.py (DAG 并行编排), core/beast_wiring.py (七兽躯体初始化/接线)
- prompt 注入: core/golden_finger.py (能力谱 prompt 注入), core/seven_beasts_fusion.py (七兽融合 prompt)

## MCP 四象融合架构
CRUX 同时作为 MCP **Server**（被外部调用）和 MCP **Client**（调用外部），双向可达：
- **CRUX → 外部**（MCP Client）: core/mcp_client.py 提供 MCPClient 单例 + 4 个 bridge tools（mcp_list_servers / mcp_list_tools / mcp_call_tool / mcp_read_resource），通过 ToolRegistry.load(mcp=True) 注入 runtime
- **外部 → CRUX**（MCP Server）: core/mcp_server.py 提供 stdio JSON-RPC server（`crux mcp-serve`），暴露全量工具含 MCP bridge tools
- **REPL 管理**: /mcp <list|add|remove|connect|disconnect|tools> 命令，handler 在 core/cli_handlers.py
- **接入点**: core/chat.py 中所有 tools.load() 调用均传 mcp=True（toggle_agent_mode / _reload_tools / load_skill / unload_skill），get_registry() 初始加载除外
- **配置持久化**: output/mcp_servers.json，auto-connect on first call，atexit cleanup

## Key Capabilities

> ⚠ 以下数量为快照，可能过期。当前准确数量以 `/tools`、`/help`、`pytest --co` 输出为准。

- 53 Commands: auto-registered in core/commands.py (COMMANDS list), /help auto-generated
- Toggle-based feature switching (非 mode 架构):
  - code_mode / agent_mode: ChatSession.toggle_code_mode() / toggle_agent_mode()
  - Skill loading: ChatSession.load_skill() / unload_skill() (showrunner / comfyui-bridge)
  - 扩展工具集 toggle: /extend <notebook|audio|browser|list> 统一管理；/browser 快捷开关
  - 花费追踪: /cost [budget <usd>|reset] + send_stream 超预算提示
  - 质量基准: /eval [json] 跑 EvalEngine 基准集（表格/JSON 输出）
  - 每次切换通过 _build_system_prompt() 重建 system prompt
- Showrunner: /showrun <goal> full creative pipeline (plan->decompose->storyboard->generate->QC)
- Marketplace: 731 skills (63 local + 668 marketplace), search/install/auto-discover
- Providers: CRUX AI / DeepSeek V4 Pro / SiliconFlow Kimi / Qwen3-Coder 30B (local CUDA)
- 113 Tools: code editing, git (13), code intelligence (7), GitHub (10), ComfyUI (10), LoRA (3), browser, file ops, MCP bridge (4 tools), patch, execute_plan, codex, notebook, audio — 动态统计见 /tools

## Rendering Contract
- ui/renderer.py:StreamingRenderer 是流式渲染的唯一合法网关（prompt_toolkit 全屏 TUI）
- 协议: ChatSession.send_stream() yield (kind, payload) 元组 → StreamingRenderer.render_stream() 分发到 message_pane
- 流式更新: add_message(streaming=True) → update_streaming(content) → finalize_streaming()
- 关键不变式: prompt_toolkit FormattedText 渲染，Box 边框装饰消息气泡

## Rules System (规范注入)
- core/rules.py: RulesManager + Rule + get_rules()，扫描 rules/*.rules.md
- 规则名 = 文件名剥两层后缀 (.rules.md → 纯名，如 rendering)
- frontmatter `default-active: true` 标记的规则首次 discover 时自动激活（系统级契约默认生效）
- 接入点: core/chat.py:_build_system_prompt() 末尾追加 get_rules().inject_prompt()，所有 mode/skill 切换自动存活

## Important Files
- core/commands.py: COMMANDS list (line 55), register() (line 148), auto_category() (line 134)
- core/chat.py: ChatSession._build_system_prompt(), send_stream() generator (yield (kind,payload) tuples)
- core/skills.py: SkillManager, get_manager()
- core/skill_loader.py: SKILL_DIRS, 旧技能注入系统
- core/marketplace.py: MarketplaceClient, CodeBuddyAdapter
- ui/tui_app.py: TuiApp 主应用（prompt_toolkit Application，输入路由，流式协调）
- ui/renderer.py: StreamingRenderer — 桥接 ChatSession 流式协议到 message_pane
- ui/message_pane.py: MessagePane — 可滚动消息缓冲区，box-drawing 装饰
- ui/input_bar.py: InputBar — 多行输入 + /command 自动补全
- ui/theme.py: COLORS 调色板 + BEAST 七兽系统 + PTK_STYLE
- crux_manifest.json: system evolution state snapshot
- assets/crux_logo*.svg: terminal flat pixel logo

## How to Extend CRUX
- Add /command: 1 entry in core/commands.py COMMANDS + 1 handler 方法在 core/cli_handlers.py
- Register dynamically: core.commands.register('key', '/name', '<args>', '<desc>')
- Auto-category: leave category='' for auto-detection
- Install skills: from core.marketplace import get_marketplace; mkt.install('skill-name')
- 流式渲染: 通过 ui/renderer.py:StreamingRenderer，不直接操作 prompt_toolkit 渲染

## Current State Snapshot

> ⚠ 本节为快照，不作为执行真源。当前准确状态以 `/tools`、`/help`、`crux_manifest.json`、`pytest --co` 输出为准。
- 53 commands, 113 tools, 63 local skills, 668 marketplace skills
- Core modules: 113 .py files in core/ (含 v5.0 新增编排/智能体/可观测子系统，见上方 Extended Architecture)
- Toggle-based: code_mode / agent_mode / skill (showrunner / comfyui-bridge) / extend (notebook/audio/browser)
- MCP 四象融合: MCP Client bridge (mcp_client.py) + MCP Server (mcp_server.py) 双向可达
- UI: prompt_toolkit 全屏 TUI (ui/tui_app.py → TuiApp)，暗夜工坊暗色主题
- Test baseline: 151 test files (动态统计见 `pytest tests/ --co -q`)

## Subsystem Docs (core/*.md)
- core/executor.md — 自主任务执行器 (Plan→Execute→Verify→Report)
- core/orchestra.md — 能力协调层 (多源冲突仲裁/组合/发现/动态切换)
- core/multi_agent.md — 多智能体并行调度 (分解/派发/聚合/共识/偷取)
- core/showrunner.md — 创意流水线导演 (Goal→Plan→Generate→Deliver)
- core/observability_stack.md — 可观测体系 (Tracing/Cost/Self-Audit)
- core/provider_resilience.md — 供应商+韧性 (Failover/CircuitBreaker/Recovery)
</INSTRUCTIONS>

<!-- Snapshot generated on 2026-06-22. Do not use as current date. -->

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
