"""Tests for core.pipeline_state — pipeline orchestration engine."""

import pytest


class TestPipelinePresets:
    def test_pipeline_presets_exist(self):
        from core.pipeline_state import PIPELINES

        assert len(PIPELINES) >= 10

    def test_known_pipeline_ids(self):
        from core.pipeline_state import PIPELINES

        for pid in [
            "video-production",
            "comfyui-studio",
            "creative-image",
            "world-building",
            "self-evolve",
            "api-development",
        ]:
            assert pid in PIPELINES

    def test_pipeline_structure(self):
        from core.pipeline_state import PIPELINES

        for _pid, pipe in PIPELINES.items():
            assert "name" in pipe
            assert "skills" in pipe
            assert "output_type" in pipe
            assert isinstance(pipe["skills"], list)
            assert len(pipe["skills"]) > 0

    def test_qa_gates_reference_existing_skills(self):
        from core.pipeline_state import PIPELINES

        for pid, pipe in PIPELINES.items():
            for gate in pipe.get("qa_gates", []):
                assert gate in pipe["skills"], f"{pid}: QA gate '{gate}' not in skills"


class TestPipelineState:
    def test_basic_state(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        assert state.run_id == "run_001"
        assert state.data == {}
        assert state.step_results == {}
        assert state.assets == []
        assert state.qa_log == []
        assert state.current_step == ""

    def test_set_get(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.set("key", "value")
        assert state.get("key") == "value"
        assert state.get("missing", "default") == "default"

    def test_record_step(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.record_step("skill1", "result text here")
        assert "skill1" in state.step_results
        assert state.current_step == "skill1"
        # Truncation at 500 chars
        long_result = "x" * 600
        state.record_step("skill2", long_result)
        assert len(state.step_results["skill2"]) <= 500

    def test_add_asset(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.add_asset("img/001.png", "skill1", "test image")
        assert len(state.assets) == 1
        assert state.assets[0]["path"] == "img/001.png"
        assert state.assets[0]["step"] == "skill1"
        assert state.assets[0]["run_id"] == "run_001"

    def test_log_qa(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.log_qa("qc-inspector", True, "passed")
        assert len(state.qa_log) == 1
        assert state.qa_log[0]["passed"] is True

    def test_context_for_next_empty(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        assert state.context_for_next() == ""

    def test_context_for_next_with_steps(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.record_step("skill1", "previous result")
        ctx = state.context_for_next()
        assert "Previous step: skill1" in ctx
        assert "previous result" in ctx

    def test_context_for_next_with_constraints(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.set("constraints", "no nudity")
        ctx = state.context_for_next()
        assert "no nudity" in ctx

    def test_context_for_next_with_assets(self):
        from core.pipeline_state import PipelineState

        state = PipelineState("run_001")
        state.add_asset("a.png", "s1", "img1")
        state.add_asset("b.png", "s2", "img2")
        state.add_asset("c.png", "s3", "img3")
        state.add_asset("d.png", "s4", "img4")
        ctx = state.context_for_next()
        # Should show last 3 assets
        assert "Assets (4)" in ctx
        assert "d.png" in ctx


class TestPipelineEngine:
    def test_list_pipelines(self):
        from core.pipeline_state import PipelineEngine

        engine = PipelineEngine()
        pipelines = engine.list_pipelines()
        assert len(pipelines) >= 10
        for p in pipelines:
            assert "id" in p
            assert "name" in p
            assert "skills" in p

    def test_run_unknown_pipeline(self):
        from core.pipeline_state import PipelineEngine

        engine = PipelineEngine()
        with pytest.raises(ValueError, match="Unknown pipeline"):
            engine.run("nonexistent_pipeline", "input")

    def test_prev_step(self):
        from core.pipeline_state import PipelineEngine

        engine = PipelineEngine()
        assert engine._prev_step(["a", "b", "c"], "b") == "a"
        assert engine._prev_step(["a", "b", "c"], "a") is None

    def test_prev_step_missing(self):
        from core.pipeline_state import PipelineEngine

        engine = PipelineEngine()
        assert engine._prev_step(["a", "b"], "z") is None

    def test_check_quality_empty_output(self):
        from core.pipeline_state import PipelineEngine, PipelineState

        engine = PipelineEngine()
        engine.state = PipelineState("test")
        assert engine._check_quality("qc", "") is False
        assert engine._check_quality("qc", "[FAIL] something") is False

    def test_check_quality_good_output(self):
        from core.pipeline_state import PipelineEngine, PipelineState

        engine = PipelineEngine()
        engine.state = PipelineState("test")
        assert engine._check_quality("qc", "good output here") is True
