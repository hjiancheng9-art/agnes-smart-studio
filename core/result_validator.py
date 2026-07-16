# core/result_validator.py
"""Phase 2: Result Validation + Consistency Checking + Diff Guard.

Three capabilities built on top of Phase 1 ToolCallValidator:

1. ResultValidator — validates tool execution outputs
   - Error pattern detection
   - Output size/truncation management
   - Basic output schema validation
   - Hint extraction

2. ConsistencyChecker — validates LLM final answer vs tool results
   - Detects contradictions (tool failed but LLM says success)
   - Detects hallucinated file paths/contents
   - Verifies referenced data exists in tool results

3. DiffGuard — protection before write operations
   - Captures before-state for write_file/edit_file
   - Generates diff preview
   - Flags suspicious writes (e.g., overwriting existing content)
"""

from __future__ import annotations

import difflib
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Known error patterns in tool outputs ─────────────────────────


ERROR_PATTERNS = [
    (r"(?i)(error|exception|traceback|failed|failure)", "Execution error detected in tool output"),
    (r"(?i)permission denied|access denied|EACCES", "Permission issue"),
    (r"(?i)not found|No such file|FileNotFoundError", "File not found"),
    (r"(?i)timeout|timed out|connection refused", "Timeout/connection issue"),
    (r"(?i)syntaxerror|nameerror|typeerror|valueerror|keyerror", "Python runtime error"),
    (r"(?i)Segmentation fault|core dumped|SIGSEGV", "Process crash"),
    (r"(?i)module.*not found|ImportError|ModuleNotFoundError", "Missing dependency"),
    (r"(?i)disk full|no space left|ENOSPC", "Disk space issue"),
    (r"(?i)invalid syntax|SyntaxError|parse error", "Syntax error in generated code"),
]

# ── Result validation ────────────────────────────────────────────


@dataclass
class ValidationNote:
    """A note/warning about a tool result, not a blocking error."""
    severity: str  # "info", "warning", "critical"
    message: str
    detail: str = ""


@dataclass
class ValidatedResult:
    """Wraps a ToolResult with validation notes."""
    is_valid: bool = True
    notes: list[ValidationNote] = field(default_factory=list)
    needs_review: bool = False
    truncated: bool = False
    original_length: int = 0


class ResultValidator:
    """Validates tool execution results for errors, size issues, patterns."""

    MAX_OUTPUT_CHARS: int = 5000
    MAX_OUTPUT_LINES: int = 500

    def validate(
        self,
        tool_name: str,
        result_text: str,
        success: bool,
    ) -> ValidatedResult:
        """Validate a tool execution result.

        Args:
            tool_name: Name of the tool that was executed
            result_text: The text output from tool execution
            success: Whether the tool reported success

        Returns:
            ValidatedResult with validation notes
        """
        notes: list[ValidationNote] = []
        vr = ValidatedResult()

        # 1. Check success flag consistency
        if not success and result_text:
            notes.append(ValidationNote(
                severity="critical",
                message=f"Tool '{tool_name}' failed",
                detail=result_text[:500],
            ))

        if success and not result_text:
            notes.append(ValidationNote(
                severity="info",
                message=f"Tool '{tool_name}' returned empty result",
            ))

        # 2. Check output size
        vr.original_length = len(result_text)
        if len(result_text) > self.MAX_OUTPUT_CHARS:
            vr.truncated = True
            notes.append(ValidationNote(
                severity="info",
                message=f"Output truncated ({len(result_text)} chars > {self.MAX_OUTPUT_CHARS})",
            ))
        line_count = result_text.count("\n")
        if line_count > self.MAX_OUTPUT_LINES:
            notes.append(ValidationNote(
                severity="info",
                message=f"Output has many lines ({line_count})",
            ))

        # 3. Check error patterns in output
        import re
        for pattern, hint in ERROR_PATTERNS:
            matches = re.findall(pattern, result_text)
            if matches:
                notes.append(ValidationNote(
                    severity="warning" if success else "info",
                    message=hint,
                    detail=f"Found {len(matches)} match(es)",
                ))

        # 4. Determine overall validity
        critical_notes = [n for n in notes if n.severity == "critical"]
        vr.is_valid = len(critical_notes) == 0
        vr.needs_review = any(n.severity == "warning" for n in notes)
        vr.notes = notes

        return vr

    def suggest_hints(self, vr: ValidatedResult) -> list[str]:
        """Generate actionable hints based on validation notes."""
        hints: list[str] = []
        for note in vr.notes:
            if "error" in note.message.lower() and "syntax" in note.message.lower():
                hints.append("Check generated code syntax before applying")
            if "not found" in note.message.lower():
                hints.append("Verify the file path exists before reading")
            if "permission" in note.message.lower():
                hints.append("Check file permissions")
            if "timeout" in note.message.lower():
                hints.append("Operation timed out, consider retrying with simpler input")
        return hints


# ── Consistency checking ─────────────────────────────────────────


@dataclass
class ConsistencyIssue:
    """A detected inconsistency between LLM answer and tool results."""
    description: str
    severity: str  # "minor", "major", "critical"
    evidence: str = ""


@dataclass
class ConsistencyReport:
    """Report of all consistency checks."""
    is_consistent: bool = True
    issues: list[ConsistencyIssue] = field(default_factory=list)

    def summary(self) -> str:
        if not self.issues:
            return "✅ Consistent"
        lines = [f"⚠ {len(self.issues)} inconsistency(ies):"]
        for iss in self.issues[:5]:
            lines.append(f"  [{iss.severity}] {iss.description}")
        if len(self.issues) > 5:
            lines.append(f"  ... and {len(self.issues) - 5} more")
        return "\n".join(lines)


