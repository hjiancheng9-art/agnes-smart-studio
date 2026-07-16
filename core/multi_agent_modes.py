"""Multi-agent mode computation — weighted scoring + 4-tier agent orchestration.

Extracted from core/multi_agent.py (P2 refactor). Contains all type definitions,
scoring functions, and mode-selection logic. Zero internal dependencies on the
coordinator classes — safe to import standalone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class SessionContext:
    """多智能体决策上下文"""

    recent_failures: int = 0
    files_touched: int = 0
    tools_used: int = 0
    error_repeated: bool = False
    task_continuation: bool = False
    previous_plan_exists: bool = False

    @staticmethod
    def from_dict(d: dict) -> SessionContext:
        return SessionContext(
            recent_failures=d.get("recent_failures", 0),
            files_touched=d.get("files_touched", 0),
            tools_used=d.get("tools_used", 0),
            error_repeated=d.get("error_repeated", False),
        )


# ═══════════════════════════════════════════════════════════
# AgentMode 4-tier system — weighted multi-factor scoring
# ═══════════════════════════════════════════════════════════


class AgentMode(Enum):
    """4-tier agent orchestration mode, selected by weighted multi-factor scoring."""

    SINGLE = "single"  # score < 3
    SINGLE_WITH_REVIEWER = "single_with_reviewer"  # score >= 3
    PLAN_EXECUTE = "plan_execute"  # score >= 5
    SWARM = "swarm"  # score >= 8


@dataclass
class AgentModeResult:
    """Record of a completed agent mode execution for long-term learning."""

    mode: AgentMode
    task_type: str
    success: bool
    latency: float
    user_correction: bool = False
    timestamp: float = field(default_factory=lambda: __import__("time", fromlist=["time"]).time())


# ─── Weighted trigger keywords ───

_TRIGGERS: dict[str, list[tuple[str, float]]] = {
    "high_complexity": [
        ("refactor", 3.0),
        ("重构", 3.0),
        ("migrate", 3.0),
        ("迁移", 3.0),
        ("architecture", 3.0),
        ("架构", 3.0),
        ("audit", 2.5),
        ("审计", 2.5),
        ("review entire", 3.0),
        ("审查整个", 3.0),
        ("review whole", 3.0),
        ("batch", 2.0),
        ("批量", 2.0),
        ("parallel", 2.5),
        ("并行", 2.5),
        ("simultaneous", 2.5),
        ("同时处理", 2.5),
        ("multi-module", 2.5),
        ("多模块", 2.5),
        ("cross-file", 2.5),
        ("跨文件", 2.5),
        ("entire project", 3.0),
        ("全项目", 3.0),
    ],
    "multi_perspective": [
        ("compare", 2.0),
        ("对比", 2.0),
        ("comparison", 2.0),
        ("比较", 2.0),
        ("pros and cons", 2.5),
        ("正反", 2.5),
        ("multi-angle", 2.5),
        ("多角度", 2.5),
    ],
    "coordination": [
        ("orchestrate", 3.0),
        ("coordinate", 2.5),
        ("协同", 2.5),
        ("multiple agents", 3.5),
        ("多智能体", 3.5),
        ("swarm", 3.5),
        ("team", 2.0),
        ("团队", 2.0),
    ],
}

_SIMPLICITY_BLOCKERS: list[tuple[str, float]] = [
    ("simple", 2.0),
    ("简单", 2.0),
    ("quick", 1.5),
    ("快速", 1.5),
    ("immediate", 2.0),
    ("立即", 2.0),
    ("direct", 2.0),
    ("直接", 2.0),
    ("single step", 3.0),
    ("单步", 3.0),
    ("one word", 3.0),
    ("一句话", 3.0),
    ("简答", 3.0),
    ("brief", 1.5),
    ("tiny", 2.0),
    ("just", 1.0),
    ("只", 1.0),
    ("only", 1.0),
]

_DESTRUCTIVE_ACTIONS: list[tuple[str, float]] = [
    ("delete", 4.0),
    ("clean", 4.0),
    ("migrate", 4.0),
    ("reset", 4.0),
    ("drop", 4.0),
    ("truncate", 4.0),
    ("purge", 4.0),
    ("rm ", 4.0),
    ("remove all", 4.0),
    ("destroy", 4.0),
    ("wipe", 4.0),
    ("nuke", 4.0),
    ("删除", 4.0),
    ("清理", 4.0),
    ("重置", 4.0),
    ("销毁", 4.0),
]

_FUZZY_INTENT: list[tuple[str, float]] = [
    ("maybe", 1.0),
    ("perhaps", 1.0),
    ("possibly", 1.0),
    ("大概", 1.0),
    ("也许", 1.0),
    ("可能", 1.0),
    ("或许", 1.0),
    ("unsure", 1.5),
    ("不确定", 1.5),
    ("not sure", 1.5),
    ("something like", 1.5),
    ("之类", 1.5),
    ("看看", 0.5),
    ("试试", 0.5),
    ("explore", 0.5),
    ("不好用", 2.0),
    ("不对劲", 2.0),
    ("还是不行", 2.0),
]


def _match_weighted(text: str, patterns: list[tuple[str, float]]) -> tuple[float, list[str]]:
    """Return (total_score, matched_patterns) for weighted pattern matching."""
    tl = text.lower()
    total = 0.0
    matched: list[str] = []
    for pat, weight in patterns:
        if pat in tl:
            total += weight
            matched.append(pat)
    return total, matched


# ─── Individual scoring functions ───


def keyword_score(goal: str) -> tuple[float, list[str]]:
    """Weighted keyword score from _TRIGGERS dict.

    Returns:
        (total_score, matched_keywords)
    """
    total = 0.0
    all_matched: list[str] = []
    for _cat, patterns in _TRIGGERS.items():
        s, m = _match_weighted(goal, patterns)
        total += s
        all_matched.extend(m)
    return total, all_matched


def length_score(goal: str) -> float:
    """Score based on task description length (complexity proxy).

    Longer tasks signal more complex requirements.
    """
    ln = len(goal)
    if ln > 2000:
        return 3.0
    if ln > 1000:
        return 2.5
    if ln > 500:
        return 1.5
    if ln > 200:
        return 0.5
    return 0.0


def file_scope_score(session: dict[str, Any]) -> float:
    """Score based on context features: breadth of files touched in session.

    More files touched → broader impact → more agents may help.
    """
    files = session.get("files_touched", 0)
    if files > 20:
        return 3.0
    if files > 10:
        return 2.0
    if files > 5:
        return 1.0
    if files > 2:
        return 0.5
    return 0.0


def failure_score(session: dict[str, Any]) -> float:
    """Score from recent failures and error repetition signals.

    Repeated failures suggest the current approach isn't working —
    more agents or perspectives may break the deadlock.
    """
    score = 0.0
    recent = session.get("recent_failures", 0)
    if recent >= 3:
        score += 3.0
    elif recent >= 2:
        score += 2.0
    elif recent >= 1:
        score += 1.0
    if session.get("error_repeated", False):
        score += 2.0
    return score


def risk_score(goal: str) -> tuple[float, list[str]]:
    """Risk score for destructive actions. Each match adds +4.

    Destructive operations warrant extra review — SWARM or PLAN_EXECUTE.
    """
    return _match_weighted(goal, _DESTRUCTIVE_ACTIONS)


def ambiguity_score(goal: str) -> tuple[float, list[str]]:
    """Ambiguity/fuzzy-intent score — unclear tasks benefit from multi-agent exploration.

    Fuzzy intent means the user hasn't specified exact steps, so multi-agent
    exploration or planning helps clarify before execution.
    """
    return _match_weighted(goal, _FUZZY_INTENT)


def simplicity_score(goal: str) -> tuple[float, list[str]]:
    """Negative weight from simplicity blockers.

    Returns positive values that are SUBTRACTED from the total.
    These are not hard stops — they reduce the score but don't block multi-agent.
    """
    return _match_weighted(goal, _SIMPLICITY_BLOCKERS)


def decomposability_score(goal: str) -> tuple[float, list[str]]:
    """DAG decomposability estimation (v6.0).

    智谱清言建议：预判任务是否能拆解为独立并行子任务。
    可分解性高的任务 → 有并行叶子节点 → 适合 SWARM。
    """
    patterns: list[tuple[str, float]] = [
        ("并且", 3.0),
        ("同时", 3.0),
        ("分别", 3.0),
        ("先", 1.5),
        ("再", 1.5),
        ("然后", 1.5),
        ("前端", 2.0),
        ("后端", 2.0),
        ("前后端", 3.0),
        ("数据库", 2.0),
        ("API", 2.0),
        ("同时生成", 4.0),
        ("并行处理", 4.0),
        ("分别处理", 3.0),
        ("各自", 2.0),
        ("多维度", 2.0),
        ("多个方面", 2.0),
        ("多角度", 2.0),
        ("提取", 1.5),
        ("转换", 1.5),
        ("合并", 1.5),
    ]
    return _match_weighted(goal, patterns)


# ─── Context state features ───


def build_context_state(
    recent_failures: int = 0,
    files_touched: int = 0,
    tools_used: int = 0,
    error_repeated: bool = False,
    task_continuation: bool = False,
) -> dict[str, Any]:
    """Build a context state features dict consumed by scoring functions.

    All values default to 0/False — callers incrementally populate from
    session state (recent tool calls, error counts, touched files, etc.).
    """
    return {
        "recent_failures": recent_failures,
        "files_touched": files_touched,
        "tools_used": tools_used,
        "error_repeated": error_repeated,
        "task_continuation": task_continuation,
    }


# ─── Main scoring + mode selection ───


def compute_agent_mode(
    goal: str,
    session: dict[str, Any] | None = None,
) -> tuple[AgentMode, float, dict[str, Any]]:
    """Compute the optimal agent mode via weighted multi-factor scoring.

    Scoring dimensions:
        keyword_score   — weighted trigger keywords (complexity/coordination/perspective)
        length_score    — task description length as complexity proxy
        file_scope_score — breadth of files touched in session
        failure_score   — recent failures + error repetition signals
        risk_score      — destructive action detection (+4 per danger match)
        ambiguity_score — fuzzy intent signals benefit from exploration
        simplicity_score — blocker words (subtracted, not hard stop)

    Thresholds:
        score >= 8  → SWARM
        score >= 5  → PLAN_EXECUTE
        score >= 3  → SINGLE_WITH_REVIEWER
        score <  3  → SINGLE

    Returns:
        (AgentMode, final_score, breakdown dict with per-dimension details)
    """
    ctx = session or {}

    kw, kw_matched = keyword_score(goal)
    ln = length_score(goal)
    fs = file_scope_score(ctx)
    ff = failure_score(ctx)
    rk, rk_matched = risk_score(goal)
    am, am_matched = ambiguity_score(goal)
    sp, sp_matched = simplicity_score(goal)
    dg, dg_matched = decomposability_score(goal)

    total = kw + ln + fs + ff + rk + am - sp + dg

    if total >= 8:
        mode = AgentMode.SWARM
    elif total >= 5:
        mode = AgentMode.PLAN_EXECUTE
    elif total >= 3:
        mode = AgentMode.SINGLE_WITH_REVIEWER
    else:
        mode = AgentMode.SINGLE

    breakdown: dict[str, Any] = {
        "keyword": {"score": kw, "matched": kw_matched},
        "length": {"score": ln, "chars": len(goal)},
        "file_scope": {
            "score": fs,
            "files_touched": ctx.get("files_touched", 0),
        },
        "failure": {
            "score": ff,
            "recent_failures": ctx.get("recent_failures", 0),
            "error_repeated": ctx.get("error_repeated", False),
        },
        "risk": {"score": rk, "matched": rk_matched},
        "ambiguity": {"score": am, "matched": am_matched},
        "simplicity": {"score": sp, "matched": sp_matched, "subtracted": True},
        "decomposability": {"score": dg, "matched": dg_matched},
        "total": round(total, 2),
        "mode": mode.value,
    }
    return mode, total, breakdown


# ─── Backward-compatible wrapper ───


def should_use_multi_agent(goal: str) -> tuple[bool, str]:
    """Backward-compatible wrapper — delegates to compute_agent_mode().

    Preserves the original (should_use: bool, reason: str) return type
    for existing callers.

    Mapping:
        SINGLE / SINGLE_WITH_REVIEWER → False (no multi-agent)
        PLAN_EXECUTE / SWARM           → True  (use multi-agent)
    """
    mode, score, _breakdown = compute_agent_mode(goal)
    should = mode in (AgentMode.PLAN_EXECUTE, AgentMode.SWARM)
    reason = f"AgentMode={mode.value} score={score:.1f}"
    return should, reason


# ─── Long-term learning ───

_agent_mode_history: list[AgentModeResult] = []


def record_agent_mode_result(result: AgentModeResult) -> None:
    """Record an agent mode execution result for long-term learning.

    Stored in-memory as _agent_mode_history. Over time, the distribution
    of success/failure per mode can inform threshold tuning.

    Args:
        result: An AgentModeResult with mode, task_type, success, latency,
                and optional user_correction.
    """
    _agent_mode_history.append(result)
    # Keep bounded — drop oldest 200 when exceeding 1000
    if len(_agent_mode_history) > 1000:
        del _agent_mode_history[:200]


def get_mode_statistics() -> dict[str, dict[str, Any]]:
    """Return success/failure statistics per AgentMode from recorded history.

    Returns:
        Dict keyed by mode value (e.g. "single", "swarm") with:
        total, success, failure, corrections, total_latency,
        success_rate, correction_rate, avg_latency.
        Empty dict if no history recorded.
    """
    if not _agent_mode_history:
        return {}

    stats: dict[str, dict[str, Any]] = {}
    for r in _agent_mode_history:
        key = r.mode.value
        if key not in stats:
            stats[key] = {
                "total": 0,
                "success": 0,
                "failure": 0,
                "corrections": 0,
                "total_latency": 0.0,
            }
        s = stats[key]
        s["total"] += 1
        if r.success:
            s["success"] += 1
        else:
            s["failure"] += 1
        if r.user_correction:
            s["corrections"] += 1
        s["total_latency"] += r.latency

    for s in stats.values():
        n = s["total"]
        s["success_rate"] = round(s["success"] / n, 3) if n > 0 else 0.0
        s["correction_rate"] = round(s["corrections"] / n, 3) if n > 0 else 0.0
        s["avg_latency"] = round(s["total_latency"] / n, 3) if n > 0 else 0.0

    return stats


