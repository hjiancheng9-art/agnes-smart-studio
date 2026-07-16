# core/reviewer_agent.py
"""Phase 4: Multi-Agent collaboration — Reviewer Agent + Debate + Task Decomposition.

Builds on existing reflection_loop.py with more advanced review patterns.

Agents:
1. **ReviewerAgent** — reviews main LLM output for errors/omissions/contradictions
2. **DebateAgent** — runs two critics on the same answer, reconciles differences
3. **TaskDecomposer** — breaks complex requests into sub-tasks before execution

All agents use the SAME model with DIFFERENT system prompts (no extra model cost).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Review result types
# ═══════════════════════════════════════════════════════════════════


class ReviewSeverity(str, Enum):
    PASS = "pass"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


@dataclass
class ReviewIssue:
    """A single issue found during review."""

    severity: ReviewSeverity
    category: str  # "factual", "completeness", "consistency", "safety", "style"
    description: str
    suggestion: str = ""
    location: str = ""  # optional location reference


@dataclass
class ReviewReport:
    """Full review result."""

    issues: list[ReviewIssue] = field(default_factory=list)
    score: int = 100  # 0-100
    summary: str = ""
    passed: bool = True

    def __post_init__(self):
        if not self.summary:
            if self.passed:
                self.summary = "All checks passed"
            elif self.issues:
                worst = max(self.issues, key=lambda x: list(ReviewSeverity).index(x.severity))
                self.summary = f"[{worst.severity.value}] {worst.description[:120]}"

    @property
    def has_critical(self) -> bool:
        return any(i.severity == ReviewSeverity.CRITICAL for i in self.issues)

    @property
    def has_major(self) -> bool:
        return any(i.severity in (ReviewSeverity.MAJOR, ReviewSeverity.CRITICAL) for i in self.issues)

    def to_llm_prompt(self, context: str = "") -> str:
        """Convert review into a correction prompt to feed back to the model."""
        if self.passed:
            return ""

        lines = ["[Self-Review Feedback]", f"Context: {context}" if context else ""]
        for i, issue in enumerate(self.issues[:10], 1):
            lines.append(f"  {i}. [{issue.severity.value}] ({issue.category}) {issue.description}")
            if issue.suggestion:
                lines.append(f"     Suggestion: {issue.suggestion}")
        if len(self.issues) > 10:
            lines.append(f"  ... and {len(self.issues) - 10} more issues")
        lines.append("\nPlease address the issues above in your next response.")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# System prompts
# ═══════════════════════════════════════════════════════════════════

REVIEWER_SYSTEM_PROMPT = """You are a **Reviewer Agent** — your job is to review the main AI assistant's response for quality issues.

You check for:
1. **Factual correctness**: Does the answer match the tool results? No hallucinations.
2. **Completeness**: Does it fully answer the user's question?
3. **Consistency**: No contradictions between the answer and tool outputs.
4. **Clarity**: Is the answer well-structured and actionable?
5. **Tool usage**: Were tools used appropriately? Could a better tool have been used?

Format your review as JSON:
{"issues": [{"severity": "pass|minor|major|critical", "category": "factual|completeness|consistency|safety|style", "description": "...", "suggestion": "..."}], "score": 0-100, "summary": "one-line summary"}

Be strict but fair. Don't nitpick minor style issues. Focus on real problems."""

DEBATE_SYSTEM_PROMPT = """You are a **Debate Agent** — your role is to critique the main AI's answer by considering an opposing viewpoint.

Analyze the answer for:
- What would a skeptic say is wrong with this answer?
- What edge cases or assumptions does the answer rely on?
- Is there a simpler approach the AI missed?
- Are the tool calls optimal, or is there a better way?

Format your critique as JSON:
{"critiques": [{"concern": "...", "counter_argument": "...", "impact": "low|medium|high"}], "overall_assessment": "agree|partial|disagree", "alternative_approach": "..."}"""

DECOMPOSER_SYSTEM_PROMPT = """You are a **Task Decomposer** — break complex user requests into a sequence of simpler sub-tasks.

Rules:
1. Each sub-task should be independently executable
2. Sub-tasks should be ordered by dependency
3. Keep descriptions concise (1 sentence each)
4. Max 10 sub-tasks per decomposition

Format as JSON:
{"tasks": [{"id": 1, "description": "...", "depends_on": [], "tools_likely_needed": ["..."]}, ...], "estimated_complexity": "low|medium|high"}"""


# ═══════════════════════════════════════════════════════════════════
# Reviewer Agent
# ═══════════════════════════════════════════════════════════════════


