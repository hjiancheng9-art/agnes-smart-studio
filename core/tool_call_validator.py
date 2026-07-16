# core/tool_call_validator.py
"""ToolCall Validator — validates LLM tool call XML syntax, params, and tool existence.

Phase 1 of CRUX intelligence improvement.
Uses ValidationIssue/ValidationError from validation_errors.py.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.validation_errors import ValidationCode, ValidationIssue

logger = logging.getLogger(__name__)


# ── Parsed call model ────────────────────────────────────────────────


@dataclass
class ParsedCall:
    """A single parsed tool call from LLM output."""
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_xml: str = ""


# ── Validation result ────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Result of validating an LLM output containing tool calls."""
    is_valid: bool = True
    tool_calls: list[dict] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    def error_messages(self) -> list[str]:
        return [i.message for i in self.issues]

    def summary(self) -> str:
        if not self.issues:
            return "OK"
        lines = [f"[{i.code.value}] {i.tool_name}: {i.message}" for i in self.issues[:10]]
        if len(self.issues) > 10:
            lines.append(f"... and {len(self.issues) - 10} more issues")
        return "\n".join(lines)


# ── Main validator ───────────────────────────────────────────────────


class ToolCallValidator:
    """Validates tool calls from LLM output.

    Args:
        schema_provider: Optional callable(tool_name) -> dict (JSON Schema)
        coerce_scalar_values: Auto-convert string params to int/float if type mismatch
        known_tools: Optional set of known tool names (auto-populated from schema_provider)
    """

    def __init__(
        self,
        schema_provider: Callable[[str], dict | None] | None = None,
        coerce_scalar_values: bool = True,
        known_tools: set[str] | None = None,
    ):
        self.schema_provider = schema_provider
        self.coerce_scalar_values = coerce_scalar_values
        self.tool_schemas: dict[str, dict] = {}
        if known_tools:
            self.tool_schemas = {t: {} for t in known_tools}

    # ── Public API ──────────────────────────────────────────────────

    def validate_llm_output(self, text: str) -> ValidationResult:
        """Full pipeline: extract, parse, validate tool calls from LLM response.

        Steps:
        1. Strip markdown code fences
        2. Extract <invoke> tags
        3. Parse XML to extract tool name + params
        4. Validate tool existence
        5. Validate params against schemas
        """
        cleaned = self._strip_markdown_fences(text)
        calls = self._extract_invoke_tags(cleaned)
        if not calls:
            # Maybe the LLM didn't call any tools — that's OK
            return ValidationResult(is_valid=True, tool_calls=[])

        parsed_calls, xml_issues = self._parse_invoke_tags(calls)
        if xml_issues:
            return ValidationResult(
                is_valid=False,
                tool_calls=[p.__dict__ for p in parsed_calls],
                issues=xml_issues,
            )

        # Validate each parsed call
        all_issues: list[ValidationIssue] = []
        valid_calls: list[dict] = []
        for pc in parsed_calls:
            issues = self._validate_one(pc)
            if issues:
                all_issues.extend(issues)
            valid_calls.append({"name": pc.name, "arguments": pc.arguments})

        is_valid = len(all_issues) == 0
        return ValidationResult(
            is_valid=is_valid,
            tool_calls=valid_calls if is_valid else [],
            issues=all_issues,
        )

    def validate_tool_call(self, name: str, args: dict) -> list[ValidationIssue]:
        """Validate a single tool call (name + args) — used from ChatSession hook."""
        issues: list[ValidationIssue] = []

        # Check tool exists
        if not self._has_tool(name):
            available = list(self.tool_schemas.keys())
            hint = f"Available: {available[:10]}" if available else "No tools registered"
            issues.append(ValidationIssue(
                code=ValidationCode.UNKNOWN_TOOL,
                message=f"Unknown tool: '{name}'",
                tool_name=name,
                hint=hint,
            ))
            return issues

        # ── 参数归一化：cdp_ask_chatgpt 接受 question/text/prompt/message/query/input ──
        if name == "cdp_ask_chatgpt":
            args = _normalize_chatgpt_args(args)

        # Validate against schema
        schema = self._get_schema(name)
        if schema:
            issues.extend(self._validate_args_with_schema(
                ParsedCall(name=name, arguments=args),
                schema,
            ))

        return issues

    def build_error_message(self, result: ValidationResult) -> str:
        """Build a correction prompt to inject back to LLM."""
        lines = [
            "Your previous tool call(s) failed validation. Please fix and retry.",
            "",
            "Issues:",
        ]
        for i, issue in enumerate(result.issues[:15], 1):
            lines.append(f"  {i}. [{issue.code.value}] {issue.message}")
            if issue.hint:
                lines.append(f"     Hint: {issue.hint}")

        if len(result.issues) > 15:
            lines.append(f"  ... and {len(result.issues) - 15} more issues")

        lines.extend([
            "",
            "Please output corrected <invoke> tags with valid parameters.",
            "Do NOT repeat the previous incorrect call.",
        ])
        return "\n".join(lines)

    # ── XML extraction ──────────────────────────────────────────────

    def _strip_markdown_fences(self, text: str) -> str:
        """Remove ```xml ... ``` or ``` ... ``` fences."""
        return re.sub(
            r'```(?:xml|json)?\s*\n?(.*?)\n?```',
            r'\1',
            text,
            flags=re.DOTALL,
        ).strip()

    def _extract_invoke_tags(self, text: str) -> list[str]:
        """Extract all <invoke ...>...</invoke> or <invoke ... /> blocks."""
        # Self-closing tags
        pattern1 = r'<invoke\b[^>]*/>'
        matches1 = re.findall(pattern1, text, re.DOTALL)
        if matches1:
            return matches1
        # Full blocks
        pattern2 = r'<invoke\b[^>]*>.*?</invoke>'
        matches2 = re.findall(pattern2, text, re.DOTALL)
        if matches2:
            return matches2
        # Fallback: extract anything between <invoke and </invoke
        start_tags = [m.start() for m in re.finditer(r'<invoke\b', text)]
        results = []
        for start in start_tags:
            end = text.find("</invoke>", start)
            if end >= 0:
                results.append(text[start:end + len("</invoke>")])
        return results

    def _parse_invoke_tags(
        self, tags: list[str],
    ) -> tuple[list[ParsedCall], list[ValidationIssue]]:
        """Parse invoke tags into ParsedCall objects."""
        calls: list[ParsedCall] = []
        issues: list[ValidationIssue] = []

        for tag in tags:
            name = self._extract_attr(tag, "name")
            if not name:
                issues.append(ValidationIssue(
                    code=ValidationCode.INVALID_INVOKE,
                    message="Missing 'name' attribute in <invoke>",
                    hint="Format: <invoke name=\"tool_name\">...</invoke>",
                ))
                continue

            # Extract params
            args = self._extract_params(tag)

            calls.append(ParsedCall(name=name, arguments=args, raw_xml=tag))

        return calls, issues

    def _extract_attr(self, tag: str, attr: str) -> str | None:
        m = re.search(rf'{attr}\s*=\s*"([^"]*)"', tag)
        return m.group(1) if m else None

    def _extract_params(self, tag: str) -> dict[str, Any]:
        """Extract <param name="x" value="y" /> from invoke tag."""
        params: dict[str, Any] = {}
        for m in re.finditer(
            r'<param\s+name="([^"]*)"\s+value="([^"]*)"\s*/?>',
            tag,
        ):
            key = m.group(1)
            raw = m.group(2)
            # Coerce types
            params[key] = self._coerce_value(raw)
        return params

    def _coerce_value(self, raw: str) -> Any:
        if not self.coerce_scalar_values:
            return raw
        # Try int
        try:
            return int(raw)
        except ValueError:
            pass
        # Try float
        try:
            return float(raw)
        except ValueError:
            pass
        # Bool
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        return raw

    # ── Schema validation ──────────────────────────────────────────

    def _validate_one(self, call: ParsedCall) -> list[ValidationIssue]:
        """Validate a single parsed call."""
        issues: list[ValidationIssue] = []

        if not self._has_tool(call.name):
            available = list(self.tool_schemas.keys())
            hint = f"Available: {available[:10]}" if available else "No tools registered"
            issues.append(ValidationIssue(
                code=ValidationCode.UNKNOWN_TOOL,
                message=f"Unknown tool: '{call.name}'",
                tool_name=call.name,
                hint=hint,
            ))
            return issues

        schema = self._get_schema(call.name)
        if schema:
            issues.extend(self._validate_args_with_schema(call, schema))

        return issues

    def _has_tool(self, name: str) -> bool:
        if name in self.tool_schemas:
            return True
        if self.schema_provider:
            try:
                schema = self.schema_provider(name)
                if schema is not None:
                    self.tool_schemas[name] = schema
                    return True
            except Exception:
                logger.debug("Exception in tool_call_validator", exc_info=True)
        return False

    def _get_schema(self, name: str) -> dict | None:
        if self.tool_schemas.get(name):
            return self.tool_schemas[name]
        if self.schema_provider:
            try:
                schema = self.schema_provider(name)
                if schema is not None:
                    self.tool_schemas[name] = schema
                    return schema
            except Exception:
                logger.debug("Exception in tool_call_validator", exc_info=True)
        return None

    def _validate_args_with_schema(self, call: ParsedCall, schema: dict) -> list[ValidationIssue]:
        """Validate parsed arguments against a JSON Schema."""
        issues: list[ValidationIssue] = []
        params = call.arguments or {}

        # Check required params
        for r in schema.get("required", []):
            if r not in params:
                issues.append(ValidationIssue(
                    code=ValidationCode.SCHEMA_MISSING_REQUIRED,
                    message=f"Missing required parameter: '{r}' for {call.name}",
                    tool_name=call.name,
                    hint=f"Add param name=\"{r}\" value=\"...\" to <invoke name=\"{call.name}\">",
                ))

        # Check param types
        properties = schema.get("properties", {})
        for pname, pval in params.items():
            prop = properties.get(pname, {})
            expected_type = prop.get("type", "string")

            if expected_type == "integer" and not isinstance(pval, int):
                issues.append(ValidationIssue(
                    code=ValidationCode.SCHEMA_TYPE_MISMATCH,
                    message=f"Parameter '{pname}' should be integer, got {type(pval).__name__}",
                    tool_name=call.name,
                    hint=f"Set value=\"{pval}\" as numeric",
                ))
            elif expected_type == "number" and not isinstance(pval, (int, float)):
                issues.append(ValidationIssue(
                    code=ValidationCode.SCHEMA_TYPE_MISMATCH,
                    message=f"Parameter '{pname}' should be number, got {type(pval).__name__}",
                    tool_name=call.name,
                ))
            elif expected_type == "array" and not isinstance(pval, (list, tuple)):
                issues.append(ValidationIssue(
                    code=ValidationCode.SCHEMA_TYPE_MISMATCH,
                    message=f"Parameter '{pname}' should be array",
                    tool_name=call.name,
                ))

            # Check enum
            enum_vals = prop.get("enum")
            if enum_vals and pval not in enum_vals:
                issues.append(ValidationIssue(
                    code=ValidationCode.SCHEMA_VALIDATION_ERROR,
                    message=f"Parameter '{pname}' value '{pval}' not in allowed: {enum_vals}",
                    tool_name=call.name,
                ))

        return issues


# ── cdp_ask_chatgpt 参数归一化（模块级别） ──────────────────────────────
# 模型可能传 text/prompt/message/query/input 而不是 question，
# 在 schema 校验和 dispatch 之前统一归一化。

_CDP_CHATGPT_ALIASES = ("question", "text", "prompt", "message", "query", "input")


def _normalize_chatgpt_args(args: dict) -> dict:
    """将 cdp_ask_chatgpt 的参数归一化为 'question'。"""
    if not isinstance(args, dict):
        return args
    for key in _CDP_CHATGPT_ALIASES:
        val = args.get(key)
        if val and isinstance(val, str) and val.strip():
            return {"question": val.strip()}
    return args
