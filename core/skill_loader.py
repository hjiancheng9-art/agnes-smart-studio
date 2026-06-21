"""Codex-compatible skill loader -- progressive disclosure markdown skills.

Supports SKILL.md files with section-based progressive disclosure:
    # Skill Name
    ## Description
    ## Instructions
    ## References
    ## Tools

Auto-discovers skills from skills_md/ and existing skills/ directories.
Injects relevant skills into agent system prompt based on task context.
"""

import json
from pathlib import Path

__all__ = [
    'AgnetaSkillSystem', 'CodexSkill', 'ROOT', 'SKILL_DIRS', 'skill_inject', 'skill_list', 'skill_load',
]

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIRS = [ROOT / "skills_md", ROOT / "skills", ROOT / "output" / "custom_tools"]

class CodexSkill:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.stem.replace(".skill", "")
        self._content = ""
        self._sections: dict[str, str] = {}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        try:
            if self.path.suffix == ".json":
                self._load_json()
            else:
                self._load_md()
        except (OSError, ValueError, RuntimeError):
            self._sections = {"description": f"(failed to load {self.path.name})"}
        self._loaded = True

    def _load_json(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._sections = {
            "description": data.get("description", ""),
            "instructions": data.get("prompt", ""),
        }
        tools = data.get("tools", [])
        if tools:
            self._sections["tools"] = json.dumps(tools, ensure_ascii=False)

    def _load_md(self):
        content = self.path.read_text(encoding="utf-8")
        sections = {}
        current_section = "description"
        current_lines = []
        for line in content.split(chr(10)):
            if line.startswith("## "):
                if current_lines:
                    sections[current_section] = chr(10).join(current_lines).strip()
                current_section = line[3:].strip().lower().replace(" ", "_")
                current_lines = []
            elif line.startswith("# "):
                if current_lines:
                    sections[current_section] = chr(10).join(current_lines).strip()
                current_section = "description"
                current_lines = [line[2:].strip()]
            else:
                current_lines.append(line)
        if current_lines:
            sections[current_section] = chr(10).join(current_lines).strip()
        self._sections = sections

    def get_level1(self) -> str:
        """First-level disclosure: name + description only."""
        self.load()
        desc = self._sections.get("description", "")
        return f"## {self.name}\n{desc[:500]}"

    def get_level2(self) -> str:
        """Full disclosure: all sections."""
        self.load()
        parts = [f"# {self.name}"]
        for key, value in self._sections.items():
            parts.append(f"## {key.title()}")
            parts.append(value)
        return "\n\n".join(parts)

    def matches_context(self, task_hint: str) -> bool:
        """Check if this skill is relevant to a task description."""
        self.load()
        text = f"{self.name} {' '.join(self._sections.values())}"
        score = 0
        for word in task_hint.lower().split():
            if word in text.lower():
                score += 1
        return score >= 1

class AgnetaSkillSystem:
    """Full Codex-compatible skill management."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.skills: dict[str, CodexSkill] = {}
        self._discovered = False

    def discover(self):
        if self._discovered:
            return
        for skill_dir in SKILL_DIRS:
            if not skill_dir.exists():
                continue
            patterns = ["*.skill.md", "*.SKILL.md", "*.skill.json"]
            for pattern in patterns:
                for sf in sorted(skill_dir.glob(pattern)):
                    skill = CodexSkill(sf)
                    skill.load()
                    self.skills[skill.name] = skill
        self._discovered = True

    def refresh(self):
        self.skills.clear()
        self._discovered = False
        self.discover()

    def list_skills(self) -> list[dict]:
        self.discover()
        return [{"name": s.name, "desc": s._sections.get("description", "")[:80]}
                for s in self.skills.values()]

    def load_skill(self, name: str) -> str | None:
        self.discover()
        skill = self.skills.get(name)
        return skill.get_level2() if skill else None

    def classify_task(self, task_hint: str) -> str:
        """Classify task as creative, engineering, or mixed."""
        creative_keywords = [
            "image", "video", "picture", "photo", "draw", "paint", "art",
            "animation", "cinematic", "visual", "design", "poster", "logo",
            "character", "scene", "storyboard", "camera", "lighting",
            "portrait", "landscape", "illustration", "render", "3d",
            "comic", "manga", "anime", "novel", "fiction", "story",
            "script", "copywriting", "creative", "color", "style",
        ]
        engineering_keywords = [
            "code", "bug", "fix", "debug", "test", "refactor", "build",
            "deploy", "api", "database", "server", "config", "error",
            "log", "trace", "audit", "security", "performance", "memory",
            "async", "import", "module", "package", "dependency", "git",
            "commit", "merge", "review", "architecture", "design pattern",
            "refactor", "optimize", "profile", "benchmark",
            "shell", "bash", "command", "script", "automation",
            "pipeline", "ci", "cd", "docker", "container",
        ]
        text_lower = task_hint.lower()
        creative_score = sum(1 for kw in creative_keywords if kw in text_lower)
        eng_score = sum(1 for kw in engineering_keywords if kw in text_lower)
        
        if creative_score > eng_score * 2:
            return "creative"
        elif eng_score > creative_score * 2:
            return "engineering"
        elif creative_score > 0 and eng_score > 0:
            return "mixed"
        else:
            return "general"

    def inject_for_task(self, task_hint: str, max_skills: int = 4) -> str:
        """Find and inject relevant skills into system prompt. Auto-routes creative vs engineering."""
        self.discover()
        self.classify_task(task_hint)
        matched = []
        for name, skill in self.skills.items():
            if skill.matches_context(task_hint):
                matched.append((name, sum(
                    1 for w in task_hint.lower().split()
                    if w in (name + " " + " ".join(skill._sections.values())).lower()
                )))
        matched.sort(key=lambda x: x[1], reverse=True)
        parts = []
        for name, _ in matched[:max_skills]:
            skill = self.skills[name]
            parts.append(skill.get_level1())
        if parts:
            return (
                "\n\n## Loaded Skills (auto-matched to task)\n"
                + "\n\n---\n\n".join(parts)
            )
        return ""

_skill_system = AgnetaSkillSystem()

def skill_inject(task_hint: str, max_skills: int = 4) -> str:
    return _skill_system.inject_for_task(task_hint, max_skills)

def skill_load(name: str) -> str | None:
    return _skill_system.load_skill(name)

def skill_list() -> list[dict]:
    return _skill_system.list_skills()