# core/executor.py — 自主任务执行器

> **Plan → Execute → Verify → Report** 循环引擎，将自然语言任务转为结构化工具调用序列。
> **v2 升级**：注入 Qoder 式智能规划、语义验证、自反思循环。

## 架构

```
TaskExecutor (同步)        AsyncTaskExecutor (asyncio)
        │                          │
        └── 共享数据模型 ──────────┘
              Step / Task (dataclass)

SmartPlanner ──→ quick_plan (fallback)
SemanticVerifier ──→ verify="goal" (LLM 语义验证)
SelfReflection ──→ retry / replan / skip (失败自修复)
```

两条实现共存，共享纯数据模型：

| 组件 | 说明 |
|------|------|
| `Step` | 单步任务：id、description、tool、args、depends_on、verify、status |
| `Task` | 任务容器：id、goal、steps 列表、**reflection_enabled**、**max_retries_per_step** |
| `TaskExecutor` | 同步版 — 顺序执行，保留兼容 |
| `AsyncTaskExecutor` | asyncio 原生版 — 独立步骤并行执行（Semaphore 限并发），按 depends_on 拓扑调度 |
| `SmartPlanner` | LLM 驱动规划，失败退回 quick_plan |
| `SemanticVerifier` | 语义级目标验证（verify="goal"） |
| `SelfReflection` | 失败分析 + 重试/重新规划/跳过 |

## 生命周期

```
1. PLAN    ─ quick_plan (关键词) 或 smart_plan (LLM 理解意图)
2. EXECUTE ─ 遍历步骤，每步调用对应 tool，track state，error recovery
             步骤失败时 → SelfReflection 分析 → retry / replan / skip
3. VERIFY  ─ 对标记了 verify 的步骤运行检查
             "syntax" → ast.parse | "test" → pytest | "goal" → LLM 语义验证
4. REPORT  ─ 返回结构化结果 + 证据
```

## 公共 API

```python
from core.executor import (
    quick_plan,              # 快速规划：goal → Task（关键词匹配）
    smart_plan,              # 智能规划：goal → Task（LLM 理解意图，失败退回 quick_plan）
    execute_plan_tool,       # 同步执行入口（注册为 /execute tool）
    async_execute_plan_tool, # async 执行入口
    TaskExecutor,            # 同步执行器
    AsyncTaskExecutor,       # async 执行器
    SmartPlanner,            # LLM 规划器
    SemanticVerifier,        # 语义验证器
    SelfReflection,          # 自反思引擎
)
```

## 自反思循环（Self-Reflection）

当 `Task.reflection_enabled=True` 时，步骤失败不直接退出，而是：

1. **ErrorClassifier** 分类错误（network_error / timeout / code_error 等）
2. **可重试错误**（网络/超时/API 限流）→ 自动 retry，不消耗 LLM 调用
3. **其他错误** → LLM 反思：分析原因，决定 retry / replan / skip
4. 受 `Task.max_retries_per_step` 限制，防止无限循环

```python
task = Task(
    id="t1",
    goal="修复登录模块的认证 bug",
    steps=[...],
    reflection_enabled=True,   # 开启自反思
    max_retries_per_step=2,    # 每步最多重试 2 次
)
```

## 语义验证（SemanticVerifier）

除了 `verify="syntax"`（ast.parse）和 `verify="test"`（pytest），新增 `verify="goal"`：

```python
Step("fix_auth", "修复认证逻辑", "edit_file",
     {"path": "core/auth.py", ...}, verify="goal")
```

执行完成后，LLM 读取相关文件内容，判断目标是否真正达成。
LLM 不可用时自动降级为通过（不阻断流程）。

## 智能规划（SmartPlanner）

```python
from core.executor import smart_plan

task = smart_plan("重构用户认证模块", context="当前使用 JWT，要改为 OAuth2")
# → LLM 生成 5-7 步结构化计划
# → LLM 失败时自动退回 quick_plan（关键词匹配）
```

`execute_plan_tool` 新增 `use_llm_plan=True` 参数：当 steps 为空时自动用 LLM 规划。

## 集成

- `core/tools.py` 注册 `execute_plan_tool` 和 `async_execute_plan_tool` 为工具
- `ui/mixins/engineering.py` `/execute` 命令调用
- `core/chat.py` 通过 `ChatSession.toggle_agent_mode()` 启用

## 依赖图示例

```
Task: "重构认证模块"
  Step 1: search_files (pattern="auth")     [无依赖]
  Step 2: read_file (path=result[1])         [depends_on: 1]
  Step 3: edit_file (patch=...)             [depends_on: 2]
  Step 4: run_tests (filter="auth")         [depends_on: 3, verify="test"]
```
