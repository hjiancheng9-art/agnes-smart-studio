"""Tests for core/methodology.py"""

from core.methodology import MethodologyState


class TestMethodology:
    def test_state_exists(self):
        assert MethodologyState is not None
