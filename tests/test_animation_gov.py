"""
TDD tests for AnimationGovernor (ui/animation_gov.py)
"""
from __future__ import annotations

from ui.animation_gov import AnimationGovernor, AnimType


class TestAnimationGovernor:
    def test_default_state(self):
        gov = AnimationGovernor()
        assert gov.enabled
        assert not gov.streaming
        assert gov.can_spin()
        assert gov.can_decorate()

    def test_streaming_disables_decoration(self):
        gov = AnimationGovernor()
        gov.streaming = True
        assert gov.can_spin()        # spinner OK during stream
        assert not gov.can_decorate()   # decoration OFF

    def test_streaming_off_restores(self):
        gov = AnimationGovernor()
        gov.streaming = True
        gov.streaming = False
        assert gov.can_decorate()

    def test_disabled_blocks_all(self):
        gov = AnimationGovernor()
        gov.enabled = False
        assert not gov.can_spin()
        assert not gov.can_decorate()

    def test_ssh_mode(self):
        gov = AnimationGovernor(ssh_mode=True)
        assert not gov.enabled

    def test_start_stop(self):
        gov = AnimationGovernor()
        assert gov.start(AnimType.SPINNER)
        assert gov.is_active(AnimType.SPINNER)
        gov.stop(AnimType.SPINNER)
        assert not gov.is_active(AnimType.SPINNER)

    def test_priority_kick(self):
        gov = AnimationGovernor()
        gov.start(AnimType.ANIMATED_BORDER)  # low priority
        assert gov.start(AnimType.SPINNER)  # high priority kicks
        assert gov.is_active(AnimType.SPINNER)

    def test_frame_rate(self):
        gov = AnimationGovernor()
        assert gov.should_frame()   # first always OK
        assert not gov.should_frame()  # too soon
        import time
        time.sleep(0.05)  # >41.7ms
        assert gov.should_frame()

    def test_stop_all(self):
        gov = AnimationGovernor()
        gov.start(AnimType.SPINNER)
        gov.start(AnimType.THINKING_FOLD)
        gov.stop_all()
        assert gov._active is None
