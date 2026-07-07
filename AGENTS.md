# AGENTS.md instructions for C:\Users\huangjiancheng\agnes-smart-studio

<INSTRUCTIONS>
# Global Instructions

CRUX Studio v6.0.0 — 平时如刀，出事成阵 · 极简内核 + 百器待命 + 七兽按需治理

> 项目命名：Agnes Smart Studio 是产品/仓库名称，CRUX Studio 是 TUI/工程系统名称。
> 本文中 CRUX 与 Agnes 指同一项目的不同层级。

## 流程强度说明

本文件定义通用铁律，但具体执行强度由 `METHODOLOGY.md` 的 A/B/C/D 任务分级决定：

- **A 级微任务**：可跳过 Plan / TDD / Worktree，但必须看 diff，必要时跑相关验证。
- **B 级普通开发**：需要简短计划和验证；Bug 修复必须补回归测试。
- **C 级复杂工程**：执行完整 Plan + 分阶段实现 + 测试 + Review。
- **D 级高风险任务**：必须 Spec + 风险评估 + 人工确认 + 隔离 + CI。


<!-- 🔥 HOT PATH END — 以下内容对日常执行非必需，已移入 AGENTS_REF.md -->

## Key Capabilities

> ⚠ 以下数量为快照，可能过期。当前准确数量以 `/tools`、`/help`、`pytest --co` 输出为准。

- 50 Commands: auto-registered in core/commands.py (COMMANDS list), /help auto-generated
- Toggle-based feature switching (非 mode 架构):
  - code_mode / agent_mode: ChatSession.toggle_code_mode() / toggle_agent_mode()
  - Skill loading: ChatSession.load_skill() / unload_skill() (showrunner / comfyui-bridge)
  - 扩展工具集 toggle: /extend <notebook|audio|browser|list> 统一管理；/browser 快捷开关
  - 花费追踪: /cost [budget <usd>|reset] + send_stream 超预算提示
  - 质量基准: /eval [json] 跑 EvalEngine 基准集（表格/JSON 输出）
  - 每次切换通过 _build_system_prompt() 重建 system prompt
- Showrunner: /showrun <goal> full creative pipeline (plan->decompose->storyboard->generate->QC)
- Marketplace: 696 skills (28 local + 668 marketplace), search/install/auto-discover
- Providers: CRUX AI / DeepSeek V4 Pro / SiliconFlow Kimi / Qwen3-Coder 30B (local CUDA)
- 97 Tools: code editing, git (13), code intelligence (7), GitHub (10), ComfyUI (10), LoRA (3), browser, file ops, MCP bridge (4 tools), patch, execute_plan, codex, notebook, audio — 动态统计见 /tools

## Rendering Contract
- ui/tui_app.py:TuiApp._stream_response 是流式渲染网关（prompt_toolkit 全屏 TUI）
- 协议: ChatSession.send_stream() yield (kind, payload) 元组 → _stream_response 分发到 message_pane
- 流式更新: message_pane.stream_start() → stream_append() → stream_end()
- 关键不变式: prompt_toolkit FormattedText 渲染，_ScrollingWindow 自定义滚动

## Rules System (规范注入)
- core/rules.py: RulesManager + Rule + get_rules()，扫描 rules/*.rules.md
- 规则名 = 文件名剥两层后缀 (.rules.md → 纯名，如 rendering)
- frontmatter `default-active: true` 标记的规则首次 discover 时自动激活（系统级契约默认生效）
- 接入点: core/chat.py:_build_system_prompt() 末尾追加 get_rules().inject_prompt()，所有 mode/skill 切换自动存活

