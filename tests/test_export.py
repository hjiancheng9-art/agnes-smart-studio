"""Tests for core.export — conversation/asset/config export engine."""

import json
from pathlib import Path


class TestExportEngine:
    def _make_engine(self, tmp_path):
        from core.export import ExportEngine

        return ExportEngine(root=tmp_path)

    def test_init_creates_export_dir(self, tmp_path):
        self._make_engine(tmp_path)
        assert (tmp_path / "output" / "exports").exists()

    def test_conversation_to_md_writes_file(self, tmp_path):
        engine = self._make_engine(tmp_path)
        messages = [
            {"role": "user", "content": "Hello there"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ]
        path = engine.conversation_to_md(messages, title="My Chat")
        p = Path(path)
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "# My Chat" in text
        assert "### USER" in text
        assert "### ASSISTANT" in text
        assert "Hello there" in text
        assert p.name.startswith("chat_")
        assert p.suffix == ".md"

    def test_conversation_to_md_handles_list_content(self, tmp_path):
        """Multimodal content (list of parts) should be flattened to text."""
        engine = self._make_engine(tmp_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                    {"type": "image_url", "image_url": {"url": "x"}},
                ],
            },
        ]
        path = engine.conversation_to_md(messages)
        text = Path(path).read_text(encoding="utf-8")
        assert "part one" in text
        assert "part two" in text

    def test_conversation_to_md_handles_non_string_content(self, tmp_path):
        engine = self._make_engine(tmp_path)
        messages = [{"role": "user", "content": 12345}]
        path = engine.conversation_to_md(messages)
        text = Path(path).read_text(encoding="utf-8")
        assert "12345" in text

    def test_conversation_to_md_truncates_long_content(self, tmp_path):
        engine = self._make_engine(tmp_path)
        long_msg = "x" * 10000
        messages = [{"role": "user", "content": long_msg}]
        path = engine.conversation_to_md(messages)
        text = Path(path).read_text(encoding="utf-8")
        # content is capped at 5000 chars in the body
        assert "x" * 5000 in text
        assert "x" * 6000 not in text

    def test_asset_list_returns_categories(self, tmp_path):
        engine = self._make_engine(tmp_path)
        # Create a fake image so the list is non-empty
        img_dir = tmp_path / "output" / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "a.png").write_bytes(b"fake")
        assets = engine.asset_list()
        assert "images" in assets
        assert "videos" in assets
        assert "exports" in assets
        assert any(a["name"] == "a.png" for a in assets["images"])

    def test_asset_list_handles_missing_dirs(self, tmp_path):
        engine = self._make_engine(tmp_path)
        assets = engine.asset_list()
        assert assets == {"images": [], "videos": [], "exports": []}

    def test_config_snapshot_includes_existing_files(self, tmp_path):
        engine = self._make_engine(tmp_path)
        (tmp_path / "models.json").write_text(json.dumps({"m": 1}), encoding="utf-8")
        (tmp_path / "tools.json").write_text(json.dumps({"t": 2}), encoding="utf-8")
        path = engine.config_snapshot()
        p = Path(path)
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "models.json" in data
        assert data["models.json"] == {"m": 1}
        assert data["tools.json"] == {"t": 2}

    def test_config_snapshot_skips_missing_files(self, tmp_path):
        engine = self._make_engine(tmp_path)
        path = engine.config_snapshot()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        # No config files present → empty snapshot
        assert data == {}


class TestModuleFunctions:
    def test_export_chat_returns_path(self, tmp_path, monkeypatch):
        from core import export as export_mod

        # Redirect ROOT so we don't pollute the real project
        monkeypatch.setattr(export_mod, "ROOT", tmp_path)
        path = export_mod.export_chat([{"role": "user", "content": "hi"}], "T")
        assert Path(path).exists()

    def test_export_assets_returns_dict(self, tmp_path, monkeypatch):
        from core import export as export_mod

        monkeypatch.setattr(export_mod, "ROOT", tmp_path)
        assets = export_mod.export_assets()
        assert isinstance(assets, dict)
        assert "images" in assets
