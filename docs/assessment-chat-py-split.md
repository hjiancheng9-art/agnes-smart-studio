# 评估：`core/chat.py` 拆分可行性

> 这是一份**评估文档**，不含实际重构改动。目的：判断 1900+ 行的 `core/chat.py`
> 是否值得拆、拆哪里、按什么顺序、风险多大。结论供维护者决策。

*评估日期：2026-07-15 · 文件规模：2009 行，1 主类 `ChatSession`（约 45 方法）+ 5 个模块级函数*

---

## 一、现状盘点

`core/chat.py` 已经**做过一轮拆分**，不是完全的单体：

| 已抽出的协作单元 | 位置 |
|------------------|------|
| 开关/toggle 逻辑 | `core/chat_toggle_mixin.py`（`ChatToggleMixin`，被继承） |
| 工具分发 | `core/chat_tool_dispatch.py`（`_dispatch_tool_impl`） |
| 工具调用辅助 | `core/chat_tool_helpers.py`（merge / sanitize / normalize） |
| 视觉回退 | `core/chat_vision.py`（`_vision_fallback`） |
| system prompt 构建 | `core/chat_prompt.py`（`build_system_prompt` + 冷加载 lore） |

所以 `chat.py` 现在承载的是**会话编排核心**。剩余体量主要集中在几个大方法：

| 方法 | 约行数 | 职责 |
|------|--------|------|
| `send_stream` | ~368 | 主流式循环：failover × tool-loop × delta 三层控制流 |
| `_run_pipeline` | ~230 | 多智能体 pipeline 异步编排 |
| `_run_tool_calls` | ~228 | 执行一轮工具调用 + 校验 + 缓存 + 遥测 |
| `__init__` | ~163 | 会话构造 + **Phase 1-14 钩子注册** |
| `_finalize_outcome` | ~94 | 收尾计费 / 学习循环 / TRM 调优 |
| `sanitize_messages` | ~79 | 修复残缺 tool-call 序列（API 约束） |
| `_auto_route` | ~77 | 路由决策（provider/model/tier 切换） |
| `_try_adversarial_bypass` | ~68 | 拒答绕过重试 |

---

## 二、评估结论（TL;DR）

**值得做「低风险、按方法搬迁」的渐进拆分，不建议做「重写 send_stream」的大手术。**

- ✅ **推荐**：抽出 3 个内聚、低耦合的关注点（钩子注册、模型/路由解析、消息序列消毒），预计能减 400-500 行，风险很低。
- ⚠️ **谨慎**：`send_stream` / `_consume_stream_delta` / `_run_tool_calls` 三者共享大量生成器协议和局部状态，拆分收益有限、回归风险高，**暂不动**或仅做「提取纯函数」级别的小改。
- 🚫 **不推荐**：为了「行数好看」把 `ChatSession` 拆成多个类——它有强内聚的会话状态（`self.messages` / `self.model` / hooks），硬拆会制造跨对象状态传递的复杂度。

---

## 三、可拆分点（按 ROI 排序）

### 🟢 P1｜钩子注册 → `core/chat_hooks_setup.py`（推荐先做）

`__init__` 里有一整块 `Phase 1-14` 的钩子注册（`register_learning_hooks` /
`register_tool_interceptor` / `register_defense_hooks` / `inject_context_hooks` /
`inject_reviewer_hooks` / `inject_skill_compiler_hooks` … 每个都包 `try/except`）。

- **抽法**：`def wire_session_hooks(session) -> None`，`__init__` 里改成一行调用。
- **收益**：`__init__` 从 ~163 行降到 ~60 行；钩子编排集中一处，方便增删 Phase。
- **风险**：极低。这些钩子本就通过 `self`/全局注册，搬到函数里传 `session` 即可。
- **前置**：确认每个 `self._pN_*_hooked` 标志位没有被别处读；从 `analyze` 看仅是占位标记。

### 🟢 P2｜模型/路由解析 → `core/chat_routing.py`（推荐）

`_build_model_aliases` / `_build_model_info` / `_refresh_aliases_and_info`（模块级）+
`_resolve_default_model` / `_auto_route` / `_vision_model_chain` / `_classify_vision_complexity`
/ `_sort_within_provider` / `_text_fallback_chain`。

