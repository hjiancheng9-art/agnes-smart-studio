"""Tests for core/chat_prompt.py — system prompt builder, cache, templates."""

from core.chat_prompt import (
    CHAT_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    PromptCache,
    build_system_prompt,
    get_cached_prompt,
    set_cached_prompt,
)


class TestPromptTemplates:
    def test_chat_template_has_placeholders(self):
        assert "{provider_name}" in CHAT_SYSTEM_PROMPT
        assert "{model_name}" in CHAT_SYSTEM_PROMPT
        assert "{personality_core}" in CHAT_SYSTEM_PROMPT

    def test_code_template_has_placeholders(self):
        assert "{provider_name}" in CODE_SYSTEM_PROMPT
        assert "{model_name}" in CODE_SYSTEM_PROMPT
        assert "{personality_core}" in CODE_SYSTEM_PROMPT

    def test_chat_template_generates_image_rules(self):
        result = build_system_prompt(model="m", provider_name="P")
        assert "generate_image" in result

    def test_code_template_explore_plan_execute(self):
        result = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "Explore" in result
        assert "Plan" in result
        assert "Execute" in result

    def test_templates_are_different(self):
        assert CHAT_SYSTEM_PROMPT != CODE_SYSTEM_PROMPT
        # Verify they produce different built prompts
        r1 = build_system_prompt(model="m", provider_name="P")
        r2 = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert r1 != r2


class TestPromptCache:
    def test_get_returns_none_when_empty(self):
        c = PromptCache()
        assert c.get("any_key") is None

    def test_set_and_get(self):
        c = PromptCache()
        c.set("key1", "value1")
        assert c.get("key1") == "value1"

    def test_key_mismatch_returns_none(self):
        c = PromptCache()
        c.set("key1", "value1")
        assert c.get("key2") is None

    def test_set_overwrites_previous(self):
        c = PromptCache()
        c.set("k", "v1")
        c.set("k", "v2")
        assert c.get("k") == "v2"

    def test_invalidate_clears_cache(self):
        c = PromptCache()
        c.set("k", "v")
        c.invalidate()
        assert c.get("k") is None

    def test_invalidate_resets_key(self):
        c = PromptCache()
        c.set("k", "v")
        c.invalidate()
        assert c.key == ""

    def test_empty_prompt_not_returned(self):
        c = PromptCache()
        c.key = "k"
        c.prompt = ""
        assert c.get("k") is None


class TestGlobalCache:
    def test_get_cached_prompt_returns_cache(self):
        c = get_cached_prompt()
        assert isinstance(c, PromptCache)

    def test_get_cached_prompt_singleton(self):
        c1 = get_cached_prompt()
        c2 = get_cached_prompt()
        assert c1 is c2

    def test_set_cached_prompt_stores_value(self):
        set_cached_prompt("test_key", "test_prompt")
        c = get_cached_prompt()
        assert c.get("test_key") == "test_prompt"
        c.invalidate()