ReviewCallback = Callable[[str, str, list[dict]], str]
"""Callback (system_prompt, user_prompt, messages) -> response_text"""


class ReviewerAgent:
    """Reviews main LLM output for quality, consistency, and completeness.

    Uses the same model with a reviewer system prompt — no extra model cost.
    Integrates with the existing reflection loop (core/reflection_loop.py).
    """

    def __init__(
        self,
        llm_callback: ReviewCallback | None = None,
        review_threshold: int = 70,  # score below this triggers re-generation
        auto_fix: bool = True,  # auto-inject review feedback
    ):
        self.llm_callback = llm_callback
        self.review_threshold = review_threshold
        self.auto_fix = auto_fix
        self._review_count: int = 0
        self._fix_count: int = 0

    def review(
        self,
        user_query: str,
        assistant_response: str,
        tool_results: list[dict] | None = None,
    ) -> ReviewReport:
        """Review an assistant response. Returns structured report.

        Args:
            user_query: The original user message
            assistant_response: The assistant's generated response
            tool_results: List of {tool_name, args, result, success} from this turn
        """
        self._review_count += 1
        report = self._rule_based_review(user_query, assistant_response, tool_results or [])

        # If LLM callback available, do deeper review
        if self.llm_callback:
            llm_report = self._llm_review(user_query, assistant_response, tool_results or [])
            if llm_report:
                # Merge issues
                report.issues.extend(llm_report.issues)
                if llm_report.score < report.score:
                    report.score = llm_report.score

        # Deduplicate
        report.issues = self._dedup(report.issues)
        report.passed = report.score >= self.review_threshold and not report.has_critical

        # Generate summary
        if report.issues:
            worst = max(report.issues, key=lambda x: list(ReviewSeverity).index(x.severity))
            report.summary = f"[{worst.severity.value}] {worst.description[:120]}"
        else:
            report.summary = "All checks passed"

        return report

    def _rule_based_review(
        self,
        query: str,
        response: str,
        tool_results: list[dict],
    ) -> ReviewReport:
        """Fast rule-based checks — no LLM call needed."""
        issues: list[ReviewIssue] = []
        score = 100

        # Check 1: Empty response
        if not response or len(response.strip()) < 5:
            issues.append(
                ReviewIssue(
                    severity=ReviewSeverity.CRITICAL,
                    category="completeness",
                    description="Response is empty or too short",
                    suggestion="Provide a substantive response to the user's query",
                )
            )
            score -= 40
            return ReviewReport(issues=issues, score=max(0, score))

        # Check 2: Tool failure not acknowledged
        failed_tools = [t for t in tool_results if not t.get("success", True)]
        if failed_tools and not any(t["tool_name"] in response for t in failed_tools):
            names = ", ".join(t["tool_name"] for t in failed_tools[:3])
            issues.append(
                ReviewIssue(
                    severity=ReviewSeverity.MAJOR,
                    category="consistency",
                    description=f"Tool(s) {names} failed but response doesn't mention it",
                    suggestion="Acknowledge the failure and suggest alternatives",
                )
            )
            score -= 20

        # Check 3: Truncation / incomplete code
        if response.count("```") % 2 != 0:
            issues.append(
                ReviewIssue(
                    severity=ReviewSeverity.MAJOR,
                    category="completeness",
                    description="Unclosed code fence — response may be truncated",
                    suggestion="Close all ``` code blocks properly",
                )
            )
            score -= 15

        # Check 4: File path hallucination
        read_files = set()
        for t in tool_results:
            args = t.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            if isinstance(args, dict):
                path = args.get("path", "")
                if path:
                    read_files.add(path)

        if read_files:
            mentioned_files = re.findall(r'["\']([^"\']+\.\w+)["\']', response)
            for mf in mentioned_files:
                if mf not in read_files and not mf.startswith("core/") and not mf.startswith("tests/"):
                    issues.append(
                        ReviewIssue(
                            severity=ReviewSeverity.MINOR,
                            category="factual",
                            description=f"File '{mf}' mentioned but not read in tool calls",
                            suggestion="Verify the file path before referencing it",
                        )
                    )
                    score -= 5

        # Check 5: Very long response without structure
        if len(response) > 3000 and "\n" not in response[:500]:
            issues.append(
                ReviewIssue(
                    severity=ReviewSeverity.MINOR,
                    category="style",
                    description="Long response without line breaks — hard to read",
                    suggestion="Add paragraph breaks and structure",
                )
            )
            score -= 5

        # Check 6: Missing tool results (LLM promised results but no tool call)
        if tool_results and len(response) < 50:
            issues.append(
                ReviewIssue(
                    severity=ReviewSeverity.MAJOR,
                    category="completeness",
                    description=f"Response too short ({len(response)} chars) despite {len(tool_results)} tool calls",
                    suggestion="Include the tool results in the response",
                )
            )
            score -= 15

        return ReviewReport(issues=issues, score=max(0, score))

    def _llm_review(
        self,
        query: str,
        response: str,
        tool_results: list[dict],
    ) -> ReviewReport | None:
        """Deep review via LLM."""
        if not self.llm_callback:
            return None

        try:
            tool_summary = json.dumps(
                [
                    {
                        "tool": t.get("tool_name", "?"),
                        "result": str(t.get("result", ""))[:200],
                        "success": t.get("success"),
                    }
                    for t in (tool_results or [])[:10]
                ]
            )

            user_prompt = f"""## Original user query
{query[:500]}

## Assistant response to review
{response[:2000]}

## Tool results from this turn
{tool_summary}

## Review task
Review the assistant response. Format as JSON:
{{"issues": [{{"severity": "pass|minor|major|critical", "category": "...", "description": "...", "suggestion": "..."}}], "score": 0-100}}"""

            result = self.llm_callback(REVIEWER_SYSTEM_PROMPT, user_prompt, [])
            return self._parse_review_json(result)
        except Exception as e:
            logger.debug(f"LLM review failed: {e}")
            return None

    def _parse_review_json(self, text: str) -> ReviewReport | None:
        """Parse JSON from LLM review response."""
        try:
            # Extract JSON block
            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if m:
                text = m.group(1)
            else:
                # Try to find JSON object directly
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    text = m.group()
            data = json.loads(text.strip())
            issues = []
            for iss in data.get("issues", []):
                severity_str = iss.get("severity", "minor").lower()
                try:
                    severity = ReviewSeverity(severity_str)
                except ValueError:
                    severity = ReviewSeverity.MINOR
                issues.append(
                    ReviewIssue(
                        severity=severity,
                        category=iss.get("category", "general"),
                        description=iss.get("description", ""),
                        suggestion=iss.get("suggestion", ""),
                    )
                )
            return ReviewReport(
                issues=issues,
                score=data.get("score", 50),
            )
        except Exception as e:
            logger.debug(f"Parse review JSON failed: {e}")
            return None

    def build_correction(self, report: ReviewReport) -> str:
        """Build a correction prompt to inject back into the conversation."""
        return report.to_llm_prompt(context="Review of last response")

    def _dedup(self, issues: list[ReviewIssue]) -> list[ReviewIssue]:
        """Remove duplicate issues."""
        seen: set[str] = set()
        result = []
        for iss in issues:
            key = iss.description[:60]
            if key not in seen:
                seen.add(key)
                result.append(iss)
        return result


