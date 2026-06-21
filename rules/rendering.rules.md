---
default-active: true
---
# 显示层契约 — 输出不重复

## 动机
历史 bug：流式渲染（rich.Live + console.print）在回复结束时把前缀重复打印到屏幕。
根因：Live 默认非 transient，stop() 固化旧快照；finally 又 console.print 全量 buf → 前缀重叠。

## 契约（DNA）
所有增量文本渲染必须遵循 ui.render.StreamingRenderer 的不变式：
1. Live 全程 transient=True，预览是临时浮层，stop() 不固化。
2. 用 flushed_len 追踪已落盘前缀，commit() 只打未落盘的尾部，每字符只打一次。
3. 副作用（info/image/video）是落盘边界：先 commit 固化文本，再展示副作用。
4. 禁止裸 console.print(delta, end="") 流式打印（绕过去重）。
5. 禁止在 Live.stop() 后再 console.print(Markdown(全量buf))（会重复前缀）。

## AI 行为规范（注入 system prompt）
- 直接回答，不要重复用户的问题
- 不要在 3 轮内重复相同内容
- 不要逐字复述已有的上下文
- 回答尽量在 2 段以内，简洁到位
- 避免无意义的寒暄和套话

## 测试守卫
- tests/test_render.py — StreamingRenderer 契约直接测试（17 用例）
- tests/test_stream_chat_dedup.py — _stream_chat 端到端去重测试（5 用例）
