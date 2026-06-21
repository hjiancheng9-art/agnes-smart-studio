"""StreamingRenderer — 流式渲染的单一落盘契约。

这是"输出不重复"DNA 的代码层固化。所有增量文本渲染（chat / plan / agent）
必须经由此类，不得直接用裸 ``console.print(delta, end="")`` 或在 Live 旁
再手动 console.print —— 那正是历史"爱重复输出"bug 的根因。

契约不变式（违反任一即 bug，由 tests/test_render.py 守护）：
1. Live 全程 ``transient=True``：预览是临时浮层，stop() 时自动擦除，绝不固化。
2. ``_flushed_len`` 记录已通过 console.print 落盘的 buf 前缀长度；
   ``commit()`` 只打印尚未落盘的尾部 ``buf[flushed_len:]``，保证每个字符只落盘一次。
3. 副作用（info/image/video）是落盘边界：先 ``commit()`` 固化已累积文本，再展示副作用。
4. ``__exit__`` 兜底 ``commit()`` 一次，收住末尾未刷新的增量；无增量时空操作，绝不重复。

设计原则：
- 渲染器只认识 console + 文本 + 副作用回调，不知道 ChatSession / history 的存在，
  保持可被任意流式源（send_stream / chat_stream）复用。
- 副作用处理通过 handlers 注入，调用方决定 image/video 如何展示与记录。
"""

from __future__ import annotations

from typing import Callable

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

__all__ = ["StreamingRenderer", "default_render_console"]

# 默认用 ui.display 的全局 console，保持与既有渲染行为一致
def default_render_console() -> Console:
    from ui.display import console
    return console


# 副作用处理器签名：(kind, payload) -> None。
# info/image/video 三类；调用方可只注册其中一部分，未注册的 kind 会被忽略。
SideEffectHandler = Callable[[str, object], None]


class StreamingRenderer:
    """transient 预览 + 单一落盘点的流式渲染器。

    用法::

        with StreamingRenderer(console) as r:
            for kind, payload in stream_source:
                if kind == "text":
                    r.append_text(payload)
                else:
                    r.run_side_effect(kind, payload)

    或手动管理生命周期（与历史 _stream_chat 等价）::

        r = StreamingRenderer(console); r.start()
        try: ...
        finally: r.stop()

    两者都保证：每个字符恰好落盘一次。
    """

    # 每 N 个 text chunk 才刷新一次 Live 预览（纯性能优化，与落盘正确性无关）
    RENDER_EVERY_N = 4

    def __init__(
        self,
        console: Console | None = None,
        *,
        refresh_per_second: int = 12,
        side_effect_handlers: dict[str, SideEffectHandler] | None = None,
    ) -> None:
        self.console = console or default_render_console()
        self._refresh = refresh_per_second
        self._handlers = side_effect_handlers or {}
        self._live: Live | None = None
        self._buf = ""
        self._flushed_len = 0  # 已固化到屏幕的 buf 前缀长度
        self._render_counter = 0

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> "StreamingRenderer":
        self._live = self._new_live("")
        self._live.start()
        return self

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def __enter__(self) -> "StreamingRenderer":
        return self.start()

    def __exit__(self, *exc) -> None:
        # 收尾兜底：固化末尾未刷新的增量（无增量时空操作，绝不重复打印）。
        # 注意：先 stop() 擦除 transient 浮层，再 commit() 落盘。
        self.stop()
        self.commit()

    # ── 核心操作 ──────────────────────────────────────────────

    def append_text(self, chunk: str) -> None:
        """累积一段文本增量并节流刷新 transient 预览（不落盘）。"""
        if not chunk:
            return
        self._buf += chunk
        self._render_counter += 1
        if self._render_counter >= self.RENDER_EVERY_N and self._live is not None:
            self._live.update(Markdown(self._buf))
            self._render_counter = 0

    def commit(self) -> None:
        """单一落盘点：把尚未固化的尾部 buf 打印一次（每个字符只打印一遍）。

        幂等：连续调用两次，第二次 tail 为空，空操作。
        """
        tail = self._buf[self._flushed_len:]
        if tail:
            self.console.print(Markdown(tail))
            self._flushed_len = len(self._buf)

    def run_side_effect(self, kind: str, payload: object) -> None:
        """副作用是落盘边界：先固化已累积文本，再展示副作用，最后重建预览。

        未注册 handler 的 kind 仅触发落盘边界（commit + 重建预览），不报错。
        """
        # 边界：停浮层 → 落盘 → 展示副作用 → 重建浮层
        self.stop()
        self.commit()
        handler = self._handlers.get(kind)
        if handler is not None:
            handler(kind, payload)
        # 重建预览：用当前完整 buf（已落盘部分不再重复打印，因为 commit 用 flushed_len 守卫）
        self._live = self._new_live(self._buf)
        self._live.start()
        self._render_counter = 0

    # ── 内部 ──────────────────────────────────────────────────

    def _new_live(self, content: str) -> Live:
        # transient=True 是契约核心：预览浮层，stop() 时不向屏幕固化，由 commit() 统一落盘
        return Live(
            Markdown(content),
            console=self.console,
            refresh_per_second=self._refresh,
            vertical_overflow="visible",
            transient=True,
        )

    # ── 只读视图（供测试断言）──────────────────────────────────

    @property
    def buffer(self) -> str:
        """已累积的全部文本（含已落盘与未落盘）。"""
        return self._buf

    @property
    def flushed_len(self) -> int:
        """已落盘前缀长度。"""
        return self._flushed_len