- **抽法**：这些大多是**纯计算/查询**，可做成接收 `session`（或更小依赖）的模块函数。
- **收益**：约 300 行迁出；路由逻辑独立可单测（现在几乎没法单独测）。
- **风险**：低-中。`_auto_route` 会改 `self.model` / provider 状态，需保留通过 `session` 回写；建议先抽纯查询部分，`_auto_route` 最后处理。

### 🟢 P3｜消息序列消毒 → `core/chat_history.py`（推荐）

`sanitize_messages`（静态）+ `restore_latest_snapshot`（classmethod）+ `_maybe_snapshot`。
这些是**会话历史 I/O**，与流式编排正交。

- **抽法**：`sanitize_messages` 已是 `@staticmethod`，几乎零成本迁出；快照读写做成模块函数。
- **收益**：约 150 行；tool-call 序列修复逻辑（API 约束相关）单独可测。
- **风险**：低。已有 `test_*` 覆盖 sanitize 行为可回归。

### 🟡 P4｜pipeline 编排 → 复用 `core/multi_agent`（谨慎）

`_run_pipeline`（~230 行）是多智能体异步编排。它已经 import 了 `core.multi_agent`，
逻辑上更应属于那一层。

- **抽法**：把 pipeline 触发/线程管理搬到 `multi_agent`，`chat.py` 只留一个薄触发点。
- **风险**：中。涉及 `threading.Thread` + `self._pipeline_result` 回填，异步生命周期要小心。
- **建议**：等 P1-P3 落地、测试网加密后再评估。

### 🔴 P5｜`send_stream` 三层循环（不推荐现在动）

`send_stream` + `_consume_stream_delta` + `_run_tool_calls` + `_finalize_outcome` 构成
**failover(while) × tool-loop(for) × delta(for)** 的生成器协议链，共享 `run_id` /
`buffer` / `_executed_signatures` / `_stream_error_break` 等大量局部状态。

- 上一轮重构已经把 delta 消费、工具执行、收尾从 `send_stream` 里提取成了子方法
  （见文件注释：「CodeBuddy/Claude/Codex 三方评分一致点名」后的拆分）。
- **再拆的收益递减**：进一步拆会把生成器协议和状态在更多函数间穿针引线，可读性不一定更好。
- **风险高**：这是热路径，任何 yield 协议错位都会导致流中断/工具丢失，且难以被单测完全覆盖。
- **建议**：只做「提取纯判定函数」的微改（如把 red-flag 检测、stream-error 判定抽成无副作用函数），**不动控制流骨架**。

---

## 四、建议的执行顺序与预期效果

```
Step 1  P3 消息消毒   （最安全，有测试兜底）      → -150 行
Step 2  P1 钩子注册   （__init__ 瘦身）           → -100 行
Step 3  P2 路由解析   （先抽纯查询，_auto_route 最后）→ -300 行
        ── 到此 chat.py 约 1400 行，且新增 3 个可单测模块 ──
Step 4  评估 P4 pipeline（视 Step1-3 后测试覆盖情况再定）
Step 5  P5 仅做纯函数微提取，不动 send_stream 骨架
```

**预期**：低风险步骤可把 `chat.py` 从 ~2000 降到 ~1400 行，同时让路由/历史/钩子三块变得**可独立单测**——这才是拆分的真正价值，而不是单纯降行数。

---

## 五、拆分前必须先补的测试（护栏）

当前 `chat.py` 的核心路径缺乏细粒度单测，直接拆有回归风险。建议**先加测试再拆**：

1. `_auto_route`：给定不同 prompt/复杂度，断言返回的 tier/provider/model（P2 护栏）
2. `sanitize_messages`：残缺 tool-call 序列的各种形态 → 断言截断点（P3 护栏，可能已部分存在）
3. `wire_session_hooks`：断言 14 个 Phase 标志位/钩子都被设置（P1 护栏）
4. `send_stream` 冒烟：用 mock client 跑一轮「文本 + 一次工具调用 + 收尾」，断言 yield 事件序列（P5 兜底，动它之前必须有）

---

## 六、一句话给决策者

> `chat.py` **不是脏乱的单体**，而是「已拆过一轮、但会话编排核心天然较大」的文件。
> 建议按 P1→P2→P3 做**低风险的关注点外迁**（顺带补路由/历史的单测），
> **不要**为了行数去重写 `send_stream` 热路径。投入产出比最高的是「让路由和历史可单测」，
> 而不是「让 chat.py 变短」。
