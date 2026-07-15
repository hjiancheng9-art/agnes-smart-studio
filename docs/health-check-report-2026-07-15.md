# CRUX Studio 代码健康体检报告

**日期**: 2026-07-15  
**版本**: v6.0.0 (HEAD: 9539aeb)  
**范围**: 全仓库静态分析 + 未提交 diff review + 测试覆盖验证

---

## 一、仓库概览

| 指标 | 数值 |
|------|------|
| Python 源文件 | 766 个 |
| Python 代码总量 | ~6.4 MB |
| 核心模块 (`core/`) | ~240 个文件 |
| 测试文件 | 157 个 |
| 技能包 (`skills/`) | ~99 个本地 + 668 市场 |
| 智能体 (`agents/`) | 21 个 .agent.md |
| 命令数 | 57 个 |
| 最近提交 | 9539aeb (2026-07-15) |

---

## 二、未提交改动 Review (5 文件)

### 2.1 `core/chat.py` — ✅ 高质量

**变更**: 在 `_build_retry_strategies()` 中新增「POSIX 命令 → Windows 等价命令」策略（策略3）。

**优点**:
- 映射表覆盖 `head/tail/grep/cat/ls/cp/mv/rm/touch/wc` 等常见 Linux 命令
- 使用 `lambda` 闭包保持命令参数不变，转换精准
- 异常安全：`try/except` 包裹，转换失败静默跳过
- 变量作用域限定在函数内（`_POSIX_MAP`），不会污染全局命名空间
- 与 `core/tools.py` 中的 `_POSIX_TO_WINDOWS` 互补：chat.py 用于 **auto-retry**（执行前修正），tools.py 用于 **诊断提示**（执行后告知用户）

**建议**:
- 考虑将 `_POSIX_MAP` 提取为模块级常量（类似 `core/tools.py` 的做法），避免每次调用都重建字典
- 建议加 1-2 个单元测试覆盖 `grep` 和 `rm` 的边界情况

### 2.2 `core/tools.py` — ✅ 重大改进

**变更**: Shell 降级链 + 诊断引擎 + 多编码解码 + 原子写入，大幅增强 Windows 兼容性。

**亮点**:
1. **`_safe_decode()`**: 优雅的多编码回退（UTF-8 → GBK → CP936 → GB2312 → Latin-1），解决 Windows cmd.exe 中文输出乱码问题
2. **`_POSIX_TO_WINDOWS` 完整映射表**: 30+ 个 Linux→Windows 命令映射，覆盖文件操作、进程管理、文本处理
3. **`_diagnose_shell_failure()` 增强**: 区分 shell 级错误 vs 应用级错误，给出可操作的修复建议
4. **`Popen + communicate()` 替代 `run(capture_output=True)`**: 修复高并发下 `_readerthread` 崩溃问题（这是关键 bug fix）
5. **应用层输出智能判断**: 有实质输出且不像 shell 报错 → 直接返回，不再盲目重试
6. **GBK 字节级中文错误检测**: `b"\xb2\xbb\xca\xc7"` 等字节模式匹配，绕过编码问题直接检测中文错误消息
7. **原子写入**: `write_file` 和 `write_text` 使用临时文件 + `os.replace()`，防止断电/崩溃导致文件损坏

**风险点**:
- `_POSIX_TO_WINDOWS` 中 `sed/awk/tr` 的值是 `"powershell -Command \"... -replace\""` 这种模板字符串，实际使用时不会正确展开。**建议**：要么删除这些伪映射，要么改为真正的 lambda 函数
- `_safe_decode` 的 `LookupError` 捕获可能过于宽泛（`LookupError` 是 `ValueError` 的父类，但 `bytes.decode()` 不会抛 `LookupError`，只会抛 `UnicodeDecodeError`）。不过不影响功能正确性

**建议**:
- 将 `_POSIX_TO_WINDOWS` 中无效的模板条目删除或修正
- 考虑增加一个 `test_safe_decode()` 单元测试

### 2.3 `tests/test_daemon.py` — ✅ 优秀

**变更**: 从简单的 `assert d is not None` 扩展到完整的 WebSocket IPC 测试套件（+119 行）。

**亮点**:
- 覆盖 `StartupDiagnostics`、命令行接口、WebSocket 连接、并发请求
- 使用 `asyncio.run()` + `websockets` 库进行真实网络测试
- `teardown_class` 正确清理 WebSocket 资源
- `test_invalid_json` 测试错误处理路径

