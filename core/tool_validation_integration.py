# core/tool_validation_integration.py
"""Tool Validation + Self-Correction integration for ChatSession.

Phase 1: ToolCall validation + Self-Correction
Phase 2: Result validation + Consistency check + Diff guard
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.benchmark.runner import BenchmarkResult, BenchmarkRunner, TaskResult
from core.benchmark.scorer import (
    BenchmarkHistory,
    BenchmarkScorecard,
    ReleaseGate,
    ReleaseGateResult,
)
from core.benchmark.tasks import TaskSuite, get_default_suite
from core.context_memory import CompiledContext, ContextCompiler
from core.crux_telemetry import (
    get_config,
    get_telemetry,
)
from core.failure_learning import (
    FailureLearningLoop,
    FailureSample,
    LearningStats,
)
from core.field_arena import (
    FieldArena,
    FieldScorecard,
    FieldSession,
    ReplaySessionResult,
)
from core.intelligence.router import IntelligencePolicyRouter
from core.repo_understanding import ProjectContextPack, ProjectOS
from core.result_validator import (
    ConsistencyChecker,
    ConsistencyReport,
    DiffGuard,
    DiffPreview,
    ResultValidator,
    ValidatedResult,
)
from core.reviewer_agent import MultiAgentLayer, ReviewReport, TaskPlan
from core.skill_compiler import (
    CompiledSkillSet,
)
from core.skill_compiler import (
    install_compiler as _install_skill_compiler,
)
from core.tool_call_validator import ToolCallValidator, ValidationResult
from core.tool_result import ToolResult
from core.trace_debugger import (
    DiagnosticReport,
    RunInspector,
    SessionRecord,
    TracePlayer,
    get_recorder,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.intelligence.policy import ExecutionPolicy
    from core.validation_errors import ValidationIssue

logger = logging.getLogger(__name__)


def _default_schema_provider(tool_name: str) -> dict | None:
    try:
        from core.tool_router import get_tool_schema

        return get_tool_schema(tool_name)
    except Exception:
        return None


@dataclass
class ValidationLayer:
    """Validation layer: Phase 1 (tool calls) + Phase 2 (results/consistency/diff)."""

    schema_provider: Callable[[str], dict | None] = field(default=_default_schema_provider)
    max_retries: int = 3

    def __post_init__(self):
        self.validator = ToolCallValidator(schema_provider=self.schema_provider)
        self.result_validator = ResultValidator()
        self.consistency_checker = ConsistencyChecker()
        self.diff_guard = DiffGuard()
        self._tool_history: list[dict] = []
        self.context_memory = ContextCompiler()
        self.multi_agent = MultiAgentLayer()
        # ── Phase 5: Skill / Prompt compiler ──
        try:
            self._skill_compiler, self._prompt_compiler, self._compiled_skills = _install_skill_compiler("skills")
        except Exception as e:
            logger.debug("Skill compiler init failed: %s", e)
            self._skill_compiler = None
            self._prompt_compiler = None
            self._compiled_skills = None
        # ── Phase 6: Telemetry + Config ──
        self.telemetry = get_telemetry()
        self.config = get_config()
        # ── Phase 8: Intelligence Policy Router ──
        self.policy_router = IntelligencePolicyRouter()
        self._current_policy: ExecutionPolicy | None = None
        # ── Phase 9: Project Intelligence Layer ──
        self.project_os: ProjectOS | None = None
        # ── Phase 10: Trace Debugger ──
        self.decision_recorder = get_recorder()
        # ── Phase 11: Failure Learning Loop ──
        self.learning_loop = FailureLearningLoop()
        # ── Phase 12: Capability Benchmark Arena ──
        self._bench_suite = get_default_suite()
        self._bench_runner = BenchmarkRunner()
        self._bench_history = BenchmarkHistory()
        # ── Phase 13: Field Arena ──
        self._field_arena = FieldArena()

    # ── Phase 1: Tool call validation ──────────────────────────

    def validate(self, llm_text: str) -> ValidationResult:
        return self.validator.validate_llm_output(llm_text)

    def validate_tool_call(self, tool_name: str, args: dict) -> list[ValidationIssue]:
        return self.validator.validate_tool_call(tool_name, args)

    def build_correction_prompt(self, result: ValidationResult) -> str:
        return self.validator.build_error_message(result)

    # ── Phase 2a: Result validation ────────────────────────────

    def validate_result(self, tool_name: str, result_text: str, success: bool) -> ValidatedResult:
        """Validate tool execution result for errors/size/patterns."""
        return self.result_validator.validate(tool_name, result_text, success)

    # ── Phase 2b: Consistency check ────────────────────────────

    def track_tool_call(self, tool_name: str, args: dict, result: str, success: bool):
        """Record a tool call for later consistency checking."""
        self._tool_history.append(
            {
                "tool_name": tool_name,
                "args": args,
                "result": result,
                "success": success,
            }
        )

    def check_consistency(self, llm_answer: str) -> ConsistencyReport:
        """Check LLM final answer against tool execution history."""
        return self.consistency_checker.check(llm_answer, self._tool_history)

    def clear_history(self):
        self._tool_history.clear()

    # ── Phase 2c: Diff guard ───────────────────────────────────

    def snapshot_before_write(self, path: str) -> str | None:
        """Capture file before write operation."""
        return self.diff_guard.snapshot_before(path)

    def preview_write(self, path: str, new_content: str) -> DiffPreview:
        """Generate diff preview for a write operation."""
        return self.diff_guard.preview_write(path, new_content)

    # ── Result wrapping (unchanged from Phase 1) ───────────────

    def wrap_tool_result(
        self, tool_name: str, raw_result: Any, error_msg: str = "", hints: list[str] | None = None
    ) -> ToolResult:
        if error_msg:
            return ToolResult.fail(
                code="TOOL_FAILED",
                message=error_msg,
                hints=hints or [],
                metadata={"tool_name": tool_name},
            )
        return ToolResult.ok(
            data=raw_result,
            hints=hints or [],
            metadata={"tool_name": tool_name},
        )

    def tool_result_to_llm_text(self, result: ToolResult) -> str:
        return result.to_llm_content()

    @staticmethod
    def from_session(session) -> ValidationLayer:
        provider = getattr(session, "_get_schema_for_tool", _default_schema_provider)
        return ValidationLayer(schema_provider=provider)

    # ── Phase 3: Context Memory Integration ────────────────────

    def record_turn(self, user_msg: str, assistant_msg: str, tool_calls: list[dict] | None = None):
        """Record a conversation turn for memory management."""
        self.context_memory.record_turn(user_msg, assistant_msg, tool_calls)

    def track_tool_use_v2(self, tool_name: str, args: dict, result: str, success: bool):
        """Track tool usage for context memory (extends track_tool_call)."""
        # Track for consistency checking (Phase 2)
        self.track_tool_call(tool_name, args, result, success)
        # Track for context memory (Phase 3)
        self.context_memory.track_tool_use(tool_name, args, result, success)

    def set_current_task(self, task: str):
        """Set current task description for working memory."""
        self.context_memory.set_current_task(task)

    def compile_context(self, current_tokens: int = 0) -> CompiledContext:
        """Compile context from all memory tiers."""
        return self.context_memory.compile(current_tokens=current_tokens)

    def inject_context_into_prompt(self, system_prompt: str, current_tokens: int = 0) -> str:
        """Inject compiled context into system prompt."""
        return self.context_memory.inject_into_system_prompt(system_prompt, current_tokens)

    # ── Phase 4: Multi-Agent collaboration ─────────────────────

    def review_turn(
        self, user_query: str, assistant_response: str, tool_results: list[dict] | None = None
    ) -> ReviewReport:
        """Review a conversation turn for quality issues."""
        return self.multi_agent.review_turn(user_query, assistant_response, tool_results)

    def critique_turn(self, user_query: str, assistant_response: str, tool_results: list[dict] | None = None):
        """Get a skeptical second opinion."""
        return self.multi_agent.critique_turn(user_query, assistant_response, tool_results)

    def plan_task(self, user_query: str) -> TaskPlan:
        """Decompose a complex request into sub-tasks."""
        return self.multi_agent.plan_task(user_query)

    def set_llm_callback(self, callback):
        """Set the LLM callback for agent review/debate/decompose."""
        self.multi_agent.llm_callback = callback
        self.multi_agent.rev.llm_callback = callback
        self.multi_agent.debate.llm_callback = callback
        self.multi_agent.decomposer.llm_callback = callback

    # ── Phase 5: Skill / Prompt compiler ───────────────────────

    @property
    def skill_report(self) -> str:
        """Get a report of all compiled skills."""
        if self._skill_compiler and self._compiled_skills:
            return self._skill_compiler.report(self._compiled_skills)
        return "Skill compiler not initialized"

    def compile_prompt(
        self,
        task_target: str = "general",
        active_skills: list[str] | None = None,
        context_memory: str = "",
        token_budget: int = 60000,
        existing_prompt: str = "",
    ) -> str:
        """Assemble an optimized system prompt from compiled skills + context."""
        if self._prompt_compiler is None:
            return existing_prompt
        try:
            result = self._prompt_compiler.compile(
                task_target=task_target,
                active_skills=active_skills,
                context_memory=context_memory,
                token_budget=token_budget,
                existing_prompt=existing_prompt,
            )
            return result.assemble()
        except Exception as e:
            logger.debug("Prompt compilation failed: %s", e)
            return existing_prompt

    def get_compiled_skills(self) -> CompiledSkillSet | None:
        return self._compiled_skills

    # ── Phase 6: Telemetry + Config ───────────────────────────

    def telemetry_report(self) -> str:
        """Get human-readable telemetry report."""
        return self.telemetry.report()

    def telemetry_export(self, path: str = "telemetry.json") -> str:
        """Export telemetry data to JSON file."""
        return self.telemetry.export(path)

    def record_telemetry(
        self,
        event: str,
        phase: str = "",
        tool_name: str = "",
        duration_ms: float = 0.0,
        success: bool = True,
        detail: str = "",
    ):
        """Record a telemetry event (no-op if telemetry disabled)."""
        if self.config.p6_telemetry:
            self.telemetry.record(event, phase, tool_name, duration_ms, success, detail)

    def is_feature_enabled(self, phase_key: str, task_target: str = "general") -> bool:
        """Check if a feature phase is enabled for the current task."""
        return self.config.is_enabled(phase_key, task_target)

    def set_config(self, **kwargs):
        """Override config values."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    # ── Phase 8: Intelligence Policy Router ───────────────────

    def route_policy(
        self,
        user_message: str,
        message_history: list[dict] | None = None,
        prior_failures: int = 0,
        prior_total_turns: int = 0,
        current_tokens: int = 0,
        force_mode: str | None = None,
    ) -> ExecutionPolicy:
        """Route task to optimal execution policy."""
        policy = self.policy_router.route(
            user_message=user_message,
            message_history=message_history,
            prior_failures=prior_failures,
            prior_total_turns=prior_total_turns,
            current_tokens=current_tokens,
            force_mode=force_mode,
        )
        self._current_policy = policy
        return policy

    @property
    def current_policy(self) -> ExecutionPolicy | None:
        return self._current_policy

    def explain_policy(self) -> str:
        """Explain the current routing decision."""
        if self._current_policy:
            return self.policy_router.explain_last()
        return "No policy set"

    def force_mode(self, mode: str) -> ExecutionPolicy:
        """Force a specific run mode, bypassing routing."""
        policy = self.policy_router.route("", force_mode=mode)
        self._current_policy = policy
        return policy

    # ── Phase 9: Project Intelligence Layer ───────────────────

    def ensure_project_index(self) -> ProjectOS:
        """Lazy-init and return ProjectOS, indexing if needed."""
        if self.project_os is None:
            self.project_os = ProjectOS()
            self.project_os.index()
        elif not self.project_os.is_indexed:
            self.project_os.index()
        return self.project_os

    def get_project_context(self, active_file: str = "") -> ProjectContextPack:
        """Build a structured project context pack for LLM injection."""
        os = self.ensure_project_index()
        return os.context_pack(active_file=active_file)

    def search_project(self, query: str) -> list:
        """Search project files by intent."""
        os = self.ensure_project_index()
        return os.search(query)

    def find_symbol(self, name: str) -> list:
        """Find symbol definitions across the repo."""
        os = self.ensure_project_index()
        return os.find_symbol(name)

    def analyze_change_impact(self, file_path: str) -> str:
        """Analyze impact of changing a file."""
        os = self.ensure_project_index()
        return os.analyze_change(file_path)

    # ── Phase 10: Trace Debugger ─────────────────────────────

    def start_trace_session(self, session_id: str = "", tags: list[str] | None = None) -> SessionRecord:
        """Start a new trace session for decision recording."""
        return self.decision_recorder.new_session(session_id, tags)

    def record_decision(
        self,
        category: str,
        decision: str,
        reason: str,
        alternatives: list[str] | None = None,
        outcome: str = "",
        duration_ms: float = 0.0,
    ):
        """Record a decision point in the current trace session."""
        current = self.decision_recorder.current
        if current:
            current.record(category, decision, reason, alternatives, outcome, duration_ms)

    def close_trace_session(self):
        """Close the current trace session."""
        self.decision_recorder.close_current()

    def inspect_trace(self, session_id: str | None = None) -> DiagnosticReport:
        """Get diagnostic report for a session."""
        record = self.decision_recorder.get(session_id) if session_id else self.decision_recorder.current
        if not record:
            return DiagnosticReport(summary="No trace data available")
        return RunInspector().inspect(record)

    def replay_trace(self, session_id: str | None = None) -> list[str]:
        """Replay a trace session step by step."""
        record = self.decision_recorder.get(session_id) if session_id else self.decision_recorder.current
        if not record:
            return ["No trace data available"]
        return TracePlayer(record).play()

    # ── Phase 11: Failure Learning Loop ───────────────────────

    def capture_failure(
        self,
        category: str,
        user_message: str = "",
        assistant_response: str = "",
        tool_calls: list[dict] | None = None,
        tool_results: list[dict] | None = None,
        actual_outcome: str = "",
        expected_outcome: str = "",
        severity: str = "medium",
    ) -> FailureSample:
        """Capture a failure event for the learning loop."""
        return self.learning_loop.capture(
            category=category,
            user_message=user_message,
            assistant_response=assistant_response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            actual_outcome=actual_outcome,
            expected_outcome=expected_outcome,
            severity=severity,
        )

    def analyze_failure(self, sample: FailureSample) -> FailureSample:
        """Analyze a failure: root cause + fix suggestion."""
        return self.learning_loop.analyze(sample)

    def export_failure(self, sample: FailureSample) -> str:
        """Export a failure to the regression set."""
        return self.learning_loop.export(sample)

    def run_failure_pipeline(
        self,
        category: str,
        user_message: str = "",
        assistant_response: str = "",
        actual_outcome: str = "",
        expected_outcome: str = "",
        severity: str = "medium",
    ) -> FailureSample:
        """Full pipeline: capture → analyze → export."""
        return self.learning_loop.run_full_pipeline(
            category=category,
            user_message=user_message,
            assistant_response=assistant_response,
            actual_outcome=actual_outcome,
            expected_outcome=expected_outcome,
            severity=severity,
        )

    @property
    def learning_stats(self) -> LearningStats:
        """Get learning loop statistics."""
        return self.learning_loop.stats()

    @property
    def failure_report(self) -> str:
        """Human-readable failure learning report."""
        return self.learning_loop.report()

    # ── Phase 12: Capability Benchmark Arena ──────────────────

    @property
    def benchmark_suite(self) -> TaskSuite:
        return self._bench_suite

    def run_benchmark(self, task_ids: list[str] | None = None) -> BenchmarkResult:
        """Run benchmark tasks and return results.

        Args:
            task_ids: Optional list of specific task IDs to run. Runs all if None.
        """
        if task_ids:
            return self._bench_runner.run_selected(self._bench_suite, task_ids)
        return self._bench_runner.run_suite(self._bench_suite)

    def score_benchmark(self, result: BenchmarkResult) -> BenchmarkScorecard:
        """Score a benchmark result and save to history."""
        prev = self._bench_history.last(result.suite_name)
        sc = BenchmarkScorecard(previous_score=prev.overall_score if prev else None)
        sc.compute(result)
        self._bench_history.save(sc)
        return sc

    def evaluate_release(self, result: BenchmarkResult) -> ReleaseGateResult:
        """Evaluate whether a benchmark result passes the release gate."""
        sc = self.score_benchmark(result)
        history = self._bench_history.load_all(result.suite_name)
        gate = ReleaseGate()
        return gate.evaluate(sc, history)

    def bench_trends(self) -> str:
        """Get trend report from benchmark history."""
        history = self._bench_history.load_all()
        if len(history) < 1:
            return "No benchmark history yet"
        latest = history[-1]
        return latest.trends(history)

    def evaluate_task(self, task_id: str, response: str, tool_calls: list[dict] | None = None) -> TaskResult:
        """Evaluate a single task with given response."""
        suite = self._bench_suite
        for task in suite.tasks:
            if task.id == task_id:
                return self._bench_runner.run_task(task, response, tool_calls)
        return TaskResult(task_id=task_id, success=False, error="Task not found")

    # ── Phase 13: Field Arena ─────────────────────────────────

    def record_field_session(self, session: FieldSession):
        """Add a field session for reality-gap testing."""
        self._field_arena.add_session(session)

    def field_replay_all(self) -> list[ReplaySessionResult]:
        """Replay all recorded field sessions."""
        return self._field_arena.replay_runner.replay_all(self._field_arena._field_sessions)

    def field_evaluate(
        self, benchmark_result: BenchmarkResult | None = None, field_weight: float = 0.3
    ) -> FieldScorecard:
        """Run field replay + combine with benchmark scores."""
        sc = self.score_benchmark(benchmark_result) if benchmark_result else None
        return self._field_arena.evaluate(sc, field_weight=field_weight)

    def field_release_gate(
        self, field_scorecard: FieldScorecard, min_bench: float = 70.0, min_field: float = 60.0
    ) -> ReleaseGateResult:
        """Dual release gate: benchmark + field passes required."""
        return self._field_arena.release_gate(field_scorecard, min_bench, min_field)

    def field_ab_compare(self, before: BenchmarkResult, after: BenchmarkResult) -> str:
        """A/B compare two benchmark runs."""
        sc_before = self.score_benchmark(before)
        sc_after = self.score_benchmark(after)
        return self._field_arena.compare(sc_before, sc_after)
