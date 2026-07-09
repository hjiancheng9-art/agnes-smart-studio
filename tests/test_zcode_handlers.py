"""Test CRUX CLI handlers — verify all commands have handler methods on CruxCLI."""

from __future__ import annotations

from core.cli_handlers import CruxCLI
from core.commands import COMMANDS, build_dispatch_table


class TestAllCommandsHaveHandlers:
    """Cross-reference COMMANDS with CruxCLI methods. 0 missing."""

    def test_all_commands_have_handlers(self):
        """Every COMMAND entry resolves to a handler that exists on CruxCLI."""
        missing: list[str] = []
        for cmd in COMMANDS:
            # Handler resolution logic mirrors build_dispatch_table:
            # handler = cmd.handler or f"_chat_{cmd.key}"
            handler_name = cmd.handler or f"_chat_{cmd.key}"
            if not hasattr(CruxCLI, handler_name):
                missing.append(f"{cmd.key} → {handler_name}")

        assert not missing, f"{len(missing)} command(s) missing handlers on CruxCLI:\n" + "\n".join(
            f"  - {m}" for m in missing
        )

    def test_missing_handler_count(self):
        """The 5 handlers we added (_chat_audit, _chat_rules, _chat_automate,
        _chat_evolve, _chat_exit) all exist on CruxCLI."""
        required = [
            "_chat_audit",
            "_chat_rules",
            "_chat_automate",
            "_chat_evolve",
            "_chat_exit",
        ]
        missing = [h for h in required if not hasattr(CruxCLI, h)]
        assert not missing, f"Missing handlers: {missing}"

    def test_command_count(self):
        """COMMANDS has 51 entries."""
        assert len(COMMANDS) == 51, f"Expected 51 commands, got {len(COMMANDS)}"

    def test_dispatch_table_size(self):
        """build_dispatch_table() has expected keys: 51 commands + 3 aliases."""
        table = build_dispatch_table()
        expected = 51 + 3  # = 54
        assert len(table) == expected, f"Expected {expected} dispatch entries, got {len(table)}"

    def test_expected_dispatch_keys(self):
        """Verify key dispatch table entries exist."""
        table = build_dispatch_table()
        # Check a sampling of keys
        for key in ("help", "all", "exit", "quit", "q", "showrun", "video", "img"):
            assert key in table, f"'{key}' missing from dispatch table"
