"""SubmissionContract — 工作流提交契约

统一提交接口：序列化、发送、分类失败。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import SubmissionError, ComfyUIOfflineError, QueueFullError


@dataclass
class SubmissionResult:
    """提交结果"""
    success: bool = False
    prompt_id: str = ""
    node_errors: list[dict] = field(default_factory=list)
    error_type: str = ""  # offline, queue_full, invalid_workflow, unknown
    error_message: str = ""
    raw_response: dict = field(default_factory=dict)
    trace_id: str = ""


class SubmissionContract:
    """提交契约 — 将 workflow JSON 提交到 ComfyUI"""

    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def submit(self, workflow: dict, trace_id: str = "") -> SubmissionResult:
        """提交 workflow 到 ComfyUI

        Args:
            workflow: workflow JSON (需含 prompt 键或直接是 prompt)
            trace_id: 追踪 ID（自动生成 if empty）

        Returns:
            SubmissionResult
        """
        import urllib.request
        import urllib.error

        tid = trace_id or uuid.uuid4().hex[:12]

        # 确保 workflow 格式正确
        payload = workflow.get("prompt", workflow) if isinstance(workflow, dict) else workflow

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/prompt",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = {}
            if e.code == 503:
                return self._fail("queue_full", "ComfyUI 队列已满", body, tid)
            return self._fail("invalid_workflow", f"HTTP {e.code}: {e.reason}", body, tid)
        except urllib.error.URLError as e:
            return self._fail("offline", f"ComfyUI 不可达: {e.reason}", {}, tid)
        except json.JSONDecodeError:
            return self._fail("unknown", "ComfyUI 返回非 JSON 响应", {}, tid)
        except OSError as e:
            return self._fail("offline", f"连接失败: {e}", {}, tid)

        prompt_id = body.get("prompt_id", "")
        if not prompt_id:
            return self._fail("unknown", "ComfyUI 未返回 prompt_id", body, tid)

        node_errors = body.get("node_errors", [])
        if node_errors:
            return SubmissionResult(
                success=False,
                prompt_id=prompt_id,
                node_errors=node_errors,
                error_type="node_error",
                error_message=f"节点错误: {node_errors}",
                raw_response=body,
                trace_id=tid,
            )

        return SubmissionResult(
            success=True,
            prompt_id=prompt_id,
            raw_response=body,
            trace_id=tid,
        )

    def _fail(self, err_type: str, msg: str, raw: dict, tid: str) -> SubmissionResult:
        return SubmissionResult(
            success=False,
            error_type=err_type,
            error_message=msg,
            raw_response=raw,
            trace_id=tid,
        )
