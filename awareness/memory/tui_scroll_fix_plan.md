# CRUX Studio TUI 界面修复方案（来自 GPT 架构诊断）

## 问题 1：鼠标滚轮不能滚动消息

**根因**: `Keys.ScrollUp/ScrollDown` 不是鼠标滚轮的主路径。鼠标滚轮要走 `UIControl.mouse_handler`。

**修法** (`message_pane.py`):
1. 在自定义 `UIControl` 子类（如 `MessagePaneControl`）加 `mouse_handler`：
   - 导入 `from prompt_toolkit.mouse_events import MouseEventType`
   - `mouse_event.event_type == MouseEventType.SCROLL_UP` → `pane.scroll_up(lines=3, user_initiated=True)` + `get_app().invalidate()`
   - `mouse_event.event_type == MouseEventType.SCROLL_DOWN` → 同理
2. 确保 `Window(content=self.control)` 用的是自定义 control，不是 `FormattedTextControl`

## 问题 2：键盘多个按键失效

**根因**: 输入框 `Buffer` 优先抢占 `↑/↓/Tab/Escape/Ctrl+C`，全局 `kb.add("up")` 不可靠。

**修法** (`tui_v2.py`):
- 消息滚动改用：`PageUp` / `PageDown` / `Ctrl+Home` / `Ctrl+End` / `Alt+↑` / `Alt+↓`
- 普通 `↑/↓` 不绑（留给输入框做历史/多行编辑）
- `kb.add("pageup")` → `scroll_page_up(user_initiated=True)`
- `kb.add("pagedown")` → `scroll_page_down(user_initiated=True)`
- `kb.add("c-home")` → `scroll_to_top(user_initiated=True)`
- `kb.add("c-end")` → `scroll_to_bottom(user_initiated=True)`
- `kb.add("escape", "up")` → `scroll_up(lines=3, user_initiated=True)` (Alt+↑)

## 问题 3：自动滚底冲突

**根因**: 流式输出无脑 `scroll_to_bottom()`，用户看历史时被拽回底部。

**修法** (`message_pane.py`):
新增 pinned 模型:
- `_pinned = True` — 用户在底部，新内容自动滚底
- `_scroll_offset = 0` — 距离底部的行数
- `_last_content_height = 0` — 上次内容总行数
- `_viewport_height = 0` — 视口高度

核心方法:
- `scroll_up(lines, user_initiated)` → `_scroll_offset += lines`，若 `_scroll_offset > 0` 则 `_pinned = False`
- `scroll_down(lines, user_initiated)` → `_scroll_offset -= lines`，若 `_scroll_offset == 0` 则 `_pinned = True`
- `scroll_to_bottom(user_initiated)` → `_scroll_offset = 0`, `_pinned = True`
- `on_content_changed()` → 仅当 `_pinned` 时 `scroll_to_bottom()`，否则 `_clamp_scroll()`
- `_create_content()` → 用 `_scroll_offset` 计算可见行

## 关键原则

1. **滚动逻辑收敛到 message_pane.py**，tui_v2.py 只负责绑定键盘调 pane 方法
2. 鼠标滚轮走 `UIControl.mouse_handler`，不依赖 `Keys.ScrollUp/ScrollDown`
3. 流式输出不再直接调 `scroll_to_bottom()`，改调 `on_content_changed()`
