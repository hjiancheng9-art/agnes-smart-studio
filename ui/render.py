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

from collections.abc import Callable

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

__all__ = ["StreamingRenderer", "default_render_console"]


# 默认用 ui.display 的全局 console，保持与既有渲染行为一致
def default_render_console() -> Console:
    from ui.theme import console

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
        self._last_para_check = 0  # char offset of last paragraph boundary check

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> StreamingRenderer:
        self._live = self._new_live("")
        self._live.start()
        self._last_para_check = len(self._buf)  # reset paragraph tracker
        return self

    def stop(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def __enter__(self) -> StreamingRenderer:
        return self.start()

    def __exit__(self, *exc) -> None:
        # 收尾兜底：固化末尾未刷新的增量（无增量时空操作，绝不重复打印）。
        # 注意：先 stop() 擦除 transient 浮层，再 commit() 落盘。
        self.stop()
        self.commit()

    # ── 核心操作 ──────────────────────────────────────────────

    def append_text(self, chunk: str) -> None:
        """累积文本增量，在段落边界或节流时刷新预览。

        遇到 \\n\\n（Markdown 段落分隔）时立即刷新，让长文本按自然段落节奏输出，
        不再等全篇写完才渲染。
        """
        if not chunk:
            return
        self._buf += chunk
        self._render_counter += 1
        # 刷新条件：节流计数 或 段落边界（双换行）
        new_text = self._buf[self._last_para_check:]
        hit_para = "\n\n" in new_text
        if (self._render_counter >= self.RENDER_EVERY_N or hit_para) and self._live is not None:
            self._live.update(Markdown(self._buf))
            self._render_counter = 0
            if hit_para:
                self._last_para_check = len(self._buf)

    def commit(self) -> None:
        """单一落盘点：把尚未固化的尾部 buf 打印一次（每个字符只打印一遍）。

        幂等：连续调用两次，第二次 tail 为空，空操作。
        """
        tail = self._buf[self._flushed_len :]
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

    # ── 流消费（同步 / 异步统一入口）─────────────────────────

    def _dispatch(self, kind: str, payload: object) -> None:
        """统一分派一个 (kind, payload) 元组到 append_text / run_side_effect。

        渲染器内部约定：kind == "text" 走文本累积，其余走副作用边界。
        同步 consume_stream 与异步 consume_async_stream 共用此分派，
        保证两条路径行为完全一致（同一 DNA）。
        """
        if kind == "text":
            self.append_text(payload)  # type: ignore[arg-type]
        else:
            self.run_side_effect(kind, payload)

    def consume_stream(self, stream) -> None:
        """消费同步迭代器，逐个分派 (kind, payload) 元组。

        与 ``for kind, payload in stream: self._dispatch(...)`` 等价，
        但封装为方法让调用方只关心"把流喂给渲染器"。

        适用：ChatSession.send_stream（同步生成器）。
        异常不在此捕获——调用方负责 KeyboardInterrupt / PermissionError 处理
        与 finally 中的 stop()/commit() 收尾。
        """
        for kind, payload in stream:
            self._dispatch(kind, payload)

    async def consume_async_stream(self, astream) -> None:
        """消费 async 迭代器，逐个分派 (kind, payload) 元组。

        与 consume_stream 行为完全一致，仅迭代方式从 ``for`` 换成 ``async for``。
        契约不变式（transient + 单一落盘点 + 副作用边界）对异步流同样生效，
        因为 append_text / commit / run_side_effect 本身都是同步纯渲染操作，
        不涉及 I/O——异步性完全来自上游 astream（如 AsyncChatSession.send_stream）。

        适用：AsyncChatSession.send_stream（async 生成器）。
        异常不在此捕获——调用方负责 KeyboardInterrupt / PermissionError 处理
        与 finally 中的 stop()/commit() 收尾。
        """
        async for kind, payload in astream:
            self._dispatch(kind, payload)

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
