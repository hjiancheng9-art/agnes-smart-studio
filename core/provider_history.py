"""Provider Failure History — 追踪 provider 历史表现，用于自适应路由。"""

import json
import os
import time
from collections import defaultdict
from typing import Any

from core.config import OUTPUT_DIR

# EMA 衰减因子：越靠近 1，历史权重越高
EMA_ALPHA = 0.3
# 最小样本数：低于此值时 adaptive_delta 限幅
MIN_SAMPLES_FOR_FULL_ADAPT = 5
# 冷启动 prior：无数据时默认 success_rate = 0.95
COLD_START_SUCCESS_RATE = 0.95


HISTORY_FILE = os.path.join(OUTPUT_DIR, "provider_history.jsonl")


def _load_history() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _append_history(entry: dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_call(provider: str, model: str, success: bool, latency_ms: float, error: str = "") -> None:
    """记录一次 provider 调用结果。"""
    _append_history(
        {
            "provider": provider,
            "model": model,
            "success": success,
            "latency_ms": latency_ms,
            "error": error,
            "timestamp": time.time(),
        }
    )


def _ema(values: list[float], alpha: float = EMA_ALPHA) -> float:
    """指数移动平均。"""
    if not values:
        return 0.0
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def get_provider_stats(provider: str, window_minutes: int = 60) -> dict[str, Any]:
    """获取 provider 在时间窗口内的统计（EMA 平滑）。"""
    now = time.time()
    cutoff = now - window_minutes * 60
    records = [r for r in _load_history() if r.get("provider") == provider and r.get("timestamp", 0) > cutoff]
    # 时间衰减权重：越近的记录权重越高
    for r in records:
        age = now - r.get("timestamp", now)
        r["_decay"] = max(0.1, 1.0 - age / (window_minutes * 60))
    total = len(records)
    if total == 0:
        return {
            "provider": provider,
            "calls": 0,
            "success_rate": COLD_START_SUCCESS_RATE,
            "avg_latency_ms": 0,
            "recent_error": "",
            "consecutive_failures": 0,
            "samples": 0,
        }

    successes = [r for r in records if r.get("success")]
    success_rate = (
        _ema([1.0] * len(successes) + [0.0] * (total - len(successes))) if total > 0 else COLD_START_SUCCESS_RATE
    )
    latencies = [r.get("latency_ms", 0) * r.get("_decay", 1.0) for r in records if r.get("latency_ms", 0) > 0]
    recent_errors = [r.get("error", "") for r in records[-5:] if not r.get("success") and r.get("error")]

    return {
        "provider": provider,
        "calls": total,
        "success_rate": round(success_rate, 3),
        "avg_latency_ms": round(_ema([r.get("latency_ms", 0) for r in records if r.get("latency_ms", 0) > 0]), 1)
        if any(r.get("latency_ms", 0) > 0 for r in records)
        else 0,
        "recent_error": recent_errors[-1] if recent_errors else "",
        "consecutive_failures": _count_consecutive_failures(records),
        "samples": total,
    }


def _count_consecutive_failures(records: list[dict]) -> int:
    """从最近的记录往前数连续失败次数。"""
    count = 0
    for r in reversed(records):
        if not r.get("success"):
            count += 1
        else:
            break
    return count


def get_all_stats(window_minutes: int = 60) -> dict[str, dict]:
    """获取所有 provider 的统计。"""
    providers: dict[str, list[dict]] = defaultdict(list)
    for r in _load_history():
        if r.get("timestamp", 0) > time.time() - window_minutes * 60:
            providers[r.get("provider", "unknown")].append(r)

    result = {}
    for pid, records in providers.items():
        result[pid] = get_provider_stats(pid, window_minutes)
    return result


def adapt_score(pid: str, base_score: float) -> float:
    """根据历史表现调整 provider 评分。"""
    stats = get_provider_stats(pid)
    if stats["calls"] == 0:
        return base_score  # 无历史数据，不调整

    adjustment = 0.0
    # 成功率调整
    if stats["success_rate"] < 0.8:
        adjustment -= (0.8 - stats["success_rate"]) * 30
    elif stats["success_rate"] > 0.95:
        adjustment += 5

    # 连续失败惩罚
    if stats["consecutive_failures"] >= 3:
        adjustment -= 40
    elif stats["consecutive_failures"] >= 2:
        adjustment -= 15

    # 延迟奖励/惩罚
    if stats["avg_latency_ms"] > 10000:  # >10s
        adjustment -= 10
    elif stats["avg_latency_ms"] > 0 and stats["avg_latency_ms"] < 2000:  # <2s
        adjustment += 5

    return base_score + adjustment
