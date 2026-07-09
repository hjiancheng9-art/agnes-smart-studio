"""
Arena Schemas — 基准竞技场数据结构
====================================
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArenaDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class PatchRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ArenaPatch:
    """待验证的补丁"""

    patch_id: str = ""
    patch: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    risk: PatchRisk = PatchRisk.MEDIUM
    source: str = ""  # "adaptive_learner" / "manual" / "policy_adapter"
    created_at: float = 0.0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.patch_id:
            self.patch_id = f"ap_{str(uuid.uuid4())[:8]}"
        if not self.created_at:
            self.created_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "patch": self.patch,
            "description": self.description,
            "risk": self.risk.value,
            "source": self.source,
            "tags": self.tags,
        }


@dataclass
class BenchmarkCase:
    """单条基准测试用例"""

    case_id: str
    type: str  # "router" / "intelligence" / "code" / "security"
    input: str
    expected: str
    acceptable: list[str] | None = None
    tags: list[str] | None = None
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "type": self.type,
            "input": self.input[:100],
            "expected": self.expected,
            "acceptable": self.acceptable,
            "tags": self.tags,
            "weight": self.weight,
        }


@dataclass
class BenchmarkResult:
    """基准测试结果"""

    case_id: str
    passed: bool
    actual: str = ""
    expected: str = ""
    score: float = 0.0
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "actual": self.actual[:100],
            "expected": self.expected[:100],
            "score": round(self.score, 2),
        }


@dataclass
class ArenaRunReport:
    """Arena 运行报告"""

    run_id: str = ""
    patch_id: str = ""
    status: ArenaDecision = ArenaDecision.FAIL
    results: list[BenchmarkResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0
    error: str = ""

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"ar_{str(uuid.uuid4())[:8]}"
        if not self.started_at:
            self.started_at = time.time()

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total_count * 100 if self.total_count else 0.0

    @property
    def decision(self) -> ArenaDecision:
        if self.pass_rate >= 90:
            return ArenaDecision.PASS
        elif self.pass_rate >= 70:
            return ArenaDecision.NEEDS_REVIEW
        return ArenaDecision.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "patch_id": self.patch_id,
            "status": self.status.value if isinstance(self.status, ArenaDecision) else self.status,
            "decision": self.decision.value,
            "total_count": self.total_count,
            "pass_count": self.pass_count,
            "pass_rate": round(self.pass_rate, 1),
            "summary": self.summary,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error[:200],
        }


@dataclass
class SandboxConfig:
    """沙箱配置"""

    max_runtime_seconds: float = 60.0
    max_tool_calls: int = 10
    allow_file_write: bool = False
    allow_shell: bool = False
    allow_network: bool = False
    isolation_level: str = "high"  # low / medium / high

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_tool_calls": self.max_tool_calls,
            "allow_file_write": self.allow_file_write,
            "allow_shell": self.allow_shell,
            "allow_network": self.allow_network,
            "isolation_level": self.isolation_level,
        }
