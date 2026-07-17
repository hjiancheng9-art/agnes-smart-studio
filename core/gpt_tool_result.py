from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from functools import wraps
from typing import Any, Callable, Mapping, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: Any = ""
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    side_effects: tuple[Any, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        output: Any = "",
        *,
        side_effects: Any = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            ok=True,
            output=output,
            side_effects=_normalize_side_effects(side_effects),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        *,
        output: Any = "",
        retryable: bool = False,
        side_effects: Any = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            ok=False,
            output=output,
            error_code=code,
            error_message=message,
            retryable=retryable,
            side_effects=_normalize_side_effects(side_effects),
            metadata=dict(metadata or {}),
        )

    @property
    def content(self) -> str:
        return self.to_model_text()

    def to_model_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output": self.output,
            "error": (
                None
                if self.ok
                else {
                    "code": self.error_code or "TOOL_ERROR",
                    "message": (
                        self.error_message
                        or "tool execution failed"
                    ),
                    "retryable": self.retryable,
                }
            ),
            "side_effects": list(self.side_effects),
            "metadata": self.metadata,
        }

    def to_model_text(self) -> str:
        if self.ok and isinstance(self.output, str):
            return self.output

        return json.dumps(
            self.to_model_dict(),
            ensure_ascii=False,
            default=str,
        )

    def __iter__(self):
        """
        Backward compatibility for old code:

            tool_result, side_effects = self._dispatch_tool(...)

        `_dispatch_tool` can now always return ToolResult without breaking the
        existing two-item unpacking path.
        """
        yield self.to_model_text()
        yield self.side_effects

    def __str__(self) -> str:
        return self.to_model_text()


def normalize_tool_result(
    value: Any,
    *,
    tool_name: str = "",
) -> ToolResult:
    if isinstance(value, ToolResult):
        return value

    if value is None:
        return ToolResult.failure(
            "TOOL_RETURNED_NONE",
            _message(
                tool_name,
                "tool returned None",
            ),
        )

    if isinstance(value, BaseException):
        return ToolResult.failure(
            "TOOL_EXCEPTION",
            _message(
                tool_name,
                f"{type(value).__name__}: {value}",
            ),
        )

    if isinstance(value, str):
        return ToolResult.success(value)

    if isinstance(value, tuple):
        return _normalize_tuple(
            value,
            tool_name=tool_name,
        )

    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_mapping(
            asdict(value),
            tool_name=tool_name,
            source_type=type(value).__name__,
        )

    if isinstance(value, Mapping):
        return _normalize_mapping(
            value,
            tool_name=tool_name,
            source_type=type(value).__name__,
        )

    return ToolResult.success(value)


