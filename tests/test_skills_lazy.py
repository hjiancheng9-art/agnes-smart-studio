"""Tests for core/skills.py — lazy loading & matching."""

from pathlib import Path

from core.skills import SKILLS_DIR, Skill, SkillManager


class TestSkillLazyLoading:
    def setup_method(self):
        self.sm = SkillManager(SKILLS_DIR)
        self.sm.discover()
        self.sm._lazy_cache.clear()

    def test_match_python_task(self):
        matched = self.sm.match_and_load("write a Python decorator for caching")
        names = [s.name for s in matched]
        assert "python-anti-patterns" in names

    def test_no_match_unrelated_task(self):
        matched = self.sm.match_and_load("deploy to kubernetes cluster with helm")
        names = [s.name for s in matched]
        # Should not match python-specific skills for a k8s task
        assert "python-anti-patterns" not in names

    def test_empty_task_no_match(self):
        matched = self.sm.match_and_load("")
        assert len(matched) == 0

    def test_cached_skill_not_reloaded(self):
        first = self.sm.match_and_load("Python type hints")
        second = self.sm.match_and_load("Python async patterns")
        first_names = {s.name for s in first}
        second_names = {s.name for s in second}
        # Skills cached in first call should appear in second without re-matching
        cached_in_both = first_names & second_names
        assert len(cached_in_both) >= len(first_names)

    def test_auto_skills_prompt_with_context(self):
        prompt = self.sm.auto_skills_prompt("base", task_context="Python type annotations and testing")
        assert "base" in prompt
        assert "python-anti-patterns" in prompt.lower() or "Python" in prompt

    def test_auto_skills_prompt_no_context(self):
        prompt = self.sm.auto_skills_prompt("base", task_context="")
        assert "base" in prompt
        # Without context, loads all auto skills (backward compatible)

    def test_clear_lazy_cache(self):
        self.sm.match_and_load("Python decorator")
        assert len(self.sm._lazy_cache) > 0
        self.sm.clear_lazy_cache()
        assert len(self.sm._lazy_cache) == 0

    def test_manual_skill_not_auto_matched(self):
        # Skills with trigger=manual should never match via match_and_load
        manual_skills = [s for s in self.sm._available.values() if s.trigger == "manual"]
        if manual_skills:
            manual_name = manual_skills[0].name
            matched = self.sm.match_and_load("any random task 12345 xyz")
            matched_names = [s.name for s in matched]
            assert manual_name not in matched_names


class TestSkillManagerBasics:
    def test_discover_loads_skills(self):
        sm = SkillManager(SKILLS_DIR)
        available = sm.discover()
        assert isinstance(available, dict)
        assert len(available) > 0

    def test_load_existing_skill(self):
        sm = SkillManager(SKILLS_DIR)
        sm.discover()
        skill = sm.load("python-expert")
        assert skill is not None
        assert skill.name == "python-expert"

    def test_load_nonexistent(self):
        sm = SkillManager(SKILLS_DIR)
        sm.discover()
        assert sm.load("nonexistent-skill-xyz") is None

    def test_validate(self):
        sm = SkillManager(SKILLS_DIR)
        result = sm.validate()
        assert "passed" in result
        assert "failed" in result


class TestSkillTriggerStates:
    def test_three_states_defined(self):
        assert Skill.TRIGGER_AUTO == "auto"
        assert Skill.TRIGGER_MANUAL == "manual"
        assert Skill.TRIGGER_OFF == "off"

    def test_invalid_trigger_falls_to_manual(self):
        data = {"name": "test", "trigger": "invalid"}
        skill = Skill(data, Path("test.skill.json"))
        assert skill.trigger == Skill.TRIGGER_MANUAL
