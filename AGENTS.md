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

## Key Capabilities
- 30 Commands: auto-registered in core/commands.py (COMMANDS list), /help auto-generated
- Toggle-based feature switching (非 mode 架构):
  - code_mode / agent_mode: ChatSession.toggle_code_mode() / toggle_agent_mode()
  - Skill loading: ChatSession.load_skill() / unload_skill() (showrunner / comfyui-bridge)
  - 每次切换通过 _build_system_prompt() 重建 system prompt
- Showrunner: /showrun <goal> full creative pipeline (plan->decompose->storyboard->generate->QC)
- Marketplace: 733 skills (45 local + 688 CodeBuddy), search/install/auto-discover
- Providers: Agnes AI / DeepSeek V4 Pro / SiliconFlow Kimi / Qwen3-Coder 30B (local CUDA)
- 52 Tools: code editing, git, testing, browser, ComfyUI, file ops

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
- agnes_manifest.json: system evolution state snapshot
- assets/agnes_logo*.svg: terminal flat pixel logo, terminal_logo.py for CLI display

## How to Extend Agnes
- Add /command: 1 entry in core/commands.py COMMANDS + 1 handler 方法在对应 Mixin (ui/mixins/*.py)
- Register dynamically: core.commands.register('key', '/name', '<args>', '<desc>')
- Auto-category: leave category='' for auto-detection
- Install skills: from core.marketplace import get_marketplace; mkt.install('skill-name')
- 流式渲染: 必须用 ui.render.StreamingRenderer，禁止直接 import rich.live.Live（守卫测试会拦）

## Current State
- 30 commands, 52 tools, 45 local skills, 733 marketplace skills
- Toggle-based: code_mode / agent_mode / skill (showrunner / comfyui-bridge)
- Terminal logo displays on startup via ui/terminal_logo.py
- llama-server with CUDA 13.3 on RTX 4060 Ti for local Qwen3-Coder 30B
- Test baseline: 927 passed, 2 skipped
</INSTRUCTIONS>

# currentDate
Today's date is 2026-06-21.

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
