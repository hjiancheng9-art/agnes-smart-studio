"""Incident Classifier — 将执行失败分类为稳定的故障类别。"""

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


"""Incident Playbook — 故障修复剧本，每条故障类别对应可执行的修复步骤。"""

# 故障修复剧本
PLAYBOOKS = {
    "provider_unavailable": {
        "title": "Provider 不可用",
        "severity": "high",
        "steps": [
            "检查 provider API key 是否有效：/provider",
            "检查网络连接是否正常",
            "尝试切换到备用 provider：/provider <name>",
            "如果持续失败，检查熔断状态：/providers",
        ],
        "auto_commands": ["/providers"],
        "suggested_commands": ["/provider crux", "/provider deepseek"],
    },
    "timeout": {
        "title": "任务超时",
        "severity": "medium",
        "steps": [
            "增大 timeout 设置或拆分任务",
            "检查 provider 响应是否正常",
            "考虑增加 max_workers 提高并行度",
        ],
        "auto_commands": ["increase_timeout:120"],
        "suggested_commands": ["/providers"],
    },
    "rate_limit": {
        "title": "频率限制 (Rate Limit)",
        "severity": "medium",
        "steps": [
            "降低请求频率，添加退避等待",
            "检查 API 配额是否用尽",
            "考虑升级套餐或切换 provider",
        ],
        "auto_commands": ["switch_provider:", "retry_with_backoff:"],
        "suggested_commands": ["/providers"],
    },
    "auth_error": {
        "title": "认证错误",
        "severity": "high",
        "steps": [
            "检查 API key 是否过期",
            "检查 API key 权限是否足够",
            "更新环境变量中的 API key",
            "重启后重试",
        ],
        "auto_commands": [],
        "suggested_commands": ["/provider"],
    },
    "dag_deadlock": {
        "title": "DAG 死锁",
        "severity": "high",
        "steps": [
            "检查任务依赖关系是否正确",
            "检查是否存在循环依赖",
            "检查是否有 task 引用了不存在的依赖",
            "查看 /replay <trace_id> 分析死锁原因",
        ],
        "auto_commands": ["/replay {trace_id}"],
        "suggested_commands": [],
    },
    "circuit_breaker": {
        "title": "熔断器触发",
        "severity": "medium",
        "steps": [
            "等待冷却时间后自动恢复",
            "查看 provider 状态：/providers",
            "如果急需恢复，手动重置熔断",
        ],
        "auto_commands": ["/providers"],
        "suggested_commands": [],
    },
    "internal_error": {
        "title": "服务端错误",
        "severity": "high",
        "steps": [
            "等待几秒后重试",
            "如果持续失败，切换 provider",
            "记录错误信息用于排查",
        ],
        "auto_commands": ["switch_provider:"],
        "suggested_commands": ["/providers"],
    },
    "model_error": {
        "title": "模型错误",
        "severity": "medium",
        "steps": [
            "检查模型 ID 是否正确",
            "确认模型在当前 provider 可用",
            "尝试切换到其他模型或 provider",
        ],
        "auto_commands": ["switch_provider:"],
        "suggested_commands": [],
    },
    "unknown": {
        "title": "未知错误",
        "severity": "low",
        "steps": [
            "收集错误日志",
            "查看 /replay <trace_id> 获取完整时间线",
            "如持续出现请联系开发团队",
        ],
        "auto_commands": ["/replay {trace_id}"],
        "suggested_commands": [],
    },
}


def get_playbook(category: str) -> dict:
    """获取指定故障类别的修复剧本。"""
    return PLAYBOOKS.get(category, PLAYBOOKS["unknown"])


def format_playbook(category: str, trace_id: str = "") -> str:
    """格式化为可读的修复指南。"""
    pb = get_playbook(category)
    lines = [
        f"故障: {pb['title']} (severity={pb['severity']})",
        "建议步骤:",
    ]
    for i, step in enumerate(pb["steps"], 1):
        formatted = step.replace("{trace_id}", trace_id)
        lines.append(f"  {i}. {formatted}")
    if pb.get("suggested_commands"):
        lines.append("可用命令:")
        for cmd in pb["suggested_commands"]:
            lines.append(f"  {cmd}")  # cmd already includes /
    return "\n".join(lines)


def auto_remediation(incident: dict, trace_id: str = "") -> list[str]:
    """基于故障分类自动生成修复命令列表。"""
    category = incident.get("primary_category", "unknown")
    pb = get_playbook(category)
    commands = []
    for cmd in pb.get("auto_commands", []):
        commands.append(cmd.replace("{trace_id}", trace_id))
    return commands


"""Incident Store — 持久化 + 趋势 + 告警门禁。"""

import json
import os
import time
from collections import Counter

from core.config import OUTPUT_DIR

INCIDENT_FILE = os.path.join(OUTPUT_DIR, "incidents.jsonl")
INCIDENT_DIR = os.path.join(OUTPUT_DIR, "incidents")
os.makedirs(INCIDENT_DIR, exist_ok=True)


def save_incident(incident: dict) -> str:
    """持久化一条故障记录。"""
    entry = {
        "timestamp": time.time(),
        "category": incident.get("primary_category", "unknown"),
        "severity": max(incident.get("severities", {}), key=incident.get("severities", {}).get)
        if incident.get("severities")
        else "low",
        "count": incident.get("total_incidents", 0),
        "recommendation": incident.get("recommendation", ""),
        "summary": incident.get("summary", ""),
    }
    with open(INCIDENT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return entry["category"]


def get_incident_trends(hours: int = 24) -> dict:
    """获取时间段内的故障趋势。"""
    cutoff = time.time() - hours * 3600
    if not os.path.exists(INCIDENT_FILE):
        return {"total": 0, "by_category": {}, "by_severity": {}, "trends": []}

    categories = Counter()
    severities = Counter()
    recent = []

    with open(INCIDENT_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("timestamp", 0) > cutoff:
                    categories[entry.get("category", "unknown")] += 1
                    severities[entry.get("severity", "low")] += 1
                    recent.append(entry)
            except (json.JSONDecodeError, KeyError):
                continue

    return {
        "total": sum(categories.values()),
        "by_category": dict(categories.most_common()),
        "by_severity": dict(severities),
        "trends": recent[-20:],
    }


def should_alert(incident: dict, threshold: int = 3) -> dict:
    """判断是否应该告警。连续同类故障超过阈值则告警。"""
    category = incident.get("primary_category", "unknown")
    if not os.path.exists(INCIDENT_FILE):
        return {"alert": False}

    cutoff = time.time() - 3600
    count = 0
    with open(INCIDENT_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("timestamp", 0) > cutoff and entry.get("category") == category:
                    count += 1
            except (json.JSONDecodeError, KeyError):
                continue

    return {
        "alert": count >= threshold,
        "category": category,
        "recent_count": count,
        "threshold": threshold,
        "reason": f"{category} 在 1 小时内出现 {count} 次 (阈值 {threshold})" if count >= threshold else "",
    }
