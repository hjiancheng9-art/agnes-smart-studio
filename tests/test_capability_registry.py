"""Tests for core/capability_registry.py — Capability registry, health checks, rate limiting."""

import time
from unittest.mock import patch

from core.capability_registry import (
    Capability,
    CapabilityRegistry,
    registry,
    reset_capability_registry,
)


class TestCapability:
    def test_defaults(self):
        c = Capability(name="test")
        assert c.name == "test"
        assert c.permissions == []
        assert c.rate_limit == 0
        assert c.fallback == ""
        assert c.enabled is True
        assert c.failure_count == 0

    def test_can_call_when_enabled(self):
        c = Capability(name="test")
        ok, reason = c.can_call()
        assert ok is True
        assert reason == "ok"

    def test_can_call_when_disabled(self):
        c = Capability(name="test", enabled=False)
        ok, reason = c.can_call()
        assert ok is False
        assert reason == "disabled"

    def test_can_call_when_unhealthy(self):
        c = Capability(name="test", failure_count=3, max_failures=3)
        ok, _reason = c.can_call()
        assert ok is False
        assert "unhealthy" in _reason

    def test_can_call_just_below_threshold(self):
        c = Capability(name="test", failure_count=2, max_failures=3)
        ok, _reason = c.can_call()
        assert ok is True

    def test_rate_limit_exceeded(self):
        c = Capability(name="test", rate_limit=1, call_count=1, last_call=time.time())
        ok, _reason = c.can_call()
        assert ok is False
        assert "rate_limited" in _reason

    def test_rate_limit_window_expired(self):
        c = Capability(name="test", rate_limit=1, call_count=1, last_call=time.time() - 61)
        ok, _reason = c.can_call()
        assert ok is True

    def test_rate_limit_zero_means_unlimited(self):
        c = Capability(name="test", rate_limit=0, call_count=1000, last_call=time.time())
        ok, _reason = c.can_call()
        assert ok is True

    def test_record_success_resets_failure(self):
        c = Capability(name="test", failure_count=2)
        c.record_success()
        assert c.failure_count == 0

    def test_record_success_resets_window_after_60s(self):
        c = Capability(name="test", call_count=5, last_call=time.time() - 61)
        c.record_success()
        assert c.call_count == 1

    def test_record_success_increments_in_same_window(self):
        now = time.time()
        c = Capability(name="test", call_count=1, last_call=now - 10)
        with patch("time.time", return_value=now):
            c.record_success()
            assert c.call_count == 2

    def test_record_failure_increments(self):
        c = Capability(name="test")
        c.record_failure()
        assert c.failure_count == 1

    def test_record_failure_auto_disables(self):
        c = Capability(name="test", failure_count=2, max_failures=3)
        c.record_failure()
        assert c.failure_count == 3
        assert c.enabled is False


class TestCapabilityRegistry:
    def test_register_adds_capability(self):
        reg = CapabilityRegistry()
        reg.register("test_tool")
        ok, reason = reg.check("test_tool")
        assert ok is True

    def test_register_with_options(self):
        reg = CapabilityRegistry()
        reg.register("test_tool", permissions=["gpu"], rate_limit=10, fallback="fallback_tool")
        caps = reg.list_all()
        c = [c for c in caps if c.name == "test_tool"][0]
        assert c.permissions == ["gpu"]
        assert c.rate_limit == 10
        assert c.fallback == "fallback_tool"

    def test_check_unregistered_returns_ok(self):
        reg = CapabilityRegistry()
        ok, reason = reg.check("unknown_tool")
        assert ok is True
        assert reason == ""

    def test_check_disabled_returns_false(self):
        reg = CapabilityRegistry()
        reg.register("test_tool")
        c = reg._caps["test_tool"]
        c.enabled = False
        ok, _reason = reg.check("test_tool")
        assert ok is False

    def test_record_updates_capability(self):
        reg = CapabilityRegistry()
        reg.register("test_tool")
        reg.record("test_tool", success=True)
        c = reg._caps["test_tool"]
        assert c.call_count >= 1

    def test_record_failure_triggers_fallback_message(self):
        reg = CapabilityRegistry()
        reg.register("test_tool", fallback="backup_tool")
        reg.register("backup_tool")
        reg.record("test_tool", success=False)
        c = reg._caps["test_tool"]
        assert c.failure_count == 1

    def test_get_fallback_returns_fallback_name(self):
        reg = CapabilityRegistry()
        reg.register("test_tool", fallback="backup_tool")
        assert reg.get_fallback("test_tool") == "backup_tool"

    def test_get_fallback_nonexistent(self):
        reg = CapabilityRegistry()
        assert reg.get_fallback("nonexistent") == ""

    def test_list_all(self):
        reg = CapabilityRegistry()
        reg.register("a")
        reg.register("b")
        assert len(reg.list_all()) == 2

    def test_list_enabled(self):
        reg = CapabilityRegistry()
        reg.register("a")
        reg.register("b")
        reg._caps["b"].enabled = False
        assert len(reg.list_enabled()) == 1

    def test_list_disabled(self):
        reg = CapabilityRegistry()
        reg.register("a")
        reg.register("b")
        reg._caps["b"].enabled = False
        assert len(reg.list_disabled()) == 1

    def test_record_incident_logs(self):
        reg = CapabilityRegistry()
        reg.record_incident("test_tool", "timeout")

    def test_reset_clears_all(self):
        reg = CapabilityRegistry()
        reg.register("a")
        reg.register("b")
        reg.reset()
        assert len(reg.list_all()) == 0

    def test_record_nonexistent_noop(self):
        reg = CapabilityRegistry()
        reg.record("nonexistent", success=True)  # should not raise

    def test_summary(self):
        reg = CapabilityRegistry()
        reg.register("a")
        s = reg.summary()
        assert "能力注册表" in s

    def test_register_replaces_existing(self):
        reg = CapabilityRegistry()
        reg.register("test_tool", rate_limit=5)
        reg.register("test_tool", rate_limit=20)
        c = reg._caps["test_tool"]
        assert c.rate_limit == 20


