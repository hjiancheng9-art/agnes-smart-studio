"""Test P13: Field Arena — reality gap closure."""

import os
import time

import pytest

from core.benchmark.runner import BenchmarkResult, TaskResult
from core.benchmark.scorer import BenchmarkScorecard
from core.field_arena import (
    FieldArena,
    FieldRecorder,
    FieldReplayRunner,
    FieldScorecard,
    FieldSession,
    FieldTurn,
    ReplaySessionResult,
)


@pytest.fixture
def sample_session():
    s = FieldSession(id="field-001", source="manual", created_at=time.time())
    s.turns.append(
        FieldTurn(
            user_message="Read auth.py",
            assistant_response="Here is auth.py content...",
            tool_calls=[{"name": "read_file", "arguments": {"path": "auth.py"}}],
            duration_ms=150.0,
            success=True,
        )
    )
    s.turns.append(
        FieldTurn(
            user_message="Fix the login bug",
            assistant_response="Fixed! Changed line 42.",
            tool_calls=[{"name": "edit_file", "arguments": {"path": "auth.py"}}],
            duration_ms=200.0,
            success=True,
        )
    )
    return s


@pytest.fixture
def recorder():
    return FieldRecorder(storage_dir="/tmp/_p13_test")


@pytest.fixture
def arena():
    return FieldArena(storage_dir="/tmp/_p13_test_arena")


class TestFieldTurn:
    def test_defaults(self):
        t = FieldTurn()
        assert t.user_message == ""
        assert t.tool_calls == []


class TestFieldSession:
    def test_creation(self, sample_session):
        assert sample_session.id == "field-001"
        assert sample_session.total_turns == 2
        assert sample_session.total_duration_ms == 350.0

    def test_to_dict(self, sample_session):
        d = sample_session.to_dict()
        assert d["id"] == "field-001"
        assert d["total_turns"] == 2


class TestFieldRecorder:
    def test_new_session(self, recorder):
        s = recorder.new_session("manual", ["debug"])
        assert s.source == "manual"
        assert "debug" in s.tags

    def test_record_turn(self, recorder):
        recorder.new_session("test")
        recorder.record_turn("Hello", "Hi there", duration_ms=50.0)
        session = recorder.finish_session()
        assert session is not None
        assert session.total_turns == 1

    def test_save_and_load(self, recorder, sample_session):
        path = recorder.save(sample_session)
        assert os.path.exists(path)
        loaded = recorder.load("field-001")
        assert loaded is not None
        assert loaded.id == "field-001"
        assert loaded.total_turns == 2

    def test_list_sessions(self, recorder, sample_session):
        recorder.save(sample_session)
        sessions = recorder.list_sessions()
        assert len(sessions) >= 1
        assert sessions[0]["id"] == "field-001"

    def test_load_nonexistent(self, recorder):
        loaded = recorder.load("no-such-session")
        assert loaded is None


class TestFieldReplayRunner:
    def test_replay_turn_no_callback(self):
        runner = FieldReplayRunner()
        turn = FieldTurn(user_message="Hello", assistant_response="Hi there")
        result = runner.replay_turn(turn)
        assert result.turn_index == 0
        assert result.replayed_response == "(no LLM callback)"

    def test_replay_turn_with_callback(self):
        runner = FieldReplayRunner(llm_callback=lambda msg: "Hi there back")
        turn = FieldTurn(user_message="Hello", assistant_response="Hi there")
        result = runner.replay_turn(turn)
        assert result.replayed_response == "Hi there back"

    def test_replay_session(self, sample_session):
        runner = FieldReplayRunner()
        result = runner.replay_session(sample_session)
        assert result.session_id == "field-001"
        assert result.total_turns == 2

    def test_text_similarity(self):
        runner = FieldReplayRunner()
        sim = runner._text_similarity("hello world", "hello world and more")
        assert sim >= 0.5
        sim2 = runner._text_similarity("abc", "xyz")
        assert sim2 == 0.0


class TestFieldScorecard:
    def test_no_data(self):
        sc = FieldScorecard()
        sc.compute()
        assert sc.overall_score == 0.0

    def test_with_benchmark(self):
        bs = BenchmarkScorecard(suite_name="t", overall_score=80.0, pass_rate=75.0)
        sc = FieldScorecard(benchmark_scorecard=bs)
        sc.compute()
        assert sc.overall_score > 0

    def test_with_field_results(self):
        r1 = ReplaySessionResult(session_id="s1", total_turns=10, matched_turns=7, match_rate=70.0)
        bs = BenchmarkScorecard(suite_name="t", overall_score=80.0, pass_rate=75.0)
        sc = FieldScorecard(benchmark_scorecard=bs, field_results=[r1], field_weight=0.3)
        sc.compute()
        # 80 * 0.7 + 70 * 0.3 = 56 + 21 = 77
        assert abs(sc.overall_score - 77.0) < 1

    def test_summary(self):
        r1 = ReplaySessionResult(session_id="s1", total_turns=5, matched_turns=4, match_rate=80.0)
        bs = BenchmarkScorecard(suite_name="t", overall_score=90.0, pass_rate=85.0)
        sc = FieldScorecard(benchmark_scorecard=bs, field_results=[r1])
        sc.compute()
        s = sc.summary()
        assert "Arena" in s