# ═══════════════════════════════════════════════════════════════════
# Debate Agent (skeptic/second opinion)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DebateResult:
    """Result of a debate/critique session."""

    agreement: str  # "agree", "partial", "disagree"
    concerns: list[dict] = field(default_factory=list)
    alternative: str = ""
    should_revise: bool = False


class DebateAgent:
    """Provides a second-opinion critique of the assistant's response.

    Can detect issues that the main review misses by approaching from
    a different (skeptical) angle. Useful for complex decisions.
    """

    def __init__(self, llm_callback: ReviewCallback | None = None):
        self.llm_callback = llm_callback

    def debate(self, query: str, response: str, tool_results: list[dict]) -> DebateResult:
        """Get a skeptical critique of the response."""
        if not self.llm_callback:
            return DebateResult(agreement="agree", should_revise=False)

        try:
            tool_summary = json.dumps(
                [{"tool": t.get("tool_name", "?"), "success": t.get("success")} for t in (tool_results or [])[:10]]
            )
            user_prompt = f"""Query: {query[:500]}

Response: {response[:2000]}

Tool results: {tool_summary}

Analyze this response from a skeptical perspective. Format as JSON:
{{"critiques": [{{"concern": "...", "counter_argument": "...", "impact": "low|medium|high"}}], "overall_assessment": "agree|partial|disagree", "alternative_approach": "..."}}"""

            result = self.llm_callback(DEBATE_SYSTEM_PROMPT, user_prompt, [])
            return self._parse_debate_json(result)
        except Exception as e:
            logger.debug(f"Debate failed: {e}")
            return DebateResult(agreement="agree", should_revise=False)

    def _parse_debate_json(self, text: str) -> DebateResult:
        try:
            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if m:
                text = m.group(1)
            else:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    text = m.group()
            data = json.loads(text.strip())
            concerns = data.get("critiques", [])
            assessment = data.get("overall_assessment", "agree")
            return DebateResult(
                agreement=assessment,
                concerns=concerns,
                alternative=data.get("alternative_approach", ""),
                should_revise=assessment in ("partial", "disagree"),
            )
        except Exception:
            return DebateResult(agreement="agree", should_revise=False)


