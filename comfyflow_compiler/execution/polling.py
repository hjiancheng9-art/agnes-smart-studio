"""PollingContract — 执行轮询契约

轮询 /history 直到完成、超时或失败。
"""

from __future__ import annotations

import time
import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .errors import PollingTimeoutError


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class PollResult:
    """轮询结果"""
    status: ExecutionStatus = ExecutionStatus.PENDING
    prompt_id: str = ""
    progress: float = 0.0  # 0-1
    current_node: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    node_errors: list[dict] = field(default_factory=list)
    elapsed: float = 0.0
    history_raw: dict = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT)

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED and bool(self.outputs)


class PollingContract:
    """轮询契约 — 监听执行进度"""

    def __init__(self, base_url: str = "http://127.0.0.1:8188",
                 poll_interval: float = 1.0,
                 default_timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.default_timeout = default_timeout

    def poll(self, prompt_id: str, timeout: float = 0.0, on_progress=None) -> PollResult:
        """轮询直到完成

        Args:
            prompt_id: 提交时返回的 prompt_id
            timeout: 超时秒数（0=default_timeout）
            on_progress: 进度回调 fn(result)

        Returns:
            PollResult
        """
        timeout = timeout or self.default_timeout
        start = time.time()
        last_status = ""

        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                return PollResult(
                    status=ExecutionStatus.TIMEOUT,
                    prompt_id=prompt_id,
                    progress=0.0,
                    error=f"执行超时 ({timeout}s)",
                    elapsed=elapsed,
                )

            result = self._poll_once(prompt_id, elapsed)
            if on_progress:
                on_progress(result)
            if result.done:
                return result

            # 打印进度变化
            status_line = f"  [{result.progress:.0%}] {result.current_node or 'waiting...'}"
            if status_line != last_status:
                last_status = status_line

            time.sleep(self.poll_interval)

    def _poll_once(self, prompt_id: str, elapsed: float) -> PollResult:
        """单次轮询"""
        try:
            req = urllib.request.Request(f"{self.base_url}/history/{prompt_id}")
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return PollResult(status=ExecutionStatus.PENDING, prompt_id=prompt_id, elapsed=elapsed)
            return PollResult(status=ExecutionStatus.UNKNOWN, prompt_id=prompt_id,
                              error=f"HTTP {e.code}: {e.reason}", elapsed=elapsed)
        except Exception as e:
            return PollResult(status=ExecutionStatus.UNKNOWN, prompt_id=prompt_id,
                              error=str(e), elapsed=elapsed)

        if not isinstance(data, dict):
            return PollResult(status=ExecutionStatus.UNKNOWN, prompt_id=prompt_id, elapsed=elapsed)

        entry = data.get(prompt_id, data)
        if not isinstance(entry, dict):
            return PollResult(status=ExecutionStatus.PENDING, prompt_id=prompt_id, elapsed=elapsed)

        status_str = entry.get("status", entry.get("status_str", ""))
        outputs = entry.get("outputs", {})

        # 检查执行错误
        if isinstance(status_str, dict):
            status_str = status_str.get("status_str", "")
            node_errors = status_str.get("node_errors", []) if isinstance(status_str, dict) else []
        else:
            node_errors = []

        # 判断状态
        if outputs:
            return PollResult(
                status=ExecutionStatus.COMPLETED,
                prompt_id=prompt_id,
                progress=1.0,
                outputs=outputs,
                elapsed=elapsed,
                history_raw=data,
            )

        if status_str in ("error", "failed"):
            return PollResult(
                status=ExecutionStatus.FAILED,
                prompt_id=prompt_id,
                progress=0.0,
                error=status_str,
                node_errors=node_errors,
                elapsed=elapsed,
                history_raw=data,
            )

        if not status_str or status_str in ("pending", "queued"):
            return PollResult(status=ExecutionStatus.PENDING, prompt_id=prompt_id, progress=0.0, elapsed=elapsed)

        return PollResult(status=ExecutionStatus.RUNNING, prompt_id=prompt_id, progress=0.5, elapsed=elapsed)