def ensure_tool_result(
    function: Callable[P, R],
) -> Callable[P, ToolResult]:
    @wraps(function)
    def wrapped(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> ToolResult:
        tool_name = _infer_tool_name(
            args,
            kwargs,
        )

        try:
            raw = function(
                *args,
                **kwargs,
            )
        except BaseException as exc:
            return ToolResult.failure(
                "TOOL_EXCEPTION",
                _message(
                    tool_name,
                    f"{type(exc).__name__}: {exc}",
                ),
                metadata={
                    "exception_type": type(exc).__name__,
                },
            )

        return normalize_tool_result(
            raw,
            tool_name=tool_name,
        )

    return wrapped


def _normalize_tuple(
    value: tuple[Any, ...],
    *,
    tool_name: str,
) -> ToolResult:
    if not value:
        return ToolResult.failure(
            "TOOL_RETURNED_EMPTY_TUPLE",
            _message(
                tool_name,
                "tool returned an empty tuple",
            ),
        )

    if len(value) == 1:
        return normalize_tool_result(
            value[0],
            tool_name=tool_name,
        )

    if len(value) == 2:
        first, second = value

        if isinstance(first, bool):
            if first:
                return ToolResult.success(second)

            return ToolResult.failure(
                "TOOL_FAILED",
                _message(
                    tool_name,
                    _stringify(second),
                ),
            )

        return ToolResult.success(
            first,
            side_effects=second,
        )

    first, second, third, *rest = value

    if isinstance(first, bool):
        side_effects = third
        metadata = (
            {"legacy_extra": rest}
            if rest
            else {}
        )

        if first:
            return ToolResult.success(
                second,
                side_effects=side_effects,
                metadata=metadata,
            )

        return ToolResult.failure(
            "TOOL_FAILED",
            _message(
                tool_name,
                _stringify(second),
            ),
            side_effects=side_effects,
            metadata=metadata,
        )

    metadata: dict[str, Any] = {
        "legacy_third": third,
    }

    if rest:
        metadata["legacy_extra"] = rest

    return ToolResult.success(
        first,
        side_effects=second,
        metadata=metadata,
    )


def _normalize_mapping(
    value: Mapping[str, Any],
    *,
    tool_name: str,
    source_type: str,
) -> ToolResult:
    data = dict(value)

    ok_value = _first_present(
        data,
        "ok",
        "success",
        "succeeded",
    )

    output = _first_present(
        data,
        "output",
        "content",
        "result",
        "value",
        "data",
    )

    side_effects = _first_present(
        data,
        "side_effects",
        "effects",
        "artifacts",
    )

    retryable = bool(
        _first_present(
            data,
            "retryable",
            "can_retry",
        )
        or False
    )

    error_code = _first_present(
        data,
        "error_code",
        "code",
    )

    error_message = _first_present(
        data,
        "error_message",
        "message",
        "error",
        "detail",
    )

    consumed = {
        "ok",
        "success",
        "succeeded",
        "output",
        "content",
        "result",
        "value",
        "data",
        "side_effects",
        "effects",
        "artifacts",
        "retryable",
        "can_retry",
        "error_code",
        "code",
        "error_message",
        "message",
        "error",
        "detail",
        "metadata",
    }

    raw_metadata = data.get("metadata")

    metadata = (
        dict(raw_metadata)
        if isinstance(raw_metadata, Mapping)
        else {}
    )

    metadata.setdefault(
        "source_type",
        source_type,
    )

    for key, item in data.items():
        if key not in consumed:
            metadata.setdefault(
                key,
                item,
            )

    if ok_value is None:
        ok = not bool(
            error_message or error_code
        )
    else:
        ok = bool(ok_value)

    if ok:
        return ToolResult.success(
            "" if output is None else output,
            side_effects=side_effects,
            metadata=metadata,
        )

    return ToolResult.failure(
        str(error_code or "TOOL_FAILED"),
        _message(
            tool_name,
            _stringify(
                error_message
                or "tool execution failed"
            ),
        ),
        output="" if output is None else output,
        retryable=retryable,
        side_effects=side_effects,
        metadata=metadata,
    )


def _normalize_side_effects(
    value: Any,
) -> tuple[Any, ...]:
    if value is None:
        return ()

    if isinstance(value, tuple):
        return value

    if isinstance(value, list):
        return tuple(value)

    return (value,)


def _first_present(
    data: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in data:
            return data[key]

    return None


def _infer_tool_name(
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> str:
    for key in (
        "tool_name",
        "name",
    ):
        value = kwargs.get(key)

        if isinstance(value, str) and value:
            return value

    for value in args[1:3]:
        if isinstance(value, str) and value:
            return value

        if isinstance(value, Mapping):
            candidate = (
                value.get("name")
                or value.get("tool_name")
            )

            if (
                isinstance(candidate, str)
                and candidate
            ):
                return candidate

    return ""


def _message(
    tool_name: str,
    message: str,
) -> str:
    return (
        f"{tool_name}: {message}"
        if tool_name
        else message
    )


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )
    except BaseException:
        return repr(value)


__all__ = [
    "ToolResult",
    "ensure_tool_result",
    "normalize_tool_result",
]