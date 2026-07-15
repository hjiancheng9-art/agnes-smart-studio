# 架构说明：`core/lore/` 与 `core/intimate_slots/`

> 面向新贡献者的导航文档。目的：解释这两个「命名抽象度高」的模块到底是什么、
> 谁在用、以及哪些是活代码、哪些是历史残留。

*生成日期：2026-07-15*

---

## TL;DR

| 模块 | 角色 | 状态 |
|------|------|------|
| `core/intimate_slots/` | **门面层**（thin re-export），暴露 7 个「贴身装备」子系统 | ✅ 活代码，被 `beast_wiring.py` 在会话启动时装配 |
| `core/lore/intimate_slots/` | **实现层**，7 个子系统的真实逻辑 | ✅ 活代码，被门面层 re-export |
| `core/lore/claude_dna.py`<br>`core/lore/codebuddy_dna.py` | DNA 叙事 prompt（`get_*_dna_prompt()`） | ⚠️ 事实死代码：prompt 从未被注入，仅目录 mtime 参与缓存指纹 |

---

## 一、两层结构：门面 + 实现

`intimate_slots`（贴身装备）是一组「随身系统能力」，采用**门面/再导出模式**分成两层：

```
core/intimate_slots/talisman.py        ← 门面（thin re-export）
    from core.lore.intimate_slots.talisman import circuit
    __all__ = ["circuit"]

core/lore/intimate_slots/talisman.py   ← 实现（真实逻辑：熔断器状态机）
    class CircuitState: ...
    circuit = CircuitBreaker(...)
```

**为什么分两层？**
- 对外统一入口 `from core.intimate_slots import <slot>`，调用方无需知道实现藏在 `lore/` 下。
- `core/intimate_slots/__init__.py` 用 `__getattr__` 懒加载子模块，避免启动时全部导入。
- 实现层放在 `lore/`（叙事/世界观层）下，与其他 lore 内容归置在一起。

> 如果将来要重构，删掉门面层需要同步改所有 `from core.intimate_slots.*` 的调用点
> （主要是 `core/beast_wiring.py`）。不要只删一层。

---

## 二、7 个贴身装备（slots）

| Slot | 中文名 | 职责 | 入口 |
|------|--------|------|------|
| `talisman` | 护符 · 熔断保护 | 连续 N 次 API 失败自动熔断，cool-down 后半探恢复 | `talisman.circuit.check(provider)` |
| `inner_armor` | 内甲 · 密钥保险柜 | API Key 落盘加密（Windows DPAPI / Linux keyring fallback），支持从环境变量迁移 | `vault.get/set/delete(key)` |
| `backpack` | 背包 · 配置快照/回滚 | 一键快照 models.json / tools.json / sessions / memory，可回滚；最多保留 10 份 | `backpack.snapshot(label)` / `backpack.rollback(name)` |
| `belt` | 腰带 · 流式数据管道 | 统一数据管道 source→transform→filter→buffer→sink，串起工具输出与终端渲染 | `pipeline.push(data, event)` / `pipeline.flush()` |
| `left_ring` | 左戒 · 遥测日志 | 全量工具调用结构化遥测（事件/工具名/延迟/错误/provider/tokens），落 JSONL | `telemetry.log(...)` |
| `right_ring` | 右戒 · 自我修复 | 系统健康评分 0-100（内存 + 磁盘 + 熔断状态），健康 <70 触发保护模式 | `healer.check()` |
| `cloak` | 斗篷 · 隐私脱敏 | 敏感信息自动脱敏（API Key / 邮箱 / 手机号 / IP / JWT），递归处理 dict/list | `cloak.sanitize(text)` / `cloak.sanitize_dict(d)` |

行为说明的权威来源是 `core/intimate_slots/__init__.py` 里的 `INTIMATE_SLOTS_PROMPT`
和 `get_intimate_prompt()`（供 system prompt 注入）。

---

## 三、运行时装配：`core/beast_wiring.py`

会话启动时，`beast_wiring.wire_all()`（由 `chat.py` 调用）把各 slot 挂到事件总线：

```python
# talisman：错误 → 记熔断；tool:after → 记成功/失败
bus.on("error",      lambda **kw: circuit.record_failure(kw.get("provider", "default")))
bus.on("tool:after", lambda error=None, **kw: circuit.record_success(None) if error is None
                                              else circuit.record_failure(str(error)))

# inner_armor：从环境变量迁移密钥
vault.migrate_from_env()

# backpack：会话启动即快照
backpack.snapshot("session_start")

# belt + cloak：给管道加一个「隐私脱敏」阶段
pipeline.add_stage("privacy", lambda d: cloak.sanitize(str(d)))

# left_ring：tool:after → 记遥测
bus.on("tool:after", lambda ...: telemetry.log("tool_call", ...))

# right_ring：启动时跑一次健康检查
healer.check()
```

每个 wiring 都包在 `try/except _INIT_SAFE` 里——**单个 slot 初始化失败不会阻断启动**，
只记 `logger.exception`。

---

## 四、`lore/` 里的 DNA 文件（`claude_dna.py` / `codebuddy_dna.py`）

这两个文件定义了 `CLAUDE_DNA_SYSTEM_PROMPT` / `CODEBUDDY_DNA_SYSTEM_PROMPT`
和对应的 `get_*_dna_prompt()` 取值函数。

**现状：事实上的死代码（prompt 维度）。**
- `get_claude_dna_prompt()` / `get_codebuddy_dna_prompt()` 在整个代码库中**从未被调用**。
- 实际被冷加载注入的 lore 是 `core.seven_beasts_fusion` 和 `core.golden_finger`
  （见 `core/chat_prompt.py` 的 `_COLD_LORE`），不是这两个 DNA 文件。

**唯一的间接作用：缓存指纹。**
`core/chat_prompt.py::_get_injections_fingerprint()` 会遍历 `core/lore/` 目录下所有
`.py` 的 mtime 生成 MD5 指纹，用于 `build_system_prompt` 的自动缓存失效。所以这两个
文件的**存在与 mtime**会参与指纹，但**内容不进 prompt**。

> **清理建议（可选，需人工确认）**：若确认不再需要 Claude/CodeBuddy 的 DNA 叙事，
> 可删除这两个文件。删除不会影响 prompt 输出，只会改变一次缓存指纹（下次启动自动重建）。
> 本文档只做记录，不擅自删除。

---

## 五、给贡献者的速查

- 想加一个新的「贴身能力」：在 `core/lore/intimate_slots/` 写实现，在
  `core/intimate_slots/` 加同名 thin re-export，在 `__init__.py` 的 `__all__`
  和 `INTIMATE_SLOTS_PROMPT` 补一段，再到 `beast_wiring.py` 挂事件。
- 想知道某个 slot 具体怎么用：看 `core/intimate_slots/__init__.py` 顶部 docstring。
- 想改熔断/密钥/快照等真实逻辑：改 `core/lore/intimate_slots/*.py`，**不要**改门面层。
- 看到 `claude_dna` / `codebuddy_dna`：它们不影响 prompt，别误以为是活跃的人格注入。
