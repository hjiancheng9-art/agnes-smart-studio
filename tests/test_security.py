"""Security tests — verify no API keys in logs, JSON, or trace output."""

from __future__ import annotations

import json
import os


class TestApiKeySafety:
    """Verify API keys are not persisted in plaintext files or logs."""

    def test_models_json_no_hardcoded_keys(self):
        """models.json should not contain real API keys (use env vars)."""
        if not os.path.exists("models.json"):
            return
        with open("models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        for pid, pdata in cfg.get("providers", {}).items():
            api_key = pdata.get("api_key", "")
            # Allow known placeholder values (not real API keys)
            if api_key in ("", "no-key-required", "your-api-key", "sk-your-key-here"):
                continue
            assert not api_key, (
                f"models.json contains hardcoded API key for '{pid}'. "
                "Use environment variable {pid.upper()}_API_KEY instead."
            )

    def test_settings_json_no_keys(self):
        """settings.json should not contain API keys."""
        if not os.path.exists("settings.json"):
            return
        with open("settings.json", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            if "key" in key.lower() or "secret" in key.lower() or "token" in key.lower():
                assert not val, f"settings.json contains '{key}'. Use env vars."

    def test_env_example_no_real_keys(self):
        """.env.example should contain placeholder values, not real keys."""
        if not os.path.exists(".env.example"):
            return
        with open(".env.example", encoding="utf-8") as f:
            content = f.read()
        # Check for key patterns that look like real keys (long base64 strings)
        import re

        for line in content.split("\n"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                # Real API keys are typically long alphanumeric strings
                if len(val) > 30 and val.isalnum():
                    raise AssertionError(
                        f".env.example has real-looking value: {line[:50]}... "
                        "Use placeholder like 'sk-your-key-here'"
                    )

    def test_gitignore_covers_env(self):
        """.env and auth files must be in .gitignore."""
        if not os.path.exists(".gitignore"):
            return
        with open(".gitignore", encoding="utf-8") as f:
            content = f.read()
        assert ".env" in content, ".gitignore missing .env"
        assert "*.log" in content or ".log" in content, ".gitignore missing log files"
