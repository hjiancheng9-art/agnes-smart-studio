"""Async ToolExecutor — Phase 1 of tool chain refactoring.

Wraps the existing synchronous _dispatch_tool_impl with:
- Async execution via asyncio.to_thread
- Per-tool timeout control
- Structured ToolOutcome instead of bare strings
- Cancel token support

Phase 2 (deferred): Middleware pipeline for validation/retry/policy.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from core.tool_outcome import RecoveryAction, ToolOutcome, ToolStatus

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_TIMEOUT = 60.0
BROWSER_TIMEOUT = 120.0
SHORT_TIMEOUT = 10.0


@dataclass
class ToolSpec:
    """Metadata for a single tool — drives executor behavior."""

    name: str
    timeout_s: float = DEFAULT_TIMEOUT
    idempotent: bool = False
    slow: bool = False  # long-running (browser, video gen)

    @classmethod
    def for_tool(cls, name: str) -> ToolSpec:
        """Heuristic defaults per tool category. Override in tools.json later."""
        if any(k in name for k in ("browser", "cdp", "pw_", "chatgpt", "gemini")):
            return cls(name=name, timeout_s=BROWSER_TIMEOUT, slow=True)
        if any(k in name for k in ("generate_video", "generate_image", "transcribe")):
            return cls(name=name, timeout_s=180.0, slow=True)
        if any(k in name for k in ("run_test", "execute_plan", "orchestrate")):
            return cls(name=name, timeout_s=300.0, slow=True)
        if any(k in name for k in ("git_", "github_")):
            return cls(name=name, timeout_s=30.0)
        return cls(name=name, timeout_s=DEFAULT_TIMEOUT)


class ToolExecutor:
    """Async executor that wraps the existing sync dispatch function."""

    def __init__(self, dispatch_fn, tool_registry=None):
        self._dispatch = dispatch_fn  # sync (tool_name, args_json) -> (result_str, side_effects)
        self._registry = tool_registry
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def execute(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        timeout_s: float | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> ToolOutcome:
        """Execute a tool call with timeout and structured outcome.

        Args:
            tool_name: Registered tool name.
            tool_args: Already-validated arguments dict.
            timeout_s: Per-call timeout override (uses ToolSpec default if None).
            cancel_event: Optional external cancel signal.

        Returns:
            ToolOutcome with status, value, and optional failure details.
        """
        try:
            from core.tool_specs import get_spec

            spec = get_spec(tool_name)
        except ImportError:
            spec = ToolSpec.for_tool(tool_name)
        effective_timeout = timeout_s or spec.timeout_s
        cancel = cancel_event or asyncio.Event()
        args_json = json.dumps(tool_args, ensure_ascii=False, default=str)

        outcome = ToolOutcome(status=ToolStatus.SUCCEEDED, tool_name=tool_name)

        async def _run():
            try:
                result_str, side_effects = await asyncio.to_thread(self._dispatch, tool_name, args_json)
                return result_str, side_effects
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Tool dispatch failed: {exc}") from exc

        task = asyncio.create_task(_run())
        self._active_tasks[tool_name] = task

        try:
            if cancel.is_set():
                task.cancel()
                return ToolOutcome.cancelled(tool_name)

            result_str, _side_effects = await asyncio.wait_for(task, timeout=effective_timeout)

            # Detect error patterns from old string-based protocol
            if isinstance(result_str, str):
                if result_str.startswith("[错误]") or result_str.startswith("[自愈失败]"):
                    outcome = ToolOutcome.failure_of(
                        "tool.error",
                        result_str,
                        tool_name,
                        recovery=RecoveryAction.NONE,
                    )
                elif result_str.startswith("[超时]"):
                    outcome = ToolOutcome.timeout(tool_name, result_str)
                else:
                    outcome = ToolOutcome.success(result_str, tool_name)
            else:
                outcome = ToolOutcome.success(str(result_str), tool_name)

            return outcome

        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return ToolOutcome.timeout(tool_name)

        except asyncio.CancelledError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return ToolOutcome.cancelled(tool_name)

        except Exception as exc:
            return ToolOutcome.failure_of(
                "tool.exception",
                str(exc),
                tool_name,
                recovery=RecoveryAction.NONE,
            )

        finally:
            self._active_tasks.pop(tool_name, None)

    def cancel_all(self) -> None:
        """Cancel all in-flight tool executions."""
        for task in list(self._active_tasks.values()):
            task.cancel()
