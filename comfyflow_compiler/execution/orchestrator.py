"""ExecutionOrchestrator — 执行编排器

一键执行：submit → poll → collect → 结构化结果。
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

from .submission import SubmissionContract, SubmissionResult
from .polling import PollingContract, PollResult, ExecutionStatus
from .output import OutputCollector, OutputResult
from .errors import ExecutionError, SubmissionError, PollingTimeoutError, OutputNotFoundError


@dataclass
class ExecutionResult:
    """完整执行结果"""
    success: bool = False
    prompt_id: str = ""
    trace_id: str = ""
    task_type: str = ""
    blueprint_used: str = ""

    # 三段
    submission: Optional[SubmissionResult] = None
    polling: Optional[PollResult] = None
    output: Optional[OutputResult] = None

    # 元信息
    error: str = ""
    error_stage: str = ""  # submission, polling, output
    total_elapsed: float = 0.0

    # 来源
    source: str = "local"  # local, mcp
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = [f"{'✅' if self.success else '❌'} trace={self.trace_id}"]
        if self.task_type:
            parts.append(f"task={self.task_type}")
        if self.blueprint_used:
            parts.append(f"blueprint={self.blueprint_used}")
        if self.total_elapsed:
            parts.append(f"elapsed={self.total_elapsed:.1f}s")
        if self.error:
            parts.append(f"error=[{self.error_stage}] {self.error}")
        if self.output:
            parts.append(self.output.summary)
        return " | ".join(parts)


class ExecutionOrchestrator:
    """执行编排器 — 提交→轮询→收集 全自动"""

    def __init__(self, base_url: str = "http://127.0.0.1:8188",
                 poll_interval: float = 1.0,
                 default_timeout: float = 300.0,
                 comfyui_output_dir: str | None = None):
        self.submission = SubmissionContract(base_url=base_url)
        self.polling = PollingContract(base_url=base_url, poll_interval=poll_interval,
                                       default_timeout=default_timeout)
        self.output = OutputCollector(comfyui_output_dir=comfyui_output_dir)

    def execute(self, workflow: dict,
                task_type: str = "",
                blueprint_used: str = "",
                trace_id: str = "",
                timeout: float = 0.0,
                output_dir: str = "",
                on_progress: Optional[Callable] = None) -> ExecutionResult:
        """一键执行

        Args:
            workflow: 工作流 JSON
            task_type: 任务类型（用于日志）
            blueprint_used: 使用的蓝图
            trace_id: 追踪 ID
            timeout: 超时秒数
            output_dir: 输出目录
            on_progress: 进度回调

        Returns:
            ExecutionResult
        """
        tid = trace_id or uuid.uuid4().hex[:12]
        start = time.time()
        result = ExecutionResult(trace_id=tid, task_type=task_type, blueprint_used=blueprint_used)

        # Step 1: 提交
        sub_result = self.submission.submit(workflow, trace_id=tid)
        result.submission = sub_result
        result.prompt_id = sub_result.prompt_id

        if not sub_result.success:
            result.success = False
            result.error = sub_result.error_message
            result.error_stage = "submission"
            result.total_elapsed = time.time() - start
            return result

        # Step 2: 轮询
        try:
            poll_result = self.polling.poll(sub_result.prompt_id, timeout=timeout, on_progress=on_progress)
            result.polling = poll_result

            if poll_result.status == ExecutionStatus.TIMEOUT:
                result.success = False
                result.error = poll_result.error
                result.error_stage = "polling"
                result.total_elapsed = time.time() - start
                return result

            if poll_result.status == ExecutionStatus.FAILED:
                result.success = False
                result.error = poll_result.error or "执行失败"
                result.error_stage = "polling"
                result.total_elapsed = time.time() - start
                return result

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.error_stage = "polling"
            result.total_elapsed = time.time() - start
            return result

        # Step 3: 收集产物
        try:
            out_result = self.output.collect(sub_result.prompt_id, poll_result.history_raw, output_dir)
            result.output = out_result
        except Exception as e:
            result.warnings.append(f"输出收集失败: {e}")

        result.success = result.polling.success if result.polling else False
        result.total_elapsed = time.time() - start
        return result
