"""Policy Gate — based on quality assessment, decide next action automatically."""

from typing import Any


def decide_action(summary: dict) -> str:
    """基于质量评估决定下一步动作。

    Actions:
        pass: 正常，无需任何操作
        retry: 部分失败，自动重试失败任务
        escalate: 严重失败，需要人工介入
        skip: 非关键失败，跳过继续
        fallback: 降级处理，切换到备选 provider
        circuit_break: 连续失败，触发熔断
    """
    quality = summary.get("quality_status", "unknown")
    flags = summary.get("quality_flags", [])
    failed = summary.get("tasks_failed", 0)
    total = summary.get("tasks_total", 0) or 1

    # 完全成功
    if quality == "success":
        return "pass"

    # 熔断触发
    if "excessive_fallback" in " ".join(flags) or any(f.startswith("excessive_fallback") for f in flags):
        return "circuit_break"

    # 死锁
    if "deadlock_detected" in flags:
        return "escalate"

    # 部分失败可重试
    fail_rate = failed / total
    if quality in ("partial_success", "timeout_degraded") and fail_rate <= 0.5:
        return "retry"

    # 高失败率不可自动恢复
    if fail_rate > 0.5:
        return "escalate"

    # 跳过
    if quality == "needs_review":
        return "escalate"

    return "pass"


def should_retry(summary: dict) -> bool:
    """是否应该重试失败任务。"""
    return decide_action(summary) == "retry"


def should_escalate(summary: dict) -> bool:
    """是否需要人工介入。"""
    return decide_action(summary) in ("escalate", "circuit_break")


def auto_recover(summary: dict) -> dict:
    """尝试基于质量评估自动恢复。

    Returns:
        {"action": str, "reason": str, "auto_retry": bool}
    """
    action = decide_action(summary)
    results = {
        "action": action,
        "auto_retry": action == "retry",
        "reason": "",
    }

    if action == "pass":
        results["reason"] = "执行正常，无需处理。"
    elif action == "retry":
        results["reason"] = (
            f"部分任务失败 ({summary.get('tasks_failed', 0)}/{summary.get('tasks_total', 0)})，自动重试。"
        )
    elif action == "escalate":
        results["reason"] = (
            f"严重失败 (fail_rate={summary.get('tasks_failed', 0) / max(summary.get('tasks_total', 1), 1):.0%})，需要人工介入。"
        )
    elif action == "circuit_break":
        results["reason"] = "fallback 次数过多，触发熔断。"
    elif action == "skip":
        results["reason"] = "非关键失败，跳过继续。"

    return results
