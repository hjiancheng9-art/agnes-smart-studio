# core/skill_compiler.py
"""Phase 5: Skill Compiler + Prompt Compiler — the final intelligence layer.

Two systems:

1. **SkillCompiler** — pre-processes skill JSON files:
   - Validates schema, target, models
   - Compiles prompts into optimized/compressed fragments
   - Builds dependency/conflict graph
   - Caches compiled output

2. **PromptCompiler** — dynamically assembles system prompt:
   - Task-type matching (media, code, general)
   - Token budget-aware assembly
   - Priority ordering (always_load → task-matched → general)
   - Deduplication of overlapping instructions
   - Section tagging for context injection

Builds on top of existing SkillManager (core/skills.py) and chat_prompt.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# Compiled Skill Model
# ═══════════════════════════════════════════════════════════════════


class TaskTarget(str, Enum):
    MEDIA = "media"
    CODE = "code"
    GENERAL = "general"
    SECURITY = "security"
    RESEARCH = "research"
    UNKNOWN = "unknown"


# Target grouping: some skills match multiple targets
_TARGET_ALIASES = {
    "media": {"media", "image", "video", "3d", "audio"},
    "code": {"code", "programming", "development", "backend", "frontend"},
    "security": {"security", "pentest", "audit"},
    "research": {"research", "analysis", "review"},
}


@dataclass
class CompiledSkill:
    """A pre-processed, compiled skill ready for prompt injection."""

    name: str
    description: str
    prompt: str
    prompt_tokens: int = 0
    target: TaskTarget = TaskTarget.UNKNOWN
    always_load: bool = False
    models: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    priority: int = 5  # 0-10, higher = loaded earlier
    file_path: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class CompiledSkillSet:
    """A set of compiled skills, ready for injection."""

    skills: dict[str, CompiledSkill] = field(default_factory=dict)

    @property
    def all_prompts(self) -> list[str]:
        return [s.prompt for s in self.skills.values() if s.prompt]

    @property
    def total_tokens(self) -> int:
        return sum(s.prompt_tokens for s in self.skills.values())

    def by_target(self, target: TaskTarget) -> list[CompiledSkill]:
        return [
            s for s in self.skills.values() if s.target == target or target in _TARGET_ALIASES.get(s.target.value, [])
        ]

    def always_load(self) -> list[CompiledSkill]:
        return sorted(
            [s for s in self.skills.values() if s.always_load],
            key=lambda x: -x.priority,
        )

    def get(self, name: str) -> CompiledSkill | None:
        return self.skills.get(name)


# ═══════════════════════════════════════════════════════════════════
# Skill Compiler
# ═══════════════════════════════════════════════════════════════════


def _normalize_prompt(prompt) -> str:
    """Flatten a skill 'prompt' field into a plain string.

    Skills may declare 'prompt' as:
      - a plain string
      - a list of strings
      - a list of blocks like {"type": "text", "content": "..."}
      - a dict with a 'content'/'text' field
    Anything else is best-effort stringified. Never raises.
    """
    if prompt is None:
        return ""
    if isinstance(prompt, str):
        return prompt

    def _block_to_str(block) -> str:
        if isinstance(block, str):
            return block
        if isinstance(block, dict):
            return str(block.get("content") or block.get("text") or "")
        return str(block)

    if isinstance(prompt, list):
        return "\n\n".join(_block_to_str(b) for b in prompt if b is not None)
    if isinstance(prompt, dict):
        return _block_to_str(prompt)
    return str(prompt)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1 token per 4 chars for English, ~1.5 for Chinese."""
    # Count CJK characters
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    ascii_chars = len(text) - cjk
    return ascii_chars // 4 + cjk // 2 + 1


def _detect_target(target_str: str) -> TaskTarget:
    """Map a target string to a TaskTarget enum."""
    target_lower = target_str.lower().strip()
    for enum_target, aliases in _TARGET_ALIASES.items():
        if target_lower == enum_target or target_lower in aliases:
            return TaskTarget(enum_target)
    return TaskTarget.UNKNOWN


