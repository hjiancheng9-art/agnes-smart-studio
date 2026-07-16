"""
TUI Dispatcher — 按 action 类型分发到 5 个渲染区
====================================================
分 5 个独立渲染出口: MessagePane / StatusBar / ToolPanel / ConfirmDialog / ErrorPanel

TUI 对接时只需要实现这 5 个 renderer 接口，不用管事件协议。
"""

from __future__ import annotations

from typing import Any


class TuiRenderer:
    """渲染器基类 — TUI 对接时继承并实现对应方法"""

    def render_message(self, run_id: str, text: str) -> None:
        raise NotImplementedError

    def render_stream_start(self, run_id: str, message: str) -> None:
        raise NotImplementedError

    def render_stream_end(self, run_id: str, message: str) -> None:
        raise NotImplementedError

    def render_error(self, run_id: str, error: str) -> None:
        raise NotImplementedError

    def render_status(self, run_id: str, status: str, phase: str, message: str) -> None:
        raise NotImplementedError

    def render_confirm(self, confirm_id: str, tool: str, message: str, risk: str) -> None:
        raise NotImplementedError

    def render_media(self, run_id: str, media_type: str, payload: dict) -> None:
        raise NotImplementedError

    def render_info(self, run_id: str, message: str) -> None:
        raise NotImplementedError

    def render_intel_analysis(self, run_id: str, payload: dict) -> None:
        raise NotImplementedError

    def render_tool_start(self, run_id: str, tool: str, args: dict) -> None:
        raise NotImplementedError

    def render_tool_result(self, run_id: str, tool: str, result: str) -> None:
        raise NotImplementedError

    def render_final(self, run_id: str, content: str) -> None:
        raise NotImplementedError

    def invalidate(self) -> None:
        """触发 UI 刷新（TUI 框架特有）"""
        pass


class TuiDispatcher:
    """TUI 分发器 — action → renderer 方法调用"""

    def __init__(self, renderer: TuiRenderer):
        self.renderer = renderer

    def dispatch(self, action: dict[str, Any]) -> None:
        """分发单个 action"""
        kind = action["type"]
        run_id = action.get("run_id", "default")

        handler = getattr(self, f"_apply_{kind}", None)
        if handler:
            handler(action)
        else:
            self.renderer.render_info(run_id, f"[{kind}] {action.get('message', '')}")

    def dispatch_batch(self, actions: list[dict[str, Any]]) -> None:
        """批量分发"""
        for action in actions:
            self.dispatch(action)
        self.renderer.invalidate()

    # ── handler 们 ──

    def _apply_stream_start(self, action: dict) -> None:
        self.renderer.render_stream_start(action["run_id"], action.get("message", ""))

    def _apply_stream_end(self, action: dict) -> None:
        self.renderer.render_stream_end(action["run_id"], action.get("message", ""))

    def _apply_append_text(self, action: dict) -> None:
        self.renderer.render_message(action["run_id"], action.get("text", ""))

    def _apply_update_status(self, action: dict) -> None:
        self.renderer.render_status(
            action["run_id"],
            action.get("status", ""),
            action.get("phase", ""),
            action.get("message", ""),
        )

    def _apply_confirm(self, action: dict) -> None:
        self.renderer.render_confirm(
            action.get("confirm_id", ""),
            action.get("tool", ""),
            action.get("message", ""),
            action.get("risk", "medium"),
        )

    def _apply_error(self, action: dict) -> None:
        self.renderer.render_error(action["run_id"], action.get("error", ""))

    def _apply_info(self, action: dict) -> None:
        self.renderer.render_info(action["run_id"], action.get("message", ""))

    def _apply_media(self, action: dict) -> None:
        self.renderer.render_media(action["run_id"], action.get("media_type", ""), action.get("payload", {}))

    def _apply_intel_analysis(self, action: dict) -> None:
        self.renderer.render_intel_analysis(action["run_id"], action.get("payload", {}))

    def _apply_tool_start(self, action: dict) -> None:
        self.renderer.render_tool_start(action["run_id"], action.get("tool", ""), action.get("args", {}))

    def _apply_tool_result(self, action: dict) -> None:
        self.renderer.render_tool_result(action["run_id"], action.get("tool", ""), action.get("result", ""))

    def _apply_final(self, action: dict) -> None:
        self.renderer.render_final(action["run_id"], action.get("content", ""))
