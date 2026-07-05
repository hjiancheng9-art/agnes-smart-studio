# GPT 正反方思辨结果 — 5 Bug 裁决 + 修复记录

## GPT 看走眼的 Bug
- **Bug 4** (spinner 异常不停止): 实际 `_spinner.stop()` 已在 `finally` 块中，异常路径正常归位。**GPT 误判，未修。**

## 已修复的 Bug

### Bug 1 (P1) — stream_start 强制 pin ✅
- `stream_start(role, *, force_pin=True)` 新增 `force_pin` 参数
- 默认 `True` 保持向后兼容（用户消息强制滚底）
- 未来命令类输出可传 `force_pin=False` 不打断用户滚动
- 文件: `message_pane.py`

### Bug 5 (P1) — activity_log 清空语义 ✅
- `_submit_user_message` 中的 `_log_clear()` 已移除
- `_send_image` 中的 `_log_clear()` 已移除
- 仅保留 `Ctrl+L` 键绑定的手动清除
- `_activity_log` 现在是 session 级 500 条操作流水
- 文件: `tui_v2.py`

### Bug 3 (P2) — 空状态 renderer 缓存 ✅
- 新增 `_empty_render_cache` 字段
- `_render()` 中缓存 `_empty_renderer()` 结果，避免每 80ms 重复渲染像素画
- `set_empty_renderer()` 和 `clear()` 时失效缓存
- 文件: `message_pane.py`

### Bug 2 (P2) — 全量 render 性能
- GPT 建议暂不优化，先加性能指标。**暂缓。**

### Textual 迁移
- GPT 支持：暂不迁移，单独分支预研。**暂缓。**

## 对话纪律
每次和 GPT 聊架构必须正反方思辨摆立场，禁止抛软问题。已归档到 `memory/gpt_dialogue_style.md`。
