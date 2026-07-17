"""Tests for core/export.py — 导出引擎"""

from core.export import ExportEngine, export_assets, export_chat


class TestExportEngine:
    def test_create(self):
        engine = ExportEngine()
        assert engine is not None

    def test_asset_list(self):
        engine = ExportEngine()
        result = engine.asset_list()
        assert isinstance(result, dict)
        assert "exports" in result

    def test_config_snapshot(self):
        engine = ExportEngine()
        result = engine.config_snapshot()
        assert isinstance(result, str)
        assert result.endswith(".json")

    def test_conversation_to_md(self):
        engine = ExportEngine()
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        result = engine.conversation_to_md(msgs)
        assert isinstance(result, str)
        assert len(result) > 0


class TestModuleFunctions:
    def test_export_chat(self):
        result = export_chat([{"role": "user", "content": "test"}])
        assert result is not None

    def test_export_assets(self):
        result = export_assets()
        assert result is not None
