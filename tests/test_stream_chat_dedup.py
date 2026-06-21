"""Regression test for the "爱重复输出" (repeating output) bug in
ui.mixins.shared.SharedMixin._stream_chat.

Root cause: the old finally-block re-printed the whole buffer via
`console.print(Markdown(buf))` whenever `_render_counter > 0`, but the Live
region had ALREADY fixated an older snapshot of buf. Result: the tail of the
answer appeared twice on screen.

This test fakes the stream (no API) and asserts every distinct chunk is
committed to the captured console exactly once.
"""
import sys
import types
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console


def _make_shared():
    """Build a minimal SharedMixin instance with a CAPTURING console.

    We swap the module-level `console` in BOTH ui.display and ui.mixins.shared
    so that all console.print output (including show_info which uses
    ui.display.console) flows into a single string we can inspect.
    A fresh Console (no force_terminal, no color legacy) keeps captured text clean.
    """
    import ui.display as display_mod
    import ui.mixins.shared as shared_mod

    captured = StringIO()
    fake_console = Console(file=captured, force_terminal=False, color_system=None, width=120)
    # Patch BOTH: shared_mod.console (used by _stream_chat) and
    # display_mod.console (used by show_info/show_warning/show_image_result etc.)
    shared_mod.console = fake_console
    display_mod.console = fake_console
    # history.add_record is called on image/video; stub it out
    shared_mod.history = MagicMock()

    # SharedMixin cooperates via MRO; instantiating it alone is enough since
    # _stream_chat only uses self for nothing beyond method lookup.
    instance = shared_mod.SharedMixin()
    return instance, captured, fake_console


class _FakeSession:
    """Fake ChatSession yielding a scripted stream of (kind, payload)."""

    def __init__(self, events):
        self._events = list(events)
        self.messages = []

    def send_stream(self, user_text):
        yield from self._events


def _capture_text(captured: StringIO) -> str:
    """Strip Rich's transient artifacts; return the committed plain text."""
    return captured.getvalue()


class TestStreamChatNoDuplicateOutput:
    """每个文本字符必须被固化到屏幕恰好一次。"""

    def test_plain_text_not_duplicated(self):
        """最简单的回归：纯文本流不应把末尾重复打印。

        旧 bug：回复结束时 _render_counter 落在 1..3（约 75% 概率），
        finally 又 console.print(Markdown(buf))，导致尾部重复。
        """
        shared, captured, _ = _make_shared()
        # 5 个 chunk，总长使 _render_counter 在结束时为 1（5 % 4 = 1），
        # 正是旧 bug 的触发条件。
        session = _FakeSession([("text", "你好"), ("text", "，"), ("text", "世界"),
                                ("text", "！"), ("text", "这是答案。")])

        shared._stream_chat(session, "hi")

        out = _capture_text(captured)
        # 关键断言：旧 bug 会把"已 live.update 固化的前缀"再 console.print 一遍，
        # 所以"你好，世界！"（前 4 个 chunk 拼成的固化快照）会重复 2 次。
        # 修复后：transient 预览不固化，前缀只由 _commit 落盘一次。
        assert out.count("你好，世界！") == 1, f"前缀被重复打印（旧 bug 形态）！\n---CAPTURED---\n{out}"
        assert out.count("这是答案。") == 1, f"末尾内容重复了！\n---CAPTURED---\n{out}"

    def test_text_emitted_exactly_once_per_chunk(self):
        """每个独立 chunk 的文本在屏幕上只出现一次。"""
        shared, captured, _ = _make_shared()
        chunks = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
        session = _FakeSession([("text", c) for c in chunks])

        shared._stream_chat(session, "x")

        out = _capture_text(captured)
        for c in chunks:
            assert out.count(c) == 1, f"chunk {c!r} 出现了 {out.count(c)} 次（应为 1）\n{out}"

    def test_render_counter_zero_path(self):
        """chunk 数刚好是 _RENDER_EVERY_N 的倍数时也不应重复（旧代码 _render_counter==0 不会重复，
        这里仍覆盖以防止回归到反方向）。"""
        shared, captured, _ = _make_shared()
        # 8 个 chunk，8 % 4 == 0
        session = _FakeSession([("text", f"块{i}") for i in range(8)])

        shared._stream_chat(session, "x")

        out = _capture_text(captured)
        assert out.count("块7") == 1, f"块7 重复了\n{out}"

    def test_info_side_effect_does_not_reprint_text(self):
        """info 是落盘边界：前面已固化的文本不应在 info 后再被打印一遍。"""
        shared, captured, _ = _make_shared()
        session = _FakeSession([
            ("text", "前半段。"),
            ("info", "中间提示"),
            ("text", "后半段。"),
        ])

        shared._stream_chat(session, "x")

        out = _capture_text(captured)
        assert out.count("前半段。") == 1, f"info 边界导致前半段重复\n{out}"
        assert out.count("后半段。") == 1, f"后半段重复\n{out}"
        assert "中间提示" in out

    def test_empty_stream_no_output(self):
        """空流不应打印任何内容（防御 None / 空字符串）。"""
        shared, captured, _ = _make_shared()
        session = _FakeSession([])
        shared._stream_chat(session, "x")
        assert _capture_text(captured) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
