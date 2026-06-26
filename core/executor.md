# core/executor.py — 自主任务执行器

> **Plan → Execute → Verify → Report** 循环引擎，将自然语言任务转为结构化工具调用序列。

## 架构

```
TaskExecutor (同步)        AsyncTaskExecutor (asyncio)
        │                          │
        └── 共享数据模型 ──────────┘
              Step / Task (dataclass)
```

两条实现共存，共享纯数据模型：

| 组件 | 说明 |
|------|------|
| `Step` | 单步任务：id、description、tool、args、depends_on、verify、status |
| `Task` | 任务容器：id、goal、steps 列表 |
| `TaskExecutor` | 同步版 — 顺序执行，保留兼容 |
| `AsyncTaskExecutor` | asyncio 原生版 — 独立步骤并行执行（Semaphore 限并发），按 depends_on 拓扑调度 |

## 生命周期

```
1. PLAN    ─ decompose() 将自然语言拆解为有序步骤 + 依赖图
2. EXECUTE ─ 遍历步骤，每步调用对应 tool，track state，error recovery
3. VERIFY  ─ 对标记了 verify="syntax"|"test" 的步骤运行检查
4. REPORT  ─ 返回结构化结果 + 证据
```

## 公共 API

```python
from core.executor import (
    quick_plan,              # 快速规划：goal → Task
    execute_plan_tool,       # 同步执行入口（注册为 /execute tool）
    async_execute_plan_tool, # async 执行入口
    TaskExecutor,            # 同步执行器
    AsyncTaskExecutor,       # async 执行器
)
```

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
