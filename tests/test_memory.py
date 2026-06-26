"""Smoke tests for utils/memory.py — user learning memory module.

Tests cover (all file I/O via tmp_path, no production data touched):
- _ensure_file / load_memory / save_memory
- record_preference / get_preference / get_all_preferences
- rate_record / _update_stats / _sync_rating_to_history
- track_generation / track_content_policy_hit / _extract_keywords
- get_tips / record_tip_shown
- record_prompt_pair / get_successful_prompts / build_evolution_context / get_evolution_stats
- record_comparison / get_recent_comparisons / get_comparison_stats
- save_session / load_session / get_recent_sessions / get_session_context
- update_user_profile / get_user_profile
- record_correction / get_corrections / build_correction_context
- record_test_pattern / build_test_context
- get_user_context / record_tool_learning / get_tool_learnings
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module (not symbols) so monkeypatch on module attrs takes effect
import utils.memory as mem_mod
from utils.memory import (
    build_correction_context,
    build_evolution_context,
    build_test_context,
    get_all_preferences,
    get_comparison_stats,
    get_corrections,
    get_evolution_stats,
    get_preference,
    get_recent_comparisons,
    get_recent_sessions,
    get_session_context,
    get_successful_prompts,
    get_tips,
    get_tool_learnings,
    get_user_context,
    get_user_profile,
    load_memory,
    load_session,
    rate_record,
    record_comparison,
    record_correction,
    record_preference,
    record_prompt_pair,
    record_test_pattern,
    record_tip_shown,
    record_tool_learning,
    save_memory,
    save_session,
    track_content_policy_hit,
    track_generation,
    update_user_profile,
)


@pytest.fixture(autouse=True)
def _isolate_memory(tmp_path, monkeypatch):
    """Redirect MEMORY_FILE and SESSION_FILE to tmp_path so tests never touch production data."""
    monkeypatch.setattr(mem_mod, "MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(mem_mod, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(mem_mod, "_OUTPUT_DIR", tmp_path)
    yield


# ── load / save ──────────────────────────────────────────────


class TestLoadSaveMemory:
    def test_load_creates_file(self, tmp_path):
        mem = load_memory()
        assert isinstance(mem, dict)
        assert "version" in mem
        assert "preferences" in mem

    def test_save_roundtrip(self):
        data = load_memory()
        data["preferences"]["color"] = {"values": {"red": 3}, "last_used": "red"}
        save_memory(data)
        reloaded = load_memory()
        assert reloaded["preferences"]["color"]["values"]["red"] == 3

    def test_save_is_atomic(self):
        """Save uses tmp+replace pattern; file content should be valid JSON."""
        data = load_memory()
        data["test_atomic"] = True
        save_memory(data)
        reloaded = load_memory()
        assert reloaded["test_atomic"] is True


# ── Preferences ───────────────────────────────────────────────


class TestPreferences:
    def test_record_and_get(self):
        record_preference("style", "anime")
        assert get_preference("style") == "anime"

    def test_get_missing_returns_default(self):
        assert get_preference("nonexistent_key") is None
        assert get_preference("nope", "fallback") == "fallback"

    def test_record_increments_count(self):
        record_preference("size", "1024x1024")
        record_preference("size", "1024x1024")
        record_preference("size", "512x512")
        prefs = get_all_preferences()
        assert prefs["size"]["favorite"] == "1024x1024"
        assert prefs["size"]["count"] == 2
        assert prefs["size"]["total_uses"] == 3

    def test_get_all_preferences_empty(self):
        result = get_all_preferences()
        assert isinstance(result, dict)

    def test_record_various_types(self):
        record_preference("count", 42)
        record_preference("flag", True)
        assert get_preference("count") == "42"
        assert get_preference("flag") == "True"


# ── Ratings ──────────────────────────────────────────────────


class TestRatings:
    def test_rate_record(self):
        rate_record("rec_001", 5)
        mem = load_memory()
        assert "rec_001" in mem["ratings"]
        assert mem["ratings"]["rec_001"]["rating"] == 5

    def test_rate_clamps_range(self):
        rate_record("rec_low", 0)
        mem = load_memory()
        assert mem["ratings"]["rec_low"]["rating"] == 1

    def test_rate_clamps_high(self):
        rate_record("rec_high", 10)
        mem = load_memory()
        assert mem["ratings"]["rec_high"]["rating"] == 5

    def test_rate_updates_stats(self):
        rate_record("r1", 4)
        rate_record("r2", 2)
        mem = load_memory()
        assert mem["stats"]["avg_rating"] == 3.0
        assert mem["stats"]["rated_count"] == 2

    def test_sync_rating_to_history_no_history(self):
        """Should not crash when history.json doesn't exist."""
        rate_record("rec_orphan", 3)  # no crash


