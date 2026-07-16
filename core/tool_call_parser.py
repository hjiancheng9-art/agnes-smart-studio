"""XML tool-call parser for local models that don't use OpenAI native format.

Supported formats from Qwen2.5-Coder and similar models:
  1. <function-call>{"name": "...", "arguments": {...}}</function-call>
  2. <function-call name="func" arguments='{"k":"v"}' />
  3. <function-call name="func" arguments="..."/>

Converts them into OpenAI-compatible tool_calls delta format.
Also strips XML/HTML tags from output text.
"""

from __future__ import annotations

import contextlib
import html
import json
import logging
import re

logger = logging.getLogger(__name__)

# ── Patterns ──────────────────────────────────────

# Match <function-call ...> body </function-call>
_FC_TAG_RE = re.compile(
    r"<function-call\b[^>]*>(.*?)</function-call>",
    re.DOTALL | re.IGNORECASE,
)

# Match <function-call name="..." arguments="..." />
_FC_SELF_CLOSE_RE = re.compile(
    r"""<function-call\s+name\s*=\s*['"]([^'"]+)['"]\s+arguments\s*=\s*['"]([^'"]*?)['"]\s*/\s*>""",
    re.IGNORECASE,
)

# Strip all XML-like tags AND their content from text
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
# Strip <function-call>...</function-call> entirely (tags + body)
_FC_BLOCK_RE = re.compile(
    r"<function-call\b[^>]*>.*?</function-call>",
    re.DOTALL | re.IGNORECASE,
)
# Strip self-closing <function-call ... />
_FC_SELF_CLOSE_STRIP_RE = re.compile(
    r"<function-call\b[^>]*?/\s*>",
    re.IGNORECASE,
)
# Strip <tools> blocks
_TOOLS_BLOCK_RE = re.compile(
    r"<tools>.*?</tools>",
    re.DOTALL | re.IGNORECASE,
)

# ── JSON / Python literal parsing ─────────────────


def _parse_args(raw: str) -> dict:
    """Try to parse arguments as JSON, Python literal, or key-value extraction."""
    if not raw or not raw.strip():
        return {}

    raw = html.unescape(raw)

    # Try JSON first
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Try Python dict literal
    try:
        import ast

        result = ast.literal_eval(raw)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError, TypeError):
        pass

    # Extract key-value pairs from malformed JSON using simple scanning
    return _extract_kv_pairs(raw)


def _extract_kv_pairs(raw: str) -> dict:
    """Extract key-value pairs from malformed JSON using string scanning.

    Handles: {"key1": "val1", "key2": "val2 with \"unescaped\" quotes"}
    """
    result: dict = {}
    # Find all "key": value pairs
    pair_re = re.compile(r'"([^"]+)"\s*:\s*("(?:[^"\\]|\\.)*"|\d+|true|false|null|\{[^}]*\})')
    for m in pair_re.finditer(raw):
        key = m.group(1)
        val = m.group(2)
        # Unquote string values
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val == "true":
            val = True
        elif val == "false":
            val = False
        elif val == "null":
            val = None
        else:
            try:
                val = int(val)
            except ValueError:
                with contextlib.suppress(ValueError):
                    val = float(val)
        result[key] = val
    return result


def _extract_tc_from_text(text: str) -> list[tuple[str, dict]]:
    """Extract (name, arguments) pairs from text.

    Handles malformed JSON. If arguments can't be parsed, uses raw string.
    """
    results: list[tuple[str, dict]] = []

    name_re = re.compile(r'"name"\s*:\s*"([^"]+)"')
    args_start_re = re.compile(r'"arguments"\s*:\s*(\{)')

    for name_match in name_re.finditer(text):
        name = name_match.group(1)
        pos = name_match.end()

        args_m = args_start_re.search(text, pos)
        if not args_m:
            continue

        # Extract args JSON via brace counting (handles nested braces, strings)
        start = args_m.start(1)
        depth = 0
        in_str = False
        esc = False
        end = start
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

        if end > start:
            args_json = text[start:end]
            args = _parse_args(args_json)
            if args:
                results.append((name, args))

    return results
    """Extract JSON objects from text using brace counting (handles nesting)."""
    results = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 0
            in_string = False
            escape = False
            start = i
            while i < len(text):
                c = text[i]
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            results.append(text[start : i + 1])
                            break
                i += 1
        i += 1
    return results


# ── Main API ──────────────────────────────────────


def extract_tool_calls(text: str) -> tuple[list[dict], str]:
    """Extract tool calls from model text output.

    Returns:
        (tool_calls, cleaned_text)
        - tool_calls: list of OpenAI-format tool call dicts
        - cleaned_text: text with all XML tags stripped
    """
    tool_calls: list[dict] = []
    call_index = 0

    # Format 1: <function-call>JSON</function-call>
    for match in _FC_TAG_RE.finditer(text):
        body = match.group(1).strip()
        if body.startswith("{"):
            data = _parse_args(body)
            name = data.pop("name", "")
            args = data.pop("arguments", data)  # if no 'arguments' key, use the rest
            if name:
                tool_calls.append(_make_tc(call_index, name, args))
                call_index += 1

    # Format 2: <function-call name="x" arguments="..." />
    for match in _FC_SELF_CLOSE_RE.finditer(text):
        name = match.group(1)
        raw_args = match.group(2)
        args = _parse_args(raw_args)
        if name:
            tool_calls.append(_make_tc(call_index, name, args))
            call_index += 1

    # Format 3: raw JSON with "name" and "arguments" keys
    # Skip content inside <tools> blocks (tool definitions, not calls)
    text_no_tools = _TOOLS_BLOCK_RE.sub("", text)
    for name, args in _extract_tc_from_text(text_no_tools):
        if name and args:
            tool_calls.append(_make_tc(call_index, name, args))
            call_index += 1

    # Strip all function-call blocks and XML tags from text
    cleaned = _FC_BLOCK_RE.sub("", text)
    cleaned = _FC_SELF_CLOSE_STRIP_RE.sub("", cleaned)
    cleaned = _TOOLS_BLOCK_RE.sub("", cleaned)
    # Strip extracted raw JSON tool call blocks
    for name, _ in _extract_tc_from_text(cleaned):
        cleaned = re.sub(
            r'\{\s*"name"\s*:\s*"' + re.escape(name) + r'".*?\n\}',
            "",
            cleaned,
            count=1,
            flags=re.DOTALL,
        )
    cleaned = _TAG_STRIP_RE.sub("", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = cleaned.strip()

    return tool_calls, cleaned


def _make_tc(index: int, name: str, arguments: dict) -> dict:
    """Build an OpenAI-format tool_call dict."""
    if not isinstance(arguments, dict):
        arguments = {}
    return {
        "id": f"call_xml_{index:04d}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def has_xml_tool_calls(text: str) -> bool:
    """Quick check if text contains XML-format tool calls."""
    return "<function-call" in text.lower()