# ═══════════════════════════════════════════════════════════════════
# Task Decomposer
# ═══════════════════════════════════════════════════════════════════


@dataclass
class SubTask:
    """A single sub-task in a decomposed plan."""

    id: int
    description: str
    depends_on: list[int] = field(default_factory=list)
    tools_likely_needed: list[str] = field(default_factory=list)


@dataclass
class TaskPlan:
    """A decomposed task plan."""

    tasks: list[SubTask] = field(default_factory=list)
    complexity: str = "low"
    original_query: str = ""

    @property
    def text(self) -> str:
        """Human-readable plan."""
        lines = [f"📋 Task Plan ({self.complexity} complexity):"]
        for task in self.tasks:
            deps = f" (after: {', '.join(str(d) for d in task.depends_on)})" if task.depends_on else ""
            tools = f" [{', '.join(task.tools_likely_needed[:3])}]" if task.tools_likely_needed else ""
            lines.append(f"  {task.id}. {task.description}{deps}{tools}")
        return "\n".join(lines)


class TaskDecomposer:
    """Breaks complex user requests into ordered sub-tasks.

    Helps the LLM handle multi-step tasks more reliably by planning first.
    """

    def __init__(self, llm_callback: ReviewCallback | None = None):
        self.llm_callback = llm_callback

    def decompose(self, user_query: str) -> TaskPlan:
        """Decompose a user request into sub-tasks."""
        if not self.llm_callback:
            # Fallback: simple decomposition
            return TaskPlan(
                tasks=[
                    SubTask(
                        id=1, description=f"Handle: {user_query[:200]}", tools_likely_needed=["read_file", "run_python"]
                    )
                ],
                complexity="unknown",
                original_query=user_query,
            )

        try:
            result = self.llm_callback(
                DECOMPOSER_SYSTEM_PROMPT,
                f"Decompose this request into sub-tasks:\n\n{user_query[:1000]}",
                [],
            )
            return self._parse_plan(result, user_query)
        except Exception as e:
            logger.debug(f"Decompose failed: {e}")
            return TaskPlan(complexity="unknown", original_query=user_query)

    def _parse_plan(self, text: str, query: str) -> TaskPlan:
        try:
            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if m:
                text = m.group(1)
            else:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    text = m.group()
            data = json.loads(text.strip())

            tasks = []
            for t in data.get("tasks", []):
                tasks.append(
                    SubTask(
                        id=t.get("id", len(tasks) + 1),
                        description=t.get("description", ""),
                        depends_on=t.get("depends_on", []),
                        tools_likely_needed=t.get("tools_likely_needed", []),
                    )
                )

            return TaskPlan(
                tasks=tasks or [SubTask(id=1, description=f"Handle: {query[:200]}")],
                complexity=data.get("estimated_complexity", "medium"),
                original_query=query,
            )
        except Exception:
            return TaskPlan(complexity="unknown", original_query=query)


# ═══════════════════════════════════════════════════════════════════
# Integration layer for ValidationLayer
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MultiAgentLayer:
    """Unified multi-agent integration for ValidationLayer.

    Provides:
    - rev: ReviewerAgent — post-turn quality review
    - debate: DebateAgent — second-opinion skeptic
    - decomposer: TaskDecomposer — pre-execution planning
    """

    llm_callback: ReviewCallback | None = None
    auto_review: bool = True  # auto-review after each turn
    auto_decompose: bool = True  # auto-decompose complex queries

    def __post_init__(self):
        self.rev = ReviewerAgent(llm_callback=self.llm_callback, auto_fix=True)
        self.debate = DebateAgent(llm_callback=self.llm_callback)
        self.decomposer = TaskDecomposer(llm_callback=self.llm_callback)

    def review_turn(
        self,
        user_query: str,
        assistant_response: str,
        tool_results: list[dict] | None = None,
    ) -> ReviewReport:
        """Review a conversation turn."""
        return self.rev.review(user_query, assistant_response, tool_results)

    def critique_turn(
        self,
        user_query: str,
        assistant_response: str,
        tool_results: list[dict] | None = None,
    ) -> DebateResult:
        """Get a skeptical second opinion."""
        return self.debate.debate(user_query, assistant_response, tool_results or [])

    def plan_task(self, user_query: str) -> TaskPlan:
        """Decompose a complex request into sub-tasks."""
        return self.decomposer.decompose(user_query)
