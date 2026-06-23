"""Tests for core.capability — capability registry & self-knowledge."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_root(tmp_path):
    """Create a minimal project root with skills/, tools.json, models.json."""
    # skills/
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "video-pipeline.skill.json").write_text(json.dumps({
        "name": "video-pipeline",
        "description": "Video generation pipeline",
        "version": "1.0",
    }), encoding="utf-8")
    (skills_dir / "storyboard.skill.json").write_text(json.dumps({
        "name": "storyboard",
        "description": "Storyboard director skill",
        "version": "2.1",
    }), encoding="utf-8")
    # One corrupted skill
    (skills_dir / "broken.skill.json").write_text("{invalid json", encoding="utf-8")

    # tools.json
    (tmp_path / "tools.json").write_text(json.dumps({
        "tools": [
            {"name": "read_file", "type": "file", "description": "Read a file"},
            {"name": "write_file", "type": "file", "description": "Write a file"},
            {"name": "search_files", "type": "search", "description": "Search files"},
        ]
    }), encoding="utf-8")

    # models.json
    (tmp_path / "models.json").write_text(json.dumps({
        "active": "main",
        "providers": {
            "main": {"name": "Main Provider", "base_url": "https://api.example.com/v1"},
            "backup": {"name": "Backup", "base_url": "https://backup.example.com/v1"},
        }
    }), encoding="utf-8")

    return tmp_path


class TestCapabilityRegistry:
    """CapabilityRegistry builds a snapshot of all CRUX capabilities."""

    def test_snapshot_structure(self, fake_root):
        from core.capability import CapabilityRegistry
        with patch.object(CapabilityRegistry, "_quick_health", return_value={"mocked": True}):
            reg = CapabilityRegistry(root=fake_root)
            snap = reg.snapshot()
        # All expected keys
        for key in ("timestamp", "skills", "tools", "providers",
                    "engines", "models", "environment", "health"):
            assert key in snap, f"Missing key: {key}"

    def test_list_skills(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        skills = reg._list_skills()
        assert skills["count"] == 3  # 2 valid + 1 broken
        names = {s.get("name") for s in skills["items"]}
        assert "video-pipeline" in names
        assert "storyboard" in names

    def test_list_skills_handles_corrupted(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        skills = reg._list_skills()
        broken = [s for s in skills["items"] if "error" in s]
        assert len(broken) == 1
        assert broken[0]["error"] == "invalid JSON"

    def test_list_skills_empty(self, tmp_path):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=tmp_path)
        skills = reg._list_skills()
        assert skills["count"] == 0
        assert skills["items"] == []

    def test_list_tools(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        tools = reg._list_tools()
        assert tools["count"] == 3
        names = {t["name"] for t in tools["items"]}
        assert "read_file" in names

    def test_list_tools_missing_file(self, tmp_path):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=tmp_path)
        tools = reg._list_tools()
        assert tools["count"] == 0

    def test_list_providers(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        providers = reg._list_providers()
        assert providers["active"] == "main"
        assert providers["count"] == 2
        for item in providers["items"]:
            assert "name" in item
            assert "is_active" in item
        active = [p for p in providers["items"] if p["is_active"]]
        assert len(active) == 1
        assert active[0]["name"] == "main"

    def test_list_providers_missing_file(self, tmp_path):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=tmp_path)
        providers = reg._list_providers()
        assert providers["count"] == 0

    def test_list_engines(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        engines = reg._list_engines()
        assert engines["count"] >= 3
        assert "text_to_image" in engines["items"]
        assert "video" in engines["items"]

    def test_list_models(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        models = reg._list_models()
        # Reads from core.config.MODELS (global)
        assert models["count"] > 0

    def test_environment_check(self, fake_root):
        from core.capability import CapabilityRegistry
        reg = CapabilityRegistry(root=fake_root)
        env = reg._check_env()
        assert "python" in env
        assert "platform" in env
        assert "encoding" in env
        assert "api_key_set" in env

    def test_snapshot_caching(self, fake_root):
        """Second snapshot() call within TTL returns cached version."""
        from core.capability import CapabilityRegistry
        with patch.object(CapabilityRegistry, "_quick_health", return_value={"mocked": True}):
            reg = CapabilityRegistry(root=fake_root)
            snap1 = reg.snapshot()
            snap2 = reg.snapshot()
        # Same timestamp = cached
        assert snap1["timestamp"] == snap2["timestamp"]

    def test_snapshot_cache_expires(self, fake_root):
        """Cache expires after TTL."""
        from core.capability import CapabilityRegistry
        with patch.object(CapabilityRegistry, "_quick_health", return_value={"mocked": True}):
            reg = CapabilityRegistry(root=fake_root)
            reg._cache_ttl = 0.01  # very short
            snap1 = reg.snapshot()
            import time
            time.sleep(0.02)
            snap2 = reg.snapshot()
        assert snap1["timestamp"] != snap2["timestamp"]


class TestCapabilitySnapshot:
    """Convenience function."""

    def test_capability_snapshot_returns_dict(self):
        from core.capability import capability_snapshot, CapabilityRegistry
        # Mock _quick_health to avoid spawning a pytest subprocess
        with patch.object(CapabilityRegistry, "_quick_health", return_value={"mocked": True}):
            snap = capability_snapshot()
        assert isinstance(snap, dict)
        assert "skills" in snap

    def test_root_constant_exists(self):
        from core.capability import ROOT
        assert ROOT.exists()


class TestRenderingInvariantsSelfCheck:
    """rendering.invariants 必须是真反射检测，不能写死 True。

    缺陷 2 的回归守护：哪天 renderer 被删或 transient 被改回 False，
    自检必须真实变红，而不是永远报绿。
    """

    def _rendering_invariants(self):
        from core.capability import CapabilityRegistry
        from unittest.mock import patch
        # _quick_health 的 tests 段会 spawn pytest（慢/可能超时），patch 掉它，
        # 只验证 rendering 段的反射检测。
        import core.pytest_runner as pr
        from types import SimpleNamespace
        with patch.object(pr, "run_pytest_safe",
                          return_value=SimpleNamespace(stdout="1 passed", stderr="")):
            h = CapabilityRegistry._quick_health(CapabilityRegistry())
        return h["rendering.invariants"]

    def test_selfcheck_reports_true_when_healthy(self):
        """renderer 在线 + transient=True 时，自检报 True。"""
        inv = self._rendering_invariants()
        assert inv["renderer_present"] is True
        assert inv["transient_preview"] is True
        assert inv["single_commit"] is True

    def test_selfcheck_turns_red_when_transient_tampered(self):
        """反证：篡改 transient=False 后，自检必须报 False（不写死）。"""
        from ui.render import StreamingRenderer
        from rich.live import Live
        from rich.markdown import Markdown

        orig = StreamingRenderer._new_live

        def tampered(self, content):
            return Live(Markdown(content), console=self.console,
                        refresh_per_second=self._refresh,
                        vertical_overflow="visible", transient=False)  # 篡改

        StreamingRenderer._new_live = tampered
        try:
            inv = self._rendering_invariants()
            assert inv["transient_preview"] is False, "自检未检测到 transient 被篡改！"
        finally:
            StreamingRenderer._new_live = orig

    def test_selfcheck_turns_red_when_renderer_missing(self):
        """反证：renderer 导入失败时，自检必须报 renderer_present=False。"""
        import sys
        orig = sys.modules.get("ui.render")
        sys.modules["ui.render"] = None  # 让 import 失败
        try:
            inv = self._rendering_invariants()
            assert inv["renderer_present"] is False
        finally:
            if orig is not None:
                sys.modules["ui.render"] = orig
            else:
                sys.modules.pop("ui.render", None)
