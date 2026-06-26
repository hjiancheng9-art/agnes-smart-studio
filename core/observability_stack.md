# 可观测性子系统 — Tracing · Metrics · Cost · Self-Audit

> 三级可观测体系：运行时追踪、成本守卫、自动审计。

## 子系统一览

| 模块 | 职责 | 行数 |
|------|------|------|
| `core/observability.py` | tracing/spans/metrics 基础设施 | ~200 |
| `core/cost_tracker.py` | Token 计费 / 预算追踪 | ~150 |
| `core/self_audit.py` | 自动诊断：bare except、裸 return、代码质量扫描 | ~120 |

## core/observability.py — 追踪与指标

```python
class Span:
    """一个追踪区间 — name、start_time、duration、attributes"""
    def __enter__/__exit__  # context manager 自动计时

class Tracer:
    """全局追踪器 — 创建 Span、收集指标"""
    def start_span(name) -> Span
    def record_metric(name, value, unit)
    def get_stats() -> dict
```

### 集成点
- `core/chat.py` — 每次 API 调用包裹 Span
- `core/executor.py` — 每个执行步骤记录 metrics
- `ui/mixins/diag.py` — `/eval` 命令读取 metrics

## core/cost_tracker.py — 成本守卫

```python
class CostTracker:
    """Token 用量 + 美元成本追踪器"""
    def record(model, input_tokens, output_tokens, cost_usd)
    def total() -> float            # 总花费
    def by_model() -> dict         # 按模型分摊
    def check_budget(budget_usd)    # 超预算预警
    def reset()                     # 重置计数
```

### 集成点
- `core/chat.py` send_stream — 每次 API 返回后 record
- `ui/mixins/diag.py` — `/cost` 命令查询
- Budget 超限时自动提醒用户

## core/self_audit.py — 自动诊断

```python
def run_audit(path=".") -> AuditReport:
    """扫描项目代码质量"""
    # 检查项:
    # - bare except 数量
    # - 裸 return 数量
    # - TODO/FIXME/HACK 标记
    # - 代码行数统计
```

### 集成点
- `core/audit_runner.py` — 统一诊断入口
- `/audit` 命令
