# CRUX Studio TUI — 自动升级包清单

## 本轮已自动修复 (当场修完)

| # | 模块 | 改动 | 自动升级 |
|---|------|------|---------|
| 1-1 | `message_pane.py` | `stream_start` 加 `force_pin` 参数 | ✅ |
| 1-2 | `tui_v2.py` | `_submit_user_message`/`_send_image` 移除 `_log_clear()` | ✅ |
| 1-3 | `message_pane.py` | `_empty_renderer` 缓存 | ✅ |
| 1-4 | `tui_v2.py` | `mouse_handler` 修复鼠标滚轮 | ✅ |
| 2-1 | `tui_v2.py` | Alt+Enter `escape, enter` | ✅ |
| 2-2 | `tui_v2.py` | streaming up/down 守卫 | ✅ |
| 2-3 | `tui_v2.py` | activity 3行 + F8 展开 | ✅ |
| 2-4 | `message_pane.py` | resize 空缓存失效 | ✅ |
| 2-5 | `agnes_tui.py` | 废弃标记 | ✅ |

## 下一批升级包 (预研/待做，不进自动更新)

| # | 模块 | 内容 | 状态 | 触发条件 |
|---|------|------|------|---------|
| P-1 | 全项目 | Textual spike 分支 | 📋 预研 | tui_v2 连续两版稳定后 |
| P-2 | `tui_v2.py` | render 性能计数/指标 | 📋 P2 | 出现肉眼抖动 >16ms |
| P-3 | `tui_v2.py` | 物理删除旧 UI | 📋 治理 | Textual 决策或 tui_v2 稳定 |
| P-4 | `message_pane.py` | cache key 加 height | 📋 优化 | 像素画随终端高度变化时 |
