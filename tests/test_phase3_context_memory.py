"""Test Phase 3: Context memory — TokenBudget + 3-tier memory + Compiler"""

import time

import pytest

from core.context_memory import (
    CompiledContext,
    ContextCompiler,
    Episode,
    EpisodicMemory,
    Fact,
    MemoryItem,
    SemanticMemory,
    TokenBudgetTracker,
    WorkingMemory,
)

# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def budget():
    return TokenBudgetTracker(hard_limit=10000)


@pytest.fixture
def wm():
    return WorkingMemory(max_items=10)


@pytest.fixture
def em():
    return EpisodicMemory(max_episodes=5, summarize_every=3)


@pytest.fixture
def sm():
    return SemanticMemory(max_facts=10, persist=False)


@pytest.fixture
def compiler():
    return ContextCompiler(
        hard_token_limit=8000,
        enable_working_memory=True,
        enable_episodic_memory=True,
        enable_semantic_memory=True,
        enable_budget_tracker=True,
    )


# ── TokenBudgetTracker ──────────────────────────────────────────────


class TestTokenBudgetTracker:
    def test_normal_usage(self, budget):
        status = budget.check(6000)
        assert status.pct == 60.0
        assert status.remaining == 4000
        assert not status.should_compress

    def test_warn_threshold(self, budget):
        status = budget.check(7500)  # 75%
        assert status.should_compress
        assert len(status.warnings) >= 1

    def test_alert_threshold(self, budget):
        status = budget.check(8800)  # 88%
        assert status.should_compress
        assert status.should_alert_user

    def test_critical_threshold(self, budget):
        status = budget.check(9600)  # 96%
        assert status.should_compress
        assert any("CRITICAL" in w for w in status.warnings)

    def test_peak_tracking(self, budget):
        budget.check(3000)
        budget.check(7000)
        budget.check(2000)
        assert budget.stats["peak_usage"] == 7000

    def test_compression_recording(self, budget):
        budget.record_compression()
        budget.record_compression()
        assert budget.stats["compression_count"] == 2

    def test_suggest_action_compress(self, budget):
        act = budget.suggest_next_action(budget.check(9500))
        assert act == "compress_history"

    def test_suggest_action_summarize(self, budget):
        act = budget.suggest_next_action(budget.check(8000))
        assert act is not None

    def test_suggest_action_none(self, budget):
        act = budget.suggest_next_action(budget.check(1000))
        assert act is None

    def test_zero_limit(self):
        b = TokenBudgetTracker(hard_limit=0)
        status = b.check(100)
        assert status.pct == 0.0  # Avoid division by zero


# ── WorkingMemory ───────────────────────────────────────────────────


class TestWorkingMemory:
    def test_set_get(self, wm):
        wm.set("task", "Fix login bug", priority=10)
        assert wm.get("task") == "Fix login bug"

    def test_get_missing(self, wm):
        assert wm.get("nonexistent") == ""
        assert wm.get("nonexistent", "default") == "default"

    def test_delete(self, wm):
        wm.set("key", "val")
        wm.delete("key")
        assert wm.get("key") == ""

    def test_expiry(self, wm):
        wm.set("temp", "val", ttl=0.001)
        time.sleep(1.5)
        assert wm.get("temp") == ""

    def test_prune_oversize(self, wm):
        tiny = WorkingMemory(max_items=3)
        for i in range(10):
            tiny.set(f"k{i}", f"v{i}", priority=i % 5, ttl=999)
        tiny.prune()
        assert len(tiny._items) <= 3

    def test_prune_removes_expired_first(self, wm):
        wm.set("keep", "val", priority=10, ttl=999)
        wm.set("expire", "old", priority=10, ttl=0.001)
        time.sleep(1.5)
        wm.prune()
        assert wm.get("keep") == "val"
        assert wm.get("expire") == ""

    def test_snapshot(self, wm):
        wm.set("task", "Fix", priority=10, ttl=999)
        wm.set("file", "auth.py", priority=5, ttl=999)
        snap = wm.snapshot()
        assert "task=Fix" in snap
        assert "auth.py" in snap

    def test_snapshot_empty(self, wm):
        assert wm.snapshot() == ""

    def test_clear(self, wm):
        wm.set("a", "b")
        wm.clear()
        assert len(wm._items) == 0

    def test_to_dict(self, wm):
        wm.set("key", "val", priority=5)
        d = wm.to_dict()
        assert d["key"]["value"] == "val"
        assert d["key"]["priority"] == 5


