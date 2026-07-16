# core/validation_errors.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


class ValidationCode(str, Enum):
    XML_NOT_FOUND = "xml_not_found"
    XML_PARSE_ERROR = "xml_parse_error"
    INVALID_ROOT = "invalid_root"
    INVALID_INVOKE = "invalid_invoke"
    MISSING_TOOL_NAME = "missing_tool_name"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT_FORMAT = "invalid_argument_format"
    ARGUMENT_PARSE_ERROR = "argument_parse_error"
    SCHEMA_MISSING_REQUIRED = "schema_missing_required"
    SCHEMA_TYPE_MISMATCH = "schema_type_mismatch"
    SCHEMA_ADDITIONAL_PROPERTY = "schema_additional_property"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    TOO_MANY_TOOL_CALLS = "too_many_tool_calls"
    UNSAFE_TOOL_CALL = "unsafe_tool_call"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    TOOL_RESULT_INVALID = "tool_result_invalid"


@dataclass(slots=True)
class ValidationIssue:
    code: ValidationCode
    message: str
    tool_name: str | None = None
    param_path: str | None = None
    raw_fragment: str | None = None
    hint: str | None = None
    retryable: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "tool_name": self.tool_name,
            "param_path": self.param_path,
            "raw_fragment": self.raw_fragment,
            "hint": self.hint,
            "retryable": self.retryable,
            "extra": self.extra,
        }

    def to_llm_line(self) -> str:
        parts: list[str] = [f"- [{self.code.value}] {self.message}"]
        if self.tool_name:
            parts.append(f"tool={self.tool_name}")
        if self.param_path:
            parts.append(f"path={self.param_path}")
        if self.hint:
            parts.append(f"hint={self.hint}")
        return " | ".join(parts)


class ValidationError(Exception):
    """
    聚合型校验异常。

    注意：
    - 不是 Python 内置 ValueError。
    - 用于把所有 XML / schema / tool-call 错误一次性返回给 self-correction。
    """

    def __init__(
        self,
        issues: Iterable[ValidationIssue],
        *,
        raw_response: str | None = None,
        message: str | None = None,
    ) -> None:
        self.issues = list(issues)
        self.raw_response = raw_response
        super().__init__(message or self.summary())

    @property
    def retryable(self) -> bool:
        return bool(self.issues) and all(issue.retryable for issue in self.issues)

    def summary(self) -> str:
        if not self.issues:
            return "Tool call validation failed."
        return "; ".join(issue.message for issue in self.issues[:5])

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "retryable": self.retryable,
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_correction_prompt(self) -> str:
        """
        注入给 LLM 的修复提示。
        核心原则：不要让模型解释错误，只让它重新输出合法 tool_calls 或最终回答。
        """
        issue_lines = "\n".join(issue.to_llm_line() for issue in self.issues)

        return f"""Your previous tool call output was invalid and was NOT executed.

Validation errors:
{issue_lines}

Please correct your response.

Rules:
1. If you need tools, output ONLY valid XML tool_calls.
2. Use this exact format:
<tool_calls>
  <invoke name="tool_name">
    <param name="arg_name">arg_value</param>
  </invoke>
</tool_calls>
3. Do not wrap XML in Markdown code fences.
4. Do not add explanations before or after the XML.
5. Use only known tool names.
6. Include all required parameters.
7. Make parameter values match the tool JSON Schema.

Return the corrected response now."""
