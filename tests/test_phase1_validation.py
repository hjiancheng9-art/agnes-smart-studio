"""Test Phase 1: ToolCall validation + Self-Correction"""

import pytest

from core.tool_call_validator import ParsedCall, ToolCallValidator, ValidationResult
from core.tool_result import ToolResult
from core.validation_errors import ValidationCode, ValidationError, ValidationIssue

# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def validator():
    """Create a ToolCallValidator with known tools."""
    schema = lambda n: {
        "read_file": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        "write_file": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        "run_bash": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    }.get(n)
    return ToolCallValidator(schema_provider=schema, known_tools={"read_file", "write_file", "run_bash"})


# ── ValidationCode enum ────────────────────────────────────────────


class TestValidationCode:
    def test_enum_values_exist(self):
        codes = [c.value for c in ValidationCode]
        assert "unknown_tool" in codes
        assert "schema_missing_required" in codes
        assert "schema_type_mismatch" in codes
        assert "xml_parse_error" in codes
        assert "tool_execution_error" in codes
        assert len(codes) == 16

    def test_enum_name_access(self):
        assert ValidationCode.UNKNOWN_TOOL == ValidationCode.UNKNOWN_TOOL
        assert ValidationCode.SCHEMA_MISSING_REQUIRED.value == "schema_missing_required"


# ── ValidationIssue ─────────────────────────────────────────────────


class TestValidationIssue:
    def test_creation(self):
        iss = ValidationIssue(
            code="unknown_tool",
            message="Tool not found",
            tool_name="fake",
            hint="Use read_file instead",
        )
        assert iss.code == "unknown_tool"
        assert "fake" in iss.tool_name
        assert iss.tool_name == "fake"

    def test_defaults(self):
        iss = ValidationIssue(code="unknown_tool", message="Tool not found")
        assert iss.tool_name is None
        assert iss.hint is None


# ── ValidationError ─────────────────────────────────────────────────


class TestValidationError:
    def test_aggregation(self):
        issues = [
            ValidationIssue(code=ValidationCode.UNKNOWN_TOOL, message="bad"),
            ValidationIssue(code=ValidationCode.INVALID_INVOKE, message="xml"),
        ]
        err = ValidationError(issues=issues)
        assert len(err.issues) == 2
        assert "bad" in str(err)

    def test_empty(self):
        err = ValidationError(issues=[])
        assert len(err.issues) == 0


# ── ToolCallValidator: valid calls ──────────────────────────────────


class TestValidatorValid:
    def test_simple_valid(self, validator):
        xml = '<invoke name="read_file"><param name="path" value="test.txt" /></invoke>'
        r = validator.validate_llm_output(xml)
        assert r.is_valid
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "read_file"
        assert r.tool_calls[0]["arguments"] == {"path": "test.txt"}

    def test_multiple_params(self, validator):
        xml = '<invoke name="write_file"><param name="path" value="a.py"/><param name="content" value="x"/></invoke>'
        r = validator.validate_llm_output(xml)
        assert r.is_valid
        assert r.tool_calls[0]["name"] == "write_file"
        assert "path" in r.tool_calls[0]["arguments"]

    def test_mixed_content(self, validator):
        text = 'Here is my answer.\n\n<invoke name="read_file"><param name="path" value="x.py"/></invoke>\n\nDone.'
        r = validator.validate_llm_output(text)
        assert r.is_valid
        assert len(r.tool_calls) == 1

    def test_markdown_fence(self, validator):
        text = '```xml\n<invoke name="read_file"><param name="path" value="x.py"/></invoke>\n```'
        r = validator.validate_llm_output(text)
        assert r.is_valid
        assert len(r.tool_calls) == 1

    def test_no_tool_calls(self, validator):
        r = validator.validate_llm_output("Just a text response, no tools.")
        assert r.is_valid
        assert len(r.tool_calls) == 0


# ── ToolCallValidator: invalid calls ────────────────────────────────


