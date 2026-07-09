# core/benchmark/runner.py
"""BenchmarkRunner — runs benchmark tasks and collects raw results.

Works with a callback-based evaluation: the benchmark provides tasks,
the runner invokes an LLM callback, and records structured results.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from core.benchmark.tasks import BenchmarkTask, TaskSuite

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """Result of running a single benchmark task."""

    task_id: str = ""
    category: str = ""
    difficulty: str = ""
    success: bool = False
    response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str = ""
    tool_call_count: int = 0
    has_expected_tools: bool = False
    has_expected_keywords: bool = False
    has_forbidden_keywords: bool = False
    response_too_short: bool = False
    score: float = 0.0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "difficulty": self.difficulty,
            "success": self.success,
            "error": self.error[:200] if self.error else "",
            "duration_ms": round(self.duration_ms, 1),
            "tool_call_count": self.tool_call_count,
            "has_expected_tools": self.has_expected_tools,
            "has_expected_keywords": self.has_expected_keywords,
            "has_forbidden_keywords": self.has_forbidden_keywords,
            "response_too_short": self.response_too_short,
            "score": round(self.score, 2),
        }


@dataclass
class BenchmarkResult:
    """Aggregated results from running a full task suite."""

    suite_name: str = ""
    timestamp: float = 0.0
    task_results: list[TaskResult] = field(default_factory=list)
    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        return round(self.passed / max(self.total_tasks, 1) * 100, 1)

    @property
    def average_score(self) -> float:
        if not self.task_results:
            return 0.0
        return round(sum(r.score for r in self.task_results) / len(self.task_results), 2)

    def by_category(self) -> dict[str, dict]:
        """Group results by category."""
        groups: dict[str, dict] = {}
        for r in self.task_results:
            if r.category not in groups:
                groups[r.category] = {"total": 0, "passed": 0, "score_sum": 0.0}
            groups[r.category]["total"] += 1
            if r.success:
                groups[r.category]["passed"] += 1
            groups[r.category]["score_sum"] += r.score
        for g in groups.values():
            g["pass_rate"] = round(g["passed"] / max(g["total"], 1) * 100, 1)
            g["avg_score"] = round(g["score_sum"] / max(g["total"], 1), 2)
        return groups

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"📊 Benchmark: {self.suite_name}",
            f"   {self.passed}/{self.total_tasks} passed ({self.pass_rate}%)",
            f"   Average score: {self.average_score}/100",
            f"   Duration: {self.total_duration_ms:.0f}ms",
            "",
            "   By category:",
        ]
        for cat, data in sorted(self.by_category().items()):
            bar = "█" * int(data["pass_rate"] / 10) + "░" * (10 - int(data["pass_rate"] / 10))
            lines.append(f"     {cat:15s} {bar} {data['pass_rate']:5.1f}% ({data['passed']}/{data['total']})")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "suite_name": self.suite_name,
            "timestamp": self.timestamp,
            "total_tasks": self.total_tasks,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": self.pass_rate,
            "average_score": self.average_score,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "by_category": self.by_category(),
            "tasks": [r.to_dict() for r in self.task_results],
        }

    def save(self, path: str):
        """Save results to JSON."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


LLMCallback = Callable[[str], str]
"""Callback signature: (user_prompt) -> assistant_response"""


class BenchmarkRunner:
    """Runs benchmark tasks and collects results.

    Usage:
        runner = BenchmarkRunner(llm_callback=my_llm_call)
        result = runner.run_suite(suite)
        print(result.summary())
    """

    def __init__(self, llm_callback: LLMCallback | None = None):
        self.llm_callback = llm_callback
        self._results: list[BenchmarkResult] = []

    def run_task(self, task: BenchmarkTask, response: str = "", tool_calls: list[dict] | None = None) -> TaskResult:
        """Evaluate a single benchmark task.

        If response and tool_calls are provided, uses them directly.
        Otherwise, invokes the LLM callback.
        """
        start = time.time()
        result = TaskResult(task_id=task.id, category=task.category, difficulty=task.difficulty)

        # Get response
        if not response and self.llm_callback:
            try:
                response = self.llm_callback(task.prompt)
            except Exception as e:
                result.error = str(e)
                response = ""

        result.response = response
        result.tool_calls = tool_calls or []
        result.tool_call_count = len(result.tool_calls)
        result.duration_ms = (time.time() - start) * 1000

        # Check expected tools
        if task.expected_tools:
            call_names = [tc.get("name", "") for tc in result.tool_calls]
            result.has_expected_tools = all(any(et in cn for cn in call_names) for et in task.expected_tools)

        # Check expected keywords in response
        if task.expected_keywords:
            response_lower = response.lower()
            keywords = task.expected_keywords if isinstance(task.expected_keywords, list) else [task.expected_keywords]
            result.has_expected_keywords = all(kw.lower() in response_lower for kw in keywords)
        else:
            result.has_expected_keywords = True

        # Check forbidden keywords
        if task.forbidden_keywords:
            response_lower = response.lower()
            result.has_forbidden_keywords = any(fk.lower() in response_lower for fk in task.forbidden_keywords)

        # Check response length
        result.response_too_short = len(response.strip()) < task.min_response_length

        # Compute score (0-100)
        score = 100.0

        if not response.strip():
            score -= 100  # empty response = complete failure
        elif result.response_too_short:
            score -= 30

        if not result.has_expected_tools and task.expected_tools:
            score -= 20

        if not result.has_expected_keywords and task.expected_keywords:
            score -= 15

        if result.has_forbidden_keywords:
            score -= 20

        if result.tool_call_count > task.max_tool_calls:
            score -= 10

        result.score = max(0.0, score)

        # Success threshold
        result.success = result.score >= 60.0

        return result

    def run_suite(self, suite: TaskSuite) -> BenchmarkResult:
        """Run all tasks in a suite and aggregate results."""
        bm_result = BenchmarkResult(
            suite_name=suite.name,
            timestamp=time.time(),
            total_tasks=suite.total,
        )

        for task in suite.tasks:
            try:
                task_result = self.run_task(task)
            except Exception as e:
                task_result = TaskResult(
                    task_id=task.id,
                    category=task.category,
                    difficulty=task.difficulty,
                    success=False,
                    error=str(e),
                )
            bm_result.task_results.append(task_result)
            if task_result.success:
                bm_result.passed += 1
            else:
                bm_result.failed += 1
            bm_result.total_duration_ms += task_result.duration_ms

        self._results.append(bm_result)
        return bm_result

    def run_selected(self, suite: TaskSuite, task_ids: list[str]) -> BenchmarkResult:
        """Run only selected tasks from a suite."""
        selected = [t for t in suite.tasks if t.id in task_ids]
        subset = TaskSuite(name=f"{suite.name} (subset)", tasks=selected)
        return self.run_suite(subset)
