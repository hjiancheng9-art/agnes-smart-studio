"""Incident Classifier — 将执行失败分类为稳定的故障类别。"""

from typing import Any


# 故障类别定义
FAILURE_TAXONOMY = {
    "provider_unavailable": {
        "keywords": ["NoProviderAvailable", "provider fallback", "create_client", "API key"],
        "severity": "high",
        "suggestion": "检查 provider API key 和网络连接",
    },

    "timeout": {
        "keywords": ["timeout", "timed out", "TimeoutError"],
        "severity": "medium",
        "suggestion": "增大 timeout 或拆分任务",
    },
    "rate_limit": {
        "keywords": ["rate limit", "429", "TooManyRequests", "quota"],
        "severity": "medium",
        "suggestion": "降低请求频率或升级套餐",
    },
    "auth_error": {
        "keywords": ["401", "403", "unauthorized", "forbidden", "auth"],
        "severity": "high",
        "suggestion": "检查 API key 权限和有效期",
    },
    "model_error": {
        "keywords": ["model not found", "model unavailable", "not supported"],
        "severity": "medium",
        "suggestion": "检查模型 ID 是否正确",
    },
    "circuit_breaker": {
        "keywords": ["circuit", "熔断", "OPEN"],
        "severity": "medium",
        "suggestion": "等待冷却或手动重置",
    },
    "dag_deadlock": {
        "keywords": ["deadlock", "DAG deadlock", "stuck"],
        "severity": "high",
        "suggestion": "检查任务依赖关系",
    },
    "internal_error": {
        "keywords": ["InternalServerError", "500", "502", "503"],
        "severity": "high",
        "suggestion": "尝试切换 provider 或等待恢复",
    },
}


def classify_failure(error_msg: str) -> dict:
    """将错误消息分类为故障类别。

    Returns:
        {"category": str, "severity": str, "suggestion": str, "confidence": float}
    """
    error_lower = error_msg.lower()
    for category, config in FAILURE_TAXONOMY.items():
        for kw in config["keywords"]:
            if kw.lower() in error_lower:
                return {
                    "category": category,
                    "severity": config["severity"],
                    "suggestion": config["suggestion"],
                    "confidence": 0.8,
                }
    return {
        "category": "unknown",
        "severity": "low",
        "suggestion": "未识别的错误类型，请人工审查",
        "confidence": 0.3,
    }


def classify_run(summary: dict, log: list[dict]) -> dict:
    """对一次完整 run 进行故障分类。"""
    # 收集所有错误消息
    errors = []
    for entry in log:
        if entry.get("event") in ("task_failed", "task_timeout", "dag_deadlock"):
            error = entry.get("error", "") or entry.get("deadlock", "") or str(entry)
            if error:
                errors.append(error)

    # 对每条错误分类
    classifications = [classify_failure(e) for e in errors]

    # 聚合统计
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    for c in classifications:
        categories[c["category"]] = categories.get(c["category"], 0) + 1
        severities[c["severity"]] = severities.get(c["severity"], 0) + 1

    # 找出主要故障类别
    primary = max(categories, key=categories.get) if categories else "none"

    # 生成摘要
    if not classifications:
        return {
            "primary_category": "none",
            "categories": {},
            "severities": {},
            "total_incidents": 0,
            "summary": "无故障事件",
            "recommendation": "",
        }

    # 找最严重类别的建议
    high_items = [c for c in classifications if c["severity"] == "high"]
    recommendation = high_items[0]["suggestion"] if high_items else classifications[0]["suggestion"]

    return {
        "primary_category": primary,
        "categories": categories,
        "severities": severities,
        "total_incidents": len(classifications),
        "summary": f"主要故障: {primary} (共{len(classifications)}次) high={severities.get('high', 0)} medium={severities.get('medium', 0)}",
        "recommendation": recommendation,
    }
