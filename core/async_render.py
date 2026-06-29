"""渲染/执行分离层 — 把"消费会话流 → 喂给渲染器"从 UI 层剥离出来。

本模块是 Phase 5（渲染/执行分离）的核心。它的目标：

1. **执行与渲染解耦**：UI 层（`ui/mixins/shared.py:_stream_chat`）原本把
   "构建副作用 handler → 启动 renderer → for kind,payload → 异常处理" 揉成一个同步方法。
   现在把"消费任意 (kind, payload) 流并喂给 renderer"这一步抽成本模块的纯函数，
   让它既能吃同步 `ChatSession.send_stream`，也能吃异步 `AsyncChatSession.send_stream`，
   两边走**同一份副作用 handler 工厂 + 同一份渲染契约**（ui.render.StreamingRenderer）。

2. **副作用 handler 可复用**：`default_side_effect_handlers()` 把 image/video/info/confirm
   四类副作用从 `_stream_chat` 的闭包提炼为工厂，UI 接入点（同步）与未来 async 接入点
   共用，避免两份实现漂移。

3. **异常路径统一**：`PermissionError`（用户拒绝高风险工具）与 `KeyboardInterrupt`
   （中断流式）的收尾语义集中在此，保证 renderer.stop()/commit() 的落盘不变式不被破坏。

渲染契约（与 ui/render.py 完全一致，不再此处重复定义）：
- transient 预览 + 单一落盘点（commit），每个字符只落盘一次。
- 副作用是落盘边界：handler 执行前 renderer 已 commit 当前累积文本。

本模块**不**知道 ChatSession / AsyncChatSession 的存在 —— 它只认识
`(kind, payload)` 流协议与 `StreamingRenderer`，保持可被任意流式源复用。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from ui.render import StreamingRenderer

__all__ = [
    "SideEffectHandler",
    "HandlerMap",
    "default_side_effect_handlers",
    "render_session_stream",
    "render_async_session_stream",
]

# 副作用处理器签名：(kind, payload) -> None
SideEffectHandler = Callable[[str, object], None]
HandlerMap = dict[str, SideEffectHandler]


def default_side_effect_handlers() -> HandlerMap:
    """构造默认副作用 handler 集合（image/video/info/confirm）。

    返回的 dict 可直接传给 ``StreamingRenderer(side_effect_handlers=...)``。
    把 UI 层 `_stream_chat` 内的 4 个闭包提炼为单一来源，避免 sync/async
    两套接入点各自维护一份而漂移。

    约定（与 ChatSession.send_stream 的 (kind, payload) 协议对齐）：
    - ``info``   → 展示提示（show_info）
    - ``image``  → 展示图片结果 + 记录历史
    - ``video``  → 展示视频结果 / 超时警告 + 记录历史
    - ``confirm``→ 高风险工具 y/n 确认；拒绝则抛 PermissionError
    """
    # 延迟导入：本模块可能被非 UI 上下文（如 headless 测试）引用，
    # 此时 ui.display / utils.history 应可被替换，故放函数体内。
    from ui.display import (
        show_image_result,
        show_info,
        show_video_result,
        show_warning,
    )
    from utils import history

    def _on_info(kind: str, payload: object) -> None:
        show_info(payload)  # type: ignore[arg-type]

    def _on_image(kind: str, payload: object) -> None:
        img_data: dict = payload  # type: ignore[assignment]
        show_image_result(img_data)
        history.add_record("text_to_image", "chat", img_data.get("model", ""), img_data)

    def _on_video(kind: str, payload: object) -> None:
        vid_data: dict = payload  # type: ignore[assignment]
        if vid_data.get("status") == "timeout":
            show_warning(f"视频超时，进度 {vid_data.get('progress', 0):.0f}%")
        else:
            show_video_result(vid_data)
        history.add_record("text_to_video", "chat", "agnes-video-v2.0", vid_data)

    def _on_confirm(kind: str, payload: object) -> None:
        data: dict = payload  # type: ignore[assignment]
        tool = data.get("tool", "?")
        args_preview = str(data.get("args", ""))[:80]
        from rich.prompt import Prompt

        choice = Prompt.ask(
            f"  ⚠ {tool} ({args_preview})  [dim][y/n][/]",
            choices=["y", "n"],
            default="n",
        )
        if choice != "y":
            raise PermissionError(f"user denied {tool}")

    return {
        "info": _on_info,
        "image": _on_image,
        "video": _on_video,
        "confirm": _on_confirm,
    }


def _dispatch_to_renderer(renderer: StreamingRenderer, kind: str, payload: Any) -> None:
    """把单个 (kind, payload) 分派给 renderer（text → append，其余 → 副作用边界）。

    与 StreamingRenderer._dispatch 同语义，但显式暴露为本模块的入口，
    让"渲染/执行分离"的调用方不需要依赖 renderer 的私有方法。
    """
    if kind == "text":
        renderer.append_text(payload)  # type: ignore[arg-type]
    else:
        renderer.run_side_effect(kind, payload)


def render_session_stream(
    renderer: StreamingRenderer,
    stream: Iterator[tuple[str, Any]],
    *,
    on_permission_denied: Callable[[PermissionError], None] | None = None,
    on_interrupt: Callable[[KeyboardInterrupt], None] | None = None,
) -> str:
    """消费**同步**会话流并渲染到 renderer，返回最终累积文本。

    等价于 ``for kind, payload in stream: renderer._dispatch(kind, payload)``，
    但额外统一了异常路径与 renderer 生命周期收尾：

    - **PermissionError**（高风险工具被拒绝）：调用 ``on_permission_denied``
      （默认空操作）后正常返回，会话不中止。renderer 已在副作用边界前 commit。
    - **KeyboardInterrupt**（用户中断）：调用 ``on_interrupt``（默认空操作），
      **不落盘残余**（stop 擦除 transient 浮层），然后重新传播异常 —— 保持与
      旧 `_stream_chat` 一致的"中断即丢弃当前不完整输出"语义。

    本函数**不负责** renderer.start()/stop() 的生命周期 —— 调用方负责
    （通常用 ``with StreamingRenderer(...) as r: render_session_stream(r, stream)``），
    因为 badge 头、路由提示等"流开始前"的落盘动作属于 UI 层职责。

    Args:
        renderer: 已注入副作用 handler 的 StreamingRenderer（调用方负责 start）。
        stream: 同步迭代器，yield ``(kind, payload)`` 元组。
        on_permission_denied: 高风险工具被拒绝时的回调（如 show_warning）。
        on_interrupt: Ctrl+C 时的回调（如回滚不完整 assistant 消息）。

    Returns:
        renderer.buffer —— 本次流渲染的累积全文（含已落盘部分），便于调用方
        做后处理（如评分、历史记录）。
    """
    try:
        for kind, payload in stream:
            _dispatch_to_renderer(renderer, kind, payload)
    except PermissionError as e:
        # 用户拒绝高风险工具：友好提示，不中止会话。
        # renderer 在 run_side_effect 内部已 commit 当前文本，状态自洽。
        if on_permission_denied is not None:
            on_permission_denied(e)
    except KeyboardInterrupt as e:
        # 中断路径：擦除 transient 浮层，不落盘残余（保持旧行为）。
        # 不在此 commit()——调用方 finally 里若再 stop()/commit() 是空安全操作。
        if on_interrupt is not None:
            on_interrupt(e)
        raise

    return renderer.buffer


async def render_async_session_stream(
    renderer: StreamingRenderer,
    astream: AsyncIterator[tuple[str, Any]],
    *,
    on_permission_denied: Callable[[PermissionError], None] | None = None,
    on_interrupt: Callable[[KeyboardInterrupt], None] | None = None,
) -> str:
    """消费**异步**会话流并渲染到 renderer，返回最终累积文本。

    与 ``render_session_stream`` 行为完全一致（同一渲染契约、同一异常路径），
    仅迭代方式从 ``for`` 换成 ``async for``。

    关键不变式：渲染本身是同步纯渲染操作（append_text/commit/run_side_effect
    均无 I/O），异步性完全来自上游 astream（如 AsyncChatSession.send_stream）。
    因此本函数不会在事件循环里阻塞任何 await 点——每个 delta 到达即同步落盘，
    保证 transient 预览的刷新节奏与同步版一致。

    Args:
        renderer: 已注入副作用 handler 的 StreamingRenderer（调用方负责 start）。
        astream: async 迭代器，yield ``(kind, payload)`` 元组。
        on_permission_denied: 高风险工具被拒绝时的回调。
        on_interrupt: Ctrl+C 时的回调。

    Returns:
        renderer.buffer —— 本次流渲染的累积全文。
    """
    try:
        async for kind, payload in astream:
            _dispatch_to_renderer(renderer, kind, payload)
    except PermissionError as e:
        if on_permission_denied is not None:
            on_permission_denied(e)
    except KeyboardInterrupt as e:
        if on_interrupt is not None:
            on_interrupt(e)
        raise

    return renderer.buffer
