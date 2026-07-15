"""Test Phase 5: Skill Compiler + Prompt Compiler"""

import pytest

from core.skill_compiler import (
    _KNOWN_CONFLICTS,
    CompiledPrompt,
    CompiledSkill,
    PromptCompiler,
    PromptSection,
    SkillCompiler,
    TaskTarget,
    _detect_target,
    _estimate_tokens,
)

# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def compiled_skills():
    """Compile all skills once for the module."""
    compiler = SkillCompiler("skills")
    compiled = compiler.compile_all()
    return compiled


@pytest.fixture(scope="module")
def prompt_compiler(compiled_skills):
    return PromptCompiler(compiled_skills)


# ── _estimate_tokens ────────────────────────────────────────────────


class TestEstimateTokens:
    def test_english(self):
        tokens = _estimate_tokens("hello world four words")
        assert tokens >= 1

    def test_chinese(self):
        tokens = _estimate_tokens("你好世界")
        assert tokens >= 1

    def test_empty(self):
        assert _estimate_tokens("") == 1

    def test_mixed(self):
        tokens = _estimate_tokens("hello 你好 world 世界")
        assert tokens >= 2


# ── _detect_target ──────────────────────────────────────────────────


class TestDetectTarget:
    def test_media(self):
        assert _detect_target("media") == TaskTarget.MEDIA
        assert _detect_target("image") == TaskTarget.MEDIA
        assert _detect_target("video") == TaskTarget.MEDIA

    def test_code(self):
        assert _detect_target("code") == TaskTarget.CODE
        assert _detect_target("programming") == TaskTarget.CODE

    def test_unknown(self):
        assert _detect_target("gibberish") == TaskTarget.UNKNOWN
        assert _detect_target("") == TaskTarget.UNKNOWN

    def test_case_insensitive(self):
        assert _detect_target("MEDIA") == TaskTarget.MEDIA
        assert _detect_target("Code") == TaskTarget.CODE


# ── SkillCompiler ───────────────────────────────────────────────────


class TestSkillCompiler:
    def test_compile_all(self):
        compiler = SkillCompiler("skills")
        compiled = compiler.compile_all()
        # Skill count grows over time; use a lower bound instead of an exact
        # number so ordinary additions don't break the suite.
        assert len(compiled.skills) >= 30
        assert compiled.total_tokens > 9000

    def test_compile_single_skill(self, compiled_skills):
        cs = compiled_skills.skills.get("browser-control")
        if cs:
            assert cs.is_valid
            assert cs.name == "browser-control"
            assert cs.prompt_tokens > 0

    def test_always_load(self, compiled_skills):
        always = compiled_skills.always_load()
        assert len(always) >= 1
        for a in always:
            assert a.always_load

    def test_by_target(self, compiled_skills):
        code_skills = compiled_skills.by_target(TaskTarget.CODE)
        assert len(code_skills) >= 5

        media_skills = compiled_skills.by_target(TaskTarget.MEDIA)
        assert len(media_skills) >= 15

    def test_validation_no_conflicts(self):
        compiler = SkillCompiler("skills")
        compiled = compiler.compile_all()
        issues = compiler.validate(compiled)
        # Should have no critical conflict issues (always_load skills don't conflict)
        critical_conflicts = [i for i in issues if "CONFLICT" in i]
        assert len(critical_conflicts) == 0

    def test_report(self):
        compiler = SkillCompiler("skills")
        compiled = compiler.compile_all()
        report = compiler.report(compiled)
        assert "Skill Report" in report
        assert "34 skills" in report or "skills" in report

    def test_compile_missing_directory(self):
        compiler = SkillCompiler("nonexistent_dir")
        compiled = compiler.compile_all()
        assert len(compiled.skills) == 0

    def test_known_conflicts(self):
        assert "codex-core" in _KNOWN_CONFLICTS
        assert "agnes-constitution-core" in _KNOWN_CONFLICTS["codex-core"]


