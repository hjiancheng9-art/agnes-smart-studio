"""Tests for TUI event dispatch — status_kinds routing, event handling."""


class TestEventKindDispatch:
    """Verify all defined event kinds are handled by the TUI dispatch.

    These tests parse the TUI source to find handled kinds and verify
    no important events are silently dropped.
    """

    def test_tui_v2_handles_all_status_events(self):
        import re

        with open("ui/tui_v2.py", encoding="utf-8") as f:
            content = f.read()

        # Extract the status_kinds set
        m = re.search(r"status_kinds\s*=\s*\{([^}]+)\}", content, re.DOTALL)
        assert m is not None, "status_kinds set not found in tui_v2.py"
        kinds_text = m.group(1)
        handled = set(re.findall(r'"(\w+)"', kinds_text))

        # These should all be handled
        required = {
            "status_update",
            "watchdog_alert",
            "watchdog_warning",
            "system_warning",
            "system_error",
            "provider_fallback",
            "notice",
            "connection_error",
            "system_info",
            "tool_failed",
            "tool_started",
            "tool_finished",
            "tool_progress",
        }
        missing = required - handled
        assert not missing, f"tui_v2.py missing handlers for: {missing}"

    def test_critical_events_have_handlers(self):
        """Verify that critical events (watchdog, provider, system) have handlers."""
        with open("ui/tui_v2.py", encoding="utf-8") as f:
            content = f.read()

        has_watchdog = "watchdog_alert" in content or "watchdog" in content.lower()
        has_provider = "provider_fallback" in content
        has_system_error = "system_error" in content

        assert has_watchdog or has_provider or has_system_error, "tui_v2.py has no handler for critical events"

    def test_error_events_use_append_error(self):
        """Error/failed/alert events should route to append_error."""
        with open("ui/tui_v2.py", encoding="utf-8") as f:
            content = f.read()

        # The error routing logic should exist
        assert "append_error" in content, "tui_v2.py missing append_error call"
        assert '"error" in kind' in content or '"failed" in kind' in content or '"alert" in kind' in content, (
            "tui_v2.py missing error detection in status_kinds routing"
        )
