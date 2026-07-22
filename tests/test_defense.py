"""Tests for core/defense.py — three-layer safety architecture."""

import pytest

# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """CircuitBreaker: prevent cascade failures by tracking consecutive errors."""

    def test_allows_by_default(self):
        """Breaker starts closed — allows requests."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test", threshold=3, cooldown=60)
        assert cb.allows() is True

    def test_opens_after_threshold_failures(self):
        """Breaker opens after threshold consecutive failures."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test", threshold=3, cooldown=60)
        cb.record_failure()  # 1
        assert cb.allows() is True
        cb.record_failure()  # 2
        assert cb.allows() is True
        cb.record_failure()  # 3 — opens
        assert cb.allows() is False  # open, blocked

    def test_closes_after_success(self):
        """record_success resets failures and re-opens."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test", threshold=2, cooldown=60)
        cb.record_failure()  # 1
        cb.record_failure()  # 2 — opens
        assert cb.allows() is False
        cb.record_success()
        assert cb.allows() is True

    def test_threshold_default_is_5(self):
        """Default threshold is 5."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test")
        assert cb.threshold == 5

    def test_cooldown_allows_after_timeout(self):
        """After cooldown expires, allows() returns True (auto-reset)."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test", threshold=1, cooldown=0)  # instant reset
        cb.record_failure()  # opens
        assert cb.allows() is True  # cooldown=0 means it auto-resets

    def test_record_failure_returns_true_when_open(self):
        """record_failure returns True when breaker opens."""
        from core.defense import CircuitBreaker

        cb = CircuitBreaker(name="test", threshold=2, cooldown=60)
        assert cb.record_failure() is False  # 1, not yet open
        assert cb.record_failure() is True  # 2, opens now


# ---------------------------------------------------------------------------
# pre_check_file_write tests
# ---------------------------------------------------------------------------


class TestPreCheckFileWrite:
    """Validate file write arguments before execution."""

    def test_valid_file_write(self):
        """Valid path and content → returns None."""
        from core.defense import pre_check_file_write

        result = pre_check_file_write("test.py", "print('hello')")
        assert result is None

    def test_empty_path_returns_error(self):
        """Empty path → returns error message."""
        from core.defense import pre_check_file_write

        err = pre_check_file_write("", "content")
        assert err is not None

    def test_none_path_raises_type_error(self):
        """None path → TypeError (Path(None) fails)."""
        from core.defense import pre_check_file_write

        with pytest.raises(TypeError):
            pre_check_file_write(None, "content")  # type: ignore

    def test_none_content_raises_type_error(self):
        """None content → TypeError (len(None) fails)."""
        from core.defense import pre_check_file_write

        with pytest.raises(TypeError):
            pre_check_file_write("test.py", None)  # type: ignore


# ---------------------------------------------------------------------------
# pre_check_bash tests
# ---------------------------------------------------------------------------


class TestPreCheckBash:
    """Validate bash commands before execution."""

    def test_simple_command_ok(self):
        """Simple safe command → returns None."""
        from core.defense import pre_check_bash

        assert pre_check_bash("echo hello") is None

    def test_empty_command_returns_error(self):
        """Empty command → returns error."""
        from core.defense import pre_check_bash

        err = pre_check_bash("")
        assert err is not None

    def test_none_command_raises_type_error(self):
        """None command → TypeError."""
        from core.defense import pre_check_bash

        with pytest.raises(TypeError):
            pre_check_bash(None)  # type: ignore


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------


class TestDefenseModule:
    """Module-level functions: get_circuit, reset_defense_state."""

    def test_get_circuit_creates_breaker(self):
        """get_circuit returns a CircuitBreaker by tool name."""
        from core.defense import get_circuit, reset_defense_state

        reset_defense_state()
        cb = get_circuit("test_tool")
        assert cb is not None
        assert hasattr(cb, "allows")

    def test_get_circuit_is_cached(self):
        """get_circuit returns the same breaker for same tool name."""
        from core.defense import get_circuit, reset_defense_state

        reset_defense_state()
        cb1 = get_circuit("tool_a")
        cb2 = get_circuit("tool_a")
        assert cb1 is cb2

    def test_reset_defense_state_clears_cache(self):
        """reset_defense_state clears all cached circuits."""
        from core.defense import get_circuit, reset_defense_state

        reset_defense_state()
        cb1 = get_circuit("tool_a")
        cb1.record_failure()
        reset_defense_state()
        cb2 = get_circuit("tool_a")
        # After reset, should be a fresh breaker
        assert cb2 is not cb1
        assert cb2.allows() is True
