"""Contract tests for core.async_render — the render/exec separation layer.
Phase 5 把"消费会话流 → 喂给 StreamingRenderer"从 UI 层剥离到 core.async_render。
本测试守护两条核心不变式：
1. **sync/async 契约一致性**：`render_session_stream` 与 `render_async_session_stream`
   对同一份 (kind, payload) 序列必须产生**逐字节相同**的落盘输出。这是"同一 DNA"
   的强断言——任何只在一条路径引入的差异都会被此测试捕获。
2. **异常路径不变式**：
   - PermissionError（高风险工具被拒）→ 调 on_permission_denied，不中止，正常返回。
   - KeyboardInterrupt（中断）→ 调 on_interrupt 后**重新传播**异常（保持旧行为）。
3. **副作用边界**：side-effect handler 在 renderer commit 当前文本后才执行
   （由 StreamingRenderer.run_side_effect 保证，此处验证回调时机正确）。
风格对齐：与 tests/test_async_chat.py 一致，async 测试用同步测试方法 +
asyncio.get_event_loop().run_until_complete()，不用 @pytest.mark.asyncio。
"""

import asyncio
import io
import sys
from pathlib import Path

import pytest
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.async_render import (
    default_side_effect_handlers,
    render_async_session_stream,
    render_session_stream,
)
from ui.render import StreamingRenderer


# ── Helpers ────────────────────────────────────────────────
def _run(coro):
    """同步运行 async 协程。
    用 asyncio.run 而非 get_event_loop().run_until_complete：
    pytest-asyncio 的 @pytest.mark.asyncio 测试在 teardown 时会清空
    当前线程的 event loop（asyncio.set_event_loop(None)），导致后续
    get_event_loop() 抛 RuntimeError。asyncio.run 每次新建+关闭 loop，
    不受全局 loop 状态污染。
    """
    return asyncio.run(coro)


def _make_renderer(handlers=None):
    """创建带捕获 console 的 StreamingRenderer。返回 (renderer, captured)。"""
    captured = io.StringIO()
    c = Console(file=captured, force_terminal=False, color_system=None, width=120)
    r = StreamingRenderer(c, side_effect_handlers=handlers or {})
    return r, captured


def _sync_stream(events):
    """把 events 列表包成同步生成器。"""
    yield from events


async def _async_stream(events):
    """把 events 列表包成 async 生成器。"""
    for kind, payload in events:
        yield kind, payload


# ── default_side_effect_handlers ───────────────────────────
class TestDefaultSideEffectHandlers:
    """验证默认副作用 handler 集合的结构。"""

    def test_returns_all_four_kinds(self):
        h = default_side_effect_handlers()
        assert set(h.keys()) == {"info", "image", "video", "confirm"}

    def test_handlers_are_callable(self):
        h = default_side_effect_handlers()
        for kind, fn in h.items():
            assert callable(fn), f"{kind} handler 不可调用"

    def test_info_handler_uses_show_info(self):
        """info handler 应调 show_info（通过捕获 console 验证文本落盘）。"""
        import ui.display as display_mod

        captured = io.StringIO()
        fake = Console(file=captured, force_terminal=False, color_system=None, width=120)
        orig = display_mod.console
        display_mod.console = fake
        try:
            h = default_side_effect_handlers()
            h["info"]("info", "测试提示文本")
        finally:
            display_mod.console = orig
        assert "测试提示文本" in captured.getvalue()

    def test_confirm_handler_raises_on_reject(self):
        """confirm handler 在用户拒绝时应抛 PermissionError。"""
        h = default_side_effect_handlers()
        from unittest.mock import patch

        with patch("rich.prompt.Confirm.ask", return_value=False), pytest.raises(PermissionError):
            h["confirm"]("confirm", {"tool": "git_push", "args": {}})

    def test_confirm_handler_passes_on_accept(self):
        """confirm handler 在用户同意时不抛异常。"""
        h = default_side_effect_handlers()
        from unittest.mock import patch

        with patch("rich.prompt.Confirm.ask", return_value=True):
            h["confirm"]("confirm", {"tool": "git_push", "args": {}})  #


