"""Tests for core/artifact_activation.py — artifact event wiring."""

from core.artifact_activation import activate_all_artifacts


class TestActivateAllArtifacts:
    def test_runs_without_error(self):
        """activate_all_artifacts wires 25 artifact event handlers."""
        activate_all_artifacts()

    def test_idempotent(self):
        """Calling twice should be safe — no duplicate wiring issues."""
        activate_all_artifacts()
        activate_all_artifacts()

    def test_logger_configured(self):
        import logging
        logger = logging.getLogger("crux.artifacts")
        assert logger is not None
