"""Self-Audit Harness: shared fixtures, factories, and trace capture."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest

from core.tool_call_validator import ToolCallValidator

# ── Trace structures ──


@dataclass
class AuditTrace:
    """Single audit test trace — captured for every test."""

    trace_id: str = ""
    version: str = "6.0.0"
    suite: str = ""
    test_name: str = ""
    input: Any = None
    route: dict = field(default_factory=dict)
    prompt: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    tool_results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    assertions: dict = field(default_factory=lambda: {"passed": 0, "failed": 0, "details": []})
    duration_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent=2) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ── Schema provider fixture ──


@pytest.fixture(scope="session")
def tool_schema_provider():
    """Provide JSON schemas for all known tools via lookup."""
    # Simplified: return a basic schema for common tools
    schemas = {
        "read_file": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        "write_file": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        "search_files": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
        "web_search": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "web_fetch": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        "run_python": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        "run_bash": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        "generate_image": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]},
    }

    def provider(name: str):
        return schemas.get(name)

    return provider


@pytest.fixture
def validator(tool_schema_provider):
    """Default ToolCallValidator instance for testing."""
    known = {
        "read_file",
        "write_file",
        "search_files",
        "web_search",
        "web_fetch",
        "run_python",
        "run_bash",
        "generate_image",
    }
    return ToolCallValidator(
        schema_provider=tool_schema_provider,
        coerce_scalar_values=True,
        known_tools=known,
    )


# ── BAD XML cases ──

BAD_XML_CASES = [
    # 1. Unclosed tag
    ("unclosed", "<invoke name='read_file'><param name='path' value='README.md'>"),
    # 2. Missing name attribute
    ("missing_name", "<invoke><param name='path' value='x' /></invoke>"),
    # 3. Unknown tool
    ("unknown_tool", "<invoke name='unknown_tool_xyz'><param name='path' value='x' /></invoke>"),
    # 4. Missing required param
    ("missing_param", "<invoke name='read_file'></invoke>"),
    # 5. Nested invoke
    ("nested", "<invoke name='read_file'><invoke name='write_file'><param name='path' value='x' /></invoke></invoke>"),
    # 6. Param without name
    ("param_no_name", "<invoke name='read_file'><param value='x' /></invoke>"),
    # 7. Invalid XML chars
    ("invalid_chars", "<invoke name='read_file'><param name='path' value='README.md & broken' /></invoke>"),
    # 8. Empty invoke
    ("empty_invoke", "<invoke></invoke>"),
    # 9. Multiple invokes
    (
        "multi",
        "<invoke name='read_file'><param name='path' value='a' /></invoke><invoke name='write_file'><param name='path' value='b' /></invoke>",
    ),
]

# ── Tool call test cases ──

VALID_TOOL_CASES = [
    {
        "name": "read_file_simple",
        "xml": '<invoke name="read_file"><param name="path" value="README.md" /></invoke>',
        "expected_tool": "read_file",
        "expected_args": {"path": "README.md"},
    },
    {
        "name": "search_files",
        "xml": '<invoke name="search_files"><param name="pattern" value="def test_" /></invoke>',
        "expected_tool": "search_files",
        "expected_args": {"pattern": "def test_"},
    },
    {
        "name": "web_search",
        "xml": '<invoke name="web_search"><param name="query" value="CRUX Studio latest version" /></invoke>',
        "expected_tool": "web_search",
        "expected_args": {"query": "CRUX Studio latest version"},
    },
]


@dataclass
class MockToolResult:
    """Simulates a tool execution result."""

    success: bool
    data: Any = None
    error: str | None = None
    hints: list = field(default_factory=list)
    metadata: dict = field(
        default_factory=lambda: {
            "tool_name": "",
            "duration_ms": 0,
            "trace_id": str(uuid.uuid4()),
        }
    )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "hints": self.hints,
            "metadata": self.metadata,
        }


# ── Audit runner helper ──


class AuditRunner:
    """Orchestrates audit tests, collects traces, produces summary report."""

    def __init__(self, output_dir: str = "output/self_audit"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.traces: list[AuditTrace] = []
        self.start_time = time.time()

    def begin_trace(self, suite: str, test_name: str, input_data: Any = None) -> AuditTrace:
        trace = AuditTrace(
            trace_id=f"audit-{uuid.uuid4().hex[:8]}",
            suite=suite,
            test_name=test_name,
            input=input_data,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        return trace

    def finish_trace(self, trace: AuditTrace):
        trace.duration_ms = (time.time() - self.start_time) * 1000
        self.traces.append(trace)

    def save_trace(self, trace: AuditTrace):
        path = self.output_dir / f"{trace.trace_id}.json"
        path.write_text(trace.to_json(), encoding="utf-8")

    def summary(self) -> dict:
        total = len(self.traces)
        passed = sum(1 for t in self.traces if t.assertions["failed"] == 0)
        failed = total - passed
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration_seconds": time.time() - self.start_time,
            "version": "6.0.0",
        }

    def generate_report(self) -> str:
        s = self.summary()
        lines = [
            "=" * 60,
            f"CRUX Studio v{s['version']} Self-Audit Report",
            "=" * 60,
            f"Total:  {s['total']}",
            f"Passed: {s['passed']}",
            f"Failed: {s['failed']}",
            f"Time:   {s['duration_seconds']:.2f}s",
            "-" * 60,
        ]
        for t in self.traces:
            status = "✅" if t.assertions["failed"] == 0 else "❌"
            lines.append(
                f"  {status} {t.suite}::{t.test_name}  (P:{t.assertions['passed']}/F:{t.assertions['failed']})"
            )
        lines.append("=" * 60)
        return "\n".join(lines)