# ── sync/async 契约一致性（核心）──────────────────────────
class TestSyncAsyncContractParity:
    """同一份 (kind, payload) 序列，sync 与 async 两条路径落盘输出必须完全一致。"""

    def test_plain_text_identical_output(self):
        events = [("text", "你好"), ("text", "，"), ("text", "世界"), ("text", "！"), ("text", "答案。")]
        r_sync, cap_sync = _make_renderer()
        r_async, cap_async = _make_renderer()
        r_sync.start()
        render_session_stream(r_sync, _sync_stream(events))
        r_sync.stop()
        r_sync.commit()
        r_async.start()
        _run(render_async_session_stream(r_async, _async_stream(events)))
        r_async.stop()
        r_async.commit()
        assert cap_sync.getvalue() == cap_async.getvalue(), (
            f"sync/async 纯文本落盘不一致！\nsync:\n{cap_sync.getvalue()}\nasync:\n{cap_async.getvalue()}"
        )

    def test_with_side_effects_identical_output(self):
        """含 info 副作用边界的序列，两条路径输出一致。"""
        handlers = {"info": lambda k, p: None}  #
        events = [("text", "前半。"), ("info", "提示"), ("text", "后半。")]
        r_sync, cap_sync = _make_renderer(handlers)
        r_async, cap_async = _make_renderer(handlers)
        r_sync.start()
        render_session_stream(r_sync, _sync_stream(events))
        r_sync.stop()
        r_sync.commit()
        r_async.start()
        _run(render_async_session_stream(r_async, _async_stream(events)))
        r_async.stop()
        r_async.commit()
        assert cap_sync.getvalue() == cap_async.getvalue()
        # 两边都应只落盘一次前半/后半
        assert cap_sync.getvalue().count("前半。") == 1
        assert cap_sync.getvalue().count("后半。") == 1

    def test_buffer_returned_identical(self):
        """两条路径返回的 renderer.buffer 必须相同。"""
        events = [("text", "ABC"), ("text", "DEF")]
        r_sync, _ = _make_renderer()
        r_async, _ = _make_renderer()
        r_sync.start()
        buf_sync = render_session_stream(r_sync, _sync_stream(events))
        r_sync.stop()
        r_async.start()
        buf_async = _run(render_async_session_stream(r_async, _async_stream(events)))
        r_async.stop()
        assert buf_sync == "ABCDEF"
        assert buf_async == "ABCDEF"

    def test_empty_stream_identical(self):
        """空流：两条路径都不产生输出。"""
        events = []
        r_sync, cap_sync = _make_renderer()
        r_async, cap_async = _make_renderer()
        r_sync.start()
        render_session_stream(r_sync, _sync_stream(events))
        r_sync.stop()
        r_sync.commit()
        r_async.start()
        _run(render_async_session_stream(r_async, _async_stream(events)))
        r_async.stop()
        r_async.commit()
        assert cap_sync.getvalue() == ""
        assert cap_async.getvalue() == ""


# ── 异常路径：PermissionError ──────────────────────────────
class TestPermissionErrorPath:
    """PermissionError（高风险工具被拒）应调回调、不中止、正常返回。"""

    def test_sync_permission_denied_calls_callback(self):
        denied = []

        def _deny(e):
            denied.append(str(e))

        def _stream_with_confirm():
            yield "text", "即将执行"
            yield "confirm", {"tool": "git_push", "args": {}}

        # confirm handler 拒绝 → 抛 PermissionError
        r, _ = _make_renderer(
            {"confirm": lambda k, p: (_ for _ in ()).throw(PermissionError("用户拒绝了 git_push 的执行"))}
        )
        r.start()
        # 不应抛异常（被 render_session_stream 捕获并转回调）
        buf = render_session_stream(
            r,
            _stream_with_confirm(),
            on_permission_denied=_deny,
        )
        r.stop()
        r.commit()
        assert "即将执行" in buf
        assert len(denied) == 1
        assert "git_push" in denied[0]

    def test_async_permission_denied_calls_callback(self):
        denied = []

        def _deny(e):
            denied.append(str(e))

        async def _astream_with_confirm():
            yield "text", "即将执行"
            yield "confirm", {"tool": "git_push", "args": {}}

        r, _ = _make_renderer(
            {"confirm": lambda k, p: (_ for _ in ()).throw(PermissionError("用户拒绝了 git_push 的执行"))}
        )
        r.start()
        buf = _run(
            render_async_session_stream(
                r,
                _astream_with_confirm(),
                on_permission_denied=_deny,
            )
        )
        r.stop()
        r.commit()
        assert "即将执行" in buf
        assert len(denied) == 1

    def test_permission_without_callback_still_returns(self):
        """没传 on_permission_denied 时，PermissionError 被吞掉，正常返回。"""

        def _stream():
            yield "text", "前"
            yield "confirm", {"tool": "x"}

        r, _ = _make_renderer({"confirm": lambda k, p: (_ for _ in ()).throw(PermissionError("nope"))})
        r.start()
        buf = render_session_stream(r, _stream())  #
        r.stop()
        assert "前" in buf