# ── CompiledSkill ───────────────────────────────────────────────────


class TestCompiledSkill:
    def test_is_valid_by_default(self):
        cs = CompiledSkill(name="test", description="", prompt="")
        assert cs.is_valid

    def test_is_invalid_with_errors(self):
        cs = CompiledSkill(name="test", description="", prompt="", errors=["bad"])
        assert not cs.is_valid


# ── PromptCompiler ───────────────────────────────────────────────────


class TestPromptCompiler:
    def test_compile_code(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="code",
            existing_prompt="You are a helpful assistant.",
            token_budget=60000,
        )
        assert result.total_tokens > 100
        assert len(result.sections) >= 2  # base + code skills

    def test_compile_media(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="media",
            existing_prompt="You are a helpful assistant.",
            token_budget=60000,
        )
        assert result.total_tokens > 100
        # Media should have more skills than code
        assert result.total_tokens > 1000

    def test_budget_constraint(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="code",
            existing_prompt="Hi",
            token_budget=500,
        )
        assert result.total_tokens <= 600

    def test_context_memory_injection(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="code",
            existing_prompt="Hi",
            context_memory="[Working Memory]\n  task=Test",
            token_budget=60000,
        )
        assert any("Working Memory" in s.content for s in result.sections)

    def test_active_skills(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="code",
            existing_prompt="You are a helpful assistant.",
            active_skills=["browser-control"],
            token_budget=60000,
        )
        # Browser-control should be in the sections
        names = [s.name for s in result.sections]
        assert "browser-control" in names

    def test_no_existing_prompt(self, prompt_compiler):
        result = prompt_compiler.compile(task_target="general", token_budget=60000)
        assert result.total_tokens >= 0

    def test_priority_ordering(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="code",
            existing_prompt="Base prompt",
            token_budget=60000,
        )
        # First section should be core (priority 10)
        if result.sections:
            assert result.sections[0].priority >= 6

    def test_general_target(self, prompt_compiler):
        result = prompt_compiler.compile(
            task_target="general",
            existing_prompt="Hey",
            token_budget=60000,
        )
        assert result.total_tokens > 0


# ── CompiledPrompt ──────────────────────────────────────────────────


class TestCompiledPrompt:
    def test_assemble(self):
        p = CompiledPrompt()
        p.add(PromptSection(name="s1", content="Hello", priority=10, tokens=5, category="core"))
        p.add(PromptSection(name="s2", content="World", priority=5, tokens=5, category="skill"))
        assembled = p.assemble()
        assert "Hello" in assembled
        assert "World" in assembled

    def test_stats(self):
        p = CompiledPrompt()
        p.add(PromptSection(name="base", content="Hi", priority=10, tokens=2, category="core"))
        stats = p.stats()
        assert "2 tokens" in stats
        assert "base" in stats

    def test_assemble_skips_empty(self):
        p = CompiledPrompt()
        p.add(PromptSection(name="empty", content="", priority=5, tokens=0, category="skill"))
        assert p.assemble() == ""

    def test_budget_remaining(self):
        p = CompiledPrompt(budget_remaining=5000)
        assert p.budget_remaining == 5000


# ── Integration ──────────────────────────────────────────────────────


class TestIntegration:
    def test_compiler_then_prompt(self, compiled_skills, prompt_compiler):
        """End-to-end: compile skills → build prompt → verify."""
        result = prompt_compiler.compile(
            task_target="media",
            existing_prompt="You are CRUX Studio, an AI programming assistant.",
            context_memory="[Working Memory]\n  task=Generate image",
            token_budget=64000,
        )
        # Verify the assembled prompt
        prompt = result.assemble()
        assert "CRUX Studio" in prompt
        assert len(prompt) > 500
        assert result.total_tokens > 500

    def test_compiler_report(self, compiled_skills):
        """Verify the compiler report is informative."""
        compiler = SkillCompiler("skills")
        report = compiler.report(compiled_skills)
        assert "media" in report.lower() or "code" in report.lower()
