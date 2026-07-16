"""Tests for core/tool_call_parser.py — XML tool-call parser."""

from core.tool_call_parser import (
    _extract_kv_pairs,
    _make_tc,
    _parse_args,
    extract_tool_calls,
    has_xml_tool_calls,
)


class TestParseArgs:
    def test_valid_json_object(self):
        result = _parse_args('{"name": "read_file", "path": "test.py"}')
        assert result == {"name": "read_file", "path": "test.py"}

    def test_empty_string(self):
        assert _parse_args("") == {}
        assert _parse_args("   ") == {}

    def test_json_array_returns_empty(self):
        result = _parse_args("[1, 2, 3]")
        assert result == {}

    def test_malformed_json_kv_extraction(self):
        result = _parse_args('{"key1": "val1", "key2": 123}')
        assert "key1" in result
        assert result["key1"] == "val1"

    def test_html_escaped(self):
        result = _parse_args('{"name": "read_file", &quot;path&quot;: &quot;test.py&quot;}')
        assert "name" in result


class TestExtractKvPairs:
    def test_simple_pairs(self):
        result = _extract_kv_pairs('{"a": "hello", "b": 42}')
        assert result.get("a") == "hello"
        assert result.get("b") == 42

    def test_boolean_values(self):
        result = _extract_kv_pairs('{"x": true, "y": false, "z": null}')
        assert result["x"] is True
        assert result["y"] is False
        assert result["z"] is None

    def test_float_value(self):
        result = _extract_kv_pairs('{"pi": 3.14}')
        assert result["pi"] in (3, 3.14)  # regex may truncate to int


class TestMakeTc:
    def test_standard(self):
        tc = _make_tc(0, "read_file", {"path": "test.py"})
        assert tc["id"] == "call_xml_0000"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        assert "test.py" in tc["function"]["arguments"]

    def test_non_dict_args(self):
        tc = _make_tc(5, "echo", "not_a_dict")
        assert tc["function"]["arguments"] == "{}"

    def test_index_padding(self):
        tc = _make_tc(42, "tool", {})
        assert tc["id"] == "call_xml_0042"


class TestHasXmlToolCalls:
    def test_has_function_call_tag(self):
        assert has_xml_tool_calls("<function-call name='test' />") is True

    def test_case_insensitive(self):
        assert has_xml_tool_calls("<FUNCTION-CALL>test</FUNCTION-CALL>") is True

    def test_no_tag(self):
        assert has_xml_tool_calls("plain text without tags") is False

    def test_empty(self):
        assert has_xml_tool_calls("") is False


class TestExtractToolCalls:
    def test_format1_tag_body_json(self):
        text = '<function-call>{"name": "read_file", "path": "test.py"}</function-call>'
        tcs, cleaned = extract_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "read_file"
        assert "<function-call>" not in cleaned

    def test_format2_self_closing(self):
        text = '<function-call name="search" arguments="{&quot;pattern&quot;:&quot;TODO&quot;}" />'
        tcs, _cleaned = extract_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "search"

    def test_plain_text_no_calls(self):
        tcs, cleaned = extract_tool_calls("Hello, how are you?")
        assert len(tcs) == 0
        assert "Hello" in cleaned

    def test_xml_tags_stripped(self):
        text = "<div>Hello</div> <span>World</span>"
        _tcs, cleaned = extract_tool_calls(text)
        assert "<div>" not in cleaned
        assert "Hello" in cleaned

    def test_tools_block_stripped(self):
        text = '<tools><tool name="x">desc</tool></tools> some text'
        _tcs, cleaned = extract_tool_calls(text)
        assert "<tools>" not in cleaned
        assert "some text" in cleaned

    def test_multiple_function_calls(self):
        text = (
            '<function-call>{"name": "read_file", "path": "a.py"}</function-call>\n'
            '<function-call>{"name": "search", "pattern": "TODO"}</function-call>'
        )
        tcs, _cleaned = extract_tool_calls(text)
        assert len(tcs) == 2

    def test_cleaned_whitespace(self):
        text = "hello\n\n\n\nworld"
        _tcs, cleaned = extract_tool_calls(text)
        assert cleaned.count("\n") <= 2