# ── 异常路径：KeyboardInterrupt ────────────────────────────
class TestKeyboardInterruptPath:
    """KeyboardInterrupt 应调 on_interrupt 后重新传播异常。"""

    def test_sync_interrupt_reraises(self):
        interrupted = []

        def _on_int(e):
            interrupted.append(True)

        def _stream_with_interrupt():
            yield "text", "部分"
            raise KeyboardInterrupt()

        r, _ = _make_renderer()
        r.start()
        with pytest.raises(KeyboardInterrupt):
            render_session_stream(
                r,
                _stream_with_interrupt(),
                on_interrupt=_on_int,
            )
        r.stop()
        assert len(interrupted) == 1

    def test_async_interrupt_reraises(self):
        interrupted = []

        def _on_int(e):
            interrupted.append(True)

        async def _astream_with_interrupt():
            yield "text", "部分"
            raise KeyboardInterrupt()

        r, _ = _make_renderer()
        r.start()
        with pytest.raises(KeyboardInterrupt):
            _run(
                render_async_session_stream(
                    r,
                    _astream_with_interrupt(),
                    on_interrupt=_on_int,
                )
            )
        r.stop()
        assert len(interrupted) == 1

    def test_interrupt_without_callback_still_reraises(self):
        """没传 on_interrupt 时，KeyboardInterrupt 仍重新传播。"""

        def _stream():
            raise KeyboardInterrupt()

        r, _ = _make_renderer()
        r.start()
        with pytest.raises(KeyboardInterrupt):
            render_session_stream(r, _stream())
        r.stop()


# ── 副作用边界时机 ─────────────────────────────────────────
class TestSideEffectBoundaryTiming:
    """副作用 handler 执行时，renderer 应已 commit 当前累积文本。"""

    def test_handler_sees_committed_text(self):
        """info handler 触发时，前面累积的文本应已落盘（flushed_len 推进）。"""
        seen_flushed = []

        def _on_info(kind, payload):
            seen_flushed.append(r.flushed_len)

        r, cap = _make_renderer({"info": _on_info})
        r.start()
        render_session_stream(
            r,
            _sync_stream(
                [
                    ("text", "前半段文本。"),
                    ("info", "提示"),
                    ("text", "后半段文本。"),
                ]
            ),
        )
        r.stop()
        r.commit()
        # handler 触发时 flushed_len 应已推进到 "前半段文本。" 的长度
        assert len(seen_flushed) == 1
        assert seen_flushed[0] == len("前半段文本。")
        # 最终全量落盘，无重复
        out = cap.getvalue()
        assert out.count("前半段文本。") == 1
        assert out.count("后半段文本。") == 1

    def test_multiple_side_effects_each_commits(self):
        """连续多个副作用边界，每个都触发 commit。"""
        seen = []

        def _on_info(kind, payload):
            seen.append((payload, r.flushed_len))

        r, cap = _make_renderer({"info": _on_info})
        r.start()
        render_session_stream(
            r,
            _sync_stream(
                [
                    ("text", "A"),
                    ("info", "1"),
                    ("text", "B"),
                    ("info", "2"),
                    ("text", "C"),
                ]
            ),
        )
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("A") == 1
        assert out.count("B") == 1
        assert out.count("C") == 1
        # flushed_len 应单调递增：1(A) → 2(AB)
        assert seen[0][1] == 1  #
        assert seen[1][1] == 2  #


# ── text dispatch 语义 ─────────────────────────────────────
class TestTextDispatchSemantics:
    """text 走 append_text，其余走 run_side_effect（与 _dispatch_to_renderer 一致）。"""

    def test_empty_text_chunk_ignored(self):
        """空字符串 text chunk 不产生输出（append_text 的守卫）。"""
        r, cap = _make_renderer()
        r.start()
        render_session_stream(r, _sync_stream([("text", ""), ("text", "")]))
        r.stop()
        r.commit()
        assert cap.getvalue() == ""

    def test_unknown_kind_treated_as_side_effect(self):
        """未知 kind 走副作用路径（run_side_effect 内部对无 handler 容错）。"""
        r, cap = _make_renderer()
        r.start()
        # 不应抛异常，且触发落盘边界
        render_session_stream(
            r,
            _sync_stream(
                [
                    ("text", "前"),
                    ("unknown_kind", "whatever"),
                    ("text", "后"),
                ]
            ),
        )
        r.stop()
        r.commit()
        out = cap.getvalue()
        assert out.count("前") == 1
        assert out.count("后") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