# ── Tracking ──────────────────────────────────────────────────


class TestTracking:
    def test_track_generation_image(self):
        track_generation("text_to_image", "a cute cat", {"url": "x.png"})
        mem = load_memory()
        assert mem["stats"]["total"] == 1
        assert mem["stats"]["image"] == 1

    def test_track_generation_video(self):
        track_generation("image_to_video", "animate", {"url": "x.mp4"})
        mem = load_memory()
        assert mem["stats"]["video"] == 1

    def test_track_generation_extracts_keywords(self):
        track_generation("text_to_image", "a cute cat", {})
        mem = load_memory()
        assert len(mem["patterns"]) == 1

    def test_track_generation_patterns_limit(self):
        for i in range(60):
            track_generation("text_to_image", f"prompt number {i}", {})
        mem = load_memory()
        assert len(mem["patterns"]) == 50

    def test_track_content_policy_hit(self):
        track_content_policy_hit("bad prompt")
        assert load_memory()["stats"]["content_policy_hits"] == 1
        track_content_policy_hit("another bad prompt")
        assert load_memory()["stats"]["content_policy_hits"] == 2


class TestExtractKeywords:
    def test_basic_split(self):
        with patch.dict("sys.modules", {"jieba": None}):
            # Force ImportError path
            from utils.memory import _extract_keywords

            result = _extract_keywords("hello world test")
            assert "hello" in result

    def test_empty_prompt(self):
        from utils.memory import _extract_keywords

        result = _extract_keywords("")
        assert result == []


# ── Tips ──────────────────────────────────────────────────────


class TestTips:
    def test_tips_new_user(self):
        tips = get_tips()
        assert len(tips) >= 1
        assert "刚开始使用" in tips[0]

    def test_tips_after_generations(self):
        for _ in range(5):
            track_generation("text_to_image", "test prompt", {})
        tips = get_tips()
        assert any("累计生成" in t for t in tips)

    def test_record_tip_shown(self):
        record_tip_shown("tip_welcome")
        mem = load_memory()
        assert "tip_welcome" in mem["tips_shown"]

    def test_record_tip_dedup(self):
        record_tip_shown("tip_xyz")
        record_tip_shown("tip_xyz")
        mem = load_memory()
        assert mem["tips_shown"].count("tip_xyz") == 1


# ── Prompt Evolution ──────────────────────────────────────────


class TestPromptEvolution:
    def test_record_low_rating_ignored(self):
        record_prompt_pair("user p", "enhanced p", "image", 2)
        assert get_successful_prompts("image") == []

    def test_record_high_rating(self):
        record_prompt_pair("user p", "enhanced p", "image", 5)
        result = get_successful_prompts("image", limit=1)
        assert len(result) == 1
        assert result[0]["rating"] == 5

    def test_evolution_limit(self):
        for i in range(35):
            record_prompt_pair(f"u{i}", f"e{i}", "image", 4)
        result = get_successful_prompts("image", limit=100)
        assert len(result) == 30

    def test_build_evolution_context_insufficient(self):
        record_prompt_pair("u", "e", "image", 5)
        ctx = build_evolution_context("image")
        assert ctx == ""  # needs at least 2

    def test_build_evolution_context(self):
        record_prompt_pair("user prompt 1", "enhanced prompt 1", "image", 5)
        record_prompt_pair("user prompt 2", "enhanced prompt 2", "image", 4)
        ctx = build_evolution_context("image")
        assert "历史成功案例" in ctx
        assert "案例1" in ctx

    def test_get_evolution_stats(self):
        record_prompt_pair("u", "e", "image", 5)
        record_prompt_pair("u", "e", "video", 4)
        stats = get_evolution_stats()
        assert stats["image"] == 1
        assert stats["video"] == 1


