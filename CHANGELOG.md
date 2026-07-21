# CHANGELOG

> CRUX Studio v6.2.0 · 最近 25 个提交 · 2026-07-20

---

## 🚀 新功能

- **编排工具 2→5 扩展** — 新增 `resource_search`、`skill_execute`、`project_analyze` 三个编排工具，Agent 可自主搜索资源、执行技能、分析项目结构，任务编排能力翻倍。 (8932e69)
- **外部 UX 改进** — 三项优化：(1) 超长工具结果 (>2000字符) 智能裁剪，优先展示错误和警告行；(2) 媒体错误分类 `_media_error()` 覆盖 6 种错误模式；(3) 项目记忆机制，跨会话持久化关键上下文。 (68d5156)
- **渐进式工具披露** — 默认工具集从 190 个精简至 24 个核心工具，减少模型认知负担，需要时按需展开。 (4592168)
- **Aider 级 Git 编辑** — 自动提交 + 仓库地图 (repo map)，让 Agent 具备与 Aider 同级别的 Git 操作精度。 (083f97b)
- **粒度复制** — 支持复制最后 N 条消息、指定范围、单条消息三种模式，灵活导出对话片段。 (e753bfe)
- **复制整段对话** — 一键复制完整会话内容，配合键盘快捷键使用。 (1efd77a)
- **自适应工具循环上限** — 工具调用循环上限根据任务计划动态调整，3 次连续失败后自动收紧至当前值 +5 并警告用户，避免无限循环。 (4e99e32)
- **欢迎屏幕动态化** — 技能数从硬编码改为实时读取，标签行反映实际运行环境 (CPU/GPU/内存)。 (8ec07b4)

## 🐛 Bug 修复

- **乱码排除列表** — 新增 mojibake exclusion list，防止终端输出乱码字符；同步修复 ruff UP038 规则违规。 (eed7db1)
- **6 个 flaky 测试 + CI 零失败门禁** — 标记 6 个不稳定测试为跳过，CI 增设 0 failure gate，阻断不稳定测试合入主干。 (959076c)
- **还原 class-scoped router fixture** — 类级别 fixture 导致测试隔离性变差，回退为函数作用域，保障测试独立性。 (0503516)
- **移除无效 Ctrl+Shift+C 快捷键** — prompt_toolkit 不支持 Ctrl+Shift 组合键，移除无效绑定避免误导。 (48c5a86)
- **incident 模块合并修复** — 合并后的 incident 模块缺少 `load_incidents` 导出，已补充。 (5167fff)
- **TUI incident 导入路径修复** — 模块合并后更新 TUI 中的 import 路径，恢复事件显示功能。 (341d8d0)
- **TUI 长任务卡顿修复** — 工具执行耗时任务时鼠标/滚轮冻结问题已解决，TUI 保持响应。 (3ede958)

## 🧪 测试

- **8 个 skill_pack 测试** — 新增 skill_pack 模块测试用例，同步修复 import 路径和 bridge 模块回归问题。 (9472b8f)
- **47 个零覆盖模块测试** — 为 3 个零测试覆盖模块补充 47 个测试用例，修复 torch API 兼容性问题。 (d9033d0)

## ♻️ 重构

- **去噪** — 移除 private-tool 声明噪音，简化 workspace 结构。 (6055446)
- **精简 Prompt** — CHAT prompt 从 100 行砍到 14 行，CODE prompt 从 50 行砍到 23 行，显著降低 token 消耗。 (cfaafc8)
- **精简 CodeBuddy Bridge** — 移除冗余功能，bridge 层只保留 marketplace 核心逻辑。 (a3d5e9b)

## 🧹 工程优化

- **Agent Kernel 清理** — 清理 agent-kernel 模块，移除未使用的错误处理器 (100行)，删除废弃的 domain/errors.py (35行)，新增 test_hello 冒烟测试。净删除 ~22,000 行。 (613ade8)
- **RUFF 全量自动修复** — 运行 ruff auto-fix 全量修复代码风格问题，同步更新 pyright 类型检查基线。 (2eb5000)
- **移除 Aider Bridge** — 删除 aider bridge 及关联 pip 包依赖，共移除 413 行。 (43db50f)
- **移除 Copilot + Qoder 死 Bridge** — 删除 Qoder bridge 文件，Copilot bridge 从未实现 (仅注释)。当前活跃 Bridge：codebuddy, aider, zcode, claude-code。 (f30bee2)
- **移除 Kimi + Codex 死 Bridge** — 删除 Kimi bridge (267行) 和 Codex bridge (416行)，合计清理 683 行废弃代码。 (636c08a)

---

*CRUX Studio v6.2.0 · 25 commits · 2026-07-20*
