# Changelog

All notable changes to this project will be documented in this file.

## [5.0.0] - 2026-06-17 to 2026-07-04

### Features

- feat(mcp): 新增 qoder bridge + MCPClient.list_servers()
- [方法论补齐-第4轮] CI/CD + 制品 + 灰度回滚 + 166工具
- [方法论补齐] 6模块27工具+DevContainer
- feat: Kimi (Moonshot AI) MCP互联桥接
- feat: 欢迎界面从单列改为双列布局 — 左 Logo + 右信息面板
- feat: 终端TUI全面重设计 — 七兽色板+消息气泡+紧凑欢迎屏
- feat: CLI启动器优化 + 模型fallback完善 + 七兽色板增强
- feat: ChatLayout 新界面 — 固定输入框 · 消息面板 · 暗夜工坊风格
- feat: Agent v5.1 自检自修闭环 + Pipeline 重构 + MCP 网格互联校验
- feat: UI v6 暗夜工坊 — 界面全面重新设计
- feat: banner 显示动态工具/技能数 (None→fallback默认值)
- feat: tool scorecard + CI pipeline + send_stream refactor + test coverage
- feat: 三级 tier 智能路由 + 技能自动触发 + flash 模型 + 视觉复杂度分级
- feat: MCP 四象融合 — Server stdio JSON-RPC + 递归防护 + UI/引擎/测试整体演进
- feat(#9): /extend unified toggle (notebook/audio/browser) + 20 integration tests
- feat(#8): /eval CLI command (table+json) + 11 tests
- feat(#7): /browser command + browser_tools ToolRegistry integration + 15 tests
- feat(#6): wire cost_tracker into ChatSession + /cost command
- feat: #5 Prompt Lab A/B system prompt 实验框架
- feat: #2 反思引擎 + #3 语义压缩 + #4 工具错误恢复
- feat(context+observability): 上下文管理三件套 + 工具调用观测 + tools.json 描述补全
- feat(tools+safety): 工具分类渲染 + 高风险操作确认门
- feat(agent): 接通代码感知层 + 执行闭环 hook + 确认机制
- feat: /all command + fix
- feat: /all command shows all 29 commands in compact view; add Optional import fix

### Bug Fixes

- fix(eng): P0 修复覆盖率门禁造假 + requirements 漏 requests + 抽 conftest
- [自修-第3轮] 方法论补齐模块自检自修
- [自修-第2轮] CLI界面三模型自检修复
- [自修] 三模型(DeepSeek+Claude+Codex)协同自检修复
- fix: KeyError — COLORS['background'] 不存在，改用 COLORS['base']
- fix: 消息滚动 — 滚动锚点自动滚底 + show_scrollbar=True + Escape焦点修复
- fix: ANSI转义码渲染 + 版本号不一致 — _parse_ansi改用ptk ANSI类 + 传正确version/provider
- fix: _refresh() → invalidate() — ptk 3.0.52兼容
- fix: _LayoutSink实现 + 修复on_submit→submit_callback + 移除非法keybindings
- fix: 启动器同步 — CHAT_SEPARATOR_STYLE兼容 + render_pixel_grid修复
- fix: async_chat 导入修复 (settings→config + _sanitize_json)
- fix: 启动器接入 ChatLayout + 八→七兽统一命名
- fix: 三项性能修复 — MAX_TOOL_LOOPS 30→100, 429/503 快速降级(fallback), Semaphore 全局限流
- fix: silent except:pass -> logging.debug + async double-close guard
- fix: 精细排查修复 — Popen 生命周期 + 静默吞异常 + async 双闭保护
- fix: run_subprocess 自适应 async — 有事件循环时自动 to_thread 防阻塞
- fix: 完成剩余 3 项审计优化 — BaseBridge 工具模块 + smoke tests + GBK 编码修复
- fix: 全线修复审计发现的 15 项问题
- fix: 重写3个断链测试文件 — test_async_chat/test_provider_selector/test_tools_root，恢复3059测试收集
- fix: 消除审计误报 — encoding.py措辞调整 + self_audit跳过自检 + 清理COMMIT_EDITMSG
- fix: 全面修复审计发现的12项问题 — bare except/空__init__/技能prompt/chcp冗余/git残留
- fix: 启动器去掉 pip install -e . 避免卡死，直接 python crux_studio.py
- fix(comfyui): tuple timeout → single int, Windows Python 3.11 兼容
- fix(批次D): 安全守卫 — sandbox 跨平台加固 + 破坏性操作二次拦截
- fix(批次C): 并发安全 — multi_agent _log 全程持锁 + memory 读写原子化
- fix(批次B): 用量/计费闭环 — 主文本流 + async + vision 漏报
- fix(批次A): 持久化原子性 + 并发锁 + 状态机校验
- fix: health-check smoke tests, remove dead code, wire summary() into prompt; add v5.0 modules
- fix(render): 修复流式输出重复 + 注入显示层契约 DNA
- fix: add missing Optional import
- fix: add missing Optional import

### Refactoring

- [重构] brain.py 拆分为5模块(2201→643行/-96KB→30KB)
- refactor: terminal_app 彻底重设计 — vertical_scroll自动滚底 + 输入框独立于ScrollablePane
- refactor: 清除全部 33 处技术债 + ruff format 全仓统一
- refactor: migrate all runtime hints and docs to              ██             ██ ██            █     █           █  ██ ██  █          ███ █ █ ██ █          ██ █ █ █ █ █          ███ █ █ ██ █           █  ██ ██  █            █     █             ██ ██              ██

### Performance

- [性能优化] MCP自动重连 + 10x文件扫描 + 工具去重

### Tests

- [测试] 方法论补齐模块 + brain拆分 单元测试(24 tests)
- test: 为 3 个高风险无测试模块补充覆盖 (66 cases)

### Documentation

- docs: update AGENTS.md — 32 commands, extend/cost/eval toggles, 1774 test baseline
- docs: 校准 AGENTS.md 过时数字与行号

### Chores

- chore: 运行时缓存(.crux_wiki/.crux_memory)脱离版本跟踪
- chore(provider): 切换 active 供应商 deepseek -> crux
- chore: .gitignore 添加 .crux_wiki/ 和 docs/adr/ (生成内容)
- chore: 补入遗漏的UI核心文件
- chore: 清理遗留调试临时文件
- chore: 移除 ffmpeg.exe 大文件 + 更新 .gitignore
- chore: ignore temp debug dump files
- chore: 整理工作区 — 清理14临时文件+5文档归位 + v5.0核心迭代批量提交
- 全面修复+优化(审计报告闭环)
- chore: 清理死代码 + 标记孤岛模块为 EXPERIMENTAL
- chore: add missing core/eval_harness.py and core/pytest_runner.py
- v2.0: Showrunner一键制片 + ComfyUI桥接 + LoRA炼丹 + 36技能 + prompt_toolkit换行
- Add 创建桌面快捷方式.bat
- Add 创建查询快捷方式.bat
- Add utils/templates.py
- Add utils/progress.py
- Add utils/memory.py
- Add utils/image_input.py
- Add utils/history.py
- Add utils/downloader.py
- Add utils/__init__.py
- Add ui/display.py
- Add ui/cli.py
- Add ui/__init__.py
- Add tools.json
- Add test_advanced.py
- Add start.sh
- Add start.bat
- Add skills/video-pipeline.skill.json
- Add skills/shell-master.skill.json
- Add skills/self-evolution.skill.json
- Add skills/python-expert.skill.json
- Add skills/prompt-engineering.skill.json
- Add skills/debug-master.skill.json
- Add skills/creative-thinking.skill.json
- Add skills/creative-engine.skill.json
- Add skills/cinematic-master.skill.json
- Add skills/api-designer.skill.json
- Add requirements.txt
- Add query.sh
- Add query.py
- Add query.bat
- Add pyproject.toml
- Add pipeline/workflows.py
- Add pipeline/__init__.py
- Add models.json
- Add make_icon.py
- Add launcher.py
- Add launch.sh
- Add launch.bat
- Add engines/video.py
- Add engines/text_to_image.py
- Add engines/image_to_image.py
- Add engines/__init__.py
- Add docs/tools.md
- Add docs/skills.md
- Add docs/plan-transcendent-thinking-embed.md
- Add docs/plan-entity-knowledge-embed.md
- Add docs/plan-beauty-portrait-embed.md
- Add docs/commands.md
- Add docs/authoring.md
- Add docs/architecture.md
- Add core/validator.py
- Add core/tools.py
- Add core/skills.py
- Add core/rules.py
- Add core/project.py
- Add core/config.py
- Add core/client.py
- Add core/chat.py
- Add core/brain.py
- Add core/agent.py
- Add core/__init__.py
- Add agnes_studio.py
- Add agnes_icon_preview.png
- Add agnes.ico
- Add README.md
- Add FAQ.md
- Add AGENTS.md
- Add .pytest_cache/v/cache/nodeids
- Add .pytest_cache/v/cache/lastfailed
- Add .pytest_cache/README.md
- Add .pytest_cache/CACHEDIR.TAG
- Add .pytest_cache/.gitignore
- Add .gitignore
- Add .env.example
- v2.0.0: 智能工作台 - 生图/生视频/聊天/编程/智能体/团队/部署/25命令

### Renaming

- rename: Agnes Smart Studio -> CRUX Studio v5.0.0 (full repo rebrand + badge/banner fixes)

### Changes

- change: start_launcher.bat main window Kimi -> CRUX

### Migration

- Migrate all subprocess.run() to run_subprocess() — 25 files

---

*Generated from git history. Future releases tracked with conventional commits.*
