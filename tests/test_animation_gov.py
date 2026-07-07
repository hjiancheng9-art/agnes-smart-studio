"""
TDD tests for AnimationGovernor (ui/animation_gov.py)
"""
from __future__ import annotations

from ui.animation_gov import AnimationGovernor, AnimType


class TestAnimationGovernor:
    def test_default_state(self):
        gov = AnimationGovernor()
        assert gov.enabled == True
        assert gov.streaming == False
        assert gov.can_spin() == True
        assert gov.can_decorate() == True

    def test_streaming_disables_decoration(self):
        gov = AnimationGovernor()
        gov.streaming = True
        assert gov.can_spin() == True        # spinner OK during stream
        assert gov.can_decorate() == False   # decoration OFF

    def test_streaming_off_restores(self):
        gov = AnimationGovernor()
        gov.streaming = True
        gov.streaming = False
        assert gov.can_decorate() == True

    def test_disabled_blocks_all(self):
        gov = AnimationGovernor()
        gov.enabled = False
        assert gov.can_spin() == False
        assert gov.can_decorate() == False

    def test_ssh_mode(self):
        gov = AnimationGovernor(ssh_mode=True)
        assert gov.enabled == False

    def test_start_stop(self):
        gov = AnimationGovernor()
        assert gov.start(AnimType.SPINNER) == True
        assert gov.is_active(AnimType.SPINNER) == True
        gov.stop(AnimType.SPINNER)
        assert gov.is_active(AnimType.SPINNER) == False

    def test_priority_kick(self):
        gov = AnimationGovernor()
        gov.start(AnimType.ANIMATED_BORDER)  # low priority
        assert gov.start(AnimType.SPINNER) == True  # high priority kicks
        assert gov.is_active(AnimType.SPINNER) == True

    def test_frame_rate(self):
        gov = AnimationGovernor()
        assert gov.should_frame() == True   # first always OK
        assert gov.should_frame() == False  # too soon
        import time
        time.sleep(0.05)  # >41.7ms
        assert gov.should_frame() == True

    def test_stop_all(self):
        gov = AnimationGovernor()
        gov.start(AnimType.SPINNER)
        gov.start(AnimType.THINKING_FOLD)
        gov.stop_all()
        assert gov._active is None
