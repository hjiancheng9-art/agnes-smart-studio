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
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "AgnetaSkillSystem",
    "CodexSkill",
    "SkillHeader",
    "ROOT",
    "SKILL_DIRS",
    "skill_inject",
    "skill_list",
    "skill_load",
]

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIRS = [ROOT / "skills_md", ROOT / "skills", ROOT / "output" / "custom_tools"]

SCHEMA_VERSION = "crux.zcode-dna.v1"


@dataclass
class SkillHeader:
    """ZCode Gene 1: SKILL.md frontmatter 的完整 Schema 定义。

    解析 skills 的 frontmatter 元数据，支持 YAML 和 Markdown 两种格式。
    遵循 ZCode Plugin identity pattern: <name>@<version>。
    """

    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    author: str | None = None
    schema_version: str = SCHEMA_VERSION
    raw_frontmatter: str = ""

    PLUGIN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

    @classmethod
    def parse(cls, content: str) -> "SkillHeader":
        """从 SKILL.md 全文解析 frontmatter 元数据。

        支持标准 YAML frontmatter (--- ... ---) 和 ## Metadata 节两种格式。
        """
        header = cls()
        header.raw_frontmatter = content[:500]

        # 尝试 YAML frontmatter: ---\nkey: value\n---
        yaml_match = re.match(r"^---\s*\n(.+?)\n---", content, re.DOTALL)
        if yaml_match:
            header._parse_yaml_block(yaml_match.group(1))
            return header

        # 尝试 ## Metadata 节（用 MULTILINE 使 ^ 匹配行首）
        meta_match = re.search(r"^## Metadata\s*\n(.+?)(?=\n## |\Z)", content, re.DOTALL | re.MULTILINE)
        if meta_match:
            header._parse_yaml_block(meta_match.group(1))

        # 从 H1 提取 name
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match and not header.name:
            header.name = h1_match.group(1).strip()

        # 从 ## Description 节提取 description
        desc_match = re.search(r"^## Description\s*\n(.+?)(?:\n## |\Z)", content, re.DOTALL)
        if desc_match and not header.description:
            header.description = desc_match.group(1).strip()[:200]

        return header

    def _parse_yaml_block(self, block: str) -> None:
        """解析 YAML 风格的键值对块。

        支持两种格式：
          key: value
          - key: value  (列表项格式)"""
        for raw_line in block.strip().split("\n"):
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            # 去掉列表项前缀 "- "
            if line.startswith("- "):
                line = line[2:]
            # 清理两端空格
            line = line.strip()
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            val = val.strip()
            if key == "name":
                self.name = val
            elif key == "version":
                self.version = val
            elif key == "description":
                self.description = val[:200]
            elif key == "tags":
                self.tags = [t.strip() for t in val.split(",") if t.strip()]
            elif key == "author":
                self.author = val

    def validate(self) -> tuple[bool, list[str]]:
        """Gene 3: Zod-style 边界校验。"""
        errors = []
        if not self.name:
            errors.append("name is required")
        elif not self.PLUGIN_NAME_RE.match(self.name):
            errors.append(f"name '{self.name}' must match {self.PLUGIN_NAME_RE.pattern}")
        if not self.version:
            errors.append("version is required")
        if self.schema_version != SCHEMA_VERSION:
            errors.append(f"schema_version must be {SCHEMA_VERSION}, got {self.schema_version}")
        return (len(errors) == 0, errors)

    def to_dict(self) -> dict:
        """序列化（用于事件负载 / 插件注册）。"""
        import dataclasses

        return dataclasses.asdict(self)