class TestValidatorInvalid:
    def test_unknown_tool(self, validator):
        r = validator.validate_llm_output('<invoke name="bogus"><param name="x" value="1"/></invoke>')
        assert not r.is_valid
        assert any("bogus" in i.message for i in r.issues)

    def test_missing_required_param(self, validator):
        r = validator.validate_llm_output('<invoke name="read_file"></invoke>')
        assert not r.is_valid  # path is required
        assert any("path" in i.message for i in r.issues)

    def test_type_mismatch(self, validator):
        r = validator.validate_llm_output('<invoke name="read_file"><param name="path" value="123"/></invoke>')
        # path=123 is string, but schema expects string → should be OK (auto-coerce)
        assert r.is_valid

    def test_multiple_calls_mixed(self, validator):
        xml = '<invoke name="read_file"><param name="path" value="a"/></invoke>\n<invoke name="bogus"><param name="x" value="1"/></invoke>'
        r = validator.validate_llm_output(xml)
        assert not r.is_valid
        assert any("bogus" in i.message for i in r.issues)

    def test_empty_input(self, validator):
        r = validator.validate_llm_output("")
        assert r.is_valid
        assert len(r.tool_calls) == 0


# ── ToolCallValidator: validate_tool_call ───────────────────────────


class TestValidateToolCall:
    def test_valid(self, validator):
        issues = validator.validate_tool_call("read_file", {"path": "test.txt"})
        assert len(issues) == 0

    def test_valid_write(self, validator):
        issues = validator.validate_tool_call("write_file", {"path": "x.py", "content": "hi"})
        assert len(issues) == 0

    def test_unknown_tool(self, validator):
        issues = validator.validate_tool_call("nonexistent", {})
        assert len(issues) >= 1
        assert "Unknown" in issues[0].message

    def test_missing_required(self, validator):
        issues = validator.validate_tool_call("read_file", {})
        assert len(issues) >= 1
        assert "path" in issues[0].message


# ── ToolCallValidator: error messages ───────────────────────────────


class TestErrorMessage:
    def test_build_error_message(self, validator):
        r = validator.validate_llm_output('<invoke name="bogus" />')
        msg = validator.build_error_message(r)
        assert "bogus" in msg
        assert "fix" in msg.lower() or "corrected" in msg.lower() or "retry" in msg.lower()

    def test_error_message_contains_hint(self, validator):
        r = validator.validate_llm_output('<invoke name="read_file"></invoke>')
        msg = validator.build_error_message(r)
        # Should contain guidance
        assert len(msg) > 20


# ── ToolResult ──────────────────────────────────────────────────────


class TestToolResult:
    def test_ok(self):
        tr = ToolResult.ok(data="hello", metadata={"tool_name": "test"})
        assert tr.success
        assert tr.data == "hello"

    def test_fail(self):
        tr = ToolResult.fail(code="ERR", message="bad")
        assert not tr.success
        assert tr.error.code == "ERR"

    def test_ok_context_includes_tool_name(self):
        tr = ToolResult.ok(data="data", metadata={"tool_name": "reader"})
        ctx = tr.to_llm_context()
        assert "reader" in ctx or "[OK]" in ctx

    def test_fail_context(self):
        tr = ToolResult.fail(code="X", message="failed")
        ctx = tr.to_llm_context()
        assert "[FAIL]" in ctx

    def test_to_llm_context_no_metadata(self):
        tr = ToolResult.ok(data="x")
        ctx = tr.to_llm_context()
        assert ctx is not None

    def test_fail_from_exception(self):
        tr = ToolResult.from_exception(ValueError("bad value"))
        assert not tr.success


# ── ParsedCall ──────────────────────────────────────────────────────


class TestParsedCall:
    def test_defaults(self):
        pc = ParsedCall(name="test")
        assert pc.name == "test"
        assert pc.arguments == {}
        assert pc.raw_xml == ""


# ── ValidationResult ────────────────────────────────────────────────


class TestValidationResult:
    def test_valid(self):
        vr = ValidationResult(is_valid=True, tool_calls=[{"name": "t", "arguments": {}}])
        assert vr.is_valid
        assert vr.summary() == "OK"

    def test_invalid_summary(self):
        issues = [ValidationIssue(code=ValidationCode.UNKNOWN_TOOL, message="bad", tool_name="x")]
        vr = ValidationResult(is_valid=False, issues=issues)
        assert "bad" in vr.summary()

    def test_error_messages(self):
        issues = [ValidationIssue(code=ValidationCode.UNKNOWN_TOOL, message="error")]
        vr = ValidationResult(is_valid=False, issues=issues)
        assert vr.error_messages() == ["error"]
