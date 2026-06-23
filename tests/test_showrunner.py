"""Unit tests for Showrunner pipeline templates and planning logic.

Tests the pure-logic parts (plan selection, template structure) without
needing a real API client. The generation steps are tested via mock client.
"""
import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.showrunner import (
    Showrunner, PipelineTemplates, StepKind, SourceKind,
    StepResult, PipelineRun, create_showrunner, list_pipeline_templates,
)


class TestPipelineTemplates:
    def test_short_video_template(self):
        steps = PipelineTemplates.short_video("cats")
        assert len(steps) == 7
        assert steps[0]["step"] == "brainstorm"
        assert steps[-1]["step"] == "deliver"
        # 图片步骤有 fallback
        img_step = next(s for s in steps if s["kind"] == StepKind.IMAGE)
        assert "fallback" in img_step

    def test_concept_art_template(self):
        steps = PipelineTemplates.concept_art("warrior")
        assert len(steps) == 5
        assert steps[0]["step"] == "explore"
        assert steps[-1]["step"] == "deliver"

    def test_novel_chapter_template(self):
        steps = PipelineTemplates.novel_chapter("chapter 1")
        assert len(steps) == 5
        assert steps[0]["step"] == "expand"
        assert steps[-1]["step"] == "deliver"

    def test_custom_template(self):
        specs = [
            {"name": "step1", "kind": "think", "source": "agnes"},
            {"name": "step2", "kind": "image", "source": "comfyui", "fallback": "external"},
        ]
        steps = PipelineTemplates.custom("goal", specs)
        assert len(steps) == 2
        assert steps[0]["kind"] == StepKind.THINK
        assert steps[1]["fallback"] == SourceKind.EXTERNAL

    def test_custom_template_unknown_kind_defaults_to_custom(self):
        steps = PipelineTemplates.custom("g", [{"name": "s", "kind": "unknown", "source": "agnes"}])
        assert steps[0]["kind"] == StepKind.CUSTOM


class TestShowrunnerPlanning:
    def setup_method(self):
        self.sr = create_showrunner()

    def test_plan_video_keywords(self):
        for kw in ["video", "animation", "short", "clip", "tiktok"]:
            plan = self.sr.plan(f"make a {kw} about cats")
            assert plan[0]["step"] == "brainstorm"
            assert len(plan) == 7

    def test_plan_concept_keywords(self):
        for kw in ["concept", "character", "illustration", "scene", "art"]:
            plan = self.sr.plan(f"create {kw} design")
            assert plan[0]["step"] == "explore"

    def test_plan_novel_keywords(self):
        for kw in ["novel", "story", "script", "write"]:
            plan = self.sr.plan(f"{kw} a chapter")
            assert plan[0]["step"] == "expand"

    def test_plan_default_fallback(self):
        plan = self.sr.plan("do something random")
        assert plan[0]["step"] == "think"
        assert len(plan) == 4

    def test_plan_is_case_insensitive(self):
        plan = self.sr.plan("MAKE A VIDEO")
        assert plan[0]["step"] == "brainstorm"


class TestShowrunnerExecution:
    def setup_method(self):
        """用 mock client 测试执行逻辑。"""
        from unittest.mock import MagicMock
        self.mock_client = MagicMock()
        self.mock_client.chat.return_value = {
            "choices": [{"message": {"content": "mock response"}}]
        }
        self.sr = Showrunner(client=self.mock_client)

    def test_think_without_client(self):
        sr = Showrunner(client=None)
        result = asyncio.run(sr._think("test"))
        assert result == {"thought": "test"}

    def test_think_with_client(self):
        result = asyncio.run(self.sr._think("analyze this"))
        assert result["thought"] == "mock response"

    def test_gen_prompt_stores_context(self):
        result = asyncio.run(self.sr._gen_prompt("a dragon"))
        assert result["prompt"] == "mock response"
        assert self.sr._context["last_prompt"] == "mock response"

    def test_run_full_pipeline(self):
        """测试完整流水线执行（think + deliver，跳过需要外部依赖的步骤）。"""
        sr = Showrunner(client=self.mock_client)
        # 自定义只含 think + deliver 的简单流水线
        pipeline = [
            {"step": "think", "kind": StepKind.THINK, "desc": "plan", "source": SourceKind.AGNES},
            {"step": "deliver", "kind": StepKind.DELIVER, "desc": "output", "source": SourceKind.CLI},
        ]
        rec = asyncio.run(sr.run("test goal", pipeline=pipeline))
        assert isinstance(rec, PipelineRun)
        assert rec.goal == "test goal"
        assert len(rec.steps) == 2
        assert rec.status == "completed"
        assert all(s.success for s in rec.steps)

    def test_on_step_callback(self):
        events = []
        sr = Showrunner(client=self.mock_client)
        sr.on_step(lambda name, status: events.append((name, status)))
        pipeline = [{"step": "think", "kind": StepKind.THINK, "desc": "x", "source": SourceKind.AGNES}]
        asyncio.run(sr.run("g", pipeline=pipeline))
        assert ("think", "running") in events
        assert ("think", "done") in events


class TestHelpers:
    def test_create_showrunner_returns_instance(self):
        sr = create_showrunner()
        assert isinstance(sr, Showrunner)

    def test_list_pipeline_templates(self):
        tpls = list_pipeline_templates()
        assert "short_video" in tpls
        assert "concept_art" in tpls
        assert "novel_chapter" in tpls

    def test_step_result_defaults(self):
        r = StepResult(step_name="x", kind=StepKind.THINK, source=SourceKind.AGNES)
        assert r.success is False
        assert r.retries == 0
        assert r.artifacts == []