# ── EpisodicMemory ──────────────────────────────────────────────────


class TestEpisodicMemory:
    def test_add_episode(self, em):
        turns = [{"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}]
        em.add(turns, ["tool1"], ["file.py"], "success")
        assert len(em.episodes) == 1
        assert em.episodes[0].outcome == "success"

    def test_snapshot(self, em):
        turns = [{"role": "user", "content": "Read code"}, {"role": "assistant", "content": "Done"}]
        em.add(turns, ["read_file"], ["app.py"], "success")
        snap = em.snapshot()
        assert "Read code" in snap

    def test_snapshot_empty(self, em):
        assert em.snapshot() == ""

    def test_fifo_eviction(self, em):
        tiny = EpisodicMemory(max_episodes=3, summarize_every=1)
        turns = [{"role": "user", "content": f"Q{i}"} for i in range(5)]
        for t in turns:
            tiny.add([t], [], [], "ok")
        assert len(tiny.episodes) == 3
        # Oldest should be evicted
        assert tiny.episodes[0].index > 0

    def test_episode_key_files(self, em):
        turns = [{"role": "user", "content": "Edit"}]
        em.add(turns, ["write_file"], ["config.py", "db.py"], "in_progress")
        assert "config.py" in em.episodes[0].key_files
        assert "db.py" in em.episodes[0].key_files

    def test_episode_to_dict(self, em):
        turns = [{"role": "user", "content": "Q"}]
        em.add(turns, ["tool"], ["file"], "success")
        d = em.to_dict()
        assert len(d) == 1
        assert d[0]["outcome"] == "success"


# ── SemanticMemory ──────────────────────────────────────────────────


class TestSemanticMemory:
    def test_remember_recall(self, sm):
        sm.remember("root", "/app", "source", 0.9, ["config"])
        assert sm.recall("root") == "/app"

    def test_recall_missing(self, sm):
        assert sm.recall("nonexistent") == ""

    def test_forget(self, sm):
        sm.remember("key", "val")
        sm.forget("key")
        assert sm.recall("key") == ""

    def test_query_by_tag(self, sm):
        sm.remember("a", "1", tags=["config"])
        sm.remember("b", "2", tags=["pref"])
        sm.remember("c", "3", tags=["config"])
        assert len(sm.query("config")) == 2
        assert len(sm.query("pref")) == 1
        assert len(sm.query("nonexistent")) == 0

    def test_prune_low_confidence(self, sm):
        tiny = SemanticMemory(max_facts=3, persist=False)
        for i in range(10):
            tiny.remember(f"f{i}", f"v{i}", confidence=0.1 + i * 0.05)
        assert len(tiny._facts) <= 3

    def test_snapshot(self, sm):
        sm.remember("root", "/app", "source", 1.0, ["config"])
        snap = sm.snapshot()
        assert "root" in snap

    def test_snapshot_empty(self, sm):
        assert sm.snapshot() == ""

    def test_to_dict(self, sm):
        sm.remember("key", "val", "src", 0.8, ["tag"])
        d = sm.to_dict()
        assert d["key"]["value"] == "val"
        assert d["key"]["confidence"] == 0.8


# ── ContextCompiler ─────────────────────────────────────────────────


class TestContextCompiler:
    def test_compile_empty(self, compiler):
        ctx = compiler.compile()
        assert not ctx.has_content  # No data yet

    def test_set_task(self, compiler):
        compiler.set_current_task("Fix authentication")
        ctx = compiler.compile()
        assert ctx.has_content
        assert "Fix authentication" in ctx.assemble()

    def test_record_turn(self, compiler):
        compiler.set_current_task("Fix auth")  # set task first to populate WM
        compiler.record_turn(
            "Read auth.py", "OK, reading", tool_calls=[{"name": "read_file", "arguments": {"path": "auth.py"}}]
        )
        assert compiler._total_turns == 1
        # track_tool_use is called internally by record_turn
        ctx = compiler.compile()
        assert ctx.has_content

    def test_compile_returns_compiled_context(self, compiler):
        ctx = compiler.compile(current_tokens=5000)
        assert isinstance(ctx, CompiledContext)
        assert ctx.budget_status is not None

    def test_inject_into_prompt(self, compiler):
        compiler.set_current_task("Test")
        prompt = compiler.inject_into_system_prompt("You are helpful.", current_tokens=2000)
        assert len(prompt) > len("You are helpful.")
        assert "Test" in prompt

    def test_inject_empty(self, compiler):
        prompt = compiler.inject_into_system_prompt("Base", current_tokens=1000)
        assert prompt == "Base" or len(prompt) >= len("Base")

    def test_stats(self, compiler):
        compiler.set_current_task("Test")
        stats = compiler.stats
        assert "total_turns" in stats
        assert "working_memory_items" in stats
        assert "episodes" in stats
        assert "semantic_facts" in stats
        assert "budget" in stats

    def test_episode_creation_on_threshold(self):
        cc = ContextCompiler(
            enable_episodic_memory=True,
            enable_working_memory=False,
            enable_semantic_memory=False,
            enable_budget_tracker=False,
        )
        cc.episodic.summarize_every = 2
        cc.record_turn("Q1", "A1")
        cc.record_turn("Q2", "A2")
        cc.record_turn("Q3", "A3")
        cc.record_turn("Q4", "A4")
        assert len(cc.episodic.episodes) >= 1


# ── CompiledContext ──────────────────────────────────────────────────


class TestCompiledContext:
    def test_has_content_false(self):
        ctx = CompiledContext()
        assert not ctx.has_content

    def test_has_content_true(self):
        ctx = CompiledContext(working_memory="[W]", episodic_memory="[E]")
        assert ctx.has_content

    def test_assemble(self):
        ctx = CompiledContext(working_memory="W", episodic_memory="E", semantic_memory="S")
        assembled = ctx.assemble()
        assert "W" in assembled
        assert "E" in assembled
        assert "S" in assembled

    def test_assemble_skips_empty(self):
        ctx = CompiledContext(working_memory="W")
        assembled = ctx.assemble()
        assert "W" in assembled
        assert "---" not in assembled or len(assembled.split("---")) == 2  # Only separator for solo section


# ── MemoryItem and Episode and Fact ──────────────────────────────────


class TestModels:
    def test_memory_item_expired(self):
        item = MemoryItem(key="k", value="v", priority=0, created_at=0, ttl_seconds=0.001)
        assert item.expired  # Past TTL

    def test_memory_item_not_expired(self):
        now = time.time()
        item = MemoryItem(key="k", value="v", priority=0, created_at=now, ttl_seconds=60)
        assert not item.expired

    def test_episode_fields(self):
        ep = Episode(
            index=1,
            summary="summary",
            turn_count=3,
            tools_used=["a"],
            key_files=["f.py"],
            outcome="ok",
            timestamp=time.time(),
        )
        assert ep.index == 1
        assert ep.turn_count == 3

    def test_fact_fields(self):
        now = time.time()
        f = Fact(key="k", value="v", source="s", confidence=0.5, created_at=now, tags=["t"])
        assert f.confidence == 0.5
        assert f.tags == ["t"]
