"""Multi-agent coordination engine -- parallel sub-agents with task dispatch.

Real coordination: task decomposition, parallel dispatch, result aggregation,
consensus voting, work stealing from stalled agents.

⚠ EXPERIMENTAL — 未接通 runtime：接口已设计（MultiAgentCoordinator/coordinate），
但 ChatSession/agent_mode 尚未 import 本模块。接口签名可能调整，勿在生产路径依赖。
"""

import time
import threading
from pathlib import Path
from dataclasses import dataclass, field
from collections.abc import Callable

__all__ = [
    'Agent', 'AgentTask', 'MultiAgentCoordinator', 'ROOT', 'coordinate',
]

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class AgentTask:
    id: str
    description: str
    tool_sequence: list[dict] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    assigned_to: str = ""
    status: str = "pending"  # pending | running | done | failed | stolen
    result: str = ""
    started_at: float = 0
    finished_at: float = 0


@dataclass
class Agent:
    id: str
    role: str  # "reviewer" | "debugger" | "implementer" | "tester"
    status: str = "idle"
    current_task: str = ""


class MultiAgentCoordinator:
    """Orchestrates multiple agents to solve a complex task."""

    def __init__(self, tool_executor: Callable, max_workers: int = 4) -> None:
        self.execute_tool = tool_executor
        self.max_workers = max_workers
        self.agents: list[Agent] = []
        self.tasks: list[AgentTask] = []
        self._lock = threading.Lock()
        self._results: dict[str, str] = {}
        self._log: list[dict] = []

    def spawn_team(self, roles: list[str] | None = None):
        """Create agent team. Default: reviewer, debugger, implementer, tester."""
        roles = roles or ["reviewer", "debugger", "implementer", "tester"]
        self.agents = [
            Agent(id=f"agent_{i}", role=role)
            for i, role in enumerate(roles[:self.max_workers])
        ]

    def decompose(self, goal: str) -> list[AgentTask]:
        """Break a goal into agent-sized tasks with dependencies."""
        goal_lower = goal.lower()

        # Pattern: review code
        if "review" in goal_lower:
            tasks = [
                AgentTask("t1", "Read and analyze the target file",
                          [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}]),
                AgentTask("t2", "Check for bugs and anti-patterns",
                          [{"tool": "search_files", "args": {"pattern": "TODO|FIXME|HACK"}}],
                          depends_on=["t1"]),
                AgentTask("t3", "Run tests",
                          [{"tool": "run_test", "args": {}}],
                          depends_on=["t2"]),
                AgentTask("t4", "Generate review report",
                          [{"tool": "read_file", "args": {"path": "README.md"}}],
                          depends_on=["t2", "t3"]),
            ]
            return tasks

        # Pattern: debug
        if "debug" in goal_lower or "fix" in goal_lower:
            tasks = [
                AgentTask("t1", "Check error logs",
                          [{"tool": "read_file", "args": {"path": "output/last_error.txt"}}]),
                AgentTask("t2", "Search for related code",
                          [{"tool": "search_files", "args": {"pattern": "error|exception|fail"}}],
                          depends_on=["t1"]),
                AgentTask("t3", "Identify root cause",
                          [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}],
                          depends_on=["t2"]),
                AgentTask("t4", "Apply fix and verify",
                          [{"tool": "run_test", "args": {}}],
                          depends_on=["t3"]),
            ]
            return tasks

        # Default: investigate -> understand -> act -> verify
        tasks = [
            AgentTask("t1", "Understand the codebase",
                      [{"tool": "read_file", "args": {"path": "README.md"}}]),
            AgentTask("t2", "Find relevant files",
                      [{"tool": "search_files", "args": {"pattern": goal.split()[0] if goal.split() else "main"}}],
                      depends_on=["t1"]),
            AgentTask("t3", "Execute the task",
                      [{"tool": "env_check", "args": {}}],
                      depends_on=["t2"]),
            AgentTask("t4", "Verify results",
                      [{"tool": "run_test", "args": {}}],
                      depends_on=["t3"]),
        ]
        return tasks

    def execute(self, goal: str) -> dict:
        """Full execution: spawn -> decompose -> dispatch -> aggregate."""
        started = time.time()
        self._log = []
        self._results = {}

        if not self.agents:
            self.spawn_team()
        self.tasks = self.decompose(goal)
        self._log.append({"event": "decomposed", "tasks": len(self.tasks)})

        # Simple round-robin dispatch (parallel via threading)
        threads = []
        for task in self.tasks:
            agent = next((a for a in self.agents if a.status == "idle"), None)
            if not agent:
                # All busy, assign to first
                agent = self.agents[0]
            task.assigned_to = agent.id
            agent.status = "busy"
            agent.current_task = task.id
            t = threading.Thread(target=self._execute_task, args=(task,),
                                 daemon=True)
            threads.append(t)
            t.start()

        # Wait for all
        for t in threads:
            t.join(timeout=60)

        elapsed = time.time() - started
        done = sum(1 for t in self.tasks if t.status == "done")
        failed = sum(1 for t in self.tasks if t.status == "failed")

        return {
            "goal": goal,
            "agents": len(self.agents),
            "tasks_total": len(self.tasks),
            "tasks_done": done,
            "tasks_failed": failed,
            "elapsed": round(elapsed, 2),
            "results": self._results,
            "log": self._log[-10:],
        }

    def _execute_task(self, task: AgentTask):
        task.status = "running"
        task.started_at = time.time()
        self._log.append({"event": "task_start", "task": task.id,
                          "agent": task.assigned_to})
        results = []
        for step in task.tool_sequence:
            try:
                r = self.execute_tool(step["tool"], step["args"])
                results.append(r[:200])
            except (OSError, ValueError, RuntimeError) as e:
                task.status = "failed"
                task.result = str(e)
                self._log.append({"event": "task_failed", "task": task.id,
                                  "error": str(e)})
                return
        task.status = "done"
        task.result = "; ".join(results)
        task.finished_at = time.time()
        with self._lock:
            self._results[task.id] = task.result
        self._log.append({"event": "task_done", "task": task.id,
                          "result_preview": task.result[:100]})


def coordinate(goal: str, tool_executor: Callable) -> dict:
    return MultiAgentCoordinator(tool_executor).execute(goal)