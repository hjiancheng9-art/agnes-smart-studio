# core/failure_learning.py
"""P11: Failure Learning Loop / Trace-to-Regression System.

Turns every failure into a learning asset:
  Detect failure → Capture trace → Extract minimal repro → Root cause → Fix suggestion → Verify → Export to regression set

Components:
  FailureSample    — snapshot of a failure (input + trace + expected vs actual)
  TraceExtractor   — extracts minimal reproduction from a session trace
  RootCauseAnalyzer— classifies failure type and suggests fixes
  FixVerifier      — replays fix to verify it resolves the issue
  RegressionExporter— exports failure cases to the regression test suite
  FailureLearningLoop— orchestrates the full pipeline
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. Failure taxonomy
# ═══════════════════════════════════════════════════════════════════


class FailureCategory(str, Enum):
    TOOL_VALIDATION_BLOCKED = "tool_validation_blocked"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    CONSISTENCY_ISSUE = "consistency_issue"
    REVIEWER_CAUGHT = "reviewer_caught"
    DIFF_GUARD_BLOCKED = "diff_guard_blocked"
    CONTEXT_OVERFLOW = "context_overflow"
    EMPTY_RESPONSE = "empty_response"
    UNCLOSED_FENCE = "unclosed_fence"
    HALLUCINATION = "hallucination"
    POLICY_MISMATCH = "policy_mismatch"
    TASK_TIMEOUT = "task_timeout"
    OTHER = "other"


class FailureSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


ROOT_CAUSE_TEMPLATES: dict[str, list[str]] = {
    FailureCategory.TOOL_VALIDATION_BLOCKED: [
        "Tool schema may be missing required parameters",
        "LLM generated invalid XML syntax",
        "Tool name may be incorrect or misspelled",
    ],
    FailureCategory.CONSISTENCY_ISSUE: [
        "LLM response contradicts tool execution results",
        "Tool failure not acknowledged in final answer",
    ],
    FailureCategory.HALLUCINATION: [
        "LLM referenced files not read in tool calls",
        "LLM fabricated tool results that never executed",
    ],
    FailureCategory.UNCLOSED_FENCE: [
        "Response truncated — check token limit or streaming buffer",
        "LLM forgot to close code block",
    ],
}


# ═══════════════════════════════════════════════════════════════════
# 2. FailureSample
# ═══════════════════════════════════════════════════════════════════


@dataclass
class FailureSample:
    """A captured failure with full context for learning.

    Fields:
      id: unique identifier
      category: what type of failure
      severity: how bad was it
      timestamp: when it happened
      user_message: what the user asked
      assistant_response: what the LLM replied (if any)
      tool_calls: what tools were invoked
      trace_snippet: key decisions from the trace leading to failure
      expected_outcome: what should have happened
      actual_outcome: what actually happened
      root_cause: identified or suggested root cause
      fix_suggestion: generated fix recommendation
      fix_verified: whether the fix was verified
      exported: whether this was added to regression set
    """

    id: str = ""
    category: str = ""
    severity: str = "medium"
    timestamp: float = 0.0
    user_message: str = ""
    assistant_response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    trace_snippet: str = ""
    expected_outcome: str = ""
    actual_outcome: str = ""
    root_cause: str = ""
    fix_suggestion: str = ""
    fix_verified: bool = False
    exported: bool = False
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "user_message": self.user_message[:500],
            "assistant_response": (self.assistant_response or "")[:500],
            "tool_calls": self.tool_calls[:5],
            "trace_snippet": self.trace_snippet[:500],
            "expected_outcome": self.expected_outcome[:300],
            "actual_outcome": self.actual_outcome[:300],
            "root_cause": self.root_cause[:300],
            "fix_suggestion": self.fix_suggestion[:300],
            "fix_verified": self.fix_verified,
            "exported": self.exported,
            "tags": self.tags,
        }


# ═══════════════════════════════════════════════════════════════════
# 3. TraceExtractor
# ═══════════════════════════════════════════════════════════════════


class TraceExtractor:
    """Extracts minimal reproduction from a session trace or decision record.

    Given a full session trace, extract the minimum context needed
    to reproduce the failure — stripping irrelevant turns.
    """

    def extract_minimal(self, decisions: list[dict], failure_idx: int = -1) -> str:
        """Extract minimal reproduction context from a decision list.

        Args:
            decisions: List of decision dicts (from SessionRecord)
            failure_idx: Index of the failing decision (default: last)

        Returns:
            Minimal trace text for reproduction.
        """
        if not decisions:
            return ""

        idx = failure_idx if failure_idx >= 0 else len(decisions) - 1
        idx = min(idx, len(decisions) - 1)

        # Take the failure + up to 3 preceding decisions
        start = max(0, idx - 3)
        relevant = decisions[start : idx + 1]

        lines = ["[Minimal Reproduction Trace]"]
        for d in relevant:
            cat = d.get("category", "?")
            dec = d.get("decision", "?")[:100]
            reason = d.get("reason", "?")[:100]
            outcome = d.get("outcome", "")
            lines.append(f"  [{cat}] {dec}")
            lines.append(f"    Reason: {reason}")
            if outcome:
                lines.append(f"    → {outcome[:80]}")

        return "\n".join(lines)

    def extract_from_failure(self, sample: FailureSample) -> str:
        """Extract the core failure context from a FailureSample."""
        lines = [
            "[Failure Context]",
            f"  Category: {sample.category}",
            f"  Severity: {sample.severity}",
            f"  User: {sample.user_message[:200]}",
        ]
        if sample.assistant_response:
            lines.append(f"  Response: {sample.assistant_response[:200]}")
        if sample.tool_calls:
            lines.append(f"  Tools ({len(sample.tool_calls)}):")
            for tc in sample.tool_calls[:3]:
                lines.append(f"    {tc.get('name', '?')}: {tc.get('arguments', {})}")
        if sample.actual_outcome:
            lines.append(f"  Actual: {sample.actual_outcome[:200]}")
        if sample.expected_outcome:
            lines.append(f"  Expected: {sample.expected_outcome[:200]}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 4. RootCauseAnalyzer
# ═══════════════════════════════════════════════════════════════════


class RootCauseAnalyzer:
    """Analyzes failure samples to identify root causes and generate fix suggestions.

    Uses rule-based classification first, then LLM callback if available.
    """

    def analyze(self, sample: FailureSample) -> FailureSample:
        """Analyze a failure sample and populate root_cause and fix_suggestion."""
        # Rule-based classification
        category = sample.category

        # Get possible root causes
        causes = ROOT_CAUSE_TEMPLATES.get(category, ["Unknown cause"])
        sample.root_cause = causes[0]

        # Generate fix suggestion
        sample.fix_suggestion = self._suggest_fix(sample)

        return sample

    def _suggest_fix(self, sample: FailureSample) -> str:
        """Generate a fix suggestion based on failure type."""
        cat = sample.category
        suggestions = {
            FailureCategory.TOOL_VALIDATION_BLOCKED: (
                "Check tool schema: verify parameter names and types match the tool definition. "
                "If it's a missing required param, add it. If it's an unknown tool, check spelling."
            ),
            FailureCategory.TOOL_EXECUTION_FAILED: (
                "Review tool error message: if it's a timeout, retry with simpler input. "
                "If it's a permission error, check file access rights."
            ),
            FailureCategory.CONSISTENCY_ISSUE: (
                "LLM response should acknowledge tool failures. "
                "Consider enabling reviewer agent to catch this automatically."
            ),
            FailureCategory.HALLUCINATION: (
                "Enable consistency checking (P2) to catch hallucinated file references. "
                "LLM may need explicit instructions to only reference files from tool results."
            ),
            FailureCategory.UNCLOSED_FENCE: (
                "Increase token limit or enable context compression. The response was likely truncated mid-output."
            ),
            FailureCategory.DIFF_GUARD_BLOCKED: (
                "DiffGuard prevented a potentially harmful write. Review the change manually if intended."
            ),
        }
        return suggestions.get(FailureCategory(cat), "Review the failure context manually.")

    def analyze_with_llm(
        self,
        sample: FailureSample,
        llm_callback: Callable[[str, str], str],
    ) -> FailureSample:
        """Deep analysis using an LLM callback."""
        prompt = (
            f"Analyze this AI assistant failure and identify root cause + fix suggestion.\n\n"
            f"Category: {sample.category}\n"
            f"User: {sample.user_message[:300]}\n"
            f"Response: {(sample.assistant_response or '')[:300]}\n"
            f"Expected: {sample.expected_outcome[:200]}\n"
            f"Actual: {sample.actual_outcome[:200]}\n\n"
            f"Respond with JSON:\n"
            f'{{"root_cause": "...", "fix_suggestion": "..."}}'
        )
        try:
            result = llm_callback("You are a failure analysis expert.", prompt)
            # Parse JSON
            import re

            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                data = json.loads(m.group())
                sample.root_cause = data.get("root_cause", sample.root_cause)
                sample.fix_suggestion = data.get("fix_suggestion", sample.fix_suggestion)
        except Exception as e:
            logger.debug(f"LLM analysis failed: {e}")

        return sample


# ═══════════════════════════════════════════════════════════════════
# 5. FixVerifier
# ═══════════════════════════════════════════════════════════════════


class FixVerifier:
    """Verifies that a fix resolves the original issue by replaying the trace.

    Compares before/after outputs to confirm the fix works.
    """

    def verify(
        self,
        sample: FailureSample,
        before_output: str = "",
        after_output: str = "",
    ) -> bool:
        """Verify a fix by comparing before and after outputs.

        Args:
            sample: The original failure sample
            before_output: The output before fix (the failure)
            after_output: The output after applying fix

        Returns:
            True if the fix appears to resolve the issue.
        """
        if not before_output or not after_output:
            return False

        # Check 1: After output is not identical to before (something changed)
        if before_output == after_output:
            return False

        # Check 2: After output doesn't contain the same error pattern
        if sample.actual_outcome and sample.actual_outcome in after_output:
            return False

        # Check 3: After output is non-empty
        return after_output.strip()

    def diff(self, before: str, after: str) -> str:
        """Generate a diff between before and after outputs."""
        lines = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="before",
            tofile="after",
            n=2,
        )
        return "".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 6. RegressionExporter
# ═══════════════════════════════════════════════════════════════════


class RegressionExporter:
    """Exports failure samples to the regression test suite.

    Saves as JSON files in a designated directory, consumable by EvalRunner.
    """

    def __init__(self, export_dir: str = ".crux/regression_cases"):
        self.export_dir = export_dir

    def export(self, sample: FailureSample) -> str:
        """Export a single failure sample to the regression set.

        Returns:
            Path to the exported file.
        """
        os.makedirs(self.export_dir, exist_ok=True)

        filename = f"{sample.category}_{sample.id}.json"
        filepath = os.path.join(self.export_dir, filename)

        data = sample.to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        sample.exported = True
        logger.info(f"Exported regression case: {filepath}")
        return filepath

    def list_cases(self) -> list[dict]:
        """List all exported regression cases."""
        if not os.path.exists(self.export_dir):
            return []

        cases = []
        for fname in sorted(os.listdir(self.export_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self.export_dir, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        data = json.load(f)
                    cases.append(
                        {
                            "id": data.get("id", fname),
                            "category": data.get("category", "?"),
                            "severity": data.get("severity", "?"),
                            "date": datetime.fromtimestamp(data.get("timestamp", 0)).isoformat()
                            if data.get("timestamp")
                            else "?",
                            "user_message": (data.get("user_message", "") or "")[:80],
                        }
                    )
                except Exception:
                    logger.debug("Exception in failure_learning", exc_info=True)
        return cases

    def import_to_eval(self) -> list[dict]:
        """Convert all regression cases into EvalRunner-compatible format."""
        from core.crux_telemetry import EvalSession, EvalTurn

        sessions = []
        for case in self.list_cases():
            fpath = os.path.join(self.export_dir, f"{case['id']}.json")
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                session = EvalSession(
                    id=data.get("id", ""),
                    description=f"Regression: {data.get('category', '?')}",
                    tags=["regression", data.get("category", "?")],
                )
                session.turns.append(
                    EvalTurn(
                        user=data.get("user_message", ""),
                        assistant=data.get("assistant_response", ""),
                        tool_results=data.get("tool_results", []),
                        expected_issues=1,
                    )
                )
                sessions.append(session)
            except Exception:
                logger.debug("Exception in failure_learning", exc_info=True)
        return sessions


# ═══════════════════════════════════════════════════════════════════
# 7. FailureLearningLoop — orchestrator
# ═══════════════════════════════════════════════════════════════════


@dataclass
class LearningStats:
    """Statistics for the failure learning loop."""

    total_failures: int = 0
    analyzed: int = 0
    verified_fixes: int = 0
    exported: int = 0
    by_category: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        lines = ["📊 Failure Learning Loop:"]
        lines.append(f"   Total failures: {self.total_failures}")
        lines.append(f"   Analyzed: {self.analyzed}")
        lines.append(f"   Verified fixes: {self.verified_fixes}")
        lines.append(f"   Exported to regression: {self.exported}")
        if self.by_category:
            lines.append("   By category:")
            for cat, count in sorted(self.by_category.items(), key=lambda x: -x[1]):
                lines.append(f"     {cat}: {count}")
        return "\n".join(lines)


class FailureLearningLoop:
    """Orchestrates the full failure learning pipeline.

    Usage:
        loop = FailureLearningLoop()
        sample = loop.capture(
            category="tool_validation_blocked",
            user_message="read file x",
            actual_outcome="Tool blocked: path missing",
            expected_outcome="Tool should accept path param",
        )
        loop.analyze(sample)       # root cause + fix suggestion
        loop.export(sample)        # save to regression set
        stats = loop.stats()
    """

    def __init__(self, export_dir: str = ".crux/regression_cases"):
        self.extractor = TraceExtractor()
        self.analyzer = RootCauseAnalyzer()
        self.verifier = FixVerifier()
        self.exporter = RegressionExporter(export_dir=export_dir)
        self.samples: list[FailureSample] = []
        self._llm_callback: Callable | None = None

    def set_llm_callback(self, callback: Callable):
        """Set optional LLM callback for deep analysis."""
        self._llm_callback = callback

    def capture(
        self,
        category: str,
        user_message: str = "",
        assistant_response: str = "",
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        actual_outcome: str = "",
        expected_outcome: str = "",
        severity: str = "medium",
        tags: list[str] | None = None,
    ) -> FailureSample:
        """Capture a failure event. Returns the FailureSample."""
        sample = FailureSample(
            id=str(uuid.uuid4())[:8],
            category=category,
            severity=severity,
            timestamp=time.time(),
            user_message=user_message,
            assistant_response=assistant_response,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            actual_outcome=actual_outcome,
            expected_outcome=expected_outcome,
            tags=tags or [],
        )
        self.samples.append(sample)
        return sample

    def capture_from_trace(
        self,
        decisions: list[dict],
        category: str = "",
        user_message: str = "",
        severity: str = "medium",
    ) -> FailureSample:
        """Capture a failure from a trace decision list."""
        # Find the failure
        failure_idx = -1
        for i, d in enumerate(decisions):
            outcome = d.get("outcome", "")
            if outcome in ("block", "failed", "issues_found"):
                failure_idx = i
                category = category or d.get("category", "other")
                break

        trace_snippet = self.extractor.extract_minimal(decisions, failure_idx)

        sample = FailureSample(
            id=str(uuid.uuid4())[:8],
            category=category,
            severity=severity,
            timestamp=time.time(),
            user_message=user_message,
            trace_snippet=trace_snippet,
            actual_outcome=f"Failure at decision {failure_idx}" if failure_idx >= 0 else "Unknown failure",
        )
        self.samples.append(sample)
        return sample

    def analyze(self, sample: FailureSample) -> FailureSample:
        """Analyze a failure sample: root cause + fix suggestion."""
        if self._llm_callback and sample.assistant_response:
            sample = self.analyzer.analyze_with_llm(sample, self._llm_callback)
        else:
            sample = self.analyzer.analyze(sample)
        return sample

    def verify(self, sample: FailureSample, before: str, after: str) -> bool:
        """Verify a fix by comparing before/after."""
        verified = self.verifier.verify(sample, before, after)
        if verified:
            sample.fix_verified = True
        return verified

    def export(self, sample: FailureSample) -> str:
        """Export a failure sample to the regression set."""
        path = self.exporter.export(sample)
        return path

    def run_full_pipeline(
        self,
        category: str,
        user_message: str = "",
        assistant_response: str = "",
        actual_outcome: str = "",
        expected_outcome: str = "",
        severity: str = "medium",
        before_output: str = "",
        after_output: str = "",
    ) -> FailureSample:
        """Run the full capture → analyze → export pipeline.

        Returns the enriched FailureSample.
        """
        # 1. Capture
        sample = self.capture(
            category=category,
            user_message=user_message,
            assistant_response=assistant_response,
            actual_outcome=actual_outcome,
            expected_outcome=expected_outcome,
            severity=severity,
        )

        # 2. Analyze
        sample = self.analyze(sample)

        # 3. Verify (if before/after provided)
        if before_output and after_output:
            self.verify(sample, before_output, after_output)

        # 4. Export
        self.export(sample)

        return sample

    def stats(self) -> LearningStats:
        """Get learning loop statistics."""
        s = LearningStats(total_failures=len(self.samples))
        for sample in self.samples:
            if sample.root_cause:
                s.analyzed += 1
            if sample.fix_verified:
                s.verified_fixes += 1
            if sample.exported:
                s.exported += 1
            s.by_category[sample.category] = s.by_category.get(sample.category, 0) + 1
        return s

    def report(self) -> str:
        """Full human-readable report."""
        return self.stats().summary()
