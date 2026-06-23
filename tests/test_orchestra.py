"""Tests for core.orchestra — multi-source capability coordination."""



class TestEnums:
    """CapabilitySource and Priority enums have expected values."""

    def test_capability_sources(self):
        from core.orchestra import CapabilitySource
        assert CapabilitySource.CLAUDE.value == "claude"
        assert CapabilitySource.CODEBUDDY.value == "codebuddy"
        assert CapabilitySource.ZBODY.value == "zbody"
        assert CapabilitySource.AGNES.value == "crux"
        assert CapabilitySource.USER.value == "user"

    def test_priority_ordering(self):
        from core.orchestra import Priority
        assert Priority.OVERRIDE.value > Priority.HIGH.value
        assert Priority.HIGH.value > Priority.NORMAL.value
        assert Priority.NORMAL.value > Priority.LOW.value
        assert Priority.LOW.value > Priority.FALLBACK.value


class TestCapability:
    """Capability data model."""

    def test_default_construction(self):
        from core.orchestra import Capability, CapabilitySource, Priority
        cap = Capability("test", CapabilitySource.AGNES)
        assert cap.name == "test"
        assert cap.source == CapabilitySource.AGNES
        assert cap.priority == Priority.NORMAL
        assert cap.enabled is True
        assert cap.conflicts_with == []

    def test_add_tag_and_matches(self):
        from core.orchestra import Capability, CapabilitySource
        cap = Capability("image_gen", CapabilitySource.AGNES, description="generate images")
        cap.add_tag("vision")
        assert cap.matches("image") is True       # name match
        assert cap.matches("generate") is True    # description match
        assert cap.matches("vision") is True      # tag match
        assert cap.matches("zzz_nothing") is False

    def test_custom_conflicts_with(self):
        from core.orchestra import Capability, CapabilitySource, Priority
        cap = Capability("a", CapabilitySource.AGNES, Priority.NORMAL,
                         conflicts_with=["b"])
        assert cap.conflicts_with == ["b"]


class TestOrchestraRegister:
    """Orchestra.register() respects priority semantics."""

    def test_register_new_capability(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        # Clear builtins for a clean test
        orch._capabilities.clear()
        cap = Capability("x", CapabilitySource.AGNES, Priority.NORMAL)
        orch.register(cap)
        assert "x" in orch._capabilities

    def test_higher_priority_replaces_lower(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        orch._capabilities.clear()
        low = Capability("x", CapabilitySource.AGNES, Priority.LOW)
        high = Capability("x", CapabilitySource.CLAUDE, Priority.OVERRIDE)
        orch.register(low)
        orch.register(high)
        assert orch._capabilities["x"].priority == Priority.OVERRIDE

    def test_lower_priority_does_not_replace_higher(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        orch._capabilities.clear()
        high = Capability("x", CapabilitySource.CLAUDE, Priority.OVERRIDE)
        low = Capability("x", CapabilitySource.AGNES, Priority.LOW)
        orch.register(high)
        orch.register(low)
        # Higher-priority existing cap blocks lower-priority replacement
        assert orch._capabilities["x"].priority == Priority.OVERRIDE

    def test_equal_priority_keeps_existing(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        orch._capabilities.clear()
        first = Capability("x", CapabilitySource.AGNES, Priority.NORMAL, description="first")
        second = Capability("x", CapabilitySource.CLAUDE, Priority.NORMAL, description="second")
        orch.register(first)
        orch.register(second)
        # Equal priority: existing.priority.value (50) >= new.priority.value (50) → keep existing
        assert orch._capabilities["x"].description == "first"


class TestOrchestraResolve:
    """resolve() returns enabled, conflict-free capabilities."""

    def test_resolve_unknown_returns_none(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        assert orch.resolve("zzz_nonexistent") is None

    def test_resolve_known_capability(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        orch._capabilities.clear()
        orch.register(Capability("y", CapabilitySource.AGNES, Priority.NORMAL))
        resolved = orch.resolve("y")
        assert resolved is not None
        assert resolved.name == "y"

    def test_resolve_disabled_by_conflict(self):
        from core.orchestra import Orchestra, Capability, CapabilitySource, Priority
        orch = Orchestra()
        orch._capabilities.clear()
        # "low_cap" conflicts with "high_cap"; high_cap has higher priority → low disabled
        orch.register(Capability("low_cap", CapabilitySource.AGNES, Priority.LOW,
                                 conflicts_with=["high_cap"]))
        orch.register(Capability("high_cap", CapabilitySource.CLAUDE, Priority.OVERRIDE))
        assert orch.resolve("low_cap") is None
        assert orch.resolve("high_cap") is not None


class TestOrchestraProfiles:
    """define_profile / active_profile orchestrate capability sets."""

    def test_builtin_coding_profile(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        active = orch.active_profile("coding")
        names = {c.name for c in active}
        assert "self_verification" in names
        assert "git_workflow" in names

    def test_builtin_video_profile(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        active = orch.active_profile("video")
        names = {c.name for c in active}
        assert "video_gen" in names
        assert "image_gen" in names

    def test_unknown_profile_falls_back_to_coding(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        active = orch.active_profile("zzz_unknown")
        # Falls back to "coding" profile
        assert len(active) > 0

    def test_define_custom_profile(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        orch.define_profile("custom", ["image_gen", "vision_analysis"])
        active = orch.active_profile("custom")
        names = {c.name for c in active}
        assert "image_gen" in names


class TestOrchestraQuery:
    """list_by_source / search / summary."""

    def test_list_by_source(self):
        from core.orchestra import Orchestra, CapabilitySource
        orch = Orchestra()
        agnes_caps = orch.list_by_source(CapabilitySource.AGNES)
        names = {c.name for c in agnes_caps}
        assert "image_gen" in names
        assert "video_gen" in names

    def test_search_finds_matching(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        results = orch.search("image")
        assert len(results) > 0
        # At least image_gen matches "image"
        assert any(c.name == "image_gen" for c in results)

    def test_search_no_match(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        results = orch.search("zzz_nonexistent_term")
        assert results == []

    def test_summary_contains_source_headers(self):
        from core.orchestra import Orchestra
        orch = Orchestra()
        s = orch.summary()
        assert "能力来源" in s
        assert "crux" in s


class TestOrchestraRules:
    """add_rule stores coordination rules."""

    def test_add_rule_appends(self):
        from core.orchestra import Orchestra, CapabilitySource
        orch = Orchestra()
        initial = len(orch._rules)
        orch.add_rule("test_condition", "activate:test", CapabilitySource.CLAUDE)
        assert len(orch._rules) == initial + 1
        last = orch._rules[-1]
        assert last["condition"] == "test_condition"
        assert last["source"] == "claude"


class TestGetOrchestraSingleton:
    """get_orchestra() returns shared singleton with builtins."""

    def test_returns_same_instance(self):
        from core.orchestra import get_orchestra
        o1 = get_orchestra()
        o2 = get_orchestra()
        assert o1 is o2

    def test_singleton_has_builtins(self):
        from core.orchestra import get_orchestra
        orch = get_orchestra()
        assert "self_verification" in orch._capabilities
        assert "image_gen" in orch._capabilities
