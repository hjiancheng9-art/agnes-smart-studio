# chat.py 拆解方案 (2093行 → ~1200行)

## 现状分析

`chat.py` 已有 10 个 `chat_*.py` 子模块，使用 5 种成熟重构模式。但文件内仍有两大巨型方法和一处重复代码：

| 区块 | 行数 | 位置 | 当前状态 |
|------|------|------|----------|
| `send_stream()` | ~525L | 890-1414 | 嵌入 ChatSession，访问大量 self 属性 |
| `_run_tool_calls()` | ~283L | 1490-1772 | 嵌入 ChatSession，访问 self.tvl/self.tools/self.messages |
| 模型别名构建器 | ~80L | 110-179 | `chat_model_helpers.py` 已存在但未被使用！ |

## 重构方案

### 步骤 1：消除重复代码 —— `chat_model_config.py`

`core/chat_model_helpers.py` 已有 `build_model_aliases()`/`build_model_info()`，但 `chat.py:124-149` 有完全重复的实现（`_build_model_aliases`/`_build_model_info`）。

- 删除 chat.py 中重复代码
- 改用 `chat_model_helpers` 的版本
- 保持 `MODEL_ALIASES`/`MODEL_INFO` 全局变量和惰性初始化逻辑

**变更量**：约 50 行删除，5 行新增

### 步骤 2：提取流式管道 —— `chat_stream.py`

将 `send_stream()` 提取为模块级生成器函数：

```python
def _send_stream_impl(self: ChatSession, user_text: str, image_url: str | None = None):
    """send_stream 核心实现，已从 ChatSession 提取"""
    # 原 525 行逻辑
```

- 使用 **Pattern C（函数注入）**——与 `chat_tool_dispatch.py` / `chat_vision.py` 一致
- ChatSession 保留瘦包装（~5行）：
  ```python
  def send_stream(self, user_text, image_url=None):
      yield from _send_stream_impl(self, user_text, image_url)
  ```
- `chat.py` 底部添加：`ChatSession.send_stream = _send_stream_impl`（但目前已有函数注入先例，更推荐瘦包装）

**变更量**：~530 行移出，~5 行保留

### 步骤 3：提取工具执行循环 —— `chat_stream_tools.py`

将 `_run_tool_calls()` 同样提取为模块级函数：

```python
def _run_tool_calls_impl(
    self: ChatSession, tool_calls, executed_sigs, executed_cache, loop_idx=0
):
    # 原 283 行逻辑
```

- 同样使用 Pattern C
- ChatSession 保留瘦包装（~4行）

**变更量**：~285 行移出，~4 行保留

### 步骤 4：收尾清理

- 顶部 import 移到对应子模块（如 `compress_tool_result` 当前在方法内懒加载，迁移后放到子模块顶部）
- `_dispatch_tool_async` (行 2078-2089) 保持原位，它已经是模块级函数
- 更新 `chat.py` 中的 `__all__` 确保向后兼容

## 最终效果

```
chat.py:  2093 行 → ~1200 行 (-43%)
  + chat_stream.py       (~540 行，新增)
  + chat_stream_tools.py (~290 行，新增)
  + chat_model_helpers  (已存在，激活使用)
```

## 向后兼容

- 所有外部调用方（`core/__init__.py`, `crux_studio.py`, `ui/tui_*.py`, 测试文件）**零改动**
- `ChatSession` 的公开 API 不变：`send_stream()`, `_run_tool_calls()` 签名和行为完全一致
- `__all__` 保持不变

## 风险控制

- 每个步骤独立提交，可单独回滚
- 每个步骤后跑 `ruff check && ruff format --check` 验证
- 每个步骤后跑相关测试：`pytest tests/test_chat_critical.py tests/test_chat_routing.py -x`