class CodexSkill:
    def __init__(self, path: Path) -> None:
        self.path = path
        raw = path.stem
        # 处理 .skill.md 和 .SKILL.md 两种后缀
        lower_stem = raw.lower()
        if lower_stem.endswith(".skill"):
            self.name = raw[:-6]
        else:
            self.name = raw
        self._content = ""
        self._sections: dict[str, str] = {}
        self._metadata: dict = {}  # target, models, etc.
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
        # Load provider-routing metadata (Agnes skill filtering)
        self._metadata = {
            "target": data.get("target", "general"),
            "models": data.get("models", ["*"]),
        }

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
        """Check if this skill is relevant to a task description.

        使用正则词边界 (\\b) 匹配，避免子串误命中：
        例如旧实现 `word in text` 会让单字 "a" 匹配到 "generation" 中的子串。
        """
        return self._match_score(task_hint) >= 1

    def _match_score(self, task_hint: str) -> int:
        """返回 task_hint 中命中技能文本的词数（词边界匹配）。"""
        self.load()
        import re

        text = f"{self.name} {' '.join(self._sections.values())}".lower()
        score = 0
        for word in task_hint.lower().split():
            if re.search(rf"\b{re.escape(word)}\b", text):
                score += 1
        return score


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

    def list_skills(self, target: str = "") -> list[dict]:
        """List discovered skills. Pass target='media'/'code'/'general' to filter."""
        self.discover()
        result = []
        for s in self.skills.values():
            skill_target = s._metadata.get("target", "general")
            if target and skill_target != target:
                continue
            result.append(
                {
                    "name": s.name,
                    "desc": s._sections.get("description", "")[:80],
                    "target": skill_target,
                    "models": s._metadata.get("models", ["*"]),
                }
            )
        return result

    def skills_for_active_provider(self, provider_id: str = "") -> list[dict]:
        """Return skills compatible with the active provider.

        Filtering rule: skill is loaded if its target matches the provider's
        runtime role, OR if skill.target='general' (works with any provider).

        provider_id: 'deepseek'|'crux'|'zhipu'. Empty = return all.
        """
        # Map provider to its primary target
        PROVIDER_TARGET = {
            "crux": "media",  # CRUX/Agnes = media generation
            "deepseek": "code",  # DeepSeek = engineering
            "zhipu": "general",  # Zhipu = free fallback, any skill
        }
        expected = PROVIDER_TARGET.get(provider_id, "")
        if not expected:
            return self.list_skills()

        return [s for s in self.list_skills() if s["target"] in ("general", expected)]

    def load_skill(self, name: str) -> str | None:
        self.discover()
        skill = self.skills.get(name)
        return skill.get_level2() if skill else None

    def classify_task(self, task_hint: str) -> str:
        """Classify task as creative, engineering, or mixed."""
        creative_keywords = [
            "image",
            "video",
            "picture",
            "photo",
            "draw",
            "paint",
            "art",
            "animation",
            "cinematic",
            "visual",
            "design",
            "poster",
            "logo",
            "character",
            "scene",
            "storyboard",
            "camera",
            "lighting",
            "portrait",
            "landscape",
            "illustration",
            "render",
            "3d",
            "comic",
            "manga",
            "anime",
            "novel",
            "fiction",
            "story",
            "script",
            "copywriting",
            "creative",
            "color",
            "style",
        ]
        engineering_keywords = [
            "code",
            "bug",
            "fix",
            "debug",
            "test",
            "refactor",
            "build",
            "deploy",
            "api",
            "database",
            "server",
            "config",
            "error",
            "log",
            "trace",
            "audit",
            "security",
            "performance",
            "memory",
            "async",
            "import",
            "module",
            "package",
            "dependency",
            "git",
            "commit",
            "merge",
            "review",
            "architecture",
            "design pattern",
            "refactor",
            "optimize",
            "profile",
            "benchmark",
            "shell",
            "bash",
            "command",
            "script",
            "automation",
            "pipeline",
            "ci",
            "cd",
            "docker",
            "container",
        ]
        text_lower = task_hint.lower()
        creative_score = sum(1 for kw in creative_keywords if kw in text_lower)
        eng_score = sum(1 for kw in engineering_keywords if kw in text_lower)

        if creative_score > eng_score * 2:
            return "creative"
        if eng_score > creative_score * 2:
            return "engineering"
        if creative_score > 0 and eng_score > 0:
            return "mixed"
        return "general"

    def inject_for_task(self, task_hint: str, max_skills: int = 4) -> str:
        """Find and inject relevant skills into system prompt. Auto-routes creative vs engineering."""
        self.discover()
        self.classify_task(task_hint)
        matched = []
        for name, skill in self.skills.items():
            score = skill._match_score(task_hint)
            if score >= 1:
                matched.append((name, score))
        matched.sort(key=lambda x: x[1], reverse=True)
        parts = []
        for name, _ in matched[:max_skills]:
            skill = self.skills[name]
            parts.append(skill.get_level1())
        if parts:
            return "\n\n## Loaded Skills (auto-matched to task)\n" + "\n\n---\n\n".join(parts)
        return ""


# ── ZCode Skill API 别名 ─────────────────────────────────────

_skill_system = AgnetaSkillSystem()


def skill_inject(task_hint: str, max_skills: int = 4) -> str:
    return _skill_system.inject_for_task(task_hint, max_skills)


def skill_load(name: str) -> str | None:
    return _skill_system.load_skill(name)


def skill_list() -> list[dict]:
    return _skill_system.list_skills()


# ZCode 兼容 API (Gene 4 Self-extending)
def listZCodeSkills() -> list[dict]:
    """ZCode 兼容：枚举所有可发现技能。"""
    return _skill_system.list_skills()


def inspectZCodeSkill(name: str) -> str | None:
    """ZCode 兼容：检查单个技能的完整内容。"""
    return _skill_system.load_skill(name)


def createSkillDiscovery(name: str, description: str, instructions: str) -> str:
    """ZCode 兼容：AI 在运行时创建新技能。

    将技能写入 skills_md/ 目录，下次自动被发现。
    返回技能文件路径。
    """
    import time

    safe_name = name.replace(" ", "-").replace("/", "_").lower()[:60]
    path = ROOT / "skills_md" / f"{safe_name}.SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"# {name}\n\n"
        f"## Description\n{description}\n\n"
        f"## Instructions\n{instructions}\n\n"
        f"## Metadata\n"
        f"- created_at: {time.time():.0f}\n"
        f"- zcode_generated: true\n"
    )
    path.write_text(content, encoding="utf-8")
    _skill_system.refresh()
    return str(path)
