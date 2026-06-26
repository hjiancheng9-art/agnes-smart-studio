# core/multi_agent.py — 多智能体协调引擎

> 并行子智能体调度：任务分解、并行派发、结果聚合、共识投票、停滞偷取。

## 架构

```
MultiAgentCoordinator (同步)          AsyncMultiAgentCoordinator (asyncio)
     │ threading + Lock                      │ asyncio.Semaphore + gather
     └── 共享数据模型 ───────────────────────┘
           AgentTask / Agent / decompose()
```

## 核心数据模型

| 类 | 职责 |
|----|------|
| `AgentTask` | 子任务：id、description、tool_sequence、depends_on、status |
| `Agent` | 智能体：name、role、task（当前任务）、result |

## 协调流程

```
1. DECOMPOSE  ─ 将复杂任务拆解为多个 AgentTask（含依赖图）
2. DISPATCH   ─ 按 depends_on 拓扑调度，独立任务并行执行
3. AGGREGATE  ─ 收集各 Agent 结果
4. CONSENSUS  ─ 对冲突结果进行投票
5. STEAL      ─ 从停滞 Agent 偷取任务重新派发
```

## 同步 vs Async

| 特性 | 同步版 | Async 版 |
|------|--------|----------|
| 并发模型 | `threading` + `Lock` | `asyncio.Semaphore` + `gather` |
| 依赖调度 | round-robin（忽略依赖） | 真正拓扑排序 |
| 工具执行 | 直接调用 Callable | 支持 async Callable + 自动 to_thread |
| runtime | 未接 ChatSession | 已接 M5 async_render |

## 公共 API

```python
from core.multi_agent import (
    Agent,                        # 智能体数据类
    AgentTask,                    # 子任务数据类
    MultiAgentCoordinator,        # 同步协调器
    coordinate,                   # 同步入口
    AsyncMultiAgentCoordinator,   # async 协调器
    async_coordinate,            # async 入口
    decompose,                    # 任务分解（纯计算）
)
```

## 集成

- `core/chat.py` — agent_mode 启用时可用
- `core/orchestra.py` — Orchestra 可调度多智能体管道
- `tests/test_multi_agent.py` — 完整测试套件
