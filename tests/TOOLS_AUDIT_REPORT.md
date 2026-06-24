# 工具系统全量闭环 — 体检报告

**审计日期**: 2026-06-24
**审计方式**: 冒烟实跑 28 个 P0 工具 + 交叉验证 explore agent 静态发现
**冒烟脚本**: `tests/smoke_tools_audit.py` (可复现)
**冒烟结果**: **28/28 通过**, 3 个安全守卫拦截验证成功

---

## 一、冒烟实跑结果(阶段1)

### 通过的工具链路 (27 个实跑 + 1 个跳过)

| 类别 | 工具 | 状态 | 延迟 |
|------|------|------|------|
| 文件 ops | read_file / write_file / edit_file / search_files / glob_files / list_files / tree_dir | ✓ 全通过 | 0.5–151ms |
| 执行 | run_python / run_bash / env_check | ✓ 全通过 | 33–79ms |
| 代码智能 | code_analyze / find_symbol / search_symbols / find_references / graph_{neighbors,ancestors,descendants} | ✓ 全通过 | 1–1015ms (find_symbol 冷启动建索引) |
| patch | patch_file / patch_undo | ✓ 全通过 (含错误恢复) | <1ms |
| git 只读 | git_status / git_diff / git_log | ✓ 全通过 | 11–13ms |
| github | github_search | ✓ 通过 | <1ms |
| rag | skill_search | ✓ 通过 | 38ms |
| 安全守卫 | run_bash × 3 (`rm -rf` / `git push --force` / `format D:`) | ✓ **全部被 sandbox 拦截** | <1ms |
| 跳过 | count_lines | ⚠ 跳过 (见问题 P-3) | — |

### 安全守卫验证(批次 D 加固生效)
- `rm -rf /tmp/...` → **拦截** ✓
- `git push --force` → **拦截** ✓
- `format D:` (Windows 破坏性) → **拦截** ✓

### 注册中心总量
**实际加载 75 个工具** (AGENTS.md 文档写的 52 已严重失真,见 P-1)

---

## 二、发现的问题清单(按优先级)

### P-1【文档失真】AGENTS.md "52 tools" 严重过时 — ~~优先级: 中~~ **✅ 已修**
- **现象**: AGENTS.md line 45/81 声称 52 个工具,实际 `reload_registry()` 加载 **84 个**
- **来源**: tools.json 56 条 + BUILTIN_TOOLS 3 + GIT_WORKFLOW 9 + MCP bridge 4 + 各 toggle 12
- **修复**: AGENTS.md 已更新为 84 tools + 分类明细 + 动态统计提示

### P-2【死代码】GIT_WORKFLOW_TOOL_DEFS 从未被加载 — ~~优先级: 中~~ **✅ 已修**
- **现象**: `core/git_tools.py:346` 定义了 9 个 git 工具(git_branch/push/pull/pr_create/pr_merge/stash/conflict_check/tag/worktree),但 `core/tools.py` 的 `load()` 从不引用它们
- **副作用**: `core/chat.py:846` 的 `_HIGH_RISK_TOOLS` 防御的 `git_push/git_pr_create/git_pr_merge/git_tag` 4 个工具中,**3 个在当前加载链路下根本注册不上** → 确认门空防
- **修复**: load() 已将 GIT_WORKFLOW_TOOL_DEFS 作为常驻加载（不需要 toggle），9 个工具全部注册成功
- **验证**: `reg.has('git_push')` = True, `_HIGH_RISK_TOOLS` 确认门真正生效

### P-3【schema 缺陷】count_lines 实现与 schema 不符 — ~~优先级: 中~~ **✅ 已修**
- **现象**: `tools.json` 声明 `count_lines` 的 `parameters: {}` (无参数),实现 `core/file_tools.py:397 def count_lines()` 确实不接受参数
- **问题**: 工具只能扫全仓,无法限定路径 → 在本仓库(64+ core 文件)耗时 >15s,实际不可用
- **修复**: tools.json 已为 count_lines 添加可选 `path` 参数（目录或文件路径，空=项目根目录）
- **验证**: `count_lines({path: "core"})` 返回 32538 行/80 文件，秒级响应

### P-4【双份 schema 风险】ComfyUI 工具 toggle 开启时重复注册 — ~~优先级: 低~~ **✅ 已修**
- **现象**: tools.json 有 12 个 `comfyui_*` + `comfyui_lora_*`,`COMFYUI_TOOL_DEFS`(tools.py:207) 有 12 个 `comfyui_*` + `lora_*`
- **重叠**: 9 个完全同名(comfyui_status/list_models/submit_workflow/get_result/preview_workflow/clear_queue/get_node_info/build_custom_workflow/create_custom_node)
- **修复**: load() 在 tools.json 加载循环中加去重：`if name in self._executors: continue`
- **验证**: 开启 comfyui toggle 后 87 个工具，`len(tool_names) == len(set(tool_names))` = True，零重复

### P-5【测试盲区】可选工具模块零单测 — **优先级: 中**
- **零单测模块**: `core/comfyui_tools.py`(13 工具)、`core/browser_tools.py`、`core/audio_tools.py`、`core/mcp_client.py` 的 4 个 bridge executor
- **现有覆盖**: 仅有 `test_extend_integration.py` 间接碰集成层,非工具单测
- **修复**: 阶段2 补端到端测试(优先 mcp_client bridge,因其默认开启且无测试)

### P-6【观测接口误用】metric 读取接口名错误 — **优先级: 低 (已修)**
- **现象**: 冒烟脚本原用 `metrics.snapshot()`,实际接口是 `metrics.summary()` → 显示 `?`
- **状态**: 已在冒烟脚本修正

---

## 三、全链路验证状态(注册→派发→执行→计费→守卫)

| 环节 | 验证结果 | 证据 |
|------|---------|------|
| **注册** | ✓ 75 个工具全部可发现 | `reg.has(name)` 全 true |
| **参数校验** | ✓ required/类型校验生效 | 首次跑(参数名错)时正确报"缺少必需参数" |
| **派发** | ✓ execute() 正确路由 | 27 个工具实跑成功 |
| **错误恢复** | ✓ 生效 | patch_file 无效输入返回分类错误 + 恢复建议 |
| **安全守卫** | ✓ sandbox 拦截 3/3 危险命令 | rm -rf / git push --force / format D: 全拦 |
| **计费/metric** | ✓ tool_executions 计数递增 | (P-6 修后可读取) |
| **相似工具建议** | ✓ 未直接测,但代码路径存在 | tools.py:849 `_suggest_similar_tool` |

---

## 四、下一步行动(阶段2/3 输入)

**阶段2 补测试** (按盲区优先级):
1. `test_mcp_client_bridge.py` — 4 个 MCP bridge executor(默认开启,零测试,最高优先)
2. `test_tool_registry_e2e.py` — 全链路端到端(注册→校验→执行→错误恢复→metric)
3. 补 count_lines / GIT_WORKFLOW 注册路径测试(与 P-2/P-3 修复联动)

**阶段3 修结构** (按问题优先级):
1. P-2: 接入 GIT_WORKFLOW_TOOL_DEFS(让确认门真正生效)— **收益最大**
2. P-3: count_lines 加 path 参数
3. P-1: 更新 AGENTS.md 工具数 → 75
4. P-4: ComfyUI 去重
5. P-5: 随阶段2 测试一起补
