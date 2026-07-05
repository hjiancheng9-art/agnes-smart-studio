# TUI 滚动修复记录

## 改动内容

### message_pane.py
1. 新增 `_MessagePaneControl(FormattedTextControl)` 子类
2. 重写 `mouse_handler()` 方法，处理 `MouseEventType.SCROLL_UP / SCROLL_DOWN`
3. 鼠标滚轮事件 → `pane.scroll_up/down(lines=_SCROLL_LINE)` → 自动更新 `_pinned` 状态
4. 导入 `from prompt_toolkit.mouse_events import MouseEventType`

### tui_v2.py
1. 移除流式输出中 4 处强制 `scroll_to_bottom()` 调用
2. 保留 Ctrl+End 键绑定（L537）
3. 流式输出时的自动滚底由 `message_pane._auto_scroll()` 根据 `_pinned` 状态自行决定
4. `_pinned=True`（用户在底部）→ 新内容自动滚底
5. `_pinned=False`（用户看历史）→ 新内容不打断

## 根因
- 鼠标滚轮事件不走 `Keys.ScrollUp/ScrollDown`（那是键盘事件），要走 `UIControl.mouse_handler()`
- 流式输出无脑 `scroll_to_bottom()` 覆盖了 `_pinned=False` 状态
- `message_pane.py` 的 `_pinned` 模型已正确实现，但没被利用

## 测试验证
- `test_zcode_message_pane.py`: 17/17 passed
- `test_zcode_ui_layout.py`: 18/18 passed
