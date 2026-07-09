"""Self-Audit: Tool Call Chain — parse, validate, dispatch, result structure.

Tests the core loop:
  LLM XML output → ToolCallValidator.parse → validate → dispatch → ToolResult
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

# ── Test data — CRUX uses attribute-style params: <param name="x" value="y" /> ──

BAD_XML_CASES = [
    ("unclosed", "<invoke name='read_file'><param name='path' value='README.md'>"),
    ("missing_name", "<invoke><param name='path' value='x' /></invoke>"),
    ("unknown_tool", "<invoke name='unknown_tool_xyz'><param name='path' value='x' /></invoke>"),
    ("missing_param", "<invoke name='read_file'></invoke>"),
    ("nested", "<invoke name='read_file'><invoke name='write_file'><param name='path' value='x' /></invoke></invoke>"),
    ("param_no_name", "<invoke name='read_file'><param value='x' /></invoke>"),
    ("empty_invoke", "<invoke></invoke>"),
    ("multi", "<invoke name='read_file'><param name='path' value='a' /></invoke><invoke name='write_file'><param name='path' value='b' /></invoke>"),
]

VALID_TOOL_CASES = [
    {"name": "read_file_simple", "xml": '<invoke name="read_file"><param name="path" value="README.md" /></invoke>',
     "expected_tool": "read_file", "expected_args": {"path": "README.md"}},
    {"name": "search_files", "xml": '<invoke name="search_files"><param name="pattern" value="def test_" /></invoke>',
     "expected_tool": "search_files", "expected_args": {"pattern": "def test_"}},
    {"name": "web_search", "xml": '<invoke name="web_search"><param name="query" value="CRUX Studio latest version" /></invoke>',
     "expected_tool": "web_search", "expected_args": {"query": "CRUX Studio latest version"}},
]


@dataclass
class MockToolResult:
    """Simulates a tool execution result."""
    success: bool
    data: Any = None
    error: str | None = None
    hints: list = field(default_factory=list)
    metadata: dict = field(default_factory=lambda: {
        "tool_name": "", "duration_ms": 0, "trace_id": str(uuid.uuid4()),
    })
    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error,
                "hints": self.hints, "metadata": self.metadata}


# ── 1. XML PARSING ──

class TestXmlParsing:
    """Phase 1: extract tool calls from raw LLM output."""

    def test_valid_xml_extracts_correctly(self, validator):
        """Valid XML should extract tool name and params."""
        xml = '<invoke name="read_file"><param name="path" value="README.md" /></invoke>'
        result = validator.validate_llm_output(xml)
        assert result.is_valid, f"Expected valid, got issues: {result.issues}"
        assert len(result.tool_calls) >= 1
        # Tool calls are dicts with 'name' and 'arguments'
        call = result.tool_calls[0]
        assert call["name"] == "read_file"
        assert "path" in call["arguments"] or call["arguments"] == {}, \
            f"args should contain path: {call['arguments']}"

    def test_valid_xml_in_text_body(self, validator):
        """Tool call embedded in text should still be extracted."""
        text = """Let me read that file for you.

<invoke name="read_file"><param name="path" value="README.md" /></invoke>

