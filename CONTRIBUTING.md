# 贡献规范 — Agnes Smart Studio

本文档约定 Agnes 项目的代码提交与协作规范。所有贡献者（含 AI 智能体）必须遵守。

---

## 1. 提交纪律（最重要）

### 1.1 单 commit 单关注点

一个 commit 只做一件事。**禁止 big-bang 提交**（单 commit > 1000 行新增或 > 20 文件变更视为异常，需拆分）。

✅ 合理的 commit：
```
feat(github): add github_write_file tool for remote file writes
test(github): cover write_file create/update/sha paths
fix(render): dedupe streaming flush point
```

❌ 禁止的 commit：
```
v5.0: 一次性加入所有新功能（216 文件 +37K 行）
update（无主题）
wip（工作进度）
```

### 1.2 Conventional Commits

格式：`<type>(<scope>): <description>`

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | bug 修复 |
| `refactor` | 重构（不改行为） |
| `test` | 新增/修复测试 |
| `docs` | 文档 |
| `chore` | 构建/配置/依赖 |
| `perf` | 性能优化 |

scope 示例：`github`、`render`、`chat`、`tools`、`agent`、`ui`。

### 1.3 提交前必跑测试

```bash
python -m pytest tests/ -q
```

任何 commit 都必须保持 **0 failures** 基线。新功能必须配套测试。

---

## 2. 文件卫生

### 2.1 禁止 0 字节占位文件

不要提交空文件作为「以后再填」的占位。需要时再创建，创建时必须有实际内容。

历史教训：`AGENTS_INSTALL_GUIDE.md`、`test123.txt`、`_test_write.txt` 等 0 字节文件曾被提交，造成历史污染。

### 2.2 临时调试文件

调试用的 `_test*.txt`、`test[0-9]*.txt`、`*_scratch.txt` 已被 `.gitignore` 忽略。**不要用 `git add -f` 强加它们**。

### 2.3 敏感内容

`.env*`、`settings.json`、`output/` 已被忽略。提交前确认 `git status` 不含这些文件。

---

## 3. 架构边界

### 3.1 core/ 模块

`core/` 当前有 ~79 个模块，新模块加入前请确认：
- 没有现成模块能承担该职责（优先扩展而非新建）
- 模块名清晰反映职责（避免 `utils2.py`、`helpers.py` 这种无意义名）
- 在 `AGENTS.md` 的架构章节登记

### 3.2 工具系统

新增工具：
1. 在对应 `core/<domain>_tools.py` 实现 `execute_*` 函数（返回 `json.dumps`）
2. 在 `tools.json` 声明工具定义（含 description + parameters schema）
3. 加测试到 `tests/test_<domain>_tools.py`
4. 如果是高风险写操作，加入 `core/chat.py` 的 `_HIGH_RISK_TOOLS`

### 3.3 渲染契约

**禁止**在 `ui/render.py` 之外 `import rich.live.Live`。`tests/test_render.py` 的守卫会拦截。

所有流式渲染必须走 `StreamingRenderer`，`_flushed_len` 是唯一落盘点。

---

## 4. 测试规范

### 4.1 风格

- 外部依赖（CLI、网络、子进程）一律 mock，不触达真实环境
- 用 `monkeypatch.setattr` 替换底层 `_run` / `_run_gh` 等函数
- 测试类按被测功能分组，方法名描述场景：`test_<scenario>_<expected>`

### 4.2 命名

```
test_browse_directory          ✅ 描述场景
test_browse_file_decodes_base64 ✅ 描述行为
test1                          ❌ 无意义
test_search                    ⚠️  过于宽泛
```

### 4.3 覆盖

- 新功能必须有测试
- 安全关键逻辑（沙箱、白名单、守卫）必须有 adversarial 测试
- 修改 `core/` 核心模块后跑全量回归 `pytest tests/ -q`

---

## 5. AI 智能体贡献者特别注意

当 AI（含 Agnes 自身）通过 `github_write_file` 等工具修改本项目代码时：

1. **禁止直接推 main** — `github_write_file` 不带 `branch` 参数会被安全守卫拦截。必须推 feature 分支。
2. **必须配套测试** — 代码改动必须同时提交对应测试。
3. **必须跑全量回归** — 提交前确认 `pytest tests/ -q` 通过。
4. **SubAgent 限制** — 子智能体自主循环中，高风险写操作（`git_push`、`git_pr_merge`、推 main）会被直接拒绝，需主会话确认。

---

## 6. 分支与 PR

- `main` 为稳定分支，所有改动经 PR 合入
- feature 分支命名：`feat/<topic>`、`fix/<topic>`、`refactor/<topic>`
- PR 标题遵循 Conventional Commits 格式
- PR 描述必须说明：改了什么 / 为什么 / 测试结果

---

## 7. 版本

当前版本：`v5.0.0`（见 `agnes_manifest.json`）

版本号变更在 `core/version.py` + `agnes_manifest.json` 同步更新。
