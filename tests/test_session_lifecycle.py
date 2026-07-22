"""Tests for core/session_lifecycle.py — session state machine."""

import pytest


class TestSessionPhase:
    """SessionPhase enum: valid phase names and ordering."""

    def test_phases_in_order(self):
        """Phases exist in expected lifecycle order."""
        from core.session_lifecycle import SessionPhase

        phases = list(SessionPhase)
        names = [p.value for p in phases]
        assert "INIT" in names
        assert "SETUP" in names
        assert "ACTIVE" in names
        assert "DRAINING" in names
        assert "SHUTDOWN" in names
        assert "TERMINATED" in names

    def test_phase_ordering(self):
        """Phase enum values are monotonic (each > previous)."""
        from core.session_lifecycle import SessionPhase

        values = [p.value for p in SessionPhase]
        for v in values:
            assert isinstance(v, int)
        for i in range(1, len(values)):
            assert values[i] > values[i - 1], f"{values[i]} not > {values[i - 1]}"


class TestSessionLifecycleTransition:
    """SessionLifecycle.transition(): deterministic state machine."""

    @pytest.fixture
    def lifecycle(self):
        from core.session_lifecycle import SessionLifecycle

        return SessionLifecycle(session_id="test-001")

    def test_initial_phase(self, lifecycle):
        """Starts at INIT phase."""
        from core.session_lifecycle import SessionPhase

        assert lifecycle.phase == SessionPhase.INIT

    def test_valid_transition(self, lifecycle):
        """INIT → SETUP → ACTIVE transitions succeed."""
        from core.session_lifecycle import SessionPhase

        lifecycle.transition(SessionPhase.SETUP)
        assert lifecycle.phase == SessionPhase.SETUP
        lifecycle.transition(SessionPhase.ACTIVE)
        assert lifecycle.phase == SessionPhase.ACTIVE

    def test_invalid_transition_raises(self, lifecycle):
        """INIT → DRAINING (skip phases) raises ValueError."""
        from core.session_lifecycle import SessionPhase

        with pytest.raises(ValueError, match=r"transition|invalid|phase"):
            lifecycle.transition(SessionPhase.DRAINING)

    def test_invalid_transition_backwards(self, lifecycle):
        """Cannot transition backwards ACTIVE → SETUP."""
        from core.session_lifecycle import SessionPhase

        lifecycle.transition(SessionPhase.SETUP)
        lifecycle.transition(SessionPhase.ACTIVE)
        with pytest.raises(ValueError):
            lifecycle.transition(SessionPhase.SETUP)

    def test_terminal_phase_locks(self, lifecycle):
        """After TERMINATED, no more transitions allowed."""
        from core.session_lifecycle import SessionPhase

        lifecycle.transition(SessionPhase.SETUP)
        lifecycle.transition(SessionPhase.ACTIVE)
        lifecycle.transition(SessionPhase.DRAINING)
        lifecycle.transition(SessionPhase.SHUTDOWN)
        lifecycle.transition(SessionPhase.TERMINATED)
        assert lifecycle.phase == SessionPhase.TERMINATED
        with pytest.raises(ValueError):
            lifecycle.transition(SessionPhase.ACTIVE)

    def test_full_lifecycle(self, lifecycle):
        """Full happy path: INIT → SETUP → ACTIVE → DRAINING → SHUTDOWN → TERMINATED."""
        from core.session_lifecycle import SessionPhase

        path = [
            SessionPhase.SETUP,
            SessionPhase.ACTIVE,
            SessionPhase.DRAINING,
            SessionPhase.SHUTDOWN,
            SessionPhase.TERMINATED,
        ]
        for p in path:
            lifecycle.transition(p)
        assert lifecycle.phase == SessionPhase.TERMINATED


