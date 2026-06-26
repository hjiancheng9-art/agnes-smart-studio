# 供应商 + 韧性子系统 — Failover · Circuit Breaker · Recovery

> 多供应商自动故障转移 + 熔断器 + 失败剧本自动恢复。

## 子系统一览

| 模块 | 职责 | 行数 |
|------|------|------|
| `core/provider.py` | 供应商注册表 + 自动 failover | ~200 |
| `core/resilience.py` | 熔断器 / 重试 / 退避策略 | ~150 |
| `core/recovery.py` | 失败剧本 — 结构化错误恢复 | ~120 |

## core/provider.py — 供应商管理

### 设计

CRUX 支持多个 LLM 供应商，当一个不可用时自动切换到下一个：

```python
class ProviderRegistry:
    """供应商注册表 — 按优先级排序，支持自动 failover"""

    def register(name, model, api_key, base_url, priority)
    def get(model) -> ProviderInfo       # 查询供应商
    def failover(model) -> ProviderInfo  # 切换到下一个可用供应商
    def list_providers() -> list
```

### 内置供应商

| 供应商 | 模型 | 优先级 |
|--------|------|--------|
| CRUX AI | crux-pro | 最高 |
| DeepSeek | deepseek-v4-pro | 高 |
| SiliconFlow | kimi | 中 |
| Qwen3-Coder 30B | local CUDA (llama-server) | 低（本地兜底） |

### 集成点
- `core/client.py` — 每次 API 调用通过 ProviderRegistry 选择供应商
- `core/chat.py` — `/model` 命令切换
- 失败时自动 failover 到下一个供应商

## core/resilience.py — 韧性策略

```python
class CircuitBreaker:
    """熔断器 — 连续失败 N 次后暂停调用，等待冷却期"""
    def __init__(threshold=5, cooldown=60)
    def call(fn, *args)  # 熔断时直接返回 None 或抛出
    def is_open -> bool   # 当前是否熔断

class RetryPolicy:
    """指数退避重试"""
    def __init__(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def execute(fn, *args)  # 自动重试
```

### 设计原则
- 指数退避 + jitter 避免惊群
- 可配置阈值/冷却期
- 每个 Provider 独立熔断器

## core/recovery.py — 失败剧本

```python
class RecoveryPlan:
    """结构化恢复策略"""
    def __init__(steps: list[RecoveryStep])

class RecoveryStep:
    """单步恢复 — action + condition"""
    # action: "retry" | "fallback_model" | "reduce_context" | "abort"
    # condition: "timeout" | "rate_limit" | "server_error" | "context_overflow"
```

### 恢复策略

| 错误类型 | 恢复动作 |
|----------|----------|
| 超时 | 指数退避重试 → 切换供应商 |
| 限速 | 等待 + 降频 → 切换供应商 |
| 服务器错误 | 切换供应商 → 本地模型兜底 |
| 上下文溢出 | 压缩上下文 → 截断历史 |

### 集成点
- `core/client.py` — API 调用失败时触发 RecoveryPlan
- `core/chat.py` — send_stream 错误恢复
- `core/executor.py` — 步骤执行失败恢复