**建议**: 无重大问题

### 2.4 `tests/test_self_heal_architecture.py` — ⚠️ 编码问题

**变更**: 新增 367 行自愈架构测试（+1 个未跟踪文件）。

**问题**:
- **文件编码**: 从 `type` 命令输出可见，文件中存在大量乱码（`???`），说明文件是用 GBK 编码保存但被当作 UTF-8 读取的。虽然 pytest 能运行通过（因为 `encoding='utf-8', errors='ignore'` 在 import 时可能兜底），但这会导致：
  - 中文注释和字符串在编辑器中显示为乱码
  - 如果有人在 UTF-8 环境下编辑此文件，可能会意外破坏中文内容
- **建议**: 在文件顶部添加 `# -*- coding: utf-8 -*-` 并确保编辑器使用 UTF-8 保存

**功能层面**: 测试覆盖了 `_build_shell_strategies` 的 10 个场景和 `_diagnose_shell_failure` 的 6 个场景，结构合理。

### 2.5 `tests/test_daemon.py` (git diff) — ✅ 配套改动

与 `test_self_heal_architecture.py` 配合，增加了 WebSocket IPC 测试。无问题。

---

## 三、死代码 / 技术债 / 架构异味

### 🔴 高优先级

#### 1. `core/runtime/` — 空目录（0 字节 `__init__.py`）

`core/runtime/` 下只有空的 `__init__.py`，而实际运行时逻辑都在 `core/runtimes/` 下。这是明显的**遗留目录**，上次重构（v5.1 热路径优化）时没有清理。

- **影响**: 零（没有被引用）
- **建议**: 直接删除 `core/runtime/` 目录

#### 2. `tools/edge/` — 53 个 `.txt` 对话导出文件（~722 KB）

`tools/edge/` 目录下有 53 个 `.txt` 文件，包括 `r1_chatgpt.txt`、`r2_zhipu_full.txt`、`zhipu_complete.txt`（109KB）等。这些都是 GPT/ChatGPT/Zhipu/Gemini 的对话导出，属于**实验过程数据**。

- **影响**: 增加仓库体积，违反项目自身的 `AGENTS.md` 文件组织规范（"输出目录规则" 要求此类文件放入 `tmp/` 子目录）
- **建议**: 迁移到 `tmp/scraps/` 或 `tmp/gpt_outputs/`，或从版本控制中排除

#### 3. `tools/edge/` — 33 个 Python 脚本（~5KB 平均）

`tools/edge/` 下有 `fetch_r2.py`、`fetch_zhipu.py`、`gemini_fetch.py`、`send_debate.py`、`round1_cwim.py`、`test_chatgpt.py` 等 33 个脚本。这些看起来是**一次性实验脚本**，用于模型对比辩论。

- **影响**: 混在 `tools/` 目录下，容易被误认为生产工具
- **建议**: 迁移到 `tmp/` 或 `tools/edge/` 下加 `__pycache__/` 忽略，或从 `.gitignore` 排除

### 🟡 中优先级

#### 4. `core/lore/` 和 `core/lore_archive/` — 叙事层代码

`core/lore/` (15KB, 3 文件) 和 `core/lore_archive/` (99KB, 16 文件) 包含 `claude_dna.py`、`codebuddy_dna.py`、`codex_dna.py`、`legendary_arsenal.py` 等。v5.1 的 changelog 提到"删除了 16 个纯叙事文件"，但这两个目录仍然存在。

- **影响**: 占用热路径内存（虽然 v5.1 做了冷加载优化），增加认知负担
- **建议**: 审查是否仍有代码引用，如无则彻底清理

#### 5. `core/intimate_slots/` — 8 个文件

`core/intimate_slots/` 下有 `arbiter.py` (453L)、`backpack.py`、`belt.py` 等 8 个文件，总计 ~1KB 的 `__init__.py`。这些是"插槽"模式的角色定义。

- **影响**: 功能代码但命名抽象度高，新人难理解
- **建议**: 考虑加 docstring 或在 `lore/` 中补充说明其架构用途

#### 6. `core/tools.py` — `_POSIX_TO_WINDOWS` 中有无效条目