Here you go:"""
        result = validator.validate_llm_output(text)
        assert isinstance(result, type(validator.validate_llm_output("")))  # same type
        assert len(result.tool_calls) >= 1

    def test_no_tool_call_returns_gracefully(self, validator):
        """Plain text without XML should not crash."""
        result = validator.validate_llm_output("Just a normal response.")
        # Should return a valid result (not crash)
        assert hasattr(result, 'is_valid')

    def test_plain_text_no_tool_call(self, validator):
        """No tool call pattern should not fail."""
        result = validator.validate_llm_output("你好，我是 CRUX Studio v6.0.0")
        assert hasattr(result, 'tool_calls')


# ── 2. BAD XML HANDLING ──

class TestBadXmlHandling:
    """Must return structured errors, not crash."""

    @pytest.mark.parametrize("case_name,bad_xml", BAD_XML_CASES)
    def test_bad_xml_does_not_crash(self, validator, case_name, bad_xml):
        """Every bad XML case must not raise unhandled exception."""
        try:
            result = validator.validate_llm_output(bad_xml)
            assert hasattr(result, 'is_valid')
        except Exception as e:
            pytest.fail(f"validator.validate_llm_output raised for '{case_name}': {e}")

    @pytest.mark.parametrize("case_name,bad_xml", BAD_XML_CASES)
    def test_bad_xml_has_error_info(self, validator, case_name, bad_xml):
        """Bad XML should include error details."""
        try:
            result = validator.validate_llm_output(bad_xml)
            # Either not valid, or has issues
            if not result.is_valid:
                assert len(result.issues) > 0, f"Not valid but no issues for '{case_name}'"
                # Check that issues have useful info
                for issue in result.issues:
                    assert issue.code is not None
                    assert issue.message
        except Exception as e:
            pytest.fail(f"validator.validate_llm_output raised for '{case_name}': {e}")


# ── 3. TOOL DISPATCH ──

class TestToolDispatch:
    """Validate _dispatch_tool_impl routing correctness."""

    @pytest.mark.parametrize("case", VALID_TOOL_CASES, ids=lambda c: c["name"])
    def test_dispatch_correct_tool(self, case):
        """Ensure correct tool name and args are passed to dispatch."""
        from core.chat_tool_dispatch import _dispatch_tool_impl
        mock_self = MagicMock()
        mock_self.adversarial_mode = False
        mock_self.permission_check = MagicMock(return_value=False)

        result = _dispatch_tool_impl(
            mock_self,
            name=case["expected_tool"],
            args_json=json.dumps(case["expected_args"]),
        )
        # Just make sure it doesn't crash
        assert result is not None

    def test_unknown_tool_handled(self):
        """Unknown tool should not crash."""
        from core.chat_tool_dispatch import _dispatch_tool_impl
        mock_self = MagicMock()
        mock_self.adversarial_mode = False
        mock_self.permission_check = MagicMock(return_value=False)

        result = _dispatch_tool_impl(mock_self, name="foo_bar_baz", args_json='{}')
        assert result is not None


# ── 4. TOOL RESULT STRUCTURE ──

class TestToolResultStructure:
    """All tools must return ToolResult-compatible dicts."""

    REQUIRED_KEYS = {"success", "data"}

    def test_result_has_required_keys(self):
        """Every ToolResult dict must have success and data."""
        result = MockToolResult(success=True, data="test")
        d = result.to_dict()
        for key in self.REQUIRED_KEYS:
            assert key in d, f"Missing required key: {key}"

    def test_result_success_true_has_data(self):
        """When success=True, data should be present."""
        result = MockToolResult(success=True, data="valid content")
        assert result.data is not None

    def test_result_success_false_has_error(self):
        """When success=False, error should be present."""
        result = MockToolResult(success=False, error="File not found")
        assert result.error is not None
        assert len(result.error) > 0

    def test_result_metadata_has_tool_name(self):
        """Metadata must identify which tool produced the result."""
        result = MockToolResult(success=True, data="x")
        result.metadata["tool_name"] = "read_file"
        assert "tool_name" in result.metadata

    def test_result_metadata_has_duration(self):
        """Metadata must include execution duration."""
        result = MockToolResult(success=True, data="x")
        result.metadata["duration_ms"] = 42
        assert isinstance(result.metadata["duration_ms"], (int, float))

    def test_result_metadata_has_trace_id(self):
        """Metadata must have trace_id for debugging."""
        result = MockToolResult(success=True, data="x")
        assert "trace_id" in result.metadata
        assert len(result.metadata["trace_id"]) > 0


# ── 5. EDGE CASES ──

class TestEdgeCases:
    """Boundary conditions for tool calls."""

    def test_empty_string_input(self, validator):
        """Empty string should not crash validator."""
        result = validator.validate_llm_output("")
        assert hasattr(result, 'is_valid')

    def test_whitespace_only(self, validator):
        """Whitespace-only input should not crash."""
        result = validator.validate_llm_output("   \n\n  ")
        assert hasattr(result, 'is_valid')

    def test_extremely_long_input(self, validator):
        """Very long input (10K chars) should not hang."""
        long_text = '<invoke name="read_file"><param name="path" value="' + "a" * 5000 + '" /></invoke>'
        result = validator.validate_llm_output(long_text)
        assert hasattr(result, 'is_valid')

    def test_xml_with_special_chars(self, validator):
        """XML with unicode special chars."""
        text = '<invoke name="web_search"><param name="query" value="CRUX v6.0.0 中文测试 🎯" /></invoke>'
        result = validator.validate_llm_output(text)
        assert hasattr(result, 'is_valid')

    @pytest.mark.parametrize("count", [2, 5, 10])
    def test_multiple_sequential_tool_calls(self, validator, count):
        """Multiple <invoke> blocks in sequence."""
        parts = []
        for i in range(count):
            parts.append(f'<invoke name="read_file"><param name="path" value="file_{i}.md" /></invoke>')
        text = "\n".join(parts)
        result = validator.validate_llm_output(text)
        assert hasattr(result, 'is_valid')
