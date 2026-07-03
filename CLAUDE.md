# Agnes Smart Studio — Claude Code 配置

> 项目命名：Agnes Smart Studio 是产品/仓库名称，CRUX Studio 是 TUI/工程系统名称。
> 本文中 CRUX 与 Agnes 指同一项目的不同层级。

> 通用方法论见 @AGENTS.md。本文件仅含 Claude Code 专有配置。

---

## 模型路由策略

当前 7 个模型，配置在 `models.json` + `core/provider.py`：

| 供应商 | 模型 | 用途 |
|--------|------|------|
| DeepSeek (active) | `deepseek-v4-pro` (heavy), `deepseek-v4-flash` (light) | 文本编码主力 |
| Zhipu (free) | `GLM-4V-Flash` | 视觉兜底 |
| CRUX (paid) | `agnes-2.0-flash` (vision主力), 2×生图, 1×视频 | 视觉 + 媒体生成 |

### 子 Agent 路由（硬约束）

| 任务 | Agent | Claude Code 路由名 | CRUX 实际模型 |
|------|-------|-------------------|-------------|
| grep / glob / 读文件 / 搜代码 | Explore | haiku | deepseek-v4-flash |
| 单文件修改、简单重构 | general-purpose | haiku | deepseek-v4-flash |
| 写测试 | general-purpose | haiku | deepseek-v4-flash |
| 调试错误/测试失败 | debugger | haiku | deepseek-v4-flash |
| 实现方案设计 | Plan | haiku | deepseek-v4-flash |
| 架构设计、多文件重构 | 主对话 | — | deepseek-v4-pro |
| 复杂调试根因分析 | 主对话 | — | deepseek-v4-pro |

### 规则
1. 读文件/搜索 → Explore + haiku，不派 general-purpose
2. 写代码 → general-purpose + haiku，简单修改不派 Pro
3. 审查/安全 → 本地规则引擎
4. 独立子任务一次并行发出，不串行等
5. 子 Agent 失败不重试同一类型，换通路
6. 禁止：派 haiku 做架构决策 / 派 Pro 做 grep

---

## 项目环境

- Python: `C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe`
- 测试: `python -m pytest tests/test_smoke.py -q`
- 冒烟: `python crux_studio.py --check`
- 启动 TUI: `python crux_studio.py --chat`
- MCP 服务: `python crux_studio.py mcp-serve`
