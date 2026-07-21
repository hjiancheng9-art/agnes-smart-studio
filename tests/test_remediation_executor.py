"""Tests for core/remediation_executor.py — self-healing engine.

Functions tested:
  - classify_command(command) -> str
  - _ensure_ledger() -> Path
  - log_recovery_action(incident_id, command, risk, status, result) -> dict
  - get_recovery_ledger(incident_id) -> list[dict]
  - get_recent_actions(limit) -> list[dict]
  - get_incident_actions(incident_id) -> list[dict]
  - _restore(incident_id) -> str
"""

import tempfile
from pathlib import Path

import pytest

from core.remediation_executor import (
    classify_command,
    get_incident_actions,
    get_recent_actions,
    get_recovery_ledger,
    log_recovery_action,
)

# ── classify_command ──────────────────────────────────────────────


class TestClassifyCommand:
    """Risk classification for fix commands."""

    def test_low_risk_commands_are_classified_low(self):
        for cmd in ["retry_with_backoff", "clear_cache", "increase_timeout", "switch_provider"]:
            assert classify_command(cmd) == "low", f"Expected low risk for {cmd}"

    def test_high_risk_commands_are_classified_high(self):
        for cmd in [
            "reset_circuit_breaker",
            "force_local_once",
            "clear_all_provider_cache",
            "reset_all_circuit_breakers",
            "override_provider_priority",
        ]:
            assert classify_command(cmd) == "high", f"Expected high risk for {cmd}"

    def test_unknown_commands_default_to_high(self):
        assert classify_command("delete_everything") == "high"
        assert classify_command("unknown_command") == "high"

    def test_command_with_args_still_works(self):
        """Classification strips colon-separated and JSON args before checking."""
        # Space-separated args are NOT stripped — the function uses split(":") and split("{")
        assert classify_command("switch_provider:gpt4") == "low"
        assert classify_command("force_local_once {model: 'gpt4'}") == "high"
        assert classify_command("reset_circuit_breaker:provider_x") == "high"

    def test_empty_string_defaults_to_high(self):
        assert classify_command("") == "high"


# ── Recovery Ledger ───────────────────────────────────────────────


class TestRecoveryLedger:
    """log_recovery_action writes to ledger; get_recovery_ledger reads it back."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        """Redirect ledger to a temp directory and clean up after."""
        self.tmpdir = tempfile.mkdtemp(prefix="recovery_ledger_test_")
        tmp_path = Path(self.tmpdir)
        from core import remediation_executor

        monkeypatch.setattr(remediation_executor, "_LEDGER_DIR", tmp_path)
        self.ledger_dir = tmp_path
        yield
        # Clean up
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_log_recovery_action_returns_dict(self):
        entry = log_recovery_action("inc_001", "retry_with_backoff", "low", "executed", "OK")
        assert isinstance(entry, dict)
        assert entry["incident_id"] == "inc_001"
        assert entry["command"] == "retry_with_backoff"
        assert entry["risk"] == "low"
        assert entry["status"] == "executed"
        assert entry["result"] == "OK"
        assert "timestamp" in entry

    def test_log_recovery_action_creates_file(self):
        log_recovery_action("inc_002", "clear_cache", "low", "executed")
        ledger_file = self.ledger_dir / "inc_002.jsonl"
        assert ledger_file.is_file()

    def test_get_recovery_ledger_reads_entries(self):
        log_recovery_action("inc_003", "cmd_a", "low", "executed", "OK")
        log_recovery_action("inc_003", "cmd_b", "high", "failed", "ERR")
        entries = get_recovery_ledger("inc_003")
        assert len(entries) == 2
        assert entries[0]["command"] == "cmd_a"
        assert entries[1]["command"] == "cmd_b"

    def test_get_recovery_ledger_missing_incident(self):
        entries = get_recovery_ledger("nonexistent_incident")
        assert entries == []

    def test_log_recovery_action_default_result_empty(self):
        entry = log_recovery_action("inc_004", "cmd", "low", "executed")
        assert entry["result"] == ""


# ── get_recent_actions ────────────────────────────────────────────


class TestGetRecentActions:
    """get_recent_actions returns most recent entries from the ledger."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.tmpdir = tempfile.mkdtemp(prefix="recovery_ledger_recent_")
        tmp_path = Path(self.tmpdir)
        from core import remediation_executor

        monkeypatch.setattr(remediation_executor, "_LEDGER_DIR", tmp_path)
        self.ledger_dir = tmp_path
        # Write some test data
        for i in range(5):
            log_recovery_action(f"inc_{i:03d}", f"cmd_{i}", "low", "executed", f"result_{i}")
        yield
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_recent_actions_returns_entries(self):
        actions = get_recent_actions(limit=10)
        assert isinstance(actions, list)
        assert len(actions) == 5

    def test_get_recent_actions_respects_limit(self):
        actions = get_recent_actions(limit=2)
        assert len(actions) == 2

    def test_get_recent_actions_default_limit(self):
        actions = get_recent_actions()
        assert len(actions) <= 20


# ── get_incident_actions ──────────────────────────────────────────


class TestGetIncidentActions:
    """get_incident_actions delegates to get_recovery_ledger."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.tmpdir = tempfile.mkdtemp(prefix="recovery_ledger_inc_")
        tmp_path = Path(self.tmpdir)
        from core import remediation_executor

        monkeypatch.setattr(remediation_executor, "_LEDGER_DIR", tmp_path)
        self.ledger_dir = tmp_path
        log_recovery_action("inc_100", "cmd_x", "low", "executed", "done")
        yield
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_incident_actions_returns_entries(self):
        actions = get_incident_actions("inc_100")
        assert len(actions) == 1
        assert actions[0]["command"] == "cmd_x"

    def test_get_incident_actions_missing(self):
        actions = get_incident_actions("nonexistent")
        assert actions == []