# ── Comparisons ──────────────────────────────────────────────


class TestComparisons:
    def test_record_comparison(self):
        entry = record_comparison(
            goal="which is better",
            image_paths=["a.png", "b.png"],
            labels=["A", "B"],
            winner="A",
            scores={"A": {"total": 45}, "B": {"total": 30}},
        )
        assert entry["winner"] == "A"
        assert entry["winner_path"] == "a.png"

    def test_record_comparison_with_prompts_feeds_evolution(self):
        record_comparison(
            goal="test",
            image_paths=["a.png", "b.png"],
            labels=["A", "B"],
            winner="A",
            prompts=["prompt A wins", "prompt B loses"],
        )
        evolved = get_successful_prompts("image")
        assert len(evolved) == 1
        assert evolved[0]["user"] == "prompt A wins"

    def test_record_comparison_limits(self):
        for i in range(110):
            record_comparison(
                goal=f"goal {i}",
                image_paths=["a.png", "b.png"],
                labels=["A", "B"],
                winner="A",
            )
        result = get_recent_comparisons(limit=200)
        assert len(result) == 100

    def test_get_recent_comparisons(self):
        record_comparison("g", ["a.png"], ["A"], "A")
        recent = get_recent_comparisons(5)
        assert len(recent) == 1

    def test_get_comparison_stats(self):
        stats = get_comparison_stats()
        assert "total" in stats
        assert "with_winner" in stats


# ── Sessions ──────────────────────────────────────────────────


class TestSessions:
    def test_save_and_load_session(self):
        save_session("sess_1", "Test session summary", [{"role": "user", "content": "hello"}], task="testing")
        session = load_session("sess_1")
        assert session["summary"] == "Test session summary"
        assert session["task"] == "testing"
        assert len(session["messages"]) == 1

    def test_save_truncates_messages(self):
        msgs = [{"role": "user", "content": "msg " * 200} for _ in range(20)]
        save_session("sess_big", "big", msgs)
        session = load_session("sess_big")
        assert len(session["messages"]) <= 10

    def test_load_nonexistent_session(self):
        session = load_session("no_such_id")
        assert session == {}

    def test_get_recent_sessions(self):
        save_session("s1", "first", [], task="t1")
        save_session("s2", "second", [], task="t2")
        recent = get_recent_sessions(5)
        assert len(recent) == 2
        assert recent[0]["id"] in ("s1", "s2")
        assert recent[1]["id"] in ("s1", "s2")
        assert recent[0]["id"] != recent[1]["id"]

    def test_get_session_context_by_id(self):
        save_session("ctx_1", "summary text", [], task="my task")
        ctx = get_session_context("ctx_1")
        assert "my task" in ctx
        assert "summary text" in ctx

    def test_get_session_context_empty(self):
        assert get_session_context("no_such") == ""

    def test_get_session_context_latest(self):
        save_session("auto_1", "auto summary", [], task="auto task")
        ctx = get_session_context()  # no id → most recent
        assert "auto summary" in ctx

    def test_get_session_context_no_sessions(self):
        ctx = get_session_context()
        assert ctx == ""


# ── User Profile ───────────────────────────────────────────────


