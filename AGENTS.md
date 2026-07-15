# AGENTS.md instructions for C:\Users\huangjiancheng\agnes-smart-studio

<INSTRUCTIONS>
# Global Instructions

CRUX Studio v6.1.0 — 极简内核 · 百器待命 · 七兽按需 · Multi-Agent 已模块化

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
  - Skill loading: ChatSession.load_skill() / unload_skill() (showrunner / creative-pipeline)
  - 扩展工具集 toggle: /extend <notebook|audio|browser|list> 统一管理；/browser 快捷开关
  - 花费追踪: /cost [budget <usd>|reset] + send_stream 超预算提示
  - 质量基准: /eval [json] 跑 EvalEngine 基准集（表格/JSON 输出）
  - 每次切换通过 _build_system_prompt() 重建 system prompt
- Creative Generation: /generate (Agnes: text/image/video) — CRUX 生成管线入口
- Marketplace: 696 skills (28 local + 668 marketplace), search/install/auto-discover
- Providers: CRUX AI (vision/media/fallback) / DeepSeek V4 Pro+Flash (primary chat/code, 1M ctx) / Zhipu GLM-4V-Flash (free vision)
- 97 Tools: code editing, git (13), code intelligence (7), GitHub (10), creative generation (Agnes+runware), browser, file ops, MCP bridge (4 tools), patch, execute_plan, codex, notebook, audio — 动态统计见 /tools

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

## 📁 文件组织规范

### 根目录只放项目核心文件

**允许：** 源码(.py)、文档(.md)、配置(.json/.yaml/.toml/.env)、构建脚本(.sh/.bat/.ps1)

**禁止：** 脚本生成的输出/临时文件、CDP浏览器碎片、GPT对话导出、任务日志、运行时残留

### 输出目录规则

| 内容类型 | 目录 |
|---------|------|
| CDP 浏览器输出 | tmp/cdp_fragments/ |
| GPT 对话导出 | tmp/gpt_outputs/ |
| 系统诊断/调试 | tmp/diagnostics/ |
| 任务日志 | tmp/job_logs/ |
| 工作流分析 | tmp/workflows/ |
| 杂项碎片 | tmp/scraps/ |
| 正式产物 | output/ |
| 图片/视频/音频 | output/images/ output/videos/ |
| 浏览器会话 | browser_sessions/ |

### 脚本规范

所有脚本在写输出文件时必须显式指定路径，不得依赖 cwd:
  tmp_dir = project_root / "tmp" / "category"

