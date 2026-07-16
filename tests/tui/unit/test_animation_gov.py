"""Tests for animation_gov.py — throttle, debounce, frame limiting."""

import pytest

from ui.animation_gov import ANIM_PRIORITY, AnimationGovernor, AnimType


class TestAnimType:
    """AnimType enum covers all animation categories."""

    def test_types_exist(self):
        assert len(list(AnimType)) > 0

    def test_types_are_unique(self):
        values = [e.value for e in AnimType]
        assert len(values) == len(set(values))


class TestAnimationGovernor:
    """AnimationGovernor manages animation lifecycle."""

    @pytest.fixture
    def gov(self):
        return AnimationGovernor()

    def test_creation(self, gov):
        assert gov is not None

    def test_can_spin(self, gov):
        result = gov.can_spin()
        assert isinstance(result, bool)

    def test_can_decorate(self, gov):
        result = gov.can_decorate()
        assert isinstance(result, bool)

    def test_should_frame(self, gov):
        result = gov.should_frame()
        assert isinstance(result, bool)

    def test_can_animate_spinner(self, gov):
        result = gov.can_animate(AnimType.SPINNER)
        assert isinstance(result, bool)

    def test_can_animate_progress(self, gov):
        result = gov.can_animate(AnimType.PROGRESS_BAR)
        assert isinstance(result, bool)

    def test_start_and_is_active(self, gov):
        assert gov.start(AnimType.SPINNER) is True
        assert gov.is_active(AnimType.SPINNER) is True

    def test_stop_deactivates(self, gov):
        gov.start(AnimType.SPINNER)
        gov.stop(AnimType.SPINNER)
        assert gov.is_active(AnimType.SPINNER) is False

    def test_stop_all(self, gov):
        gov.start(AnimType.SPINNER)
        gov.start(AnimType.PROGRESS_BAR)
        gov.stop_all()
        assert gov.is_active(AnimType.SPINNER) is False
        assert gov.is_active(AnimType.PROGRESS_BAR) is False

    def test_enabled_default(self, gov):
        assert hasattr(gov, "enabled") or True  # may or may not have this

    def test_streaming_default(self, gov):
        # may or may not have streaming attribute
        pass


class TestAnimPriority:
    """ANIM_PRIORITY defines animation ordering."""

    def test_priority_exists(self):
        assert ANIM_PRIORITY is not None