class TestUserProfile:
    def test_update_and_get(self):
        update_user_profile("role", "developer")
        assert get_user_profile("role") == "developer"

    def test_update_keeps_history(self):
        update_user_profile("language", "Python")
        update_user_profile("language", "Rust")
        assert get_user_profile("language") == "Rust"
        profile = get_user_profile()
        assert isinstance(profile, dict)

    def test_get_all_profile(self):
        update_user_profile("role", "designer")
        profile = get_user_profile()
        assert "role" in profile

    def test_get_missing_key(self):
        assert get_user_profile("nonexistent") == ""


# ── Corrections ──────────────────────────────────────────────


class TestCorrections:
    def test_record_and_get(self):
        record_correction("deleted wrong file", "should have asked first", context="file ops")
        corrections = get_corrections()
        assert len(corrections) == 1
        assert corrections[0]["what_happened"] == "deleted wrong file"

    def test_record_dedup(self):
        record_correction("same mistake", "same fix", context="ctx")
        record_correction("same mistake", "same fix", context="ctx")
        corrections = get_corrections()
        assert len(corrections) == 1  # deduped

    def test_build_correction_context(self):
        record_correction("did X", "do Y instead")
        ctx = build_correction_context()
        assert "Past corrections" in ctx
        assert "Don't:" in ctx

    def test_build_correction_context_empty(self):
        ctx = build_correction_context()
        assert ctx == ""

    def test_corrections_limit(self):
        for i in range(60):
            record_correction(f"err {i}", f"fix {i}", context="unique")
        corrections = get_corrections(limit=100)
        assert len(corrections) == 50


# ── Test Patterns ─────────────────────────────────────────────


class TestTestPatterns:
    def test_record_and_build(self):
        record_test_pattern("my_tool", "assertion failed", "added missing import")
        ctx = build_test_context("my_tool")
        assert "Past test patterns" in ctx
        assert "my_tool" in ctx

    def test_build_empty(self):
        ctx = build_test_context()
        assert ctx == ""

    def test_build_filter_by_tool(self):
        record_test_pattern("tool_a", "err a", "fix a")
        record_test_pattern("tool_b", "err b", "fix b")
        ctx_a = build_test_context("tool_a")
        assert "tool_a" in ctx_a
        assert "tool_b" not in ctx_a

    def test_patterns_limit(self):
        for i in range(60):
            record_test_pattern(f"t{i}", f"fail {i}", f"fix {i}")
        data = json.loads(mem_mod.SESSION_FILE.read_text(encoding="utf-8"))
        assert len(data["test_patterns"]) == 50


# ── User Context ─────────────────────────────────────────────


class TestUserContext:
    def test_empty_context(self):
        ctx = get_user_context()
        assert ctx == ""

    def test_context_with_profile_and_corrections(self):
        update_user_profile("role", "ML engineer")
        update_user_profile("language", "Python")
        record_correction("bad habit", "good habit")
        ctx = get_user_context()
        assert "用户记忆" in ctx
        assert "ML engineer" in ctx
        assert "Python" in ctx

    def test_context_role_only(self):
        update_user_profile("role", "designer")
        ctx = get_user_context()
        assert "用户角色: designer" in ctx


# ── Tool Learnings ───────────────────────────────────────────


class TestToolLearnings:
    def test_record_and_get(self):
        record_tool_learning("read_file", "permission denied", "use try/except wrapper")
        ctx = get_tool_learnings("read_file")
        assert "permission denied" in ctx

    def test_get_empty(self):
        ctx = get_tool_learnings("nonexistent")
        assert ctx == ""

    def test_get_all(self):
        record_tool_learning("t1", "e1", "f1")
        ctx = get_tool_learnings()
        assert "工具历史经验" in ctx

    def test_learnings_limit(self):
        for i in range(35):
            record_tool_learning(f"tool_{i}", f"err_{i}", f"fix_{i}")
        data = json.loads(mem_mod.SESSION_FILE.read_text(encoding="utf-8"))
        assert len(data["tool_learnings"]) == 30