如 2.2 所述，`sed`、`awk`、`tr`、`xargs`、`tee`、`watch` 等命令的映射值是模板字符串而非可执行代码。

- **影响**: 如果 `_POSIX_TO_WINDOWS` 被用作诊断提示，用户会得到误导性的建议
- **建议**: 删除无效条目或修正为真实建议

#### 7. 测试覆盖率不均衡

- `test_phase5_skill_compiler.py` 有 13 个 ERROR（导入失败）
- `test_version.py` 全部 7 个 FAIL
- `test_zcode_*.py` 系列有多个 FAIL

这些都不是本次改动引入的，但表明**部分测试套件已经过时**，可能是在 v6.0 重构后没有更新。

- **建议**: 标记为 `@pytest.mark.skip(reason="needs update for v6.0")` 或修复

### 🟢 低优先级

#### 8. `core/chat.py` 文件过大

`core/chat.py` 超过 1900 行，虽然 v5.1 做了拆分（`_consume_stream_delta`、`_execute_tool_call`、`_finish_turn` 等提取），但仍然是单体。

- **建议**: 长期可考虑按职责拆分（如 `chat/stream.py`、`chat/tools.py`、`chat/routing.py`）

#### 9. `core/commands.py` 与 `HELP.md` 不同步

`HELP.md` 声称 57 个命令，但实际 COMMANDS 列表可能有增减。

- **建议**: 将 HELP.md 改为自动生成（类似 `AGENTS.md` 的热路径拆分）

#### 10. `.gitignore` 不完整

`core/runtime/`（空目录）、`tools/edge/*.txt`、`tools/edge/*.py`（实验脚本）等未被 `.gitignore` 排除。

- **建议**: 更新 `.gitignore` 排除 `tmp/`、`output/`、`*.txt`（在 `tools/edge/` 下）

---

## 四、测试状态

### 本次改动验证

| 测试文件 | 结果 |
|----------|------|
| `tests/test_daemon.py` | ✅ 13/13 通过 |
| `tests/test_self_heal_architecture.py` | ✅ 39/39 通过 |
| 合计 | ✅ 52/52 通过 |

### 全量测试状态（含已存在问题）

- **总测试数**: ~650+
- **已通过**: ~580+
- **已失败**: ~35（均为预存问题）
- **已错误**: ~13（`test_phase5_skill_compiler.py` 导入失败）
- **已跳过**: ~20+

**结论**: 本次未提交改动**没有引入任何新的测试失败**。所有 52 个新增/修改测试均通过。预存的 ~50 个失败/错误测试是 v6.0 重构后未及时更新的遗留问题。

---

## 五、综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | ⭐⭐⭐⭐☆ | 整体优秀，Windows 兼容性改进显著 |
| 测试覆盖 | ⭐⭐⭐☆☆ | 核心路径覆盖好，部分套件过时 |
| 架构清晰度 | ⭐⭐⭐☆☆ | 模块化充分，但有遗留目录和叙事层代码 |
| 文档同步 | ⭐⭐⭐☆☆ | HELP.md 与代码不同步 |
| 仓库整洁度 | ⭐⭐⭐☆☆ | `tools/edge/` 和 `core/runtime/` 需要清理 |

---

## 六、行动建议（按优先级排序）

### 立即执行（本 PR 内）

1. ✅ **合并本次改动** — 52 个测试全部通过，改动质量高
2. ⚠️ 清理 `core/tools.py` 中 `_POSIX_TO_WINDOWS` 的无效条目（`sed/awk/tr/xargs/tee/watch`）

### 短期（下个迭代）

3. 🗑️ 删除 `core/runtime/` 空目录
4. 📦 将 `tools/edge/*.txt` 和实验脚本迁移到 `tmp/` 或加入 `.gitignore`
5. 🔧 修复 `test_phase5_skill_compiler.py` 的 13 个 ERROR（标记 skip 或修复导入）
6. 🔧 修复 `test_version.py` 的 7 个 FAIL（版本号或数据结构变更导致）

### 中期（下季度）

7. 📖 将 `HELP.md` 改为自动生成
8. 📖 为 `core/lore/` 和 `core/intimate_slots/` 补充架构文档
9. 🏗️ 评估 `core/chat.py` 的拆分可行性（>1900 行）
10. 🧪 补充 `_safe_decode()` 的单元测试

---

*报告由 AgnesCode 生成 | 2026-07-15*
