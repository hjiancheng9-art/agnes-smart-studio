"""Multi-agent data models — extracted from core/multi_agent.py.

Pure dataclasses shared by MultiAgentCoordinator, AgentSwarm, and SmartDecomposer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


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
    tier: str = "auto"
    task_type: str = ""


@dataclass
class Agent:
    id: str
    role: str  # "reviewer" | "debugger" | "implementer" | "tester"
    status: str = "idle"
    current_task: str = ""
    context_history: list[dict] = field(default_factory=list)
    created_at: float = 0.0
    total_tasks_completed: int = 0