class TestFieldArena:
    def test_add_session(self, arena, sample_session):
        arena.add_session(sample_session)
        assert len(arena._field_sessions) >= 1

    def test_evaluate_no_sessions(self, arena):
        bs = BenchmarkScorecard(suite_name="t", overall_score=80.0, pass_rate=75.0)
        sc = arena.evaluate(bs)
        assert sc.benchmark_scorecard is not None

    def test_release_gate_pass(self, arena):
        bs = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        sc = FieldScorecard(benchmark_scorecard=bs, overall_field_pass_rate=80.0, overall_score=82.0)
        result = arena.release_gate(sc, min_benchmark_score=70.0, min_field_pass_rate=60.0)
        assert result.decision == "pass"

    def test_release_gate_block_field(self, arena):
        bs = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        sc = FieldScorecard(benchmark_scorecard=bs, overall_field_pass_rate=30.0, overall_score=50.0)
        result = arena.release_gate(sc, min_benchmark_score=70.0, min_field_pass_rate=60.0)
        assert result.decision == "block"

    def test_compare(self, arena):
        bs_before = BenchmarkScorecard(suite_name="t", overall_score=70.0, pass_rate=65.0)
        bs_after = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        comparison = arena.compare(bs_before, bs_after)
        assert "70.0" in comparison
        assert "85.0" in comparison


class TestIntegration:
    def test_validation_layer_has_field_arena(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        assert hasattr(vl, "_field_arena")

    def test_record_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        session = FieldSession(id="vl-test", source="manual")
        session.turns.append(FieldTurn(user_message="hi", assistant_response="hello"))
        vl.record_field_session(session)
        results = vl.field_replay_all()
        assert len(results) >= 1

    def test_field_evaluate_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        tr = TaskResult(task_id="t1", category="qa", difficulty="easy", success=True, response="ok", score=90.0)
        br = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[tr])
        sc = vl.field_evaluate(br)
        assert sc.overall_score > 0

    def test_release_gate_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        bs = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        sc = FieldScorecard(benchmark_scorecard=bs, overall_field_pass_rate=80.0, overall_score=82.0)
        result = vl.field_release_gate(sc)
        assert result.decision in ("pass", "warn", "block")

    def test_ab_compare_through_layer(self):
        from core.tool_validation_integration import ValidationLayer

        vl = ValidationLayer()
        t1 = TaskResult(task_id="t1", category="qa", difficulty="easy", success=True, response="a", score=70.0)
        t2 = TaskResult(task_id="t1", category="qa", difficulty="easy", success=True, response="b", score=90.0)
        br_before = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[t1])
        br_after = BenchmarkResult(suite_name="test", total_tasks=1, passed=1, failed=0, task_results=[t2])
        comparison = vl.field_ab_compare(br_before, br_after)
        assert "70.0" in comparison

    def test_chat_p13_flag(self):
        import py_compile

        py_compile.compile("core/chat.py", doraise=True)

    def test_field_session_empty_turns(self):
        s = FieldSession(id="empty-test")
        assert s.total_turns == 0
        assert s.total_duration_ms == 0.0

    def test_field_session_to_dict_empty(self):
        s = FieldSession(id="empty-dict")
        d = s.to_dict()
        assert d["total_turns"] == 0

    def test_field_recorder_finish_none(self):
        r = FieldRecorder(storage_dir="/tmp/_p13_test_none")
        assert r.finish_session() is None

    def test_replay_turn_both_empty(self):
        runner = FieldReplayRunner(llm_callback=lambda m: "")
        turn = FieldTurn(user_message="", assistant_response="")
        result = runner.replay_turn(turn)
        assert result.match  # both empty = match

    def test_replay_turn_with_callback_match(self):
        runner = FieldReplayRunner(llm_callback=lambda m: "exact match")
        turn = FieldTurn(user_message="hello", assistant_response="exact match")
        result = runner.replay_turn(turn)
        assert result.similarity > 0.5

    def test_replay_session_result_pass_rate(self):
        r = ReplaySessionResult(session_id="s1", total_turns=10, matched_turns=8)
        assert r.pass_rate == 80.0

    def test_replay_session_result_empty(self):
        r = ReplaySessionResult()
        assert r.pass_rate == 0.0

    def test_arena_compare_with_dims(self):
        from core.benchmark.scorer import DimensionScore

        bs_before = BenchmarkScorecard(suite_name="t", overall_score=70.0, pass_rate=65.0)
        bs_before.dimensions = [DimensionScore(name="code_gen", pass_rate=60.0, avg_score=65.0)]
        bs_after = BenchmarkScorecard(suite_name="t", overall_score=85.0, pass_rate=80.0)
        bs_after.dimensions = [DimensionScore(name="code_gen", pass_rate=80.0, avg_score=82.0)]
        arena = FieldArena(storage_dir="/tmp/_p13_arena_compare")
        comp = arena.compare(bs_before, bs_after)
        assert "code_gen" in comp

    def test_field_scorecard_no_benchmark(self):
        sc = FieldScorecard(field_weight=0.5)
        sc.compute()
        assert sc.overall_score == 0.0

    def test_field_scorecard_replay_result(self, sample_session):
        from core.field_arena import FieldReplayRunner

        runner = FieldReplayRunner()
        replay_result = runner.replay_session(sample_session)
        bs = BenchmarkScorecard(suite_name="t", overall_score=80.0, pass_rate=75.0)
        sc = FieldScorecard(benchmark_scorecard=bs, field_results=[replay_result])
        sc.compute()
        assert sc.overall_score > 0
