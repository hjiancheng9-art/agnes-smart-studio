"""Tests for core/pipeline_tools.py — shot ranges, scene detection helpers, constants."""

from core.pipeline_tools import (
    EXECUTOR_MAP,
    PIPELINE_TOOLS,
    _build_shot_ranges,
    _densify_ranges,
    _paced_ranges,
    _target_shots,
)


class TestTargetShots:
    def test_default_sensitivity(self):
        shots = _target_shots(60.0)
        assert shots > 0

    def test_sensitivity_scales(self):
        low = _target_shots(60.0, sensitivity=20)
        high = _target_shots(60.0, sensitivity=80)
        assert high > low

    def test_short_video(self):
        shots = _target_shots(5.0)
        assert shots > 0


class TestBuildShotRanges:
    def test_single_cut(self):
        cuts = [10.0]
        ranges = _build_shot_ranges(cuts, duration=30.0)
        assert len(ranges) >= 2

    def test_no_cuts(self):
        ranges = _build_shot_ranges([], duration=10.0)
        assert len(ranges) == 1
        assert ranges[0]["startTime"] == 0.0
        assert ranges[0]["endTime"] == 10.0

    def test_ranges_cover_full_duration(self):
        ranges = _build_shot_ranges([5.0, 15.0], duration=30.0)
        total = sum(r["duration"] for r in ranges)
        assert abs(total - 30.0) < 1.0

    def test_min_shot_enforced(self):
        ranges = _build_shot_ranges([0.1, 0.2, 0.3], duration=10.0, min_shot=2.0)
        for r in ranges:
            assert r["duration"] >= 1.9


class TestPacedRanges:
    def test_distributes_evenly(self):
        ranges = _paced_ranges(duration=30.0, count=3)
        assert len(ranges) == 3

    def test_covers_duration(self):
        ranges = _paced_ranges(duration=10.0, count=2)
        total = sum(r["duration"] for r in ranges)
        assert abs(total - 10.0) < 0.1

    def test_default_count_is_one(self):
        ranges = _paced_ranges(duration=10.0, count=0)
        assert len(ranges) == 1


class TestDensifyRanges:
    def test_adds_shots(self):
        original = _paced_ranges(duration=10.0, count=1)
        result = _densify_ranges(original, target=3)
        assert len(result) >= len(original)

    def test_respects_min_shot(self):
        original = _paced_ranges(duration=1.0, count=1)
        result = _densify_ranges(original, target=5, min_shot=0.3)
        for r in result:
            assert r["duration"] >= 0.29

    def test_empty_input(self):
        result = _densify_ranges([], target=3)
        assert result == []


class TestConstants:
    def test_executor_map_exists(self):
        assert isinstance(EXECUTOR_MAP, dict)

    def test_tool_defs_exists(self):
        assert isinstance(PIPELINE_TOOLS, list)
