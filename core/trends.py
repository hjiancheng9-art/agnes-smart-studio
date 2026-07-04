"""Historical trends analysis — reads JSONL data to compute metrics over time."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "output"


def _read_jsonl(filename: str, limit: int = 1000) -> list[dict]:
    path = OUTPUT / filename
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    records.append(json.loads(line))
            if len(records) >= limit:
                break
    return records


def cost_trends(days: int = 7) -> dict:
    """Cost trends: daily spending by model."""
    try:
        path = OUTPUT / "cost_state.json"
        if not path.exists():
            return {"error": "no cost data"}
        state = json.loads(path.read_text(encoding="utf-8"))
        by_day = state.get("by_day", {})
        by_model = state.get("by_model", {})
        return {
            "total_cost": state.get("total_cost", 0),
            "total_calls": state.get("total_calls", 0),
            "days": dict(sorted(by_day.items())[-days:]),
            "top_models": sorted(by_model.items(), key=lambda x: -x[1].get("cost", 0))[:5],
        }
    except Exception as e:
        return {"error": str(e)}


def tool_health_trends() -> dict:
    """Tool health: success rate, latency, call volume from tool_calls.jsonl."""
    records = _read_jsonl("tool_calls.jsonl", 500)
    if not records:
        return {"error": "no tool call data"}

    by_tool: dict[str, dict] = {}
    for r in records:
        name = r.get("tool", "unknown")
        if name not in by_tool:
            by_tool[name] = {"calls": 0, "success": 0, "total_ms": 0, "max_ms": 0}
        stats = by_tool[name]
        stats["calls"] += 1
        if r.get("status") == "ok":
            stats["success"] += 1
        dur = r.get("duration_ms", 0)
        stats["total_ms"] += dur
        stats["max_ms"] = max(stats["max_ms"], dur)

    result = {}
    for name, stats in sorted(by_tool.items(), key=lambda x: -x[1]["calls"]):
        calls = stats["calls"]
        result[name] = {
            "calls": calls,
            "success_rate": f"{stats['success']/calls*100:.0f}%" if calls else "0%",
            "avg_ms": f"{stats['total_ms']/calls:.0f}" if calls else "0",
            "max_ms": stats["max_ms"],
        }
    return result


def quality_trends() -> dict:
    """Quality score snapshot from tool_scorecard.json."""
    path = OUTPUT / "tool_scorecard.json"
    if not path.exists():
        return {"error": "no scorecard data"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "total_tools": data.get("total_tools", 0),
            "average_score": data.get("average_score", 0),
            "grade_distribution": data.get("grade_distribution", {}),
            "untested_tools": data.get("untested_tools", 0),
        }
    except Exception as e:
        return {"error": str(e)}
