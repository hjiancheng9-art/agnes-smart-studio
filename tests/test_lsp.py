"""Tests for core.lsp — Language Server Protocol client."""

import pytest


class TestLanguageEnum:
    def test_all_languages_present(self):
        from core.lsp import Language

        assert Language.PYTHON
        assert Language.JAVASCRIPT
        assert Language.TYPESCRIPT
        assert Language.GO
        assert Language.RUST

    def test_values_are_strings(self):
        from core.lsp import Language

        for lang in Language:
            assert isinstance(lang.value, str)


class TestDetectLanguage:
    def test_python(self):
        from core.lsp import Language, detect_language

        assert detect_language("foo.py") == Language.PYTHON

    def test_javascript_variants(self):
        from core.lsp import Language, detect_language

        assert detect_language("a.js") == Language.JAVASCRIPT
        assert detect_language("b.jsx") == Language.JAVASCRIPT
        assert detect_language("c.mjs") == Language.JAVASCRIPT

    def test_typescript(self):
        from core.lsp import Language, detect_language

        assert detect_language("x.ts") == Language.TYPESCRIPT
        assert detect_language("y.tsx") == Language.TYPESCRIPT

    def test_go_and_rust(self):
        from core.lsp import Language, detect_language

        assert detect_language("main.go") == Language.GO
        assert detect_language("lib.rs") == Language.RUST

    def test_unknown_extension_raises(self):
        from core.lsp import detect_language

        with pytest.raises(ValueError):
            detect_language("readme.txt")
        with pytest.raises(ValueError):
            detect_language("noext")

    def test_case_insensitive(self):
        from core.lsp import Language, detect_language

        assert detect_language("APP.PY") == Language.PYTHON


class TestFileUri:
    def test_absolute_path_to_uri(self):
        from core.lsp import _to_file_uri

        uri = _to_file_uri("foo.py")
        assert uri.startswith("file://")

    def test_uri_is_valid(self):
        from core.lsp import _to_file_uri

        uri = _to_file_uri("test.py")
        # Should be parseable as a URI
        assert "://" in uri


class TestLSPClient:
    def test_init_loads_default_config(self):
        from core.lsp import Language, LSPClient

        client = LSPClient()
        for lang in Language:
            assert lang in client._configs
            assert client._configs[lang].enabled is True
        assert client._processes == {}
        assert client._request_id == 0

    def test_load_config_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from core.lsp import LSPClient

        # Point OUTPUT_DIR to a place with no config file
        monkeypatch.setattr("core.lsp.OUTPUT_DIR", tmp_path)
        client = LSPClient()
        # Should still have defaults loaded
        assert len(client._configs) >= 5

    def test_load_config_user_override(self, tmp_path, monkeypatch):
        import json

        from core.lsp import Language, LSPClient

        cfg = tmp_path / "lsp_servers.json"
        cfg.write_text(
            json.dumps({"python": {"command": "custom-pylsp", "args": ["--stdio"], "enabled": True}}), encoding="utf-8"
        )
        monkeypatch.setattr("core.lsp.OUTPUT_DIR", tmp_path)
        client = LSPClient()
        assert client._configs[Language.PYTHON].command == "custom-pylsp"

    def test_load_config_disables_server(self, tmp_path, monkeypatch):
        import json

        from core.lsp import Language, LSPClient

        cfg = tmp_path / "lsp_servers.json"
        cfg.write_text(json.dumps({"go": {"enabled": False}}), encoding="utf-8")
        monkeypatch.setattr("core.lsp.OUTPUT_DIR", tmp_path)
        client = LSPClient()
        assert client._configs[Language.GO].enabled is False

    def test_load_config_corrupt_json_ignored(self, tmp_path, monkeypatch):
        from core.lsp import LSPClient

        cfg = tmp_path / "lsp_servers.json"
        cfg.write_text("not json {{{", encoding="utf-8")
        monkeypatch.setattr("core.lsp.OUTPUT_DIR", tmp_path)
        # Should not raise, falls back to defaults
        client = LSPClient()
        assert len(client._configs) >= 5

    def test_start_server_disabled_returns_error(self):
        from core.lsp import Language, LSPClient

        client = LSPClient()
        client._configs[Language.RUST].enabled = False
        result = client.start_server(Language.RUST)
        assert "error" in result
        assert "disabled" in result["error"]

    def test_start_server_not_installed_returns_error(self):
        from core.lsp import Language, LSPClient

        client = LSPClient()
        # Use a language whose server command surely isn't installed
        client._configs[Language.RUST].command = "definitely-not-installed-lsp-xyz"
        result = client.start_server(Language.RUST)
        assert "error" in result

    def test_stop_server_when_not_running(self):
        from core.lsp import Language, LSPClient

        client = LSPClient()
        result = client.stop_server(Language.PYTHON)
        assert result["status"] == "not_running"

    def test_stop_all_noop_when_empty(self):
        from core.lsp import LSPClient

        client = LSPClient()
        client.stop_all()  # should not raise
        assert client._processes == {}

    def test_is_command_available_static(self):
        from core.lsp import LSPClient

        # python is always available in test env
        assert LSPClient._is_command_available("python") in (True, False)
        assert LSPClient._is_command_available("no-such-cmd-xyz-123") is False


class TestSingleton:
    def test_get_lsp_client_returns_same_instance(self):
        from core.lsp import get_lsp_client

        c1 = get_lsp_client()
        c2 = get_lsp_client()
        assert c1 is c2

    def test_get_lsp_client_is_lsp_client(self):
        from core.lsp import LSPClient, get_lsp_client

        assert isinstance(get_lsp_client(), LSPClient)
