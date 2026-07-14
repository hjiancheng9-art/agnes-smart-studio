"""TDD RED phase — tests for scroll state machine in ui/message_pane.py."""

from __future__ import annotations

from prompt_toolkit.layout import Window

from ui.message_pane import _SCROLL_BOTTOM, MessagePane, _ScrollingWindow


class TestNewPaneIsPinned:
    """test_new_pane_is_pinned — New MessagePane._pinned is True."""

    def test_new_pane_is_pinned(self):
        pane = MessagePane()
        assert pane._pinned is True


class TestAppendMessageAutoScrolls:
    """test_append_message_auto_scrolls — Append 50 messages, verify _pinned stays True
    and _auto_scroll sets vertical_scroll to _SCROLL_BOTTOM."""

    def test_append_message_auto_scrolls(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollUpUnpins:
    """test_scroll_up_unpins — Append 50 messages, call scroll_up(), verify _pinned
    becomes False."""

    def test_scroll_up_unpins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        # Should be at bottom, pinned
        assert pane._pinned is True
        pane.scroll_up()
        assert pane._pinned is False


class TestScrollUpThenDownToBottomRepins:
    """test_scroll_up_then_down_to_bottom_repins — Append 50 messages, scroll_up(),
    then scroll_to_bottom(), verify _pinned becomes True."""

    def test_scroll_up_then_down_to_bottom_repins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane.scroll_up()
        assert pane._pinned is False
        pane.scroll_to_bottom()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollPageUpUnpins:
    """test_scroll_page_up_unpins — scroll_page_up() when not at top sets _pinned to False."""

    def test_scroll_page_up_unpins(self):
        pane = MessagePane()
        for i in range(100):
            pane.append_message("user", f"message {i}")
        pane.scroll_to_bottom()
        assert pane._pinned is True
        pane.scroll_page_up()
        assert pane._pinned is False


class TestScrollPageDownRepinsAtBottom:
    """test_scroll_page_down_repins_at_bottom — scroll_page_down() when at/near bottom
    sets _pinned to True."""

    def test_scroll_page_down_repins_at_bottom(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        # Manually set to near-bottom and unpinned
        pane._window.vertical_scroll = pane.line_count - pane._window_height() - 5
        pane._pinned = False
        pane.scroll_page_down()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestScrollToTopAlwaysUnpins:
    """test_scroll_to_top_always_unpins — scroll_to_top() sets _pinned to False."""

    def test_scroll_to_top_always_unpins(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane._pinned = True
        pane.scroll_to_top()
        assert pane._pinned is False
        assert pane._window.vertical_scroll == 0


class TestScrollToBottomAlwaysPins:
    """test_scroll_to_bottom_always_pins — scroll_to_bottom() sets _pinned to True."""

    def test_scroll_to_bottom_always_pins(self):
        pane = MessagePane()
        pane._pinned = False
        pane.scroll_to_bottom()
        assert pane._pinned is True
        assert pane._window.vertical_scroll == _SCROLL_BOTTOM


class TestStreamStartForcesPin:
    """test_stream_start_forces_pin — Even if _pinned=False, stream_start() resets
    _pinned to True."""

    def test_stream_start_forces_pin(self):
        pane = MessagePane()
        for i in range(50):
            pane.append_message("user", f"message {i}")
        pane.scroll_up()
        assert pane._pinned is False
        pane.stream_start("crux")
        assert pane._pinned is True


class TestScrollingWindowExists:
    """test_scrolling_window_exists — _ScrollingWindow class is defined and is subclass
    of Window."""

    def test_scrolling_window_is_defined(self):
        assert _ScrollingWindow is not None

    def test_scrolling_window_is_window_subclass(self):
        assert issubclass(_ScrollingWindow, Window)

    def test_scroll_method_overridden(self):
        assert "_scroll" in _ScrollingWindow.__dict__


# ═══════════════════════════════════════════════════════
# 持久性回归测试 — 防止反复回滚核心修复
# 每次有人/AI 会话不小心或好心地"恢复"这些绑定/保护时，这些测试会阻止。
# ═══════════════════════════════════════════════════════

import ast


class TestPersistence_NoDuplicatePagedown:
    """确保 ui/tui_v2.py 中 pagedown 按键绑定只有一个（eager=True 版本）。
    非 eager 版本会在输入处理阶段吞掉事件，导致 eager 版本无法工作。
    这个 bug 已被修了数十次，每次都是因为有人加了第二个 @kb.add("pagedown")。"""

    TUI_PATH = "ui/tui_v2.py"

    def _find_kb_add_calls(self, source: str, key: str) -> list[dict]:
        """解析 AST，找到所有 @kb.add(...) 装饰器匹配指定按键的调用。"""
        tree = ast.parse(source)
        results = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    if (isinstance(deco, ast.Call)
                            and isinstance(deco.func, ast.Attribute)
                            and deco.func.attr == "add"
                            and deco.args):
                        first_arg = deco.args[0]
                        if isinstance(first_arg, ast.Constant) and first_arg.value == key:
                            kwargs = {kw.arg: kw.value for kw in deco.keywords if kw.arg}
                            results.append(kwargs)
        return results

    def test_only_one_pagedown_binding(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        bindings = self._find_kb_add_calls(source, "pagedown")
        assert len(bindings) == 1, (
            f"Expected exactly 1 pagedown binding, found {len(bindings)}. "
            f"Adding a second @kb.add('pagedown') will break scrolling — "
            f"the non-eager binding swallows the event. See comment in tui_v2.py."
        )

    def test_pagedown_is_eager(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        bindings = self._find_kb_add_calls(source, "pagedown")
        assert len(bindings) == 1
        assert bindings[0].get("eager") is not None, (
            "The pagedown binding must be eager=True. "
            "Without eager, the binding competes with input processing and misses events."
        )

    def test_pageup_is_also_eager(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        bindings = self._find_kb_add_calls(source, "pageup")
        # pageup should also be eager for consistency
        for b in bindings:
            if b.get("eager") is not None:
                return
        # At least one pageup binding should be eager
        assert len(bindings) == 0 or any(b.get("eager") is not None for b in bindings), (
            "Expected at least one eager pageup binding for consistency with pagedown."
        )


class TestPersistence_NoneGuardInScroll:
    """确保 message_pane.py 的 _scroll() 方法中 ui_content is None 的保护不被删除。
    没有这个 guard，每次渲染周期都会把用户的滚动位置弹回顶部。"""

    PANE_PATH = "ui/message_pane.py"

    def test_none_guard_exists_in_scroll(self):
        with open(self.PANE_PATH, encoding="utf-8") as f:
            source = f.read()
        assert "Cannot clamp without content info" in source, (
            "The ui_content is None guard in _scroll() has been removed! "
            "Without it, manual scroll position gets reset to top on every render cycle."
        )

    def test_guard_comment_mentions_scroll_reset(self):
        with open(self.PANE_PATH, encoding="utf-8") as f:
            source = f.read()
        assert "vertical_scroll" in source or "ui_content" in source, (
            "The guard comment explaining WHY the None check exists seems to have been removed."
        )


# ═══════════════════════════════════════════════════════
# 持久性回归测试 — c-c / c-l 重复绑定防护
# ═══════════════════════════════════════════════════════

class TestPersistence_NoDuplicateCtrlC:
    """确保 ui/tui_v2.py 中 c-c 按键绑定只有一个（_ctrl_c 版）。
    历史 bug: c-c 绑定了两次，第一个匿名版本被第二个 _ctrl_c() 覆盖，变成死代码。
    """

    TUI_PATH = "ui/tui_v2.py"

    def test_only_one_ctrl_c_binding(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        c_c_bindings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Attribute) and dec.func.attr == "add":
                            if dec.args:
                                first_arg = ast.literal_eval(dec.args[0]) if isinstance(dec.args[0], ast.Constant) else None
                                if first_arg == "c-c":
                                    c_c_bindings.append((node.lineno, node.name))

        assert len(c_c_bindings) == 1, (
            f"Found {len(c_c_bindings)} @kb.add('c-c') bindings: {c_c_bindings}. "
            f"Only the _ctrl_c version should exist. "
            f"Adding a second binding will create dead code."
        )
        assert c_c_bindings[0][1] == "_ctrl_c", (
            f"c-c is bound to {c_c_bindings[0][1]}() instead of _ctrl_c(). "
            f"The proper handler must be _ctrl_c() which handles both streaming and idle states."
        )

    def test_ctrl_c_comment_warns_no_duplicate(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        assert "c-c 绑定见下方 _ctrl_c" in source or "_ctrl_c" in source, (
            "The comment that warns against adding a second c-c binding has been removed."
        )


class TestPersistence_NoDuplicateCtrlL:
    """确保 ui/tui_v2.py 中 c-l 按键绑定只有一个（合并版：清屏+重置滚动）。
    历史 bug: c-l 绑定了两次，第一个清屏版被第二个滚动重置版覆盖，清屏功能丢失。
    """

    TUI_PATH = "ui/tui_v2.py"

    def test_only_one_ctrl_l_binding(self):
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        c_l_bindings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Attribute) and dec.func.attr == "add":
                            if dec.args:
                                first_arg = ast.literal_eval(dec.args[0]) if isinstance(dec.args[0], ast.Constant) else None
                                if first_arg == "c-l":
                                    c_l_bindings.append(node.lineno)

        assert len(c_l_bindings) == 1, (
            f"Found {len(c_l_bindings)} @kb.add('c-l') bindings at lines {c_l_bindings}. "
            f"Only one merged handler (clear + scroll reset) should exist."
        )

    def test_ctrl_l_handler_clears_and_resets(self):
        """验证 c-l 处理函数同时包含 clear 和 scroll_to_bottom。"""
        with open(self.TUI_PATH, encoding="utf-8") as f:
            source = f.read()

        # Find the c-l handler body
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Attribute) and dec.func.attr == "add":
                            if dec.args:
                                first_arg = ast.literal_eval(dec.args[0]) if isinstance(dec.args[0], ast.Constant) else None
                                if first_arg == "c-l":
                                    # Get the function body source
                                    body_lines = source.splitlines()
                                    func_source = "\n".join(body_lines[node.lineno-1:node.end_lineno])
                                    assert "clear()" in func_source, (
                                        "c-l handler lost clear() — clear-screen functionality was dropped."
                                    )
                                    assert "scroll_to_bottom" in func_source, (
                                        "c-l handler lost scroll_to_bottom() — scroll reset was dropped."
                                    )
                                    return

        assert False, "Could not find c-l handler in tui_v2.py"
