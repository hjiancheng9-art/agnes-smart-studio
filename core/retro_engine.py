"""复盘(Retro)引擎 — 项目复盘、经验沉淀、持续改进

方法论第9章: 结构化复盘流程、数据收集、模式识别、改进行动追踪。
每次项目/冲刺结束后自动生成复盘报告。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

RETRO_DIR = Path("output/retros")
RETRO_DIR.mkdir(parents=True, exist_ok=True)


def retro_create(
    project: str,
    sprint: str = "current",
    what_went_well: list[str] | None = None,
    what_could_improve: list[str] | None = None,
    action_items: list[dict] | None = None,
) -> dict:
    """Create a retrospective entry.

    action_items: [{"task": str, "owner": str, "deadline": str}]
    """
    retro = {
        "id": f"{project}_{sprint}_{datetime.now().strftime('%Y%m%d')}",
        "project": project,
        "sprint": sprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "what_went_well": what_went_well or [],
        "what_could_improve": what_could_improve or [],
        "action_items": action_items or [],
    }
    (RETRO_DIR / f"{retro['id']}.json").write_text(json.dumps(retro, indent=2, ensure_ascii=False), encoding="utf-8")
    return retro


def retro_list(project: str | None = None) -> list[dict]:
    """List retrospectives."""
    results = []
    for p in sorted(RETRO_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        if project and r.get("project") != project:
            continue
        results.append(r)
    return results


def retro_summarize(project: str) -> dict:
    """Summarize all retros for a project, identifying recurring patterns."""
    retros = retro_list(project)
    if not retros:
        return {"error": f"No retros found for {project}"}

    all_well = []
    all_improve = []
    all_actions = []

    for r in retros:
        all_well.extend(r.get("what_went_well", []))
        all_improve.extend(r.get("what_could_improve", []))
        all_actions.extend(r.get("action_items", []))

    # Simple pattern detection
    from collections import Counter

    well_patterns = Counter(all_well).most_common(5)
    improve_patterns = Counter(all_improve).most_common(5)

    return {
        "project": project,
        "total_retros": len(retros),
        "top_strengths": [p for p, _ in well_patterns],
        "top_improvements": [p for p, _ in improve_patterns],
        "open_actions": len([a for a in all_actions if "done" not in a.get("status", "")]),
        "summary": f"{len(retros)} retros analyzed, {len(all_well)} strengths, {len(all_improve)} improvements",
    }


RETRO_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "retro_create",
            "description": "Create a retrospective entry for a project/sprint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "sprint": {"type": "string", "description": "Sprint or milestone name"},
                    "what_went_well": {"type": "array", "items": {"type": "string"}},
                    "what_could_improve": {"type": "array", "items": {"type": "string"}},
                    "action_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                                "owner": {"type": "string"},
                                "deadline": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["project"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retro_list",
            "description": "List retrospectives, optionally filtered by project.",
            "parameters": {"type": "object", "properties": {"project": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retro_summarize",
            "description": "Analyze all retros for a project, detect recurring patterns.",
            "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "required": ["project"]},
        },
    },
]

RETRO_EXECUTOR_MAP = {
    "retro_create": lambda **kw: json.dumps(retro_create(**kw), ensure_ascii=False),
    "retro_list": lambda **kw: json.dumps(retro_list(**kw.get("project")), ensure_ascii=False),  # pyright: ignore[reportCallIssue]
    "retro_summarize": lambda **kw: json.dumps(retro_summarize(**kw.get("project", "")), ensure_ascii=False),
}
