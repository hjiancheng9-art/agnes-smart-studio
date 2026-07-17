"""Unit tests for core.tool_call_parser — XML tool call extraction."""

from __future__ import annotations

from core.tool_call_parser import extract_tool_calls, has_xml_tool_calls


class TestHasXmlToolCalls:
    def test_detects_function_call_tag(self):
        assert has_xml_tool_calls("<function-call>test</function-call>") is True

    def test_detects_self_closing_tag(self):
        assert has_xml_tool_calls('<function-call name="t" arguments="{}"/>') is True

    def test_no_xml_in_plain_text(self):
        assert has_xml_tool_calls("hello world") is False

    def test_other_tags_not_detected(self):
        assert has_xml_tool_calls("<html><body>text</body></html>") is False

    def test_empty_string(self):
        assert has_xml_tool_calls("") is False


class TestExtractToolCalls:
    def test_plain_text_no_tool_calls(self):
        tools, cleaned = extract_tool_calls("Just some regular text.")
        assert tools == []
        assert "Just some regular text." in cleaned

    def test_self_closing_tag(self):
        text = '<function-call name="search" arguments="{&quot;q&quot;:&quot;test&quot;}"/>'
        tools, _ = extract_tool_calls(text)
        assert len(tools) >= 1
        assert tools[0]["function"]["name"] == "search"

    def test_body_tag_with_json(self):
        text = '<function-call>{"name":"read_file","arguments":{"path":"/x"}}</function-call>'
        tools, cleaned = extract_tool_calls(text)
        assert len(tools) >= 1
        assert any(t["function"]["name"] == "read_file" for t in tools)
        assert "<function-call>" not in cleaned

    def test_text_surrounding_preserved(self):
        text = 'Before <function-call name="x" arguments="{&quot;k&quot;:1}"/> After'
        tools, cleaned = extract_tool_calls(text)
        assert len(tools) >= 1
        assert "Before" in cleaned
        assert "After" in cleaned
        assert "<function-call>" not in cleaned

    def test_malformed_json_in_body(self):
        text = "<function-call>{not valid json}</function-call>"
        tools, _ = extract_tool_calls(text)
        # Should not crash on malformed JSON
        assert isinstance(tools, list)

    def test_html_tags_stripped(self):
        text = "<div>Hello</div> world"
        _, cleaned = extract_tool_calls(text)
        assert "Hello" in cleaned
        assert "<div>" not in cleaned
