"""Unit tests for core.gpt_tool_result — ToolResult, normalize_tool_result, ensure_tool_result."""

from __future__ import annotations

from dataclasses import dataclass

from core.gpt_tool_result import (
    ToolResult,
    ensure_tool_result,
    normalize_tool_result,
)

# ═══════════════════════════════════════════════════════════════
# ToolResult construction
# ═══════════════════════════════════════════════════════════════


class TestToolResultSuccess:
    def test_success_with_string(self):
        r = ToolResult.success("hello")
        assert r.ok is True
        assert r.output == "hello"
        assert r.error_code is None
        assert r.side_effects == ()

    def test_success_with_side_effects(self):
        r = ToolResult.success("done", side_effects=[("info", "msg")])
        assert r.ok is True
        assert r.side_effects == (("info", "msg"),)

    def test_success_metadata(self):
        r = ToolResult.success("ok", metadata={"elapsed": 1.2})
        assert r.metadata == {"elapsed": 1.2}

    def test_content_property_returns_string_output(self):
        r = ToolResult.success("result")
        assert r.content == "result"

    def test_content_property_returns_json_for_non_string(self):
        r = ToolResult.success([1, 2, 3])
        assert "1" in r.content
        assert "2" in r.content

    def test_str_matches_content(self):
        r = ToolResult.success("hi")
        assert str(r) == "hi"


class TestToolResultFailure:
    def test_failure_with_code_and_message(self):
        r = ToolResult.failure("ERR", "something went wrong")
        assert r.ok is False
        assert r.error_code == "ERR"
        assert r.error_message == "something went wrong"

    def test_failure_retryable(self):
        r = ToolResult.failure("TIMEOUT", "timeout", retryable=True)
        assert r.retryable is True

    def test_failure_content_includes_error(self):
        r = ToolResult.failure("E1", "bad")
        assert "bad" in r.content
        assert "E1" in r.content


class TestToolResultToModelDict:
    def test_success_dict(self):
        d = ToolResult.success("x").to_model_dict()
        assert d["ok"] is True
        assert d["output"] == "x"
        assert d["error"] is None

    def test_failure_dict(self):
        d = ToolResult.failure("E2", "msg").to_model_dict()
        assert d["ok"] is False
        assert d["error"]["code"] == "E2"
        assert d["error"]["message"] == "msg"


class TestToolResultIterUnpacking:
    """Backward compatibility: tuple unpacking (text, side_effects)."""

    def test_success_unpack(self):
        text, sides = ToolResult.success("abc")
        assert text == "abc"
        assert sides == ()

    def test_success_with_sides_unpack(self):
        text, sides = ToolResult.success("x", side_effects=[("info", "y")])
        assert "x" in str(text)
        assert sides == (("info", "y"),)

    def test_failure_unpack(self):
        text, sides = ToolResult.failure("E", "msg")
        assert "E" in str(text)
        assert "msg" in str(text)
        assert sides == ()


# ═══════════════════════════════════════════════════════════════
# normalize_tool_result
# ═══════════════════════════════════════════════════════════════


class TestNormalizeToolResult:
    def test_passthrough_toolresult(self):
        r = ToolResult.success("x")
        assert normalize_tool_result(r) is r

    def test_none_input(self):
        r = normalize_tool_result(None, tool_name="test")
        assert r.ok is False
        assert r.error_code == "TOOL_RETURNED_NONE"

    def test_exception_input(self):
        r = normalize_tool_result(ValueError("bad"), tool_name="f")
        assert r.ok is False
        assert "ValueError" in r.error_message or "ValueError" in r.content

    def test_string_input(self):
        r = normalize_tool_result("hello")
        assert r.ok is True
        assert r.output == "hello"

    def test_two_tuple_text_sides(self):
        r = normalize_tool_result(("text", [("info", "m")]))
        assert r.ok is True
        assert r.output == "text"
        assert r.side_effects == (("info", "m"),)

    def test_two_tuple_bool_true(self):
        r = normalize_tool_result((True, "good"))
        assert r.ok is True
        assert r.output == "good"

    def test_two_tuple_bool_false(self):
        r = normalize_tool_result((False, "bad"))
        assert r.ok is False
        assert "bad" in r.error_message

    def test_dataclass_input(self):
        @dataclass
        class FakeResult:
            ok: bool = True
            output: str = "dc"
            side_effects: list = None

        r = normalize_tool_result(FakeResult())
        assert r.ok is True
        assert r.output == "dc"

    def test_dict_input(self):
        r = normalize_tool_result({"ok": False, "error_code": "X", "error_message": "fail"})
        assert r.ok is False
        assert r.error_code == "X"

    def test_empty_tuple(self):
        r = normalize_tool_result(())
        assert r.ok is False
        assert r.error_code == "TOOL_RETURNED_EMPTY_TUPLE"

    def test_three_tuple(self):
        r = normalize_tool_result(("a", [("info",)]))
        assert r.ok is True
        assert r.output == "a"


# ═══════════════════════════════════════════════════════════════
# ensure_tool_result decorator
# ═══════════════════════════════════════════════════════════════


class TestEnsureToolResult:
    def test_wraps_string_return(self):
        @ensure_tool_result
        def foo():
            return "ok"

        r = foo()
        assert isinstance(r, ToolResult)
        assert r.ok is True
        assert r.output == "ok"

    def test_wraps_exception(self):
        @ensure_tool_result
        def bar():
            raise RuntimeError("boom")

        r = bar()
        assert isinstance(r, ToolResult)
        assert r.ok is False
        assert r.error_code == "TOOL_EXCEPTION"
        assert "boom" in r.error_message

    def test_wraps_toolresult_return(self):
        @ensure_tool_result
        def baz():
            return ToolResult.success("direct")

        r = baz()
        assert r.ok is True
        assert r.output == "direct"

    def test_infers_tool_name_from_positional_arg(self):
        @ensure_tool_result
        def some_tool(name, tool_name, *args):
            raise RuntimeError("x")

        # _infer_tool_name checks args[1:3] for string values
        r = some_tool("ignored", "my-tool")
        assert "my-tool" in r.error_message

    def test_preserves_function_metadata(self):
        @ensure_tool_result
        def documented():
            """Docstring."""
            return "x"

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "Docstring."
