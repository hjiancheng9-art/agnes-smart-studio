# TUI 第二轮迭代 — 5 个交互升级 (GPT 正反方思辨结果)

## 迭代 1 (P1) — Alt+Enter 换行不稳定 ✅
- `@kb.add("escape", "c-m")` → `@kb.add("escape", "enter")`
- 用 `escape, enter` 替代 `alt-enter`，更贴近终端实际输入
- 文件: `tui_v2.py`

## 迭代 2 (P1) — streaming 期间 ↑/↓ 误触历史 ✅
- 新增 `Condition(lambda: self._streaming)` 过滤器 `_is_streaming`
- streaming 期间 ↑/↓ 只移动光标，不触发 Buffer history
- Enter 已由 `_thinking` 守卫拦截（已有逻辑）
- 文件: `tui_v2.py`

## 迭代 3 (P1) — activity 栏从 1 行升级到 3 行可展开 ✅
- 默认 3 行（collapsed），F8 展开到 10 行（expanded）
- `_activity_expanded=False`, `_activity_collapsed_height=3`, `_activity_expanded_height=10`
- height lambda 根据 expanded 状态动态切换
- 文件: `tui_v2.py`

## 迭代 4 (P1) — resize 后像素画错位 ✅
- 空状态缓存 key 增加 `render_info.window_width`
- 新增 `invalidate_empty_cache()` 方法
- `clear()` 时同时失效 cache key
- 文件: `message_pane.py`

## 迭代 5 (P1) — 三套 UI 共存治理 ✅
- `agnes_tui.py` 顶部加 DEPRECATED 标记
- `terminal_app.py` 不存在（已废弃）
- 统一入口指向 `tui_v2.py`
- 当前不物理删除，等 Textual 决策后再清理

## 验证
- 35/35 测试通过
- 语法编译通过
- 14 项检查点全部确认
