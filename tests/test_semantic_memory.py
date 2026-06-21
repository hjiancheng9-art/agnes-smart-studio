"""Tests for core.semantic_memory — cross-session memory with context injection."""

import json


class TestSemanticMemoryInit:
    """SemanticMemory construction and loading."""

    def test_loads_from_custom_path(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({"preferences": {"k": "v"}, "decisions": []}),
                        encoding="utf-8")
        mem = SemanticMemory(path=path)
        assert mem.data["preferences"]["k"] == "v"

    def test_defaults_on_missing_file(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "nonexistent.json")
        assert mem.data == {"preferences": {}, "decisions": [],
                            "project_context": {}, "corrections": [],
                            "learned_patterns": {}}

    def test_defaults_on_corrupt_file(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        path = tmp_path / "memory.json"
        path.write_text("not json {{{", encoding="utf-8")
        mem = SemanticMemory(path=path)
        assert "preferences" in mem.data
        assert mem.data["decisions"] == []


class TestRecordDecision:
    """record_decision stores decisions with truncation and cap."""

    def test_records_decision(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.record_decision("chose option A", "A", "worked well")
        assert len(mem.data["decisions"]) == 1
        entry = mem.data["decisions"][0]
        assert entry["context"] == "chose option A"
        assert entry["choice"] == "A"
        assert entry["outcome"] == "worked well"
        assert "ts" in entry

    def test_truncates_long_fields(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        long_text = "x" * 500
        mem.record_decision(long_text, long_text, long_text)
        entry = mem.data["decisions"][0]
        assert len(entry["context"]) == 200
        assert len(entry["choice"]) == 200
        assert len(entry["outcome"]) == 200

    def test_caps_at_100_decisions(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        for i in range(110):
            mem.record_decision(f"ctx{i}", f"ch{i}", f"out{i}")
        assert len(mem.data["decisions"]) == 100
        # Most recent kept
        assert mem.data["decisions"][-1]["choice"] == "ch109"

    def test_persists_to_disk(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        path = tmp_path / "m.json"
        mem = SemanticMemory(path=path)
        mem.record_decision("c", "a", "o")
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert len(loaded["decisions"]) == 1


class TestRecordCorrection:
    """record_correction stores mistakes for future avoidance."""

    def test_records_correction(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.record_correction("used mutable default", "use None + copy")
        assert len(mem.data["corrections"]) == 1
        entry = mem.data["corrections"][0]
        assert "mutable" in entry["problem"]
        assert entry["fix"] == "use None + copy"

    def test_caps_at_50_corrections(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        for i in range(55):
            mem.record_correction(f"p{i}", f"f{i}")
        assert len(mem.data["corrections"]) == 50


class TestLearnPattern:
    """learn_pattern stores code patterns for application."""

    def test_stores_pattern(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.learn_pattern("naming", "camelCase", "snake_case")
        assert "naming" in mem.data["learned_patterns"]
        pat = mem.data["learned_patterns"]["naming"]
        assert pat["pattern"] == "camelCase"
        assert pat["replacement"] == "snake_case"
        assert "ts" in pat


class TestPreferences:
    """set_preference / get_preference store key-value settings."""

    def test_set_and_get(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.set_preference("language", "python")
        assert mem.get_preference("language") == "python"

    def test_get_with_default(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        assert mem.get_preference("nonexistent", default="fallback") == "fallback"

    def test_overwrite_preference(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.set_preference("x", "1")
        mem.set_preference("x", "2")
        assert mem.get_preference("x") == "2"


class TestProjectContext:
    """set_project_context stores project metadata."""

    def test_sets_context(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.set_project_context("framework", "fastapi")
        assert mem.data["project_context"]["framework"] == "fastapi"


class TestBuildContextInjection:
    """build_context_injection generates prompt text from memory."""

    def test_empty_when_no_data(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        assert mem.build_context_injection() == ""

    def test_includes_preferences(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.set_preference("lang", "python")
        text = mem.build_context_injection()
        assert "User Preferences" in text
        assert "python" in text

    def test_includes_corrections(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.record_correction("the mistake", "the fix")
        text = mem.build_context_injection()
        assert "Critical Corrections" in text
        assert "the mistake" in text
        assert "the fix" in text

    def test_includes_patterns(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.learn_pattern("style", "old", "new")
        text = mem.build_context_injection()
        assert "Learned Code Patterns" in text

    def test_includes_project_context(self, tmp_path):
        from core.semantic_memory import SemanticMemory
        mem = SemanticMemory(path=tmp_path / "m.json")
        mem.set_project_context("db", "postgres")
        text = mem.build_context_injection()
        assert "Project Context" in text
        assert "postgres" in text


class TestGetMemorySingleton:
    """get_memory() returns shared singleton."""

    def test_returns_same_instance(self):
        from core.semantic_memory import get_memory
        m1 = get_memory()
        m2 = get_memory()
        assert m1 is m2
