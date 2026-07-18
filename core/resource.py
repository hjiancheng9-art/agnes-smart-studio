"""Unified Resource model — tools, skills, prompts, knowledge as first-class types.

Inspired by Coze Studio's orthogonal resource design:
    models · workflows · plugins · knowledge · prompts → resources

For CRUX, resources are:
    SkillResource     — LLM prompt template (from skills/ .skill.json)
    ToolResource      — executable tool (from tools.json / MCP bridges)
    PromptResource    — reusable prompt template (from prompts/)
    KnowledgeResource — document / dataset for RAG (from knowledge/)

Usage:
    from core.resource import ResourceRegistry
    reg = ResourceRegistry()
    reg.load_all()
    results = reg.search("code review")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.resource")

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Resource:
    """Base resource type."""
    name: str
    kind: str  # skill | tool | prompt | knowledge
    description: str = ""
    source: str = "local"  # local | mcp | community
    installed: bool = True
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class ToolResource(Resource):
    kind: str = "tool"
    function: str = ""  # import path
    parameters: dict = field(default_factory=dict)
    category: str = "general"
    timeout: int = 30


@dataclass
class PromptResource(Resource):
    kind: str = "prompt"
    text: str = ""
    target_model: str = ""  # e.g. "deepseek-v4-pro"


class ResourceRegistry:
    """Unified discovery layer for all resource types."""

    def __init__(self):
        self._resources: dict[str, list[Resource]] = {}
        self._loaded = False

    def load_all(self) -> int:
        """Load all resources from disk. Returns total count."""
        count = 0
        count += self._load_skills()
        count += self._load_tools()
        count += self._load_prompts()
        self._loaded = True
        return count

    def _load_skills(self) -> int:
        skills = []
        skills_dir = ROOT / "skills"
        if skills_dir.is_dir():
            for f in sorted(skills_dir.glob("*.skill.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    s = Resource(
                        name=data.get("name", f.stem.replace(".skill", "")),
                        kind="skill",
                        description=data.get("description", "")[:200],
                        source="local",
                        version=data.get("version", "1.0.0"),
                        author=data.get("author", ""),
                        tags=data.get("tags", []),
                    )
                    skills.append(s)
                except (json.JSONDecodeError, OSError):
                    pass
        # Markdown skills
        md_dir = ROOT / "skills_md"
        if md_dir.is_dir():
            for f in sorted(md_dir.glob("*.skill.md")):
                skills.append(Resource(
                    name=f.stem.replace(".skill", ""),
                    kind="skill",
                    description=f.stem.replace("-", " ").title(),
                    source="local",
                ))
        self._resources["skill"] = skills
        logger.debug("Loaded %d skill resources", len(skills))
        return len(skills)

    def _load_tools(self) -> int:
        tools = []
        tools_file = ROOT / "tools.json"
        if tools_file.is_file():
            try:
                data = json.loads(tools_file.read_text(encoding="utf-8"))
                tool_list = data.get("tools", data) if isinstance(data, dict) else data
                for t in tool_list:
                    if isinstance(t, dict) and t.get("name"):
                        tools.append(ToolResource(
                            name=t["name"],
                            kind="tool",
                            description=t.get("description", "")[:200],
                            function=t.get("function", ""),
                            parameters=t.get("parameters", {}),
                            category=t.get("category", "general"),
                            timeout=t.get("timeout", 30),
                        ))
            except (json.JSONDecodeError, OSError):
                pass
        self._resources["tool"] = tools
        logger.debug("Loaded %d tool resources", len(tools))
        return len(tools)

    def _load_prompts(self) -> int:
        prompts = []
        prompts_dir = ROOT / "prompts"
        if prompts_dir.is_dir():
            for f in sorted(prompts_dir.glob("*.txt")):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    prompts.append(PromptResource(
                        name=f.stem,
                        kind="prompt",
                        description=f"Prompt template: {f.stem}",
                        text=text,
                    ))
                except OSError:
                    pass
        self._resources["prompt"] = prompts
        logger.debug("Loaded %d prompt resources", len(prompts))
        return len(prompts)

    def search(self, query: str, kind: str | None = None) -> list[Resource]:
        """Search across all resources (or filter by kind)."""
        if not self._loaded:
            self.load_all()
        results = []
        kinds = [kind] if kind else ["skill", "tool", "prompt"]
        for k in kinds:
            for r in self._resources.get(k, []):
                text = f"{r.name} {r.description} {' '.join(r.tags)}".lower()
                if any(term in text for term in query.lower().split()):
                    results.append(r)
        return results

    def list_by_kind(self, kind: str) -> list[Resource]:
        if not self._loaded:
            self.load_all()
        return self._resources.get(kind, [])

    @property
    def total_count(self) -> int:
        if not self._loaded:
            self.load_all()
        return sum(len(v) for v in self._resources.values())

    def summary(self) -> str:
        if not self._loaded:
            self.load_all()
        parts = ["## CRUX Resources"]
        for kind in ("skill", "tool", "prompt"):
            count = len(self._resources.get(kind, []))
            parts.append(f"- {kind}s: {count}")
        parts.append(f"- total: {self.total_count}")
        return "\n".join(parts)


# ── Singleton ──────────────────────────────────────────

_registry: ResourceRegistry | None = None


def get_registry() -> ResourceRegistry:
    global _registry
    if _registry is None:
        _registry = ResourceRegistry()
        _registry.load_all()
    return _registry