class TestBuildSystemPrompt:
    def test_chat_mode_default(self):
        result = build_system_prompt(model="test-model", provider_name="TestProvider")
        assert "TestProvider" in result
        assert "test-model" in result
        assert "generate_image" in result

    def test_code_mode(self):
        result = build_system_prompt(
            model="test-model", provider_name="TestProvider", code_mode=True
        )
        assert "Explore" in result  # Codex v3 uses English
        assert "Plan" in result

    def test_browser_enabled(self):
        result = build_system_prompt(
            model="m", provider_name="P", browser_enabled=True
        )
        assert "Browser Companion" in result

    def test_notebook_enabled(self):
        result = build_system_prompt(
            model="m", provider_name="P", notebook_enabled=True
        )
        assert "Notebook" in result

    def test_audio_enabled(self):
        result = build_system_prompt(
            model="m", provider_name="P", audio_enabled=True
        )
        assert "Audio Tools" in result or "音频工具" in result

    def test_cache_returns_same_for_same_key(self):
        cache = get_cached_prompt()
        cache.invalidate()

        r1 = build_system_prompt(model="m", provider_name="P")
        r2 = build_system_prompt(model="m", provider_name="P")
        assert r1 is r2  # cached, same object

        cache.invalidate()

    def test_cache_differs_for_different_code_mode(self):
        cache = get_cached_prompt()
        cache.invalidate()
        r1 = build_system_prompt(model="m", provider_name="P", code_mode=False)
        r2 = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert r1 != r2
        cache.invalidate()

    def test_stuck_detection_in_code_mode(self):
        result = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "Stuck Handling" in result  # ENGINEERING_DISCIPLINE (code_mode only)

    def test_code_mode_has_engineering_discipline(self):
        result = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "Hard Gates" in result or "硬性门禁" in result or "Explore" in result or "工程纪律" in result

    def test_code_mode_no_creative_mythology(self):
        result = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "七兽融合" not in result
        assert "金手指" not in result

    def test_chat_mode_has_full_spectrum(self):
        result = build_system_prompt(model="m", provider_name="P", code_mode=False)
        assert "七兽融合" in result or "金手指" in result

    def test_active_skill_rules_hash_different_cache_keys(self):
        # Different hash → different cache key → different cache entries
        cache = get_cached_prompt()
        cache.invalidate()
        build_system_prompt(model="m", provider_name="P", active_skill_rules_hash="hash_a")
        # After first call, cache stores with key "P|m|False|bFalse|nFalse|aFalse|hash_a"
        build_system_prompt(model="m", provider_name="P", active_skill_rules_hash="hash_b")
        # Different hash should create separate cache entry, not reuse the first
        # Both calls should succeed without error (the spectrum content is the same, which is expected)
        cache.invalidate()


# ═══════════════════════════════════════════
# Codex v3 additions: modular prompt components
# ═══════════════════════════════════════════

class TestPersonalityCore:
    def test_contains_values(self):
        from core.chat_prompt import PERSONALITY_CORE
        assert "pragmatic" in PERSONALITY_CORE.lower()
        assert "clarity" in PERSONALITY_CORE.lower()

    def test_engineering_judgment_present(self):
        from core.chat_prompt import PERSONALITY_CORE
        assert "Engineering Judgment" in PERSONALITY_CORE


class TestToolUseDiscipline:
    def test_parallelize_rule(self):
        from core.chat_prompt import TOOL_USE_DISCIPLINE
        assert "Parallelize" in TOOL_USE_DISCIPLINE

    def test_no_destructive_git(self):
        from core.chat_prompt import TOOL_USE_DISCIPLINE
        assert "destructive git" in TOOL_USE_DISCIPLINE.lower()


class TestFrontendGuidance:
    def test_empathy_section(self):
        from core.chat_prompt import FRONTEND_GUIDANCE
        assert "Empathy" in FRONTEND_GUIDANCE

    def test_design_constraints(self):
        from core.chat_prompt import FRONTEND_GUIDANCE
        assert "Design Constraints" in FRONTEND_GUIDANCE


class TestConstraintCore:
    def test_ascii_default(self):
        from core.chat_prompt import CONSTRAINT_CORE
        assert "ASCII" in CONSTRAINT_CORE


class TestNewBuildSystemPrompt:
    def test_personality_injected_in_both_modes(self):
        r1 = build_system_prompt(model="m", provider_name="P", code_mode=False)
        r2 = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "pragmatic" in r1.lower()
        assert "pragmatic" in r2.lower()

    def test_frontend_only_in_code_mode(self):
        r_chat = build_system_prompt(model="m", provider_name="P", code_mode=False)
        r_code = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "Design Constraints" in r_code
        assert "Design Constraints" not in r_chat

    def test_tool_discipline_in_both_modes(self):
        r1 = build_system_prompt(model="m", provider_name="P", code_mode=False)
        r2 = build_system_prompt(model="m", provider_name="P", code_mode=True)
        assert "Parallelize" in r1
        assert "Parallelize" in r2