class TestSessionLifecycleFeatures:
    """SessionLifecycle: record_error, age, is_active, can_accept_input, health_report."""

    @pytest.fixture
    def lifecycle(self):
        from core.session_lifecycle import SessionLifecycle, SessionPhase

        lc = SessionLifecycle(session_id="test-001")
        lc.transition(SessionPhase.SETUP)
        lc.transition(SessionPhase.ACTIVE)
        return lc

    def test_record_error_increases_count(self, lifecycle):
        """record_error increments error_count."""
        lifecycle.record_error("something went wrong")
        assert lifecycle.error_count == 1
        assert "something" in lifecycle.last_error

    def test_record_error_multiple(self, lifecycle):
        """Multiple errors accumulate."""
        for i in range(3):
            lifecycle.record_error(f"error {i}")
        assert lifecycle.error_count == 3

    def test_age_seconds_returns_positive(self, lifecycle):
        """age_seconds returns time since creation."""
        age = lifecycle.age_seconds()
        assert isinstance(age, float)
        assert age >= 0
        assert age < 5  # should be near-instant

    def test_is_active_true_in_active_phase(self, lifecycle):
        """is_active returns True when phase is ACTIVE."""
        assert lifecycle.is_active() is True

    def test_is_active_false_after_draining(self, lifecycle):
        """is_active returns False after DRAINING."""
        from core.session_lifecycle import SessionPhase

        lifecycle.transition(SessionPhase.DRAINING)
        assert lifecycle.is_active() is False

    def test_can_accept_input_active(self, lifecycle):
        """can_accept_input returns True when phase is ACTIVE."""
        assert lifecycle.can_accept_input() is True

    def test_can_accept_input_draining(self, lifecycle):
        """can_accept_input returns False when draining or later."""
        from core.session_lifecycle import SessionPhase

        lifecycle.transition(SessionPhase.DRAINING)
        assert lifecycle.can_accept_input() is False

    def test_can_accept_input_init(self):
        """can_accept_input returns False during INIT/SETUP."""
        from core.session_lifecycle import SessionLifecycle

        lc = SessionLifecycle(session_id="init-test")
        assert lc.can_accept_input() is False

    def test_health_report_has_keys(self, lifecycle):
        """health_report returns dict with expected keys."""
        report = lifecycle.health_report()
        assert isinstance(report, dict)
        assert "session_id" in report
        assert "phase" in report
        assert "error_count" in report
        assert "age_seconds" in report
        assert "is_active" in report

    def test_health_report_after_error(self, lifecycle):
        """health_report reflects recorded errors."""
        lifecycle.record_error("disk full")
        report = lifecycle.health_report()
        assert report["error_count"] == 1
        assert "disk" in report.get("last_error", "")

    def test_session_id_persists(self, lifecycle):
        """session_id is stored and returned."""
        assert lifecycle.session_id == "test-001"


class TestSessionLifecycleEdgeCases:
    """Edge cases for SessionLifecycle."""

    def test_transition_same_phase_raises(self):
        """Transitioning to current phase raises ValueError."""
        from core.session_lifecycle import SessionLifecycle, SessionPhase

        lc = SessionLifecycle(session_id="edge-1")
        with pytest.raises(ValueError):
            lc.transition(SessionPhase.INIT)  # already INIT

    def test_transition_none_raises(self, lifecycle):
        """Passing None to transition raises."""
        from core.session_lifecycle import SessionLifecycle

        lc = SessionLifecycle(session_id="none-test")
        with pytest.raises((ValueError, TypeError)):
            lc.transition(None)  # type: ignore

    def test_health_report_after_shutdown(self):
        """health_report works after full shutdown."""
        from core.session_lifecycle import SessionLifecycle, SessionPhase

        lc = SessionLifecycle(session_id="shutdown-test")
        lc.transition(SessionPhase.SETUP)
        lc.transition(SessionPhase.ACTIVE)
        lc.transition(SessionPhase.DRAINING)
        lc.transition(SessionPhase.SHUTDOWN)
        lc.transition(SessionPhase.TERMINATED)
        report = lc.health_report()
        assert report["phase"] == "TERMINATED"
        assert report["is_active"] is False
