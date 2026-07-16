"""Goal Mode — 借鉴 Kimi Code Goal Mode.

将模糊意图转化为明确完成契约，含预算管理 + 停止规则。

提取自 core/executor.py 以消除循环导入风险。
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

# fcntl is Unix-only; on Windows it's not available
HAS_FCNTL = False
_fcntl_module = None
if sys.platform != "win32":
    try:
        import fcntl as _fcntl_module  # type: ignore[import-unused]

        HAS_FCNTL = True
    except ImportError:
        pass

ROOT = Path(__file__).resolve().parent.parent
_GOALS_FILE = ROOT / "output" / "goals.json"


@dataclass
class Goal:
    """A goal-mode task with clear finish line, boundaries, and budget."""

    id: str
    intent: str
    finish_line: str = ""
    boundaries: str = ""
    status: str = "active"  # active | paused | completed | cancelled
    max_steps: int = 20
    max_tool_calls: int = 100
    max_duration_seconds: int = 0  # 0 = unlimited
    steps_executed: int = 0
    tool_calls_made: int = 0
    created_at: str = ""
    updated_at: str = ""
    evidence: str = ""

    def is_budget_exhausted(self) -> bool:
        return self.steps_executed >= self.max_steps or self.tool_calls_made >= self.max_tool_calls

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Goal:
        return cls(**data)


class GoalManager:
    """Persistent goal manager backed by a JSON file.

    借鉴 Kimi Code 的 CreateGoal / GetGoal / SetGoalBudget / UpdateGoal 理念，
    用 Python dataclass + JSON 实现，与 task_manager 风格一致。
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _GOALS_FILE
        self._goals: dict[str, Goal] = {}
        self._active_goal_id: str = ""
        self._next_id: int = 1
        self._lock = threading.RLock()
        self._load()

    def create(self, intent: str, finish_line: str = "", boundaries: str = "", max_steps: int = 20) -> Goal:
        with self._lock:
            gid = f"goal-{self._next_id:03d}"
            self._next_id += 1
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            goal = Goal(
                id=gid,
                intent=intent,
                finish_line=finish_line,
                boundaries=boundaries,
                max_steps=max_steps,
                created_at=now,
                updated_at=now,
            )
            self._goals[gid] = goal
            if not self._active_goal_id:
                self._active_goal_id = gid
            self._save()
            return goal

    def get(self, goal_id: str = "") -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            return self._goals.get(gid)

    def set_budget(
        self,
        goal_id: str = "",
        max_steps: int | None = None,
        max_tool_calls: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            goal = self._goals.get(gid)
            if goal is None:
                return None
            if max_steps is not None:
                goal.max_steps = max_steps
            if max_tool_calls is not None:
                goal.max_tool_calls = max_tool_calls
            if max_duration_seconds is not None:
                goal.max_duration_seconds = max_duration_seconds
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return goal

    def update(
        self, goal_id: str = "", status: str = "", evidence: str = "", auto_evaluate: bool = True
    ) -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            goal = self._goals.get(gid)
            if goal is None:
                return None
            if status:
                goal.status = status
            if evidence:
                goal.evidence = evidence
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # ── 自动评估：标记 completed 时触发独立评估器 ──
            eval_result = None
            if status == "completed" and auto_evaluate:
                try:
                    from core.goal_evaluator import GoalVerdict, get_evaluator

                    evaluator = get_evaluator()
                    eval_result = evaluator.evaluate(goal, use_llm=True)
                    # 评估不通过时自动退回 needs_fix
                    if eval_result.verdict != GoalVerdict.PASS:
                        goal.status = "needs_fix"
                        goal.evidence = (
                            f"{evidence}\n\n[自动评估] {eval_result.verdict.value}: "
                            f"{eval_result.evidence}\n"
                            f"问题: {'; '.join(eval_result.issues)}"
                        )
                except (ImportError, OSError, RuntimeError, ValueError):
                    pass  # 评估器不可用时静默降级，不影响完成标记

            self._save()

            # 返回评估结果作为额外属性（非破坏性附加）
            if eval_result:
                goal._eval_result = eval_result  # type: ignore[attr-defined]

            return goal

    def _ensure_active_goal(self) -> Goal | None:
        """Return the current active goal, auto-switching if exhausted.

        If the active goal's budget is exhausted, try the next active goal.
        If no active goal exists, returns None (unlimited execution).
        """
        goal = self._goals.get(self._active_goal_id)
        if goal is not None and goal.is_budget_exhausted():
            # Try next active goal
            for g in self._goals.values():
                if g.status == "active" and not g.is_budget_exhausted():
                    self._active_goal_id = g.id
                    self._save()
                    return g
            # All goals exhausted → unlimited
            return None
        return goal

    def record_step(self) -> bool:
        """Record a step execution; returns True if budget still available.

        If no active goal exists, returns True (unlimited execution).
        If the active goal's budget is exhausted, auto-switches to next active goal.
        """
        with self._lock:
            goal = self._ensure_active_goal()
            if goal is None:
                return True  # no goal or all exhausted → unlimited
            goal.steps_executed += 1
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return not goal.is_budget_exhausted()

    def record_tool_call(self) -> bool:
        """Record a tool call; returns True if budget still available.

        If no active goal exists, returns True (unlimited execution).
        """
        with self._lock:
            goal = self._ensure_active_goal()
            if goal is None:
                return True  # no goal or all exhausted → unlimited
            goal.tool_calls_made += 1
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return not goal.is_budget_exhausted()

    def _save(self) -> None:
        data = {
            "goals": [g.to_dict() for g in self._goals.values()],
            "active_goal_id": self._active_goal_id,
            "next_id": self._next_id,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # File lock for multi-process safety (Unix only)
        if HAS_FCNTL and _fcntl_module is not None:
            lock_path = self._path.with_suffix(".lock")
            try:
                lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
                _fcntl_module.flock(lock_fd, _fcntl_module.LOCK_EX)
                try:
                    tmp = self._path.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
                    os.replace(tmp, self._path)
                finally:
                    _fcntl_module.flock(lock_fd, _fcntl_module.LOCK_UN)
                    os.close(lock_fd)
                return
            except OSError:
                pass
        # Fallback: no fcntl or lock failure
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        self._next_id = data.get("next_id", 1)
        self._active_goal_id = data.get("active_goal_id", "")
        for gd in data.get("goals", []):
            try:
                goal = Goal.from_dict(gd)
                self._goals[goal.id] = goal
            except (TypeError, KeyError):
                continue


# ── Module-level singleton ──────────────────────────────────

_goal_manager: GoalManager | None = None


def get_goal_manager() -> GoalManager:
    """Get or create the global GoalManager singleton."""
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager


__all__ = [
    "Goal",
    "GoalManager",
    "get_goal_manager",
]
