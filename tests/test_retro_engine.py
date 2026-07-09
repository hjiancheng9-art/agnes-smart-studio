"""Tests for core/retro_engine.py — 回顾引擎"""

from core.retro_engine import retro_create, retro_list, retro_summarize


class TestRetroCreate:
    """创建回顾测试"""

    def test_create_basic(self):
        result = retro_create(
            project="CRUX",
            sprint="v6.0.0",
            what_went_well=["覆盖率高", "性能优化"],
            what_could_improve=["文档不足"],
            action_items=[{"task": "补测试", "owner": "dev", "deadline": "2025-03-01"}],
        )
        assert isinstance(result, dict)
        assert result["project"] == "CRUX"
        assert result["sprint"] == "v6.0.0"

    def test_create_minimal(self):
        result = retro_create(project="CRUX")
        assert isinstance(result, dict)

    def test_create_empty_lists(self):
        result = retro_create(
            project="CRUX",
            sprint="v1",
            what_went_well=[],
            what_could_improve=[],
            action_items=[],
        )
        assert isinstance(result, dict)

    def test_create_chinese_text(self):
        result = retro_create(
            project="CRUX",
            sprint="v1",
            what_went_well=["测试覆盖率大幅提升"],
        )
        assert isinstance(result, dict)

    def test_create_has_created_at(self):
        result = retro_create(project="CRUX")
        assert "created_at" in result

    def test_create_without_sprint(self):
        result = retro_create(project="CRUX")
        assert isinstance(result, dict)


class TestRetroList:
    """列出回顾测试"""

    def test_list_returns_list(self):
        retros = retro_list(project="CRUX")
        assert isinstance(retros, list)

    def test_list_all_projects(self):
        retros = retro_list()
        assert isinstance(retros, list)


class TestRetroSummarize:
    """回顾总结测试"""

    def test_summarize_returns_dict(self):
        retro_create(project="CRUX", what_went_well=["A"])
        summary = retro_summarize(project="CRUX")
        assert isinstance(summary, dict)

    def test_summarize_empty_project(self):
        summary = retro_summarize(project="NO_SUCH_PROJECT")
        assert isinstance(summary, dict)
