# Agnes Smart Studio 优化升级方案

> 基于两轮实战数据（traces.jsonl 188 轮 + cost_log 575 次调用）+ 10 个已修 bug 的完整排查
> 制定日期：2026-06-19 · 状态：✅ 全部实施完毕

## 一、现状诊断（数据驱动）

### 1.1 已修复的 bug（10 个，地基已稳）

| 类别 | 修复 |
|------|------|
| 卡壳主因 | history 全量读写、HTTP 超时×重试叠加、压缩位置、subprocess 无超时、LSP 阻塞读 |
| 隐藏问题 | gallery 读旧格式、迁移崩溃丢数据、failover 后 engine 失效 |
| 实战回归 | ContentPolicyError 未导入、676万token撑爆上下文 |

**结论：崩溃类、卡死类问题已清零。剩余的是"慢"和"浪费"。**

### 1.2 实测性能画像

**单轮对话耗时分布（188 轮）：**
- 中位数：6.7 秒
- P75：~30 秒
- P95：~75 秒
- 最长：352 秒

**`/biz` 审计一轮的构成（实测）：**
- 18 轮工具调用 = 18 次 chat_stream 往返
- 25 次 chat_stream + 11 次 chat（其中压缩占大头）
- read_file 被调用 7 次（触发死循环检测）
- DeepSeek-v4-pro 单次响应 50-76 秒

### 1.3 三大效率瓶颈（升级目标）

| # | 瓶颈 | 证据 | 影响 |
|---|------|------|------|
| **A** | 工具结果无缓存，重复调用全量重算 | read_file 7 次、无任何工具缓存机制 | 浪费轮次 + 浪费 token + 浪费时间 |
| **B** | 压缩调用过于频繁（每轮都触发） | `/biz` 一轮 11 次压缩 LLM 调用 | 额外 11 次网络往返 |
| **C** | 模型响应慢时无择速/无预判 | DeepSeek 单次 50-76s，无超时降级 | 用户长时间盯着转圈 |

---

## 二、升级方案（分三个优先级）

每个优化独立可交付、可验证、可回滚。建议按 P0→P1→P2 顺序实施。

---

### P0：工具结果缓存（最高性价比）

**目标：消除重复工具调用的浪费**

**问题**：`read_file`/`search_files`/`list_files`/`count_lines` 等只读工具，同一参数在同一会话内被反复调用，每次都全量执行。实测 read_file 被调 7 次。

**方案**：在 `_dispatch_tool` 层加一个**会话级 LRU 缓存**，仅缓存幂等只读工具。

```
core/chat.py - _dispatch_tool:
  _READ_ONLY_TOOLS = {"read_file", "list_files", "search_files",
                      "count_lines", "tree_dir", "env_check", ...}
  _tool_cache: dict[sig, (result, timestamp)]  # 会话级，sig = name+args

  执行前：
    if name in _READ_ONLY_TOOLS:
      sig = hash(name + args_json)
      if sig in _tool_cache and not 文件被修改:
        return _tool_cache[sig]  # 命中，0 耗时
    执行后：
      _tool_cache[sig] = result
```

**缓存失效策略**（关键，避免脏读）：
- `read_file`：记录文件 mtime，下次命中前比对，mtime 变了就失效
- `list_files`/`tree_dir`：TTL 30 秒
- `search_files`/`count_lines`：TTL 60 秒（结果稳定）

**预期收益**：
- `/biz` 这类审计任务：read_file 从 7 次 → 1 次（6 次命中缓存）
- 减少 6 次工具执行 + 6 次工具结果塞进上下文（省 token）
- 实测这类任务总耗时预计降 30-40%

**改动范围**：`core/chat.py`（`_dispatch_tool` 加缓存层）、新增 `core/tool_cache.py`
**风险**：低（只读工具幂等性明确，mtime 失效避免脏读）

**✅ 实施记录**：
- 新建 `core/tool_cache.py`：`ToolResultCache` 类，LRU 缓存 128 条，线程安全
- 17 个只读工具可缓存（read_file/search_files/glob_files/list_files/tree_dir/count_lines/env_check/git_*/web_*/check_file_exists 等）
- 文件类工具 mtime 失效，目录/扫描类 30s TTL，Git 类 15s TTL，网络类 120s TTL，env_check 600s TTL
- 7 个写操作工具执行后清空整个缓存（run_bash/run_python/write_file/edit_file/git_add_commit/pip_install/download_file）
- chat.py `_dispatch_tool` 集成：缓存命中时跳过工具执行+hooks+tracing，直接返回结果
- 可观测性：`cache_hit` attribute + `tool.{name}.cache_hit` metric

---

### P1：压缩调用优化（减少网络往返）

**目标：把 11 次压缩调用降到 1-2 次**

**问题**：当前每轮工具循环都调 `auto_compress_if_needed`，虽然内部 `needs_compression` 廉价，但一旦超阈值就触发一次完整 LLM 调用。`/biz` 一轮触发了 11 次。

**方案**：两层优化

**优化1：纯本地截断优先，LLM 摘要兜底**

