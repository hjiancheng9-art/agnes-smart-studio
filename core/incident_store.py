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
