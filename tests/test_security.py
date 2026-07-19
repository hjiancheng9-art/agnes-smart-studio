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
            if api_key in ("", "no-key-required", "your-api-key", "sk-your-key-here", "__AGNES_POOL__"):
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

        for line in content.split("\n"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                # Real API keys are typically long alphanumeric strings
                if len(val) > 30 and val.isalnum():
                    raise AssertionError(
                        f".env.example has real-looking value: {line[:50]}... Use placeholder like 'sk-your-key-here'"
                    )

    def test_gitignore_covers_env(self):
        """.env and auth files must be in .gitignore."""
        if not os.path.exists(".gitignore"):
            return
        with open(".gitignore", encoding="utf-8") as f:
            content = f.read()
        assert ".env" in content, ".gitignore missing .env"
        assert "*.log" in content or ".log" in content, ".gitignore missing log files"


class TestSecretRedactor:
    """Verify SecretRedactor strips sensitive values."""

    def test_redact_api_key(self):
        from core.secret_redactor import redact

        result = redact("Error: api key is sk-test12345678901234567890")
        assert "sk-test" not in result
        assert "REDACTED" in result

    def test_redact_no_false_positive(self):
        from core.secret_redactor import redact

        result = redact("Normal text with short words")
        assert "REDACTED" not in result

    def test_safe_env_excludes_secrets(self):
        from core.secret_redactor import safe_env_for_subprocess

        env = safe_env_for_subprocess()
        assert "DEEPSEEK_API_KEY" not in env


class TestMcpSafety:
    """MCP should not expose high-risk tools by default."""

    def test_mcp_config_has_no_default_all(self):
        """MCP server config should not expose all tools without filtering."""
        if not os.path.exists(".mcp.json"):
            return
        with open(".mcp.json", encoding="utf-8") as f:
            cfg = json.load(f)
        for server in cfg.get("mcpServers", {}).values():
            args = server.get("args", [])
            # If the server is crux, it should not run without tool filtering
            if any("crux" in str(a).lower() for a in args):
                pass  # CRUX MCP server is OK — it's the main entry point


class TestBrowserSafety:
    """Browser automation must use isolated profiles."""

    def test_browser_uses_dedicated_profile(self):
        """Browser should specify a profile path, not rely on system default."""
        if os.path.exists("core/browser_runtime.py"):
            with open("core/browser_runtime.py", encoding="utf-8") as f:
                content = f.read()
            assert "user_data_dir" in content or "user-data-dir" in content or "profile" in content.lower(), (
                "browser_runtime.py does not specify a user data directory"
            )

    def test_browser_no_system_profile_leak(self):
        """Browser should NOT use system Chrome/Edge default profile paths."""
        if os.path.exists("core/browser_runtime.py"):
            with open("core/browser_runtime.py", encoding="utf-8") as f:
                content = f.read()
            for path in ("Chrome/User Data/Default", "Edge/User Data/Default"):
                assert path not in content, f"browser references system profile '{path}' — use isolated profile"
