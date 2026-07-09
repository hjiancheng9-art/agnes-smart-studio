# core/tool_result.py

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolError:
    code: str
    message: str
    detail: Any | None = None
    retryable: bool = True
    exception_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "retryable": self.retryable,
            "exception_type": self.exception_type,
        }


@dataclass(slots=True)
class ToolResult:
    """
    所有工具执行结果统一包装成：

    {
      "success": true/false,
      "data": ...,
      "error": {...} | null,
      "hints": [...]
    }
    """

    success: bool
    data: Any = None
    error: ToolError | None = None
    hints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        data: Any = None,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        return cls(
            success=True,
            data=data,
            error=None,
            hints=hints or [],
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        *,
        code: str,
        message: str,
        detail: Any | None = None,
        hints: list[str] | None = None,
        retryable: bool = True,
        metadata: dict[str, Any] | None = None,
        exception_type: str | None = None,
    ) -> ToolResult:
        return cls(
            success=False,
            data=None,
            error=ToolError(
                code=code,
                message=message,
                detail=detail,
                retryable=retryable,
                exception_type=exception_type,
            ),
            hints=hints or [],
            metadata=metadata or {},
        )

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        code: str = "tool_execution_error",
        retryable: bool = True,
        include_traceback: bool = False,
        hints: list[str] | None = None,
    ) -> ToolResult:
        detail: dict[str, Any] = {
            "exception": repr(exc),
        }

        if include_traceback:
            detail["traceback"] = traceback.format_exc()

        return cls.fail(
            code=code,
            message=str(exc) or exc.__class__.__name__,
            detail=detail,
            retryable=retryable,
            hints=hints,
            exception_type=exc.__class__.__name__,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
            "hints": self.hints,
            "metadata": self.metadata,
        }

    def to_json(self, *, ensure_ascii: bool = False, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=ensure_ascii,
            indent=indent,
            default=str,
        )

    def to_llm_content(self) -> str:
        """
        注入回 LLM 的工具结果文本。
        不直接把 Python repr / traceback 暴露给模型。
        """
        return self.to_json(ensure_ascii=False, indent=2)
    def to_llm_context(self) -> str:
        """Compact single-line context for LLM consumption."""
        name = self.metadata.get("tool_name", "unknown")
        if self.success:
            return f"[OK] {name}: {self._summarize(self.data)}"
        err = self.error.message if hasattr(self.error, 'message') else str(self.error)
        return f"[FAIL] {name}: {err}"

    def to_llm_line(self) -> str:
        """One-liner for tool result summary."""
        name = self.metadata.get("tool_name", "unknown")
        status = "OK" if self.success else "FAIL"
        if self.success:
            return f"[{status}] {name}: {self._summarize(self.data)}"
        err = self.error.message if hasattr(self.error, 'message') else str(self.error)
        return f"[{status}] {name}: {err}"

    @staticmethod
    def _summarize(data: Any, max_len: int = 200) -> str:
        """Safe summarizer — truncates long outputs."""
        if data is None:
            return "(no output)"
        s = str(data)
        if len(s) > max_len:
            return s[:max_len] + f"...[{len(s)} total]"
        return s

