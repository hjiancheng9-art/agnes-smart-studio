"""Orchestration tools: resource search, skill execution, project analysis.

These are invoked by the orchestrator to dynamically discover and execute
skills and tools during orchestration runs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to project root and tools registry
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_JSON = _PROJECT_ROOT / "tools.json"


def resource_search(query: str) -> dict[str, Any]:
    """Search all available resources (skills + tools) matching a query.

    Args:
        query: Natural language query to match against resource names/descriptions.

    Returns:
        Dict with 'skills' and 'tools' lists containing matching resources.
    """
    query_lower = query.lower()
    results: dict[str, list[dict[str, Any]]] = {"skills": [], "tools": []}

    # Search tools registry
    try:
        if _TOOLS_JSON.exists():
            data = json.loads(_TOOLS_JSON.read_text(encoding="utf-8"))
            for t in data.get("tools", []):
                name = t.get("name", "")
                desc = t.get("description", "")
                if query_lower in name.lower() or query_lower in desc.lower():
                    results["tools"].append(
                        {
                            "name": name,
                            "type": t.get("type", ""),
                            "description": desc,
                        }
                    )
    except Exception as exc:
        logger.warning("Failed to search tools: %s", exc)

    return results


def skill_execute(skill_name: str, **kwargs: Any) -> dict[str, Any]:
    """Execute a named skill with optional arguments.

    Args:
        skill_name: Name of the skill to execute.
        **kwargs: Additional arguments passed to the skill.

    Returns:
        Dict with 'ok', 'skill', and 'result' or 'error'.
    """
    # Stub: actual skill execution is handled by the SkillsManager at runtime.
    # This function exists so the tool registry can resolve the import path.
    return {
        "ok": False,
        "skill": skill_name,
        "error": f"Skill '{skill_name}' must be executed via SkillsManager (stub)",
    }


def project_analyze(path: str = ".") -> dict[str, Any]:
    """Analyze project structure at the given path.

    Args:
        path: Project directory path (default: current directory).

    Returns:
        Dict with 'files', 'directories', 'language' info.
    """
    target = Path(path).resolve()
    if not target.exists():
        return {"ok": False, "error": f"Path does not exist: {path}"}

    files = []
    dirs = []
    extensions: dict[str, int] = {}

    try:
        for entry in sorted(target.iterdir()):
            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue
            if entry.is_file():
                files.append(entry.name)
                ext = entry.suffix.lower()
                extensions[ext] = extensions.get(ext, 0) + 1
            elif entry.is_dir():
                dirs.append(entry.name)
    except PermissionError:
        return {"ok": False, "error": f"Permission denied: {path}"}

    # Detect primary language
    primary = max(extensions, key=extensions.get) if extensions else "unknown"

    return {
        "ok": True,
        "path": str(target),
        "files": len(files),
        "directories": len(dirs),
        "sample_files": files[:20],
        "sample_dirs": dirs[:20],
        "primary_language": primary.lstrip("."),
        "extensions": extensions,
    }
