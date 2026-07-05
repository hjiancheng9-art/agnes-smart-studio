"""Run quality gate — 给每次执行一个质量评级。"""

from typing import Any


def assess_quality(summary: dict) -> dict:
    """对一次执行结果做质量评估。

    Returns:
        quality_status: success | partial_success | failed | needs_review | cost_exceeded | timeout_degraded
        quality_score: 0.0 ~ 1.0
        quality_flags: 问题标记列表
        recommendation: 建议
    """
    total = summary.get("tasks_total", 0) or 1
    done = summary.get("tasks_done", 0)
    failed = summary.get("tasks_failed", 0)
    skipped = summary.get("tasks_skipped", 0)
    timed_out = summary.get("tasks_timeout", 0)
    cancelled = summary.get("tasks_cancelled", 0)

    flags: list[str] = []
    score = 1.0

    # 失败率
    fail_rate = failed / total
    if fail_rate > 0.5:
        flags.append("high_failure_rate")
        score -= 0.4
    elif fail_rate > 0.2:
        flags.append("partial_failure")
        score -= 0.2

    # 超时
    if timed_out > 0:
        flags.append(f"timeout_{timed_out}")
        score -= 0.15 * min(timed_out, 3)

    # 跳过
    if skipped > 0:
        flags.append(f"skipped_{skipped}")
        score -= 0.1 * min(skipped, 3)

    # 取消
    if cancelled > 0:
        flags.append(f"cancelled_{cancelled}")
        score -= 0.1

    # 死锁
    events = summary.get("events", {})
    if events.get("deadlocks", 0) > 0:
        flags.append("deadlock_detected")
        score -= 0.3

    # fallback 过多
    fallbacks = events.get("fallbacks", 0)
    if fallbacks > 2:
        flags.append(f"excessive_fallback_{fallbacks}")
        score -= 0.1 * min(fallbacks, 5)

    score = max(0.0, min(1.0, score))

    # 判定状态
    if score >= 0.8 and done == total:
        status = "success"
    elif score >= 0.5 and done > 0:
        status = "partial_success"
    elif score <= 0.0 or failed == total:
        status = "failed"
    elif timed_out > 0 or cancelled > 0:
        status = "timeout_degraded"
    else:
        status = "needs_review"

    recommendation = _recommend(status, flags)
    return {
        "quality_status": status,
        "quality_score": round(score, 2),
        "quality_flags": flags,
        "recommendation": recommendation,
    }


def _recommend(status: str, flags: list[str]) -> str:
    if status == "success":
        return "执行正常，无需处理。"
    if status == "failed":
        return "执行完全失败，检查 provider 可用性和 task 配置。"
    if status == "partial_success":
        return "部分任务失败，审查失败原因后重试。"
    if status == "timeout_degraded":
        return "部分任务超时，考虑增大 timeout_seconds 或拆分任务。"
    if status == "needs_review":
        return "执行异常，建议人工审查。"
    return ""
