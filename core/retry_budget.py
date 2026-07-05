"""Retry Budget & Recovery Ledger — 自动恢复的账本和预算控制。"""

from typing import Any


# 全局预算：每个 root_trace_id 最多重试次数
DEFAULT_MAX_RETRIES = 3
DEFAULT_COOLDOWN_SEC = 30  # 重试冷却

# 每个 run 的重试账本
_retry_ledger: dict[str, list[dict]] = {}  # root_trace_id -> [{attempt, time, action, result}]


def get_retry_count(root_trace_id: str) -> int:
    """获取当前 run 已重试次数。"""
    return len(_retry_ledger.get(root_trace_id, []))


def can_retry(root_trace_id: str, max_retries: int = DEFAULT_MAX_RETRIES) -> bool:
    """是否还可以重试。"""
    count = get_retry_count(root_trace_id)
    return count < max_retries


def record_retry_attempt(root_trace_id: str, action: str, result: str) -> dict:
    """记录一次重试尝试。"""
    import time
    if root_trace_id not in _retry_ledger:
        _retry_ledger[root_trace_id] = []
    entry = {
        "attempt": len(_retry_ledger[root_trace_id]) + 1,
        "time": time.time(),
        "action": action,
        "result": result,
    }
    _retry_ledger[root_trace_id].append(entry)
    return entry


def get_retry_budget(root_trace_id: str, max_retries: int = DEFAULT_MAX_RETRIES) -> dict[str, Any]:
    """获取当前重试预算状态。"""
    used = get_retry_count(root_trace_id)
    remaining = max_retries - used
    return {
        "root_trace_id": root_trace_id,
        "max_retries": max_retries,
        "used": used,
        "remaining": remaining,
        "exhausted": remaining <= 0,
        "history": _retry_ledger.get(root_trace_id, []),
    }


def auto_retry_decision(summary: dict, max_retries: int = DEFAULT_MAX_RETRIES) -> dict:
    """基于预算和策略决定是否自动重试。

    Returns:
        {"should_retry": bool, "reason": str, "budget": dict}
    """
    root_id = summary.get("root_trace_id", "")
    from core.policy_gate import should_retry, should_escalate

    budget = get_retry_budget(root_id, max_retries)

    if not should_retry(summary):
        return {"should_retry": False, "reason": "质量评估不满足重试条件", "budget": budget}

    if budget["exhausted"]:
        return {"should_retry": False, "reason": f"重试预算耗尽 ({max_retries}次已用完)", "budget": budget}

    if should_escalate(summary):
        return {"should_retry": False, "reason": "需要人工介入，自动重试已停用", "budget": budget}

    return {"should_retry": True, "reason": f"允许重试 (剩余 {budget['remaining']} 次)", "budget": budget}


def reset_ledger(root_trace_id: str) -> None:
    """重置指定 run 的重试账本。"""
    _retry_ledger.pop(root_trace_id, None)