# Known conflict pairs — skills that shouldn't load together
_KNOWN_CONFLICTS: dict[str, list[str]] = {
    "codex-core": ["agnes-constitution-core"],
    "agnes-constitution-core": ["codex-core"],
}


class SkillCompiler:
    """Pre-processes skill JSON files: validate, compile, build graph, cache.

    Usage:
        compiler = SkillCompiler(skills_dir="skills")
        compiled = compiler.compile_all()  # all skills
        compiler.validate()                # check for conflicts
        compiler.report()                  # print summary
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.known_conflicts = dict(_KNOWN_CONFLICTS)

    def compile_all(self) -> CompiledSkillSet:
        """Compile all skill JSON files in the skills directory."""
        skill_set = CompiledSkillSet()

        if not self.skills_dir.exists():
            logger.warning(f"Skills dir not found: {self.skills_dir}")
            return skill_set

        for f in sorted(self.skills_dir.iterdir()):
            if f.suffix == ".json":
                cs = self._compile_one(f)
                if cs.is_valid:
                    skill_set.skills[cs.name] = cs
                else:
                    for err in cs.errors:
                        logger.warning(f"Skill {cs.name}: {err}")

        # Build conflict/dep graph after all compiled
        self._build_graph(skill_set)

        return skill_set

    def _compile_one(self, file_path: Path) -> CompiledSkill:
        """Compile a single skill JSON file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return CompiledSkill(
                name=file_path.stem,
                description="",
                prompt="",
                errors=[f"Failed to parse: {e}"],
                file_path=str(file_path),
            )

        name = data.get("name", file_path.stem)
        description = data.get("description", "")
        prompt_text = _normalize_prompt(data.get("prompt", ""))
        target_str = data.get("target", "general")
        always_load = data.get("always_load", False)
        models = data.get("models", [])

        warnings: list[str] = []
        errors: list[str] = []

        # Validate target
        target = _detect_target(target_str)
        if target == TaskTarget.UNKNOWN:
            warnings.append(f"Unknown target '{target_str}', treating as general")

        # Validate models field
        if not isinstance(models, list):
            warnings.append("'models' field should be a list")

        # Estimate tokens
        tokens = _estimate_tokens(prompt_text)

        # Extract keywords from name + description
        keywords = re.findall(r"[a-zA-Z_]\w+", name + " " + description[:200])

        # Compress prompt: remove excess whitespace
        compressed = self._compress_prompt(prompt_text)

        return CompiledSkill(
            name=name,
            description=description,
            prompt=compressed,
            prompt_tokens=tokens,
            target=target,
            always_load=always_load,
            models=models if isinstance(models, list) else [],
            keywords=keywords[:10],
            file_path=str(file_path),
            warnings=warnings,
            errors=errors,
        )

    def _compress_prompt(self, prompt: str) -> str:
        """Compress a prompt: strip excess whitespace, normalize line breaks."""
        # Strip leading/trailing whitespace per line
        lines = [l.strip() for l in prompt.split("\n")]
        # Remove consecutive blank lines (max 1)
        result = []
        blank_count = 0
        for l in lines:
            if not l:
                blank_count += 1
                if blank_count <= 1:
                    result.append("")
            else:
                blank_count = 0
                result.append(l)
        return "\n".join(result).strip()

    def _build_graph(self, skill_set: CompiledSkillSet):
        """Build conflict and dependency graph."""
        # Conflicts
        for name, cs in skill_set.skills.items():
            cs.conflicts_with = self.known_conflicts.get(name, [])

        # Deps: if skill A mentions skill B by name in description
        for name, cs in skill_set.skills.items():
            deps = []
            for other_name in skill_set.skills:
                if other_name != name and other_name in cs.description:
                    deps.append(other_name)
            cs.depends_on = deps

    def validate(self, skill_set: CompiledSkillSet) -> list[str]:
        """Validate the full skill set for issues."""
        issues: list[str] = []

        # Check conflicts
        for name, cs in skill_set.skills.items():
            for conflict_name in cs.conflicts_with:
                if conflict_name in skill_set.skills:
                    other = skill_set.skills[conflict_name]
                    if cs.always_load and other.always_load:
                        issues.append(f"CONFLICT: '{name}' and '{conflict_name}' are both always_load and conflict!")

        # Check long prompts — tiered to avoid noise:
        #   < 5000:  normal documentation volume, silent (most official-converted
        #            skills like docx/xlsx/pptx legitimately live here)
        #   5000-10000: notable, worth a heads-up but not alarming
        #   > 10000: genuinely large, splitting is strongly advised
        # The old flat 2000 threshold flagged 16+ healthy skills as "LARGE", drowning
        # out the few that actually warrant attention.
        for name, cs in skill_set.skills.items():
            if cs.prompt_tokens > 10000:
                issues.append(f"LARGE: '{name}' is {cs.prompt_tokens} tokens — consider splitting")
            elif cs.prompt_tokens > 5000:
                issues.append(f"HEFTY: '{name}' is {cs.prompt_tokens} tokens — review if needed")

        # Check missing deps
        for name, cs in skill_set.skills.items():
            for dep in cs.depends_on:
                if dep not in skill_set.skills:
                    issues.append(f"MISSING DEP: '{name}' depends on '{dep}' but not found")

        return issues

    def report(self, skill_set: CompiledSkillSet) -> str:
        """Generate a human-readable report of the skill set."""
        lines = [
            f"📦 Skill Report: {len(skill_set.skills)} skills",
            f"   Total prompt tokens: ~{skill_set.total_tokens}",
            f"   Always load: {len(skill_set.always_load())}",
            "   By target:",
        ]

        by_target: dict[str, int] = {}
        for cs in skill_set.skills.values():
            key = cs.target.value
            by_target[key] = by_target.get(key, 0) + 1
        for target, count in sorted(by_target.items()):
            lines.append(f"     {target}: {count}")

        lines.append("")
        for cs in sorted(skill_set.skills.values(), key=lambda x: -x.priority):
            flag = "🔵" if cs.always_load else "  "
            lines.append(f"  {flag} {cs.name:35s} {cs.target.value:10s} {cs.prompt_tokens:5d}tok")
            if cs.conflicts_with:
                lines.append(f"      ⚠ conflicts: {', '.join(cs.conflicts_with)}")
            if cs.warnings:
                for w in cs.warnings:
                    lines.append(f"      ⚠ {w}")
            if cs.errors:
                for e in cs.errors:
                    lines.append(f"      ❌ {e}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Prompt Compiler
# ═══════════════════════════════════════════════════════════════════


@dataclass
class PromptSection:
    """A section of the assembled system prompt."""

    name: str
    content: str
    priority: int = 5
    tokens: int = 0
    category: str = "general"  # "core", "skill", "memory", "context"


@dataclass
class CompiledPrompt:
    """The final assembled system prompt with all sections."""

    sections: list[PromptSection] = field(default_factory=list)
    total_tokens: int = 0
    budget_remaining: int = 0

    def assemble(self, separator: str = "\n\n") -> str:
        """Assemble all sections into a single prompt string."""
        return separator.join(s.content for s in self.sections if s.content)

    def add(self, section: PromptSection):
        self.sections.append(section)
        self.total_tokens += section.tokens

    def stats(self) -> str:
        lines = [f"Prompt: {len(self.sections)} sections, ~{self.total_tokens} tokens"]
        for s in self.sections:
            lines.append(f"  [{s.category:8s}] {s.name:30s} {s.tokens:5d}tok (pri={s.priority})")
        if self.budget_remaining:
            lines.append(f"  Budget remaining: {self.budget_remaining} tokens")
        return "\n".join(lines)


class PromptCompiler:
    """Dynamically assembles the system prompt from compiled skills + context.

    Strategy:
    1. Core: always_load skills (highest priority)
    2. Task-matched: skills whose target matches current task
    3. Active: skills that are explicitly loaded (by user / skill manager)
    4. Context: working/episodic/semantic memory (from Phase 3)
    5. Token Budget: if over limit, drop lowest-priority sections

    Usage:
        compiler = PromptCompiler(compiled_skills)
        prompt = compiler.compile(
            task_target="code",
            active_skills=["my-skill"],
            context_memory="...",
            token_budget=60000,
            existing_prompt="...",
        )
    """

    def __init__(self, compiled_skills: CompiledSkillSet):
        self.skills = compiled_skills

    def compile(
        self,
        task_target: str = "general",
        active_skills: list[str] | None = None,
        context_memory: str = "",
        token_budget: int = 60000,
        existing_prompt: str = "",
    ) -> CompiledPrompt:
        """Assemble the system prompt.

        Args:
            task_target: Current task type (media/code/general)
            active_skills: Explicitly loaded skill names
            context_memory: Context from Phase 3 memory tiers
            token_budget: Max allowed tokens
            existing_prompt: Base system prompt to extend
        """
        result = CompiledPrompt(budget_remaining=token_budget)
        target = _detect_target(task_target)

        # 1. Core: existing base prompt
        if existing_prompt:
            result.add(
                PromptSection(
                    name="base",
                    content=existing_prompt,
                    priority=10,
                    tokens=_estimate_tokens(existing_prompt),
                    category="core",
                )
            )

        # 2. Always-load skills (highest priority among skills)
        for cs in self.skills.always_load():
            if result.total_tokens + cs.prompt_tokens > token_budget:
                break
            result.add(
                PromptSection(
                    name=cs.name,
                    content=cs.prompt,
                    priority=8,
                    tokens=cs.prompt_tokens,
                    category="skill",
                )
            )

        # 3. Active / explicitly loaded skills (explicit intent outranks
        #    inferred task matching, so reserve budget for these first).
        for name in active_skills or []:
            cs = self.skills.get(name)
            if cs and cs.name not in [s.name for s in result.sections]:
                if result.total_tokens + cs.prompt_tokens > token_budget:
                    break
                # Check conflicts
                if any(cf in [s.name for s in result.sections] for cf in cs.conflicts_with):
                    continue  # Skip conflicting skill
                result.add(
                    PromptSection(
                        name=cs.name,
                        content=cs.prompt,
                        priority=7,
                        tokens=cs.prompt_tokens,
                        category="skill",
                    )
                )

        # 4. Task-matched skills (auto-loaded by inferred target)
        if target != TaskTarget.UNKNOWN:
            for cs in sorted(self.skills.by_target(target), key=lambda x: -x.priority):
                if cs.always_load:
                    continue  # Already added
                if cs.name in [s.name for s in result.sections]:
                    continue  # Already added as an active skill
                if result.total_tokens + cs.prompt_tokens > token_budget:
                    break
                result.add(
                    PromptSection(
                        name=cs.name,
                        content=cs.prompt,
                        priority=6,
                        tokens=cs.prompt_tokens,
                        category="skill",
                    )
                )

        # 5. Context memory (from Phase 3)
        if context_memory and result.total_tokens < token_budget:
            mem_tokens = _estimate_tokens(context_memory)
            if result.total_tokens + mem_tokens <= token_budget:
                result.add(
                    PromptSection(
                        name="context_memory",
                        content=context_memory,
                        priority=4,
                        tokens=mem_tokens,
                        category="context",
                    )
                )

        # Update remaining budget
        result.budget_remaining = max(0, token_budget - result.total_tokens)
        return result


# ═══════════════════════════════════════════════════════════════════
# Integration for ChatSession
# ═══════════════════════════════════════════════════════════════════


def install_compiler(skills_dir: str = "skills") -> tuple[SkillCompiler, PromptCompiler, CompiledSkillSet]:
    """One-shot install: compile skills + create prompt compiler.

    Returns:
        (compiler, prompt_compiler, compiled_skills)
    """
    compiler = SkillCompiler(skills_dir=skills_dir)
    compiled = compiler.compile_all()
    issues = compiler.validate(compiled)
    if issues:
        for iss in issues:
            logger.warning(f"Skill issue: {iss}")

    prompt_compiler = PromptCompiler(compiled)
    logger.info(f"Skill compiler: {len(compiled.skills)} skills, ~{compiled.total_tokens} tokens total")
    return compiler, prompt_compiler, compiled
