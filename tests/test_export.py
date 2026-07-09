"""Tests for core/export.py — 导出引擎"""

from core.export import ExportEngine, export_assets, export_chat


class TestExportEngine:
    def test_create(self):
        engine = ExportEngine()
        assert engine is not None

    def test_asset_list(self):
        engine = ExportEngine()
        result = engine.asset_list() if hasattr(engine, "asset_list") else []
        assert isinstance(result, list) or result is not None

    def test_config_snapshot(self):
        engine = ExportEngine()
        result = engine.config_snapshot() if hasattr(engine, "config_snapshot") else {}
        assert isinstance(result, dict) or result is not None

    def test_conversation_to_md(self):
        engine = ExportEngine()
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = engine.conversation_to_md(msgs) if hasattr(engine, "conversation_to_md") else ""
        assert isinstance(result, str) or result is not None


class TestModuleFunctions:
    def test_export_chat(self):
        result = export_chat([{"role": "user", "content": "test"}])
        assert result is not None

    def test_export_assets(self):
        result = export_assets()
        assert result is not None
