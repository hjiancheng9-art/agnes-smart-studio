---
default-active: true
---
# 贡献规范 — 提交 · 文件 · 架构 · 测试 · AI 守则

此规则 default-active，自动注入所有 code_mode 会话。真源：CONTRIBUTING.md。

## 一、提交纪律

- **单 commit 单关注点**：一个 commit 只做一件事。禁止单 commit > 1000 行新增或 > 20 文件变更。
- **Conventional Commits**：`type(scope): description`
  - type: feat / fix / refactor / test / docs / chore / perf
  - scope: 模块名（如 github、render、chat、tools、ui）
- **禁止无意义 message**："update"、"wip"、"fix" 等不说明具体内容的提交信息。
- **提交前必跑测试**：`pytest tests/ -q`，0 failures 基线。新功能必须配套测试。

## 二、文件卫生

- **禁止 0 字节占位文件**：不提交空文件，创建时必须有实际内容。
- **禁止提交敏感内容**：`.env*`、`settings.json`、`output/` 已 gitignore，用 `git status` 确认后再提交。
- **禁止 `git add -f` 强加被忽略文件**：调试用的临时文件属于 `.gitignore` 范围。

## 三、架构边界

- **core/ 模块**：新增前确认没有现成模块能承担该职责。优先扩展而非新建。
- **工具系统**：新增工具按三步走 — 实现 `execute_*` → 声明 `tools.json` → 加测试。高风险写操作加入 `_HIGH_RISK_TOOLS`。
- **渲染**：所有流式渲染走 `StreamingRenderer`，不要在 `ui/render.py` 外 `import rich.live.Live`。

## 四、测试规范

- **外部依赖一律 mock**：不触达真实 CLI / 网络 / 子进程。
- **命名描述场景**：`test_browse_directory` 而非 `test1`。
- **新功能必须有测试**；安全关键逻辑（沙箱、白名单、守卫）必须有 adversarial 测试。
- **修改 core/ 后跑全量回归**：`pytest tests/ -q`。

## 五、AI 智能体守则

> 当 AI（含 CRUX 自身）通过工具修改本项目代码时必须遵守以下铁律：

1. **禁止直接推 main**：`git_push` 不加 `branch` 参数会被安全守卫拦截。必须推 feature 分支。
2. **必须配套测试**：代码改动必须同时提交对应测试，不含测试的 PR 不得合入。
3. **必须跑全量回归**：提交前确认 `pytest tests/ -q` 全通过。
4. **SubAgent 写操作受限**：子智能体自主循环中，`git_push`、`git_pr_merge`、推 main 会被直接拒绝，需主会话确认。
5. **写前读，改后验**：改代码前先读文件，改完跑 lint + 相关测试。
6. **不可逆操作需确认**：删除文件、重命名、删除 > 5 行逻辑，先列影响面再等用户确认。

## 六、分支与 PR

- `main` 为稳定分支，所有改动经 PR 合入。
- feature 分支命名：`feat/<topic>` / `fix/<topic>` / `refactor/<topic>`。
- PR 标题遵循 Conventional Commits 格式。
- PR 描述必须说明：改了什么 / 为什么 / 测试结果。
