"""
TUI Event Reducer — 事件 → UI 状态变化
=========================================
把 StreamEvent 转成 UI action（reduce 模式）。
让 renderer 只处理 action，不直接碰业务状态。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.stream_protocol import StreamEvent

    from .tui_run_state import RunStateStore


class TuiEventReducer:
    """事件归约器 — StreamEvent → UI action dict"""

    def __init__(self, run_store: RunStateStore):
        self.run_store = run_store

    def reduce(self, event: StreamEvent) -> dict[str, Any]:
        """单事件 → UI action"""
        kind = event.kind
        payload = event.payload
        run_id = payload.get("run_id", event.run_id)

        handler = getattr(self, f"_handle_{kind}", None)
        if handler:
            return handler(run_id, payload)

        return self._handle_unknown(run_id, kind, payload)

    # ── handler 们 ──

    def _handle_stream_start(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.update(run_id, status="STARTED", phase="stream_start", is_streaming=True)
        return {
            "type": "stream_start",
            "run_id": run_id,
            "message": payload.get("message", ""),
            "state": self.run_store.get(run_id),
        }

    def _handle_stream_end(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.finish(run_id)
        return {
            "type": "stream_end",
            "run_id": run_id,
            "message": payload.get("message", ""),
            "state": self.run_store.get(run_id),
        }

    def _handle_status(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.update(
            run_id,
            status=payload.get("status", "RUNNING"),
            phase=payload.get("phase", ""),
            message=payload.get("message", ""),
        )
        return {
            "type": "update_status",
            "run_id": run_id,
            "status": payload.get("status", ""),
            "phase": payload.get("phase", ""),
            "message": payload.get("message", ""),
            "state": self.run_store.get(run_id),
        }

    def _handle_text(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.update(run_id, last_event_at=__import__("time").time())
        return {
            "type": "append_text",
            "run_id": run_id,
            "text": payload.get("message", payload.get("text", "")),
        }

    def _handle_info(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {
            "type": "info",
            "run_id": run_id,
            "message": payload.get("message", payload.get("info", "")),
        }

    def _handle_confirm(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {
            "type": "confirm",
            "run_id": run_id,
            "confirm_id": payload.get("confirm_id", ""),
            "tool": payload.get("tool", ""),
            "message": payload.get("message", ""),
            "risk": payload.get("risk", "medium"),
        }

    def _handle_error(self, run_id: str, payload: dict) -> dict[str, Any]:
        error_msg = payload.get("message", payload.get("error", "Unknown error"))
        self.run_store.error(run_id, error_msg)
        return {
            "type": "error",
            "run_id": run_id,
            "error": error_msg,
            "state": self.run_store.get(run_id),
        }

    def _handle_image(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {"type": "media", "run_id": run_id, "media_type": "image", "payload": payload}

    def _handle_video(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {"type": "media", "run_id": run_id, "media_type": "video", "payload": payload}

    def _handle_intel_analysis(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {"type": "intel_analysis", "run_id": run_id, "payload": payload}

    def _handle_tool_start(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.update(run_id, phase="tool_running")
        return {
            "type": "tool_start",
            "run_id": run_id,
            "tool": payload.get("tool", ""),
            "args": payload.get("args", {}),
        }

    def _handle_tool_result(self, run_id: str, payload: dict) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "run_id": run_id,
            "tool": payload.get("tool", ""),
            "result": payload.get("result", ""),
        }

    def _handle_final(self, run_id: str, payload: dict) -> dict[str, Any]:
        self.run_store.finish(run_id)
        return {
            "type": "final",
            "run_id": run_id,
            "content": payload.get("content", ""),
            "state": self.run_store.get(run_id),
        }

    def _handle_unknown(self, run_id: str, kind: str, payload: dict) -> dict[str, Any]:
        return {"type": "info", "run_id": run_id, "message": f"[{kind}] {payload.get('message', str(payload)[:100])}"}
