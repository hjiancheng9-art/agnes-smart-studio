"""TUI Control Plane Integration — 连接 Control Plane 与 TUI v2

用法：在 ui/tui_v2.py 的 CRUXApp 中：
    from ui.tui_control import TuiControlMixin

    class CRUXApp(TuiControlMixin, ...):
        ...
"""

import threading
import time

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
                f"待发送 ({control().outbox.UNDO_WINDOW_MS / 1000:.0f}s 可撤销): {self._shorten(text, 60)}",
            )
        )

        # 启动定时器自动提交
        self._start_pending_timer()

    def _start_pending_timer(self) -> None:
        """启动 pending 消息自动提交定时器。"""
        if hasattr(self, "_pending_timer") and self._pending_timer:
            return

        def wait_and_commit():
            remaining = control().get_pending_timer()
            time.sleep(remaining if remaining > 0 else 2.0)
            # 检查是否已被撤销
            pending = control().outbox.get_pending()
            if pending:
                msg = pending[0]
                control().outbox.commit(msg.id)
                # 提交到 TUI 的流式响应
                self._log_append(("→", "class:activity-info", f"消息已发送: {self._shorten(msg.text, 60)}"))
                with self._state_lock:
                    self._thinking = True
                    self._streaming = True
                self._worker_thread = threading.Thread(
                    target=self._stream_response,
                    args=(msg.text,),
                    daemon=True,
                    name="stream-response",
                )
                self._worker_thread.start()

        self._pending_timer = threading.Thread(target=wait_and_commit, daemon=True, name="pending-timer")
        self._pending_timer.start()

    def _undo_pending(self) -> bool:
        """撤销 pending 消息。返回是否成功撤销。"""
        if not hasattr(self, "_pending_msg_id"):
            return False
        if control().retract(self._pending_msg_id):
            self._log_append(("→", "class:activity-warn", "消息已撤销"))
            # 从消息面板移除
            self.message_pane.messages.pop()  # 移除最后一条用户消息
            self._ui(self.message_pane._render)
            self._pending_msg_id = None
            self._pending_text = None
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
