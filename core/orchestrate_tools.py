"""Orchestration tools — search, execute, analyze.  Registered as CRUX tools.

Usage (from LLM tool-calling):
    resource_search("code review")      → list matching skills + tools
    skill_execute("code-review", "review this file")  → run a skill
    project_analyze()                   → suggest skills for current project
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("crux.orchestrate_tools")


def resource_search(query: str) -> str:
    """Search all registered resources (skills + tools) for a query."""
    try:
        from core.resource import get_registry

        reg = get_registry()
        results = reg.search(query)
        if not results:
            return json.dumps({"query": query, "results": [], "hint": "Try broader terms or install more skills"})
        items = []
        for r in results[:10]:
            items.append({"name": r.name, "kind": r.kind, "description": r.description[:120], "source": r.source})
        return json.dumps({"query": query, "count": len(results), "results": items}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def skill_execute(skill_name: str, goal: str) -> str:
    """Execute a named skill against a specific goal."""
    try:
        from core.skill_orchestrator import get_orchestrator

        orch = get_orchestrator()
        orch._last_goal = goal
        ok, output = orch._run_skill(skill_name)
        return json.dumps({"skill": skill_name, "ok": ok, "output": output[:2000]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def project_analyze() -> str:
    """Analyze current project and suggest relevant skills."""
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        # Detect project type from markers
        markers = []
        if (root / "pyproject.toml").exists():
            markers.append("Python")
        if (root / "package.json").exists():
            markers.append("Node.js")
        if (root / "go.mod").exists():
            markers.append("Go")
        if (root / "Cargo.toml").exists():
            markers.append("Rust")
        # Find matching skills
        suggestions = []
        for marker in markers:
            try:
                from core.skill_orchestrator import get_orchestrator

                orch = get_orchestrator()
                matches = orch.search(f"{marker} development", top_k=3)
                for m in matches:
                    suggestions.append(
                        {"for": marker, "skill": m.name, "score": round(m.score, 3), "desc": m.description[:80]}
                    )
            except Exception:
                import logging

                logging.getLogger("crux").debug("silent except", exc_info=True)
        return json.dumps(
            {"detected": markers, "suggestions": suggestions, "hint": "Use skill_execute to run a suggested skill"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool definitions (OpenAI function-calling format) ──

ORCHESTRATE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "resource_search",
            "description": "Search all available resources (skills + tools) matching a query. Use before picking a skill to execute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query, e.g. 'code review' or 'fix flaky tests'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_execute",
            "description": "Execute a named skill against a goal. Use resource_search first to find the right skill name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Exact skill name, e.g. 'code-review'"},
                    "goal": {"type": "string", "description": "What to do, e.g. 'review tests/test_chat.py for bugs'"},
                },
                "required": ["skill_name", "goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_analyze",
            "description": "Analyze the current project structure and suggest relevant skills. Call this first when entering a new project.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]
