"""Tests for core/docs_engine.py — 文档引擎"""

from core.docs_engine import generate_all, generate_help_md, sync_agents_md, sync_manifest


class TestDocsEngine:
    def test_generate_all(self):
        result = generate_all()
        assert isinstance(result, dict)

    def test_generate_help_md(self):
        result = generate_help_md()
        assert isinstance(result, str)

    def test_sync_agents_md(self):
        result = sync_agents_md()
        assert isinstance(result, str)

    def test_sync_manifest(self):
        result = sync_manifest()
        assert isinstance(result, dict)