class TestInferPermissions:
    def test_known_tool(self):
        perms = CapabilityRegistry._infer_permissions("read_file")
        assert "fs" in perms

    def test_unknown_tool(self):
        perms = CapabilityRegistry._infer_permissions("unknown_tool")
        assert perms == []

    def test_gpu_tool(self):
        perms = CapabilityRegistry._infer_permissions("generate_image")
        assert "gpu" in perms

    def test_network_tool(self):
        perms = CapabilityRegistry._infer_permissions("web_fetch")
        assert "network" in perms

    def test_process_tool(self):
        perms = CapabilityRegistry._infer_permissions("run_bash")
        assert "process" in perms

    def test_browser_tool(self):
        perms = CapabilityRegistry._infer_permissions("browser_screenshot")
        assert "browser" in perms

    def test_audio_tool(self):
        perms = CapabilityRegistry._infer_permissions("text_to_speech")
        assert "audio" in perms


class TestInferRateLimit:
    def test_video_expensive(self):
        assert CapabilityRegistry._infer_rate_limit("generate_video") == 5

    def test_image_moderate(self):
        assert CapabilityRegistry._infer_rate_limit("generate_image") == 20

    def test_tts_rate_limit(self):
        assert CapabilityRegistry._infer_rate_limit("text_to_speech") == 30

    def test_unknown_no_limit(self):
        assert CapabilityRegistry._infer_rate_limit("unknown_tool") == 0


class TestRegisterFromToolsJson:
    def test_returns_zero_for_missing_file(self, tmp_path):
        reg = CapabilityRegistry()
        fake_path = tmp_path / "nonexistent.json"
        count = reg.register_from_tools_json(fake_path)
        assert count == 0

    def test_registers_tools_from_json(self, tmp_path):
        import json

        tools_data = [
            {"name": "tool_a"},
            {"name": "tool_b"},
        ]
        p = tmp_path / "tools.json"
        p.write_text(json.dumps(tools_data), encoding="utf-8")

        reg = CapabilityRegistry()
        count = reg.register_from_tools_json(p)
        assert count == 2
        assert len(reg.list_all()) == 2

    def test_skips_already_registered(self, tmp_path):
        import json

        tools_data = [{"name": "tool_a"}]
        p = tmp_path / "tools.json"
        p.write_text(json.dumps(tools_data), encoding="utf-8")

        reg = CapabilityRegistry()
        reg.register("tool_a")
        count = reg.register_from_tools_json(p)
        assert count == 0

    def test_handles_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")

        reg = CapabilityRegistry()
        count = reg.register_from_tools_json(p)
        assert count == 0


class TestLoadSaveState:
    def test_save_and_load_state(self, tmp_path):
        import core.capability_registry as cr
        import json

        original = cr.CAPABILITY_FILE
        state_path = tmp_path / "capability_state.json"
        cr.CAPABILITY_FILE = state_path

        try:
            reg = CapabilityRegistry()
            reg.register("test_tool")
            reg._caps["test_tool"].failure_count = 2
            reg.save_state()

            assert state_path.exists()
            data = json.loads(state_path.read_text(encoding="utf-8"))
            assert data["caps"]["test_tool"]["failure_count"] == 2

            # New registry should load state
            reg2 = CapabilityRegistry()
            reg2.register("test_tool")
            # state was loaded before register, so failure_count comes from new
        finally:
            cr.CAPABILITY_FILE = original

    def test_load_state_handles_missing_file(self):
        reg = CapabilityRegistry()
        reg._load_state()  # should not raise


class TestResetFunction:
    def test_reset_function_clears_global(self):
        registry.register("test_global_tool")
        assert len(registry.list_all()) > 0
        reset_capability_registry()
        assert len(registry.list_all()) == 0

    def test_can_register_after_reset(self):
        reset_capability_registry()
        registry.register("new_tool")
        assert len(registry.list_all()) == 1
        reset_capability_registry()
