"""ADR (Architecture Decision Record) — 架构决策追踪

方法论第8章: 用 ADR 记录每次架构决策，配合 Mermaid 架构图可视化。
每次决策包含: 上下文、决策、后果、状态、关联。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parent.parent / "docs" / "adr"


def _ensure_adr_dir() -> None:
    """创建 ADR 目录（延迟到首次使用时，避免 import 时产生文件系统副作用）。"""
    ADR_DIR.mkdir(parents=True, exist_ok=True)


def adr_create(
    title: str,
    context: str,
    decision: str,
    consequences: str,
    status: str = "proposed",
    related: list[str] | None = None,
) -> dict:
    """Create an Architecture Decision Record.

    Status: proposed | accepted | deprecated | superseded
    """
    _ensure_adr_dir()
    # Find next number
    existing = list(ADR_DIR.glob("*.json"))
    num = len(existing) + 1

    adr = {
        "id": f"ADR-{num:04d}",
        "number": num,
        "title": title,
        "status": status,
        "context": context,
        "decision": decision,
        "consequences": consequences,
        "related": related or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (ADR_DIR / f"ADR-{num:04d}.json").write_text(
        json.dumps(adr, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    # Also generate markdown
    _adr_to_markdown(adr)
    return adr


def _adr_to_markdown(adr: dict):
    md = f"""# {adr["id"]}: {adr["title"]}

- **Status**: {adr["status"]}
- **Date**: {adr["created_at"][:10]}

## Context

{adr["context"]}

## Decision

{adr["decision"]}

## Consequences

{adr["consequences"]}
"""
    if adr.get("related"):
        md += "\n## Related\n\n"
        for r in adr["related"]:
            md += f"- {r}\n"

    (ADR_DIR / f"{adr['id']}.md").write_text(md, encoding="utf-8")


def adr_list(status: str | None = None) -> list[dict]:
    """List ADRs."""
    results = []
    for p in sorted(ADR_DIR.glob("ADR-*.json")):
        adr = json.loads(p.read_text(encoding="utf-8"))
        if status and adr.get("status") != status:
            continue
        results.append(adr)
    return results


def adr_update(
    adr_id: str, status: str | None = None, decision: str | None = None, consequences: str | None = None
) -> dict:
    """Update an ADR's status or content."""
    path = ADR_DIR / f"{adr_id}.json"
    if not path.exists():
        return {"error": f"{adr_id} not found"}

    adr = json.loads(path.read_text(encoding="utf-8"))
    if status:
        adr["status"] = status
    if decision:
        adr["decision"] = decision
    if consequences:
        adr["consequences"] = consequences
    adr["updated_at"] = datetime.now(timezone.utc).isoformat()

    path.write_text(json.dumps(adr, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    _adr_to_markdown(adr)
    return adr


def adr_mermaid() -> str:
    """Generate a Mermaid timeline diagram of all ADRs."""
    adrs = adr_list()
    if not adrs:
        return "No ADRs recorded."

    lines = [
        "gantt",
        "    title Architecture Decision Timeline",
        "    dateFormat  YYYY-MM-DD",
        "    axisFormat  %Y-%m-%d",
    ]
    for adr in adrs:
        date = adr.get("created_at", "")[:10]
        title = adr["title"].replace('"', "'")
        lines.append(f"    section {adr['status']}")
        lines.append(f"    {title} : {date}, 1d")

    return "\n".join(lines)


ADR_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "adr_create",
            "description": "Create an Architecture Decision Record (ADR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "context": {"type": "string", "description": "Why this decision was needed"},
                    "decision": {"type": "string", "description": "What was decided"},
                    "consequences": {"type": "string", "description": "Impact of this decision"},
                    "status": {"type": "string", "enum": ["proposed", "accepted", "deprecated", "superseded"]},
                    "related": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "context", "decision", "consequences"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adr_list",
            "description": "List all ADRs.",
            "parameters": {"type": "object", "properties": {"status": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adr_update",
            "description": "Update ADR status or content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "adr_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["proposed", "accepted", "deprecated", "superseded"]},
                    "decision": {"type": "string"},
                    "consequences": {"type": "string"},
                },
                "required": ["adr_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adr_mermaid",
            "description": "Generate Mermaid timeline diagram of all ADRs.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

ADR_EXECUTOR_MAP = {
    "adr_create": lambda **kw: json.dumps(adr_create(**kw), ensure_ascii=False),
    "adr_list": lambda **kw: json.dumps(adr_list(status=kw.get("status")), ensure_ascii=False),
    "adr_update": lambda **kw: json.dumps(adr_update(**kw), ensure_ascii=False),
    "adr_mermaid": lambda **kw: json.dumps(adr_mermaid(), ensure_ascii=False),
}
