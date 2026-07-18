"""TUI Control Plane Integration — 连接 Control Plane 与 TUI v2

用法：在 ui/tui_v2.py 的 CRUXApp 中：
    from ui.tui_control import TuiControlMixin

    class CRUXApp(TuiControlMixin, ...):
        ...
"""

from __future__ import annotations

import threading
import time
from typing import Any

from core.control_plane import (
    control,
)


class TuiControlMixin:
    """TUI Control Plane 混入类 —— 为 CRUXApp 添加控制通道能力。

    提供：
    - 消息发送改为 pending → committed（2 秒撤销窗口）
    - Ctrl+Z 撤销 pending 消息
    - Ctrl+C 取消当前 run（不退出 TUI）
    - Esc 暂停当前 run
    - 执行中插话走 priority queue
    - 状态栏显示 pending 倒计时
    """

    # Dynamic attrs set by subclass — declared for type checking
    message_pane: Any = None  # type: ignore[assignment]
    _state_lock: Any = None  # type: ignore[assignment]
    _streaming: bool = False
    _log_append: Any = None  # type: ignore[assignment]
    _shorten: Any = None  # type: ignore[assignment]
    _thinking: bool = False
    _queue_input_while_streaming: Any = None  # type: ignore[assignment]
    _worker_thread: Any = None  # type: ignore[assignment]
    _stream_response: Any = None  # type: ignore[assignment]

    # ── 消息发送改造 ──

    def _submit_with_control(self, text: str) -> None:
        """替代 _submit_user_message — 先走 pending 窗口。"""
        text = (text or "").strip()
        if not text:
            return

        # 显示在消息面板
        self.message_pane.append_message("user", text)

        # 判断是否正在 streaming
        with self._state_lock:
            is_streaming = self._streaming

        if is_streaming:
            # 执行中 → 走优先插话
            control().priority_message(text)
            self._log_append(("→", "class:activity-info", f"优先插话入队: {self._shorten(text, 60)}"))
            self._queue_input_while_streaming(text)
            return

        # 空闲 → 走 pending 窗口
        msg = control().send_message(text)
        self._pending_msg_id = msg.id
        self._pending_text = text

        self._log_append(
            (
                "→",
                "class:activity-info",
                f"待发送 ({control().outbox.UNDO_WINDOW_MS / 1000:.0f}s 可撤销): {self._shorten(text, 30)}",
            )
        )

        # 启动定时器自动提交
        self._start_pending_timer()

    def _start_pending_timer(self) -> None:
        """启动 pending 消息自动提交定时器。"""
        if getattr(self, "_pending_timer", None) is not None:
            return

        def wait_and_commit():
            try:
                remaining = control().get_pending_timer()
                time.sleep(remaining if remaining > 0 else 2.0)
                # Commit the specific pending message by ID (not pending[0]
                # which may be a different message if user sent multiple).
                msg_id = getattr(self, "_pending_msg_id", None)
                if msg_id and control().outbox.get_pending():
                    control().outbox.commit(msg_id)
                    msg_text = getattr(self, "_pending_text", "")
                    self._log_append(("→", "class:activity-info", f"消息已发送: {self._shorten(msg_text, 60)}"))
                    with self._state_lock:
                        self._thinking = True
                        self._streaming = True
                    # Don't clobber a live worker thread.
                    old = getattr(self, "_worker_thread", None)
                    if old is not None and old.is_alive():
                        return
                    self._worker_thread = threading.Thread(
                        target=self._stream_response,
                        args=(msg_text,),
                        daemon=True,
                        name="stream-response",
                    )
                    self._worker_thread.start()
            finally:
                # Clear the timer reference so the next message can start a new one.
                self._pending_timer = None

        self._pending_timer = threading.Thread(target=wait_and_commit, daemon=True, name="pending-timer")
        self._pending_timer.start()

    def _undo_pending(self) -> bool:
        """撤销 pending 消息。返回是否成功撤销。"""
        msg_id = getattr(self, "_pending_msg_id", None)
        if not msg_id:
            return False
        if control().retract(msg_id):
            self._log_append(("→", "class:activity-warn", "消息已撤销"))
            # Remove the last message from the pane (user pending message).
            self.message_pane.pop_last_message()
            self._ui(self.message_pane._auto_scroll)
            self._pending_msg_id = None
            self._pending_text = ""
            return True
        return False

    # ── 控制事件响应 ──

    def _cancel_run(self) -> None:
        """取消当前 run（Ctrl+C）。"""
        if not control().runs.is_running:
            # 没在运行 → 取消 worker 的 streaming
            self._cancel_current_response()
            return

        # 发送 cancel control event
        control().cancel_run("用户请求取消")
        self._log_append(("→", "class:activity-warn", "用户请求取消当前执行"))

        with self._state_lock:
            self._cancel_requested = True

    def _pause_run(self) -> None:
        """暂停当前 run（Esc）。"""
        if not control().runs.is_running:
            return

        control().pause_run("用户请求暂停")
        self._log_append(("→", "class:activity-warn", "用户请求暂停当前执行"))

    def _resume_run(self) -> None:
        """恢复暂停的 run。"""
        if not control().runs.is_paused:
            return

        control().runs.resume()
        self._log_append(("→", "class:activity-info", "执行已恢复"))

    # ── 状态栏 ──

    def _get_control_status(self) -> str:
        """获取 Control Plane 状态文本（供底部显示）。"""
        return control().get_status_line()

    # ── 快捷键绑定（供 _setup_keybindings 调用） ──

    def _bind_control_keys(self, kb) -> None:
        """绑定 Control Plane 快捷键。

        Ctrl+Z    撤销 pending 消息
        Ctrl+C    取消当前 run（不退出 TUI）
        Esc       暂停当前 run
        Ctrl+Y    恢复暂停的 run（可选）
        """

        # Ctrl+Z: 撤销 pending 消息
        @kb.add("c-z")
        def _(event):
            if self._undo_pending():
                return
            # 没有 pending 消息时按 Ctrl+Z 无效果

        # Ctrl+C: 取消当前 run（不退出 TUI）
        @kb.add("c-c")
        def _(event):
            self._cancel_run()

        # Esc: 暂停当前 run
        @kb.add("escape")
        def _(event):
            self._pause_run()

        # Ctrl+Y: 恢复暂停的 run
        @kb.add("c-y")
        def _(event):
            self._resume_run()
