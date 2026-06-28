"""Tests for core/plugin_system.py — PluginManifest, PluginManager lifecycle."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.plugin_system import (
    PLUGIN_DIR,
    SCHEMA_VERSION,
    PluginInstance,
    PluginManager,
    PluginManifest,
)


class TestPluginManifest:
    def test_defaults(self):
        m = PluginManifest(name="test", version="1.0.0")
        assert m.name == "test"
        assert m.version == "1.0.0"
        assert m.permissions == []
        assert m.hooks == []
        assert m.schema_version == SCHEMA_VERSION

    def test_from_json_minimal(self):
        m = PluginManifest.from_json({"name": "test"})
        assert m.name == "test"
        assert m.version == "0.1.0"

    def test_from_json_full(self):
        data = {
            "name": "my_plugin",
            "version": "2.0.0",
            "permissions": ["fs", "network"],
            "hooks": ["on_start"],
            "description": "A test plugin",
            "author": "test",
            "dependencies": ["dep1"],
        }
        m = PluginManifest.from_json(data)
        assert m.name == "my_plugin"
        assert m.permissions == ["fs", "network"]
        assert m.hooks == ["on_start"]
        assert m.dependencies == ["dep1"]

    def test_validate_ok(self):
        m = PluginManifest(name="test", version="1")
        ok, reason = m.validate()
        assert ok is True
        assert reason == "ok"

    def test_validate_schema_mismatch(self):
        m = PluginManifest(name="test", version="1", schema_version="bogus")
        ok, reason = m.validate()
        assert ok is False
        assert "Schema mismatch" in reason

    def test_validate_unknown_permission(self):
        m = PluginManifest(name="test", version="1", permissions=["fs", "bogus_perm"])
        ok, reason = m.validate()
        assert ok is False
        assert "Unknown permissions" in reason

    def test_validate_all_valid_permissions(self):
        valid = ["fs", "network", "gpu", "browser", "audio", "process", "self"]
        m = PluginManifest(name="test", version="1", permissions=valid)
        ok, _reason = m.validate()
        assert ok is True


class TestPluginInstance:
    def test_default_state(self):
        m = PluginManifest(name="test", version="1")
        pi = PluginInstance(manifest=m)
        assert pi.state == "unloaded"
        assert pi.module is None
        assert pi.instance is None


class TestPluginManager:
    def test_init_empty(self):
        pm = PluginManager()
        assert pm.loaded_names == []
        assert pm.active_names == []

    def test_discover_empty_dir(self):
        pm = PluginManager()
        # PLUGIN_DIR likely has no valid plugins
        plugins = pm.discover()
        assert isinstance(plugins, list)

    def test_discover_with_plugin_dir(self, tmp_path):
        pm = PluginManager()
        # PLUGIN_DIR is the parent; plugins live inside it
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        with patch("core.plugin_system.PLUGIN_DIR", tmp_path):
            discovered = pm.discover()
            assert len(discovered) == 1
            assert discovered[0] == plugin_dir

    def test_load_from_valid_plugin(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text(
            "class Plugin:\n    def activate(self): pass\n    def deactivate(self): pass",
            encoding="utf-8",
        )

        pi = pm.load(plugin_dir)
        assert pi is not None
        assert pi.manifest.name == "test"
        assert pi.state == "loaded"

    def test_load_missing_manifest(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "bad_plugin"
        plugin_dir.mkdir()
        result = pm.load(plugin_dir)
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "bad_json"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("not json", encoding="utf-8")
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        result = pm.load(plugin_dir)
        assert result is None

    def test_load_validation_fails(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "invalid_perm"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "bad", "permissions": ["bogus"]}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        result = pm.load(plugin_dir)
        assert result is None

    def test_load_duplicate_returns_existing(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "dup"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "dup"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pi1 = pm.load(plugin_dir)
        pi2 = pm.load(plugin_dir)
        assert pi1 is pi2

    def test_activate_and_deactivate(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "activate_test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "activate_test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pi = pm.load(plugin_dir)
        assert pi is not None

        ok = pm.activate("activate_test")
        assert ok is True

        ok2 = pm.deactivate("activate_test")
        assert ok2 is True

    def test_activate_nonexistent(self):
        pm = PluginManager()
        assert pm.activate("nonexistent") is False

    def test_deactivate_non_active(self):
        pm = PluginManager()
        assert pm.deactivate("nonexistent") is False

    def test_unload(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "unload_test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "unload_test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pm.load(plugin_dir)
        assert pm.unload("unload_test") is True
        assert pm.unload("unload_test") is False  # already gone

    def test_unload_active_plugin(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "active_unload"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "active_unload"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pm.load(plugin_dir)
        pm.activate("active_unload")
        assert "active_unload" in pm.active_names
        assert pm.unload("active_unload") is True
        assert pm._active == set()

    def test_get(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "get_test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "get_test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pm.load(plugin_dir)
        pi = pm.get("get_test")
        assert pi is not None
        assert pi.manifest.name == "get_test"

    def test_get_nonexistent(self):
        pm = PluginManager()
        assert pm.get("nonexistent") is None

    def test_load_all(self, tmp_path):
        pm = PluginManager()
        for name in ["p1", "p2"]:
            pd = tmp_path / name
            pd.mkdir()
            (pd / "plugin.json").write_text(
                json.dumps({"name": name}), encoding="utf-8"
            )
            (pd / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        with patch("core.plugin_system.PLUGIN_DIR", tmp_path):
            count = pm.load_all()
            assert count == 2
            assert len(pm.loaded_names) == 2

    def test_summary_empty(self):
        pm = PluginManager()
        s = pm.summary()
        assert "无已加载插件" in s

    def test_summary_with_plugins(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "summary_test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "summary_test", "description": "Hello"}),
            encoding="utf-8",
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pm.load(plugin_dir)
        s = pm.summary()
        assert "summary_test" in s
        assert "Hello" in s

    def test_loaded_names_returns_list(self, tmp_path):
        pm = PluginManager()
        plugin_dir = tmp_path / "names_test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "names_test"}), encoding="utf-8"
        )
        (plugin_dir / "main.py").write_text("class Plugin: pass", encoding="utf-8")

        pm.load(plugin_dir)
        assert "names_test" in pm.loaded_names
