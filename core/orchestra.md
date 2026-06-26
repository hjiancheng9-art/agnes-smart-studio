# core/orchestra.py — 能力协调层

> 多源能力编排：解决能力冲突、组合、发现、动态切换。

## 设计背景

CRUX 的能力来自五个源头：

| Source | 来源 | 示例能力 |
|--------|------|----------|
| `CLAUDE` | Claude 推理引擎 | 推理、自修正、failover、并行执行 |
| `CODEBUDDY` | CodeBuddy 工具链 | LSP、MCP、浏览器、Git、任务管理 |
| `ZBODY` | 业务规则 | 领域逻辑、自定义工作流 |
| `AGNES` | CRUX 内置 | 生图/生视频/视觉引擎 |
| `USER` | 用户自定义 | 用户扩展技能/工具 |

## 核心抽象

```python
class Priority(Enum):
    OVERRIDE = 100   # 强制覆盖（Claude 行为规则）
    HIGH     = 80     # 用户自定义
    NORMAL   = 50     # 默认
    LOW      = 30     # 可被覆盖
    FALLBACK = 10     # 备选

class Capability:
    """一项可被编排的能力 — name + source + priority + metadata"""

class Orchestra:
    """能力注册表 + 冲突仲裁 + 动态切换"""
```

## 四大职责

1. **能力冲突仲裁** — 同名工具来自两个源时，按 Priority 选择
2. **能力组合** — 把不同源的能力编排成 pipeline
3. **能力发现** — 模型能查到当前可用的所有能力清单
4. **动态切换** — 根据任务类型自动激活/停用能力集

## 公共 API

```python
from core.orchestra import (
    Orchestra,            # 能力协调器（单例）
    get_orchestra,        # 获取全局单例
    Capability,           # 能力数据类
    CapabilitySource,     # 来源枚举
    Priority,             # 优先级枚举
)
```

## 线程安全

`Orchestra` 内部使用 `threading.Lock` 保护能力注册表，支持多线程并发访问。
