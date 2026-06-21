"""Autonomous task executor -- plan, execute, verify loop.

The engine that turns a natural-language task into a sequence of tool calls
with dependency tracking, error recovery, and verification gates.

Lifecycle:
    1. PLAN   — decompose task into ordered steps with dependencies
    2. EXECUTE — run each step with its tool, track state, recover from errors
    3. VERIFY  — run tests / syntax checks, confirm the goal is met
    4. REPORT  — return structured result with evidence
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

__all__ = [
    'ROOT', 'Step', 'Task', 'TaskExecutor', 'quick_plan',
]

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Step:
    id: str
    description: str
    tool: str
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verify: str | None = None  # "syntax" | "test" | None
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""
    error: str = ""


@dataclass
class Task:
    id: str
    goal: str
    steps: list[Step] = field(default_factory=list)
    status: str = "pending"
    errors_allowed: int = 0


class TaskExecutor:
    """Executes a decomposed task with dependency tracking and verification."""

    def __init__(self, tool_executor: Callable, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.execute_tool = tool_executor  # (tool_name, args) -> result_str
        self._log: list[dict] = []

    def run(self, task: Task) -> dict:
        """Run all steps in dependency order. Returns final report."""
        start_ts = time.time()
        task.status = "running"
        errors = 0

        for step in task.steps:
            ready = all(
                any(s.id == dep and s.status == "done" for s in task.steps)
                for dep in step.depends_on
            )
            if not ready:
                step.status = "skipped"
                step.error = f"Dependencies not met: {step.depends_on}"
                continue

            step.status = "running"
            self._log.append({"ts": time.time(), "step": step.id, "event": "start"})
            try:
                result = self.execute_tool(step.tool, step.args)
                step.result = result[:500]
                step.status = "done"
                self._log.append({"ts": time.time(), "step": step.id,
                                  "event": "done", "result_preview": result[:100]})
            except (OSError, ValueError, RuntimeError) as e:
                step.error = f"{type(e).__name__}: {e}"
                step.status = "failed"
                errors += 1
                self._log.append({"ts": time.time(), "step": step.id,
                                  "event": "failed", "error": step.error})
                if errors > task.errors_allowed:
                    break

            # Verification
            if step.verify == "syntax":
                try:
                    import ast
                    py_files = list(self.root.rglob("*.py"))
                    for pf in py_files[:30]:
                        if "__pycache__" not in pf.parts:
                            ast.parse(pf.read_text(encoding="utf-8"))
                    self._log.append({"ts": time.time(), "step": step.id,
                                      "event": "verify_syntax_ok"})
                except SyntaxError as se:
                    step.status = "failed"
                    step.error = f"Syntax check failed: {se}"
                    errors += 1
                    break
            elif step.verify == "test":
                # 经 run_pytest_safe 统一封装：在 pytest 内运行时自动短路，
                # 避免验证步骤 spawn 子 pytest 跑完整 tests/ 造成无限递归 fork。
                from core.pytest_runner import run_pytest_safe
                r = run_pytest_safe(test_target="tests/", timeout=30, cwd=self.root)
                out = r.stdout or ""
                if "failed" in out and "0 failed" not in out:
                    step.status = "failed"
                    step.error = f"Tests failed: {out[-200:]}"
                    errors += 1
                    break
                self._log.append({"ts": time.time(), "step": step.id,
                                  "event": "verify_tests_ok"})

        elapsed = time.time() - start_ts
        all_done = all(s.status == "done" for s in task.steps)
        task.status = "done" if all_done else "failed" if errors > 0 else "partial"

        return {
            "goal": task.goal,
            "status": task.status,
            "elapsed": round(elapsed, 2),
            "steps_total": len(task.steps),
            "steps_done": sum(1 for s in task.steps if s.status == "done"),
            "steps_failed": sum(1 for s in task.steps if s.status == "failed"),
            "steps_skipped": sum(1 for s in task.steps if s.status == "skipped"),
            "details": [{"id": s.id, "status": s.status, "error": s.error,
                         "result_preview": s.result[:100]}
                        for s in task.steps if s.status != "done"],
            "log": self._log[-10:],
        }


def quick_plan(goal: str) -> Task:
    """Generate a simple plan for common task patterns (no LLM needed)."""
    goal_lower = goal.lower()
    steps = []
    
    # Pattern: fix bug
    if "fix" in goal_lower or "bug" in goal_lower or "repair" in goal_lower:
        steps = [
            Step("1_read_error", "Read error log", "read_file",
                 {"path": "output/last_error.txt"}),
            Step("2_search_code", "Search for related code", "search_files",
                 {"pattern": goal.split()[-1] if goal.split() else "TODO"}),
            Step("3_fix", "Apply fix", "edit_file",
                 {"path": "PLACEHOLDER", "old_text": "PLACEHOLDER",
                  "new_text": "PLACEHOLDER"},
                 depends_on=["2_search_code"]),
            Step("4_verify", "Verify syntax", "env_check", {},
                 verify="syntax", depends_on=["3_fix"]),
        ]
    
    # Pattern: audit / check
    if "audit" in goal_lower or "check" in goal_lower or "scan" in goal_lower:
        steps = [
            Step("1_audit", "Run self-audit", "env_check", {}),
            Step("2_tests", "Run tests", "run_test", {},
                 verify="test", depends_on=["1_audit"]),
        ]
    
    # Pattern: test
    if "test" in goal_lower:
        steps = [
            Step("1_test", "Run test suite", "run_test", {},
                 verify="test"),
        ]
    
    if not steps:
        steps = [
            Step("1_understand", "Analyze the goal", "read_file",
                 {"path": "README.md"}),
            Step("2_verify", "Verify environment", "env_check", {}),
        ]
    
    return Task(id=f"task_{int(time.time())}", goal=goal, steps=steps, errors_allowed=1)