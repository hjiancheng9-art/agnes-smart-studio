"""Tests for utils/provider_switcher.py — provider switching and .env sync."""

import json
from unittest.mock import patch

from utils.provider_switcher import ROOT, switch_provider


class TestConstants:
    def test_root_exists(self):
        assert ROOT.exists()


class TestSwitchProvider:
    def test_unknown_provider(self):
        with patch("utils.provider_switcher.json.loads") as mock_load:
            mock_load.return_value = {"providers": {"deepseek": {}}}
            ok, msg = switch_provider("nonexistent")
            assert ok is False
            assert "Unknown" in msg

    def test_broken_models_json(self):
        with patch("utils.provider_switcher.json.loads", side_effect=json.JSONDecodeError("bad", "", 0)):
            ok, msg = switch_provider("deepseek")
            assert ok is False
            assert "error" in msg.lower()

    def test_switches_and_writes_models_json(self, tmp_path):
        models_path = tmp_path / "models.json"
        models_path.write_text(
            json.dumps({"providers": {"deepseek": {"base_url": "https://api.deepseek.com", "api_key": "sk-test", "name": "DeepSeek"}}}),
            encoding="utf-8",
        )
        env_path = tmp_path / ".env"
        env_path.write_text("CRUX_BASE_URL=old\nCRUX_API_KEY=old-key\nOTHER=keep\n", encoding="utf-8")

        with patch("utils.provider_switcher.ROOT", tmp_path):
            ok, msg = switch_provider("deepseek")
            assert ok is True
            assert "deepseek" in msg

            # Check models.json updated
            data = json.loads(models_path.read_text(encoding="utf-8"))
            assert data["active"] == "deepseek"

            # Check .env synced
            env_content = env_path.read_text(encoding="utf-8")
            assert "https://api.deepseek.com" in env_content
            assert "sk-test" in env_content
            assert "OTHER=keep" in env_content  # unrelated lines preserved

    def xtest_returns_error_for_missing_file(self):
        with patch("utils.provider_switcher.ROOT").root as mock_root:
            mock_root.__truediv__.return_value.read_text.side_effect = OSError
            ok, msg = switch_provider("deepseek")
            assert ok is False
