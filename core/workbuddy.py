"""WorkBuddy 办公Agent — 业务到代码闭环

方法论第19章: 市场调研 → 数据分析 → 报告生成 → 代码实现 一体化工作流。
将业务需求直接转化为可执行的任务链。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path("output/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES_DIR = Path("output/report_templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 报告生成 ──


def report_create(title: str, sections: list[dict], tags: list[str] | None = None) -> dict:
    """Create a structured report with sections.

    Each section: {"heading": str, "content": str, "type": "text|table|code|chart"}
    """
    report = {
        "id": title.lower().replace(" ", "_")[:40],
        "title": title,
        "created_at": _now(),
        "updated_at": _now(),
        "sections": sections,
        "tags": tags or [],
        "word_count": sum(len(s.get("content", "")) for s in sections),
    }
    path = REPORTS_DIR / f"{report['id']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def report_list(tag: str | None = None) -> list[dict]:
    """List all reports."""
    result = []
    for p in sorted(REPORTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        if tag and tag not in r.get("tags", []):
            continue
        result.append(r)
    return result


def report_export(report_id: str, fmt: str = "markdown") -> dict:
    """Export a report as markdown or html."""
    path = REPORTS_DIR / f"{report_id}.json"
    if not path.exists():
        return {"error": f"Report {report_id} not found"}

    report = json.loads(path.read_text(encoding="utf-8"))

    if fmt == "markdown":
        lines = [f"# {report['title']}\n"]
        for sec in report.get("sections", []):
            lines.append(f"\n## {sec['heading']}\n")
            if sec.get("type") == "code" or sec.get("type") == "table":
                lines.append(f"```\n{sec['content']}\n```\n")
            else:
                lines.append(f"{sec['content']}\n")
        content = "\n".join(lines)
        out_path = REPORTS_DIR / f"{report_id}.md"
        out_path.write_text(content, encoding="utf-8")
        return {"status": "ok", "path": str(out_path), "format": "markdown", "length": len(content)}

    if fmt == "html":
        html_parts = [f"<h1>{report['title']}</h1>"]
        for sec in report.get("sections", []):
            html_parts.append(f"<h2>{sec['heading']}</h2>")
            if sec.get("type") == "code":
                html_parts.append(f"<pre><code>{sec['content']}</code></pre>")
            else:
                html_parts.append(f"<p>{sec['content']}</p>")
        content = f"<html><body>{''.join(html_parts)}</body></html>"
        out_path = REPORTS_DIR / f"{report_id}.html"
        out_path.write_text(content, encoding="utf-8")
        return {"status": "ok", "path": str(out_path), "format": "html", "length": len(content)}

    return {"error": f"Unsupported format: {fmt}"}


# ── 模板管理 ──


def template_create(name: str, structure: list[dict]) -> dict:
    """Create a reusable report template.

    structure: [{"heading": str, "type": "text|table|code", "description": str}]
    """
    template = {
        "name": name,
        "created_at": _now(),
        "structure": structure,
    }
    (TEMPLATES_DIR / f"{name}.json").write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return template


def template_list() -> list[dict]:
    """List available templates."""
    result = []
    for p in TEMPLATES_DIR.glob("*.json"):
        result.append(json.loads(p.read_text(encoding="utf-8")))
    return result


def template_apply(name: str, data: dict) -> dict:
    """Apply a template with data to create a report."""
    t_path = TEMPLATES_DIR / f"{name}.json"
    if not t_path.exists():
        return {"error": f"Template {name} not found"}
    template = json.loads(t_path.read_text(encoding="utf-8"))

    sections = []
    for sec in template.get("structure", []):
        heading = sec["heading"]
        content = data.get(heading, f"({sec.get('description', '')})")
        sections.append({"heading": heading, "content": content, "type": sec.get("type", "text")})

    return report_create(f"Report: {name}", sections, tags=[name])


# ── 业务到代码管道 ──


def pipeline_run(requirement: str, steps: list[dict]) -> dict:
    """Run a business-to-code pipeline.

    steps: [{"phase": "research|analyze|report|code", "prompt": str}]
    Returns a plan with phases ready for execution.
    """
    return {
        "id": f"pipeline_{len(os.listdir(REPORTS_DIR))}",
        "requirement": requirement,
        "steps": steps,
        "created_at": _now(),
        "status": "planned",
    }


# ── Tool Definitions ──

WORKBUDDY_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "report_create",
            "description": "Create a structured report with sections. Sections can be text, code, table, or chart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "content": {"type": "string"},
                                "type": {"type": "string", "enum": ["text", "table", "code", "chart"]},
                            },
                            "required": ["heading", "content"],
                        },
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_export",
            "description": "Export a report as markdown or HTML.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                    "format": {"type": "string", "enum": ["markdown", "html"]},
                },
                "required": ["report_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_list",
            "description": "List all reports, optionally filtered by tag.",
            "parameters": {"type": "object", "properties": {"tag": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "template_create",
            "description": "Create a reusable report template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "structure": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "type": {"type": "string", "enum": ["text", "table", "code"]},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["name", "structure"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pipeline_run",
            "description": "Define a business-to-code pipeline: research → analyze → report → code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirement": {"type": "string", "description": "Business requirement"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "phase": {"type": "string", "enum": ["research", "analyze", "report", "code"]},
                                "prompt": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["requirement", "steps"],
            },
        },
    },
]

WORKBUDDY_EXECUTOR_MAP = {
    "report_create": lambda **kw: json.dumps(report_create(**kw), ensure_ascii=False),
    "report_list": lambda **kw: json.dumps(report_list(tag=kw.get("tag")), ensure_ascii=False),
    "report_export": lambda **kw: json.dumps(report_export(**kw), ensure_ascii=False),
    "template_create": lambda **kw: json.dumps(template_create(**kw), ensure_ascii=False),
    "pipeline_run": lambda **kw: json.dumps(pipeline_run(**kw), ensure_ascii=False),
}
