"""
ZCode TDD: core/skills.py tests.
Tests SkillManager instantiation, singleton, discover, and skill operations.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_manager():
    """Return a fresh SkillManager with no shared state."""
    from core.skills import SkillManager, reset_skill_manager

    reset_skill_manager()
    mgr = SkillManager()
    yield mgr
    reset_skill_manager()


# ---------------------------------------------------------------------------
# 1. SkillManager instantiation and singleton
# ---------------------------------------------------------------------------


class TestSkillManagerInstantiation:
    def test_instantiate(self, fresh_manager):
        from core.skills import SkillManager

        assert isinstance(fresh_manager, SkillManager)

    def test_default_attributes(self, fresh_manager):
        assert fresh_manager._loaded is None
        assert isinstance(fresh_manager._available, dict)
        assert isinstance(fresh_manager._all_skills, dict)
        assert isinstance(fresh_manager._overrides, dict)

    def test_singleton_get_manager(self):
        from core.skills import SkillManager, get_manager, reset_skill_manager

        reset_skill_manager()
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2
        assert isinstance(m1, SkillManager)
        reset_skill_manager()

    def test_reset_skill_manager(self):
        from core.skills import get_manager, reset_skill_manager

        reset_skill_manager()
        m1 = get_manager()
        reset_skill_manager()
        m2 = get_manager()
        assert m1 is not m2
        reset_skill_manager()

    def test_custom_skills_dir(self, tmp_path):
        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=tmp_path)
        assert mgr._dir == tmp_path


# ---------------------------------------------------------------------------
# 2. discover method
# ---------------------------------------------------------------------------


class TestSkillManagerDiscover:
    def test_discover_returns_dict(self, fresh_manager):
        result = fresh_manager.discover()
        assert isinstance(result, dict)

    def test_discover_creates_dir_if_missing(self, tmp_path):
        from core.skills import SkillManager

        sub = tmp_path / "nonexistent_skills"
        assert not sub.exists()
        mgr = SkillManager(skills_dir=sub)
        mgr.discover()
        assert sub.exists()

    def test_discover_loads_skill_files(self, fresh_manager, tmp_path):
        import json

        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        skill_file = skill_dir / "test.skill.json"
        skill_file.write_text(
            json.dumps(
                {
                    "name": "test-skill",
                    "description": "A test skill",
                    "version": "1.0",
                    "prompt": "You are a test skill with at least 20 chars of prompt text.",
                }
            ),
            encoding="utf-8",
        )

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        available = mgr.discover()
        assert "test-skill" in available

    def test_discover_ignores_off_trigger(self, fresh_manager, tmp_path):
        import json

        skill_dir = tmp_path / "skills_off"
        skill_dir.mkdir()
        skill_file = skill_dir / "hidden.skill.json"
        skill_file.write_text(
            json.dumps(
                {
                    "name": "hidden-skill",
                    "description": "Hidden",
                    "version": "1.0",
                    "trigger": "off",
                    "prompt": "You are a hidden skill with enough prompt text here.",
                }
            ),
            encoding="utf-8",
        )

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        available = mgr.discover()
        assert "hidden-skill" not in available

    def test_discover_handles_invalid_json(self, fresh_manager, tmp_path):
        skill_dir = tmp_path / "skills_bad"
        skill_dir.mkdir()
        (skill_dir / "bad.skill.json").write_text("not json", encoding="utf-8")

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        available = mgr.discover()
        assert isinstance(available, dict)


# ---------------------------------------------------------------------------
# 3. available_names (list_available)
# ---------------------------------------------------------------------------


class TestSkillManagerListAvailable:
    def test_available_names_is_list(self, fresh_manager):
        fresh_manager.discover()
        names = fresh_manager.available_names
        assert isinstance(names, list)

    def test_available_names_after_discover(self, fresh_manager, tmp_path):
        import json

        skill_dir = tmp_path / "skills_list"
        skill_dir.mkdir()
        (skill_dir / "a.skill.json").write_text(
            json.dumps(
                {
                    "name": "skill-a",
                    "description": "Skill A",
                    "version": "1.0",
                    "prompt": "You are skill A with enough prompt text for validation purposes.",
                }
            ),
            encoding="utf-8",
        )
        (skill_dir / "b.skill.json").write_text(
            json.dumps(
                {
                    "name": "skill-b",
                    "description": "Skill B",
                    "version": "1.0",
                    "prompt": "You are skill B with enough prompt text for validation purposes.",
                }
            ),
            encoding="utf-8",
        )

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        mgr.discover()
        names = mgr.available_names
        assert "skill-a" in names
        assert "skill-b" in names


# ---------------------------------------------------------------------------
# 4. Skill operations (load, unload, get_system_prompt)
# ---------------------------------------------------------------------------


class TestSkillOperations:
    def test_load_skill(self, fresh_manager):
        from core.skills import Skill

        fresh_manager.create_examples()
        fresh_manager.discover()
        skill = fresh_manager.load("python-expert")
        assert skill is not None
        assert isinstance(skill, Skill)
        assert skill.name == "python-expert"

    def test_load_nonexistent(self, fresh_manager):
        fresh_manager.discover()
        skill = fresh_manager.load("nonexistent-skill")
        assert skill is None

    def test_unload(self, fresh_manager):
        fresh_manager.create_examples()
        fresh_manager.discover()
        fresh_manager.load("python-expert")
        assert fresh_manager.loaded is not None
        fresh_manager.unload()
        assert fresh_manager.loaded is None

    def test_get_system_prompt_with_loaded_skill(self, fresh_manager):
        fresh_manager.create_examples()
        fresh_manager.discover()
        fresh_manager.load("python-expert")
        base = "You are a helpful assistant."
        result = fresh_manager.get_system_prompt(base)
        assert base in result
        assert "python-expert" in result

    def test_get_system_prompt_no_skill(self, fresh_manager):
        fresh_manager.unload()
        base = "You are a helpful assistant."
        result = fresh_manager.get_system_prompt(base)
        assert result == base

    def test_get_extra_tools_empty(self, fresh_manager):
        fresh_manager.unload()
        tools = fresh_manager.get_extra_tools()
        assert tools == []

    def test_get_extra_tools_with_skill(self, fresh_manager):
        fresh_manager.create_examples()
        fresh_manager.discover()
        # python-expert has no tools in its definition
        fresh_manager.load("python-expert")
        tools = fresh_manager.get_extra_tools()
        # The example skills don't define tools
        assert isinstance(tools, list)

    def test_skill_object_fields(self, fresh_manager):
        from core.skills import Skill

        fresh_manager.create_examples()
        fresh_manager.discover()
        skill = fresh_manager.load("python-expert")
        assert skill.name == "python-expert"
        assert len(skill.description) > 0
        assert len(skill.version) > 0
        assert len(skill.prompt) > 0
        assert isinstance(skill.icon, str)
        assert isinstance(skill.tools, list)
        assert skill.trigger in (Skill.TRIGGER_AUTO, Skill.TRIGGER_MANUAL, Skill.TRIGGER_OFF)
        assert skill.file is not None


# ---------------------------------------------------------------------------
# 5. Trigger modes
# ---------------------------------------------------------------------------


class TestSkillTriggerModes:
    def test_auto_skills_prompt_no_auto_skills(self, fresh_manager):
        """auto_skills_prompt should inject configured auto skills (e.g. caliber)."""
        fresh_manager.create_examples()
        fresh_manager.discover()
        base = "Base prompt."
        result = fresh_manager.auto_skills_prompt(base)
        # With skill_overrides.json configured, auto skills will be injected
        assert result != base  # Injection happened
        assert "Skill 自动激活" in result

    def test_list_all_includes_all(self, fresh_manager, tmp_path):
        import json

        skill_dir = tmp_path / "skills_trigger"
        skill_dir.mkdir()
        (skill_dir / "auto.skill.json").write_text(
            json.dumps(
                {
                    "name": "auto-skill",
                    "description": "Auto",
                    "version": "1.0",
                    "trigger": "auto",
                    "prompt": "Auto skill with enough prompt text for validation.",
                }
            ),
            encoding="utf-8",
        )
        (skill_dir / "off.skill.json").write_text(
            json.dumps(
                {
                    "name": "off-skill",
                    "description": "Off",
                    "version": "1.0",
                    "trigger": "off",
                    "prompt": "Off skill with enough prompt text for validation.",
                }
            ),
            encoding="utf-8",
        )

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        all_skills = mgr.list_all()
        names = {s.name for s in all_skills}
        assert "auto-skill" in names
        assert "off-skill" in names

    def test_get_trigger(self, fresh_manager, tmp_path):
        import json

        skill_dir = tmp_path / "skills_gettrig"
        skill_dir.mkdir()
        (skill_dir / "manual.skill.json").write_text(
            json.dumps(
                {
                    "name": "manual-skill",
                    "description": "Manual",
                    "version": "1.0",
                    "trigger": "manual",
                    "prompt": "Manual skill with enough prompt text for validation.",
                }
            ),
            encoding="utf-8",
        )

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        trigger = mgr.get_trigger("manual-skill")
        assert trigger == "manual"

    def test_get_trigger_nonexistent(self, fresh_manager):
        result = fresh_manager.get_trigger("no-such-skill")
        assert result is None

    def test_set_trigger_invalid_value(self, fresh_manager):
        result = fresh_manager.set_trigger("some-skill", "invalid")
        assert result is False

    def test_set_trigger_nonexistent_skill(self, fresh_manager):
        result = fresh_manager.set_trigger("no-such-skill", "auto")
        assert result is False


# ---------------------------------------------------------------------------
# 6. Validate
# ---------------------------------------------------------------------------


class TestSkillValidate:
    def test_validate_returns_dict(self, fresh_manager):
        fresh_manager.create_examples()
        fresh_manager.discover()
        result = fresh_manager.validate()
        assert isinstance(result, dict)
        assert "passed" in result
        assert "failed" in result

    def test_validate_with_examples(self, fresh_manager):
        fresh_manager.create_examples()
        fresh_manager.discover()
        result = fresh_manager.validate()
        # Example skills should all pass validation
        assert len(result["passed"]) > 0

    def test_validate_invalid_json(self, fresh_manager, tmp_path):
        skill_dir = tmp_path / "skills_val"
        skill_dir.mkdir()
        (skill_dir / "broken.skill.json").write_text("{not json", encoding="utf-8")

        from core.skills import SkillManager

        mgr = SkillManager(skills_dir=skill_dir)
        result = mgr.validate()
        assert len(result["failed"]) >= 1


# ---------------------------------------------------------------------------
# 7. Resolve skill executor
# ---------------------------------------------------------------------------


class TestResolveSkillExecutor:
    def test_resolve_generate_image(self):
        from core.skills import resolve_skill_executor

        executor = resolve_skill_executor("generate_image")
        assert callable(executor)

    def test_resolve_text_to_speech(self):
        from core.skills import resolve_skill_executor

        executor = resolve_skill_executor("text_to_speech")
        assert callable(executor)

    def test_resolve_unknown_tool(self):
        from core.skills import resolve_skill_executor

        executor = resolve_skill_executor("nonexistent_tool")
        assert callable(executor)