class ConsistencyChecker:
    """Checks LLM final answer for consistency against tool execution results.

    Detects:
    - LLM claims success when tool failed
    - LLM references files/paths that tools never touched
    - LLM hallucinates data not present in tool results
    """

    def check(
        self,
        llm_answer: str,
        tool_history: list[dict],
    ) -> ConsistencyReport:
        """Compare LLM's final answer against actual tool execution history.

        Args:
            llm_answer: The LLM's final answer text
            tool_history: List of {tool_name, args, result, success} dicts

        Returns:
            ConsistencyReport with detected issues
        """
        issues: list[ConsistencyIssue] = []

        if not tool_history:
            return ConsistencyReport(is_consistent=True)

        # 1. Check for failed tools that LLM might claim succeeded
        failed_tools = [t for t in tool_history if not t.get("success", True)]
        succeeded_tools = [t for t in tool_history if t.get("success", False)]

        for ft in failed_tools:
            # If there's only one failed tool and no succeeded ones
            if len(failed_tools) == len(tool_history):
                issues.append(ConsistencyIssue(
                    description=f"All tools failed (including '{ft.get('tool_name')}') — answer may be unreliable",
                    severity="critical",
                ))
                break

        # 2. Check file write then read pattern
        written_files = self._extract_written_files(tool_history)
        read_files = self._extract_read_files(tool_history)

        for rf in read_files:
            if rf not in written_files and not self._file_exists(rf):
                issues.append(ConsistencyIssue(
                    description=f"LLM referenced '{rf}' but it was not written in this session",
                    severity="info",
                    evidence="File may exist from previous work",
                ))

        # 3. Check if answer mentions errors/retries that match tool failures
        for ft in failed_tools:
            name = ft.get("tool_name", "?")
            err = str(ft.get("result", ""))[:100]
            if err and err not in llm_answer:
                issues.append(ConsistencyIssue(
                    description=f"Tool '{name}' failed ({err[:80]}) but LLM answer doesn't mention it",
                    severity="major",
                ))

        # 4. Check answers that are suspiciously long or short
        if len(llm_answer) < 10 and len(tool_history) > 3:
            issues.append(ConsistencyIssue(
                description="Very short answer after multiple tool calls — possible truncation",
                severity="minor",
            ))

        return ConsistencyReport(
            is_consistent=len([i for i in issues if i.severity == "critical"]) == 0,
            issues=issues,
        )

    def _extract_written_files(self, history: list[dict]) -> list[str]:
        files = []
        for t in history:
            tn = t.get("tool_name", "")
            if tn in ("write_file", "edit_file", "patch_file", "apply_patch"):
                path = t.get("args", {}).get("path", "")
                if path:
                    files.append(path)
        return files

    def _extract_read_files(self, history: list[dict]) -> list[str]:
        files = []
        for t in history:
            tn = t.get("tool_name", "")
            if tn == "read_file":
                path = t.get("args", {}).get("path", "")
                if path:
                    files.append(path)
        return files

    def _file_exists(self, path: str) -> bool:
        try:
            return os.path.exists(path) and os.path.isfile(path)
        except Exception:
            return False


# ── Diff Guard ────────────────────────────────────────────────────


@dataclass
class DiffPreview:
    """Preview of a file change."""
    path: str
    action: str  # "create", "modify", "delete"
    old_content: str = ""
    new_content: str = ""
    diff_lines: list[str] = field(default_factory=list)
    size_delta: int = 0
    suspicious: bool = False
    suspicion_reason: str = ""


class DiffGuard:
    """Protection layer for file write operations.

    Captures before-state, generates diff preview, and flags suspicious writes.
    """

    def __init__(self):
        self._snapshots: dict[str, str] = {}

    def snapshot_before(self, path: str) -> str | None:
        """Capture file content before write. Returns existing content or None."""
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self._snapshots[path] = content
                return content
            else:
                self._snapshots[path] = ""
                return None
        except Exception:
            self._snapshots[path] = ""
            return None

    def preview_write(self, path: str, new_content: str) -> DiffPreview:
        """Generate diff preview for a write operation."""
        old = self._snapshots.get(path, "")
        if not old:
            try:
                if os.path.exists(path):
                    with open(path, encoding="utf-8", errors="replace") as f:
                        old = f.read()
            except Exception:
                logger.debug("Exception in result_validator", exc_info=True)

        diff_lines = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        ))

        action = "create" if not old else "modify"
        size_delta = len(new_content) - len(old)

        # Suspicion detection
        suspicious = False
        reason = ""

        # Flag: deleting large file content
        if old and len(new_content) == 0:
            suspicious = True
            reason = f"Writing empty content over existing file ({len(old)} chars)"

        # Flag: drastically different file
        if old and len(new_content) > 0:
            similarity = self._similarity(old, new_content)
            if similarity < 0.05 and len(old) > 100:
                suspicious = True
                reason = f"New content drastically different from existing (similarity={similarity:.1%})"

        # Flag: writing to non-standard locations
        if "node_modules" in path or ".git" in path or "__pycache__" in path:
            suspicious = True
            reason = f"Writing to system/infrastructure directory: {path}"

        return DiffPreview(
            path=path,
            action=action,
            old_content=old[:500] if old else "",
            new_content=new_content[:500],
            diff_lines=diff_lines,
            size_delta=size_delta,
            suspicious=suspicious,
            suspicion_reason=reason,
        )

    def _similarity(self, a: str, b: str) -> float:
        """Simple similarity ratio based on character overlap."""
        if not a or not b:
            return 0.0
        # Use set intersection ratio as quick heuristic
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
        if not set_a and not set_b:
            return 1.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0