```
core/agent.py - auto_compress_if_needed:
  if needs_compression(messages):
    # 第一层：纯本地，0 网络开销
    messages = self._truncate_messages(messages)  # 已实现
    # 截断后若仍超阈值，才触发 LLM 摘要
    if self.needs_compression(messages):
      messages = self.compress(messages, client, model)
```

当前 `_truncate_messages` 把单条限 8000 字符，大部分情况截断后就不超阈值了，**根本不需要 LLM 摘要调用**。

**优化2：压缩结果缓存**

同一批消息的摘要结果缓存，避免短时间内重复摘要。

**预期收益**：
- 压缩 LLM 调用从 11 次 → 0-1 次（截断兜住大部分）
- `/biz` 一轮省 10 次网络往返 × 平均 3 秒 = 省 ~30 秒

**改动范围**：`core/agent.py`（`auto_compress_if_needed` 改两级）、`core/chat.py`（压缩调用点不变）
**风险**：低（截断已验证，摘要只是少触发）

**✅ 实施记录**：
- `auto_compress_if_needed` 重写为两级：Tier 1 免费（`_truncate_messages`），Tier 2 代价（LLM compress）仅在 Tier 1 不足时触发
- 截断后 `needs_compression` 仍超阈值才调 LLM，绝大多数情况 Tier 1 已解决（大工具结果被截断到 8000 字符）

---

### P2：智能供应商择速（体验优化）

**目标：模型慢时自动降级或预警**

**问题**：DeepSeek-v4-pro 单次 50-76 秒，用户只能干等。切换 Agnes 可能更快但用户不会手动切。

**方案**：供应商健康度评分 + 自动建议

```
core/provider.py - 新增 ProviderHealth:
  记录每个供应商的近期平均响应时间、成功率
  当 active 供应商连续 3 次响应 > 30s：
    yield ("info", "⚠️ DeepSeek 当前响应较慢（均 65s），可 /provider switch agnes 试试")
```

**不做自动切换**（避免打断用户意图），只做**主动提示**，让用户决定。

**加分项：首字节超时**

```
core/client.py - chat_stream:
  首字节（第一个 delta）若 15 秒内未到 → 标记慢
  连续慢则累积健康分
```

**预期收益**：
- 不减少绝对耗时，但让用户**知情**（知道是模型慢，不是卡死）
- 引导用户在慢时主动切换，实际体验改善

**改动范围**：`core/provider.py`（新增健康追踪）、`core/chat.py`（提示注入）
**风险**：极低（只读 + 提示，不改变核心流程）

**✅ 实施记录**：
- `ProviderState` 新增 `_latencies` 字段（每个供应商最近 10 次响应延迟的 deque）
- `record_latency()` 记录每次 LLM 调用耗时，`health_hint()` 在连续 3 次以上平均 >15s 时返回警告
- `chat.py` `_send_stream_inner`：首轮 LLM 调用前检查 `health_hint()`，有则 yield `("info", hint)`
- `chat.py` `_send_stream_inner`：每次 LLM 流完成后记录 `_llm_elapsed` 到 ProviderState
- 不自动切换，仅提示用户可用 `/provider` 手动切换

---

## 三、实施计划

| 阶段 | 内容 | 改动文件 | 验证方式 | 预计工作量 |
|------|------|---------|---------|-----------|
| **P0** | 工具结果缓存 | chat.py + 新 tool_cache.py | 重跑 `/biz`，确认 read_file 只读 1 次 | 中 |
| **P1** | 压缩两级优化 | agent.py | `/biz` 一轮，确认压缩调用 ≤1 次 | 小 |
| **P2** | 供应商健康提示 | provider.py + chat.py | DeepSeek 慢时出现提示 | 小 |

每阶段独立交付，每阶段交付后：
1. 跑 `test_smoke.py` 确认无回归
2. 实战跑一轮 `/biz`，对比 traces 耗时
3. 对比 cost_log 的调用次数

---

## 四、明确不做的（避免过度设计）

| 不做 | 原因 |
|------|------|
| 多模型并行竞速（同时调 3 个供应商取最快） | 成本 3 倍，ROI 低 |
| 把 read_file 改成全文索引/向量检索 | 过度工程，缓存已解决 80% 问题 |
| 重写工具调度为 DAG 执行 | 架构大改，风险高，当前串行+并行已够用 |
| 自动切换供应商 | 打断用户意图，提示即可 |

---

## 五、验收标准

实施完 P0+P1 后，重跑 `/biz` 应满足：

| 指标 | 当前 | 目标 |
|------|------|------|
| read_file 调用次数 | 7 | ≤ 2 |
| 压缩 LLM 调用 | 11 | ≤ 1 |
| chat_stream 总往返 | 25 | ≤ 18 |
| 单轮 P95 耗时 | 75s | ≤ 45s |
| 崩溃/token爆炸 | 0（已修） | 0 |

---

## 六、决策点（需用户确认）

1. **P0 的缓存失效策略**：mtime 比对（精确但需文件系统调用）vs TTL（简单但可能短暂脏读）——建议 mtime
2. **P2 是否要"自动切换"**：当前方案只提示不切，是否需要加一个 `/provider auto` 模式？
3. **实施节奏**：一次性全做（P0+P1+P2），还是先 P0 验证再继续？
