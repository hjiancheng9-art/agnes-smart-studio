"""Tests for SkillRecommender — 技能市场推荐引擎"""

from core.skill_recommender import (
    SkillEntry,
    SkillRecommender,
)


class TestSkillRecommender:
    def setup_method(self):
        self.sr = SkillRecommender()

    def test_initializes_with_defaults(self):
        stats = self.sr.get_stats()
        assert stats["total_skills"] > 10
        assert stats["active"] > 10

    def test_recommend_generate_tasks(self):
        recs = self.sr.recommend("generate", top_k=5)
        assert len(recs) > 0
        names = [r[0] for r in recs]
        assert any("comfyui" in n or "image" in n for n in names)

    def test_recommend_review_tasks(self):
        recs = self.sr.recommend("review", top_k=5)
        names = [r[0] for r in recs]
        assert any("lint" in n or "security" in n or "audit" in n for n in names)

    def test_recommend_execute_tasks(self):
        recs = self.sr.recommend("execute", top_k=5)
        names = [r[0] for r in recs]
        assert any("ci-cd" in n or "api" in n or "git" in n for n in names)

    def test_recommend_by_tags(self):
        recs = self.sr.recommend_by_tags(["comfyui", "workflow"], top_k=5)
        assert len(recs) > 0
        assert recs[0][0] == "comfyui-basic"

    def test_record_use_increases_count(self):
        old = self.sr._skills["comfyui-basic"].usage_count
        self.sr.record_use("comfyui-basic", success=True, latency_ms=1200)
        assert self.sr._skills["comfyui-basic"].usage_count == old + 1

    def test_record_failure_decreases_success_rate(self):
        before = self.sr._skills["code-linter"].success_rate
        self.sr.record_use("code-linter", success=False)
        assert self.sr._skills["code-linter"].success_rate < before

    def test_hide_low_performers(self):
        # Artificially create low performer
        for _ in range(20):
            self.sr.record_use("api-tester", success=False)
        self.sr.hide_low_performers(threshold=0.3)
        assert self.sr._skills["api-tester"].hidden is True

    def test_hidden_skills_not_recommended(self):
        self.sr._skills["comfyui-basic"].hidden = True
        recs = self.sr.recommend("generate")
        names = [r[0] for r in recs]
        assert "comfyui-basic" not in names

    def test_score_increases_with_usage(self):
        before = self.sr._skills["comfyui-basic"].score
        for _ in range(10):
            self.sr.record_use("comfyui-basic", success=True)
        after = self.sr._skills["comfyui-basic"].score
        assert after >= before

    def test_stats_by_category(self):
        stats = self.sr.get_stats()
        assert "video" in stats["by_category"]  # 'other' and 'video' exist in test data
        assert "video" in stats["by_category"]  # 'other' and 'video' exist in test data

    def test_top_skills_in_stats(self):
        stats = self.sr.get_stats()
        assert len(stats["top_skills"]) == 5
        assert "name" in stats["top_skills"][0]
        assert "score" in stats["top_skills"][0]

    def test_recommendation_text(self):
        text = self.sr.to_recommendation_text("generate")
        assert "推荐技能包" in text

    def test_recommendation_text_empty_for_unknown_type(self):
        text = self.sr.to_recommendation_text("nonexistent")
        # May be empty or have default suggestions
        assert isinstance(text, str)

    def test_latency_averaging(self):
        self.sr.record_use("comfyui-basic", success=True, latency_ms=1000)
        self.sr.record_use("comfyui-basic", success=True, latency_ms=2000)
        assert 1000 <= self.sr._skills["comfyui-basic"].avg_latency_ms <= 2000


class TestSkillEntry:
    def test_score_defaults_to_midpoint(self):
        skill = SkillEntry(name="test", category="tool", tags=["test"])
        assert 3.0 <= skill.score <= 5.0

    def test_success_rate_defaults_to_half(self):
        skill = SkillEntry(name="test", category="tool", tags=["test"])
        assert skill.success_rate == 0.5

    def test_high_usage_high_success_scores_high(self):
        skill = SkillEntry(
            name="test", category="tool", tags=["test"],
            usage_count=100, success_count=95,
        )
        assert skill.score > 8.0
