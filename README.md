# 🧭 CRUX Studio v6.2.0

> **AI 驱动的终端编码助手** · 自愈架构 · 多智能体编排 · 媒体生成 · 技能市场  
> 代号：*Agnes Smart Studio*  
> 哲学：**平时如刀，出事成阵**

---

## 📋 目录

- [总览](#-总览)
- [核心能力](#-核心能力)
- [快速上手](#-快速上手)
- [架构](#-架构)
- [七兽智能体系统](#-七兽智能体系统)
- [贴身七件（Intimate Slots）](#-贴身七件intimate-slots)
- [自愈四层架构](#-自愈四层架构)
- [自我进化引擎](#-自我进化引擎)
- [技能市场](#-技能市场)
- [命令参考](#-命令参考)
- [项目结构](#-项目结构)
- [技术栈](#-技术栈)
- [测试](#-测试)
- [贡献](#-贡献)
- [许可](#-许可)

---

## 🔭 总览

CRUX Studio 是一个全功能的 **AI 编程辅助终端应用**，融合了：

| 维度 | 能力 |
|------|------|
| 🤖 **编码助手** | 代码生成、审查、调试、重构、测试驱动开发 |
| 🧠 **多智能体** | 7 个独立智能体角色（七兽），协同完成任务 |
| 🔧 **工具网格** | 113+ 注册工具覆盖文件、搜索、Git、浏览器、MCP 等 |
| 🎨 **媒体创作** | 文生图、图生图、视频生成，带审美增强 |
| 🛡️ **自愈系统** | 四层容灾：Watchdog → 重试 → 恢复 → 自审计 |
| 📦 **技能市场** | 97 个已安装技能 + 767 个市场可用技能 |
| 🔗 **MCP 桥接** | Model Context Protocol 连接外部工具和服务 |
| 💾 **语义记忆** | 跨会话记忆、知识库、偏好学习 |

### 统计数据

| 指标 | 数值 |
|------|------|
| 注册工具 | 113 |
| 核心模块 | 261 |
| 测试文件 | 193 |
| 已安装技能 | 97 |
| 市场技能 | 767 |
| 命令 | 59 |
| 版本 | 6.2.0 |

---

## ⚡ 核心能力

### 1. 🤖 编码全流程支持

```
代码生成 → 代码审查 → 调试排查 → 重构优化 → 测试覆盖 → 文档编写 → 提交推送
```

- **智能代码补全**：上下文感知的代码建议
- **多文件编辑**：跨文件重构、批量修改
- **TDD 工作流**：先写测试再写实现
- **代码审查**：自动审查 Pull Request 和本地变更
- **安全加固**：硬编码密钥检测、注入防护、XSS 防护

### 2. 🎨 媒体生成

| 功能 | 引擎 | 说明 |
|------|------|------|
| 文生图 | `engines/text_to_image.py` | 从文字描述生成图片，支持风格/构图/审美增强 |
| 图生图 | `engines/image_to_image.py` | 以参考图为基准进行编辑或风格迁移 |
| 视频生成 | `engines/video.py` | 从文字或多帧图片生成视频，支持运镜/过渡 |
| 批量生成 | `engines/batch_grid.py` | 批量生成组合为网格图 |

### 3. 🧠 多模型路由

支持动态切换供应商和模型：

- CRUX AI、DeepSeek、Kimi（通过 `models.json` 配置）
- 自动故障切换：`deepseek → crux → local → codebuddy`
- 流式输出、工具调用、视觉理解

### 4. 🔧 工具网格

113 个注册工具，按类别划分：

| 类别 | 示例工具 |
|------|---------|
| 文件操作 | `read_file`, `write_file`, `edit_file`, `patch_file`, `grep`, `glob_files` |
| 代码分析 | `code_analyze`, `code_review`, `find_symbol`, `lsp_diagnostics` |
| 运行环境 | `run_bash`, `run_python`, `run_test`, `run_lint`, `run_format` |
| Git/GitHub | `git_*` 系列, `github_*` 系列, `git_pr_create`, `git_pr_merge` |
| 网络 | `web_fetch`, `web_search`, `http_request`, `download_file` |
| 浏览器 | `browser_ai` (CDP 连接 Edge), `mcp_vision_server` |
| 媒体 | `generate_image`, `generate_video`, `view_image` |
| 技能 | `skill_search`, `skill_load`, `skill_install`, `skill_list` |
| 编排 | `execute_plan`, `agent_swarm`, `orchestrate` |
| MCP | `mcp_get_tool_description` (Model Context Protocol) |

### 5. 🧩 MCP 桥接

通过 Model Context Protocol 连接外部工具和服务：

- **MCP 服务器**：在 `core/mcp_servers/` 中注册
- **第四象限分析**：基于 MCP 的深度分析框架（见 `docs/mcp-fourth-quadrant.md`）
- **视觉服务器**：`mcp_vision_server.py` 提供视觉能力 MCP 接口

### 6. 💾 语义记忆与知识管理

- **跨会话记忆**：`awareness/` 目录持久化
- **技能记忆**：`.crux_memory/` 记录技能使用历史
- **知识库**：`docs/llm-knowledge-base/` 沉淀专家知识
- **偏好学习**：`adaptive_learner.py` 自适应学习用户偏好

---

## 🚀 快速上手

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd agnes-smart-studio

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 等配置

# 4. 启动
python crux_studio.py          # 终端模式（带 TUI）
python crux_repl.py            # 纯 REPL 模式
```

### 启动方式

| 命令 | 说明 |
|------|------|
| `python crux_studio.py` | 全屏 TUI 模式（推荐） |
| `python crux_studio.py --repl` | 纯文本 REPL 模式 |
| `python crux_repl.py` | 简化 REPL 入口 |
| `crux.bat` / `crux-tui.bat` | Windows 一键启动 |
| `launch.bat` | 图形菜单选择器 |

### 常用命令

```
/help             查看全部 59 个命令
/agent            启动智能体模式
/skill list       列出已安装技能
/tool list        列出注册工具
/brain <prompt>   使用审美增强生成
/beast <name>     加载特定智能体
/self-heal        执行自愈检查
```

---

## 🏗️ 架构

### 六级分层架构

```
┌─────────────────────────────────────────────────────────┐
│  入口层  crux_studio.py / crux_repl.py / launcher.bat    │
├─────────────────────────────────────────────────────────┤
│  UI 层   tui_app.py / tui_v2.py / message_pane.py       │
│           widgets_v2.py / markdown_renderer.py           │
├─────────────────────────────────────────────────────────┤
│  会话层  chat.py / agent.py / skills.py                  │
│           mod_chat/ / mod_agents/                        │
├─────────────────────────────────────────────────────────┤
│  智能层  brain.py / brain_aesthetics.py / brain_vision.py│
│           brain_creative.py / brain_combat.py            │
├─────────────────────────────────────────────────────────┤
│  工具层  tools.json / core/mod_tools/                    │
│           tool registry / routing / browser tools        │
├─────────────────────────────────────────────────────────┤
│  引擎层  engines/text_to_image.py / image_to_image.py    │
│           engines/video.py / batch_grid.py                │
├─────────────────────────────────────────────────────────┤
│  客户端  async_client.py / core/mod_provider/            │
│           API clients / streaming / model routing        │
├─────────────────────────────────────────────────────────┤
│  API     CRUX AI / DeepSeek / Kimi (models.json)         │
└─────────────────────────────────────────────────────────┘
```

### 三条数据流

```
🎨 生图/视频流:
  用户输入 → brain.enhance() → engine.generate() → client.create_image/video() → 展示

💬 聊天流:
  用户消息 → chat_stream() → LLM 响应 → tool_calls → _dispatch_tool() → 结果喂回 → 二次响应

🤖 智能体流:
  /agent 加载 tools.json → LLM 自动选择工具 → ToolRegistry.execute() → 结果 → LLM 总结
```

### 分层包架构（7 个 mod_* 包）

为保持扁平导入兼容性，核心功能按层组织：

| 包 | 模块数 | 职责 |
|----|--------|------|
| `core/mod_tools/` | 43 | 工具注册、路由、浏览器、基础设施工具 |
| `core/mod_provider/` | 18 | API 客户端、流式、模型路由 |
| `core/mod_chat/` | 26 | 对话引擎、会话管理、技能 |
| `core/mod_agents/` | 13 | 单智能体 + 多智能体编排 |
| `core/mod_self_heal/` | 18 | 自审计、自愈、回滚、恢复 |
| `core/mod_intel/` | 9 | LSP、语义搜索、知识图谱 |
| `core/intimate_slots/` | 8 | 贴身七件保护机制 |

---

## 🐉 七兽智能体系统

七兽是 CRUX Studio 的七个智能体角色，各司其职，协同工作：

| 神兽 | 角色 | 职责 | 模块 |
|------|------|------|------|
| 🐯 **白虎** Baihu | **灾难恢复** | 自愈修复、异常恢复、回滚操作 | `mod_self_heal/` |
| 🐢 **玄武** Xuanwu | **能力守护** | 安全加固、边界校验、熔断保护 | `intimate_slots/` |
| 🐉 **青龙** Qinglong | **工程编排** | 并行任务、多步编排、执行计划 | `agent.py` |
| 🐦 **朱雀** Zhuque | **创意引擎** | 视觉生成、审美增强、创意生产 | `brain_*.py` |
| 🦄 **麒麟** Qilin | **仲裁裁决** | 方案评估、决策权衡、冲突解决 | `brain_combat.py` |
| 🐍 **腾蛇** Tengshe | **深度分析** | 语义搜索、知识图谱、根因分析 | `mod_intel/` |
| 🐲 **应龙** Yinglong | **全局感知** | 上下文管理、全局状态、元认知 | `awareness_graph.py` |

调用方式：`/beast qinglong` 或通过编排引擎自动分配。

---

## 🛡️ 贴身七件（Intimate Slots）

七件"贴身装备"为运行时提供全方位保护：

| 装备 | 功能 | 文件 |
|------|------|------|
| 🪬 **护符** Talisman | **熔断保护** — 连续失败时切断调用，冷却后恢复 | `talisman.py` |
| 🥋 **内甲** Inner Armor | **密钥加密** — API Key 等敏感信息安全存储 | `inner_armor.py` |
| 🎒 **行囊** Backpack | **配置快照/回滚** — 安全保存和恢复配置状态 | `backpack.py` |
| 🎗️ **腰带** Belt | **速率限制** — 防止 API 调用过频 | `belt.py` |
| 🧥 **斗篷** Cloak | **请求脱敏** — 日志中隐藏敏感字段 | `cloak.py` |
| 💍 **左戒** Left Ring | **仲裁评分** — 对工具调用和提供商事件评分 | `left_ring.py` |
| 💍 **右戒** Right Ring | **降级响应** — 评分不足时触发降级策略 | `right_ring.py` |

评分机制：24 小时半衰期指数衰减，总分低于阈值时自动降级。

---

## ⚕️ 自愈四层架构

> **"修自己，不断自己"** — 永久激活，不可关闭

```
第四层 · 代码级     self_audit.py    语法/导入/配置/测试 → 自动修复
  ↑ 前三层都失败
第三层 · 会话级     recovery.py      供应商宕机/磁盘满/配置损坏 → 自动切换
  ↑ 重试耗尽
第二层 · 请求级     resilience.py    错误分类 → 指数退避重试 → 降级
  ↑ 首次失败
第一层 · 运行时     watchdog.py      每 10 秒探活，自动切换/清理
```

### 第一层：Watchdog（始终运行）

| 检查项 | 频率 | 动作 |
|--------|------|------|
| Provider 健康 | 每 30 秒 | ping 失败 → 自动切换供应商 |
| 磁盘空间 | 每 120 秒 | 低于 1GB → 清理缓存 |
| 上下文内存 | 每 60 秒 | 超过 800K tokens → 自动压缩 |
| 子进程存活 | 持续 | 进程死 → 自动重启 |

### 第二层：请求级重试

错误分类决策矩阵：

| 错误类型 | 策略 |
|----------|------|
| Rate Limit (429) | 指数退避 1s→2s→4s→8s，最多 3 次 |
| Network Error | 重试 3 次，间隔 2s |
| Auth Error (401/403) | 不重试，立即报告 |
| Timeout | 重试 2 次，超时翻倍 |
| 其他 | 重试 1 次后熔断 60s |

### 第三层：会话级恢复

| 场景 | 自动动作 |
|------|---------|
| 供应商宕机 | 按优先级切换：deepseek → crux → local → codebuddy |
| 配置损坏 | 从 `snapshots/` 恢复最近备份 |
| 磁盘不足 | 自动清理 `output/images/` + `tmp/` |

### 第四层：代码级自审计

9 个扫描器：语法、静默异常、导入错误、配置漂移、测试失败、Hook 缺口、乱码、全局状态泄露、不稳定测试。

---

## 🧬 自我进化引擎

> 目标：让 CRUX Studio 随时随地变得更强、更聪明、更可靠

### 进化双环模型

```
内环（运行时）: 观察 → 决策 → 执行 → 验证 → 调优 → 记录
外环（开发时）: 治理 → 切片 → 验证 → 快照 → 恢复 → 交接
```

### 进化维度

| 维度 | 神兽 | 目标 | 机制 |
|------|------|------|------|
| 🧠 知识进化 | 腾蛇 | 每次对话更懂用户 | 语义记忆、跨会话记忆、知识库 |
| ⚔️ 能力进化 | 白虎+朱雀 | 写得更准、修得更快 | 自动自愈、代码审查、TDD |
| 🔮 创造进化 | 麒麟 | 生图更美、输出更专业 | 审美增强、Prompt 进化 |
| 🛡️ 防御进化 | 玄武 | 更安全的运行环境 | 安全加固、边界校验 |

详见 `docs/self-evolution/README.md`

---

## 📦 技能市场

CRUX Studio 拥有丰富的技能生态系统：

```
已安装: 97 个技能包
市场:   767 个可用技能
分类:   creative, decision, frontend, full-stack, graphics, mobile,
        other, quality, tool, video
源:     Local / CodeBuddy 本地 / CodeBuddy 远程
```

### 常用技能

| 技能 | 用途 |
|------|------|
| `debug-master` | 系统化调试协议 |
| `code-reviewer` | 代码审查自动修复 |
| `security-hardening` | 安全加固 |
| `python-anti-patterns` | Python 反模式检测 |
| `api-designer` | REST/GraphQL API 设计 |
| `shell-master` | Shell 脚本最佳实践 |
| `tdd-workflow` | 测试驱动开发工作流 |

### 技能管理

```bash
/skill list                # 列出已安装技能
/skill search <keyword>    # 搜索技能市场
/skill install <name>      # 安装技能
/skill load <name>         # 加载技能到当前会话
```

---

## ⌨️ 命令参考

共 59 个命令，按类别划分：

### 创意生产

| 命令 | 说明 |
|------|------|
| `/imagine <prompt>` | 生成图片（带审美增强） |
| `/image <prompt>` | 直接生成图片 |
| `/video <desc>` | 生成视频 |
| `/enhance` | 审美增强/优化 |

### 编码

| 命令 | 说明 |
|------|------|
| `/review` | 审查当前变更 |
| `/lint` | 运行代码检查 |
| `/format` | 格式化代码 |
| `/test` | 运行测试 |
| `/debug` | 调试模式 |

### 智能体

| 命令 | 说明 |
|------|------|
| `/agent` | 启动智能体 |
| `/beast <name>` | 加载神兽智能体 |
| `/swarm` | 并行子智能体分配 |

### 系统

| 命令 | 说明 |
|------|------|
| `/help` | 帮助 |
| `/self-heal` | 执行自愈检查 |
| `/audit` | 运行完整审计 |
| `/memory` | 查看记忆 |
| `/provider <name>` | 切换模型供应商 |

---

## 📁 项目结构

```
agnes-smart-studio/
├── crux_studio.py          # 主入口（CLI + TUI）
├── crux_repl.py            # REPL 入口
├── launcher.bat            # Windows 图形启动器
├── core/                   # 核心逻辑 (261 模块)
│   ├── agent.py            # 智能体引擎
│   ├── brain*.py           # 大脑模块 (审美/视觉/创意)
│   ├── chat.py             # 对话引擎
│   ├── skills.py           # 技能管理系统
│   ├── bootstrap.py        # 启动工具
│   ├── intimate_slots/     # 贴身七件保护机制
│   ├── mod_tools/          # 工具注册与路由 (43)
│   ├── mod_provider/       # API 客户端 (18)
│   ├── mod_chat/           # 对话引擎 (26)
│   ├── mod_agents/         # 智能体编排 (13)
│   ├── mod_self_heal/      # 自愈系统 (18)
│   ├── mod_intel/          # 智能模块 (9)
│   ├── interfaces/         # 接口定义
│   ├── gateway/            # 网关
│   └── mcp_servers/        # MCP 服务器
├── ui/                     # 终端 UI (10+ 模块)
│   ├── tui_app.py          # TUI 应用
│   ├── tui_v2.py           # TUI 版本 2
│   ├── message_pane.py     # 消息面板
│   ├── widgets_v2.py       # UI 组件
│   └── markdown_renderer.py
├── engines/                # 媒体生成引擎
│   ├── text_to_image.py
│   ├── image_to_image.py
│   └── video.py
├── tools/                  # 工具模块
│   ├── browser_ai.py       # 浏览器 AI 工具 (CDP)
│   └── crux_bridge.py
├── tests/                  # 测试 (193 文件)
│   ├── test_*.py
│   ├── integration/
│   └── self_audit/
├── skills/                 # 已安装技能包
├── skills_md/              # 技能文档
├── docs/                   # 文档
│   ├── adr/                # 架构决策记录
│   ├── self-evolution/     # 自我进化文档
│   └── llm-knowledge-base/ # LLM 知识库
├── agents/                 # 智能体配置
├── prompts/                # 提示词模板
├── rules/                  # 编码规则
├── awareness/              # 持久化记忆
├── output/                 # 输出目录
│   ├── images/
│   ├── videos/
│   └── projects/
├── tools.json              # 工具注册表
├── models.json             # 模型配置
└── .crux_identity.md       # 项目身份标识
```

---

## 🛠 技术栈

| 技术 | 用途 |
|------|------|
| **Python 3.10+** | 主语言 |
| **asyncio** | 异步运行时 |
| **Rich** | 终端渲染 (Markdown/Tables/Spinners) |
| **prompt_toolkit** | 输入处理 (补全/历史/多行) |
| **httpx** | HTTP 客户端 (流式/重试) |
| **Pillow** | 图片处理 |
| **Playwright** | 浏览器自动化 (CDP) |
| **pytest** | 测试框架 |
| **ruff** | 代码检查+格式化 |
| **pyright** | 类型检查 |
| **nest_asyncio** | 嵌套事件循环支持 |

---

## 🧪 测试

```
tests/
├── test_*.py               # 单元测试
├── integration/             # 集成测试
├── self_audit/              # 自审计测试
├── conftest.py              # 共享 fixtures
├── conftest_leak.py         # 全局状态泄漏检测
└── conftest_vcr.py          # VCR 录制回放
```

**测试纪律**：
- TDD 为先：没有失败的测试，不写生产代码
- 单 commit 单关注点
- CI 门禁：0 failure 基线
- 不稳定测试标记为 `xfail` 并及时修复

**运行测试**：
```bash
pytest tests/ -q                    # 快速运行
pytest tests/test_*.py -v           # 详细输出
pytest tests/ --coverage            # 覆盖率报告
```

---

## 🤝 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献规范。

### 核心准则

- **Conventional Commits**：`type(scope): description`
- **单 commit 单关注点**：禁止单 commit > 1000 行或 > 20 文件
- **提交前必跑测试**：`pytest tests/ -q` 0 failure
- **新功能配套测试**：没有测试覆盖的功能不算完成

---

## 📄 许可

本项目基于 [MIT License](LICENSE) 开源。

---

*CRUX Studio v6.2.0 · 113 tools · 97 skills · 261 core modules · 193 test files*
