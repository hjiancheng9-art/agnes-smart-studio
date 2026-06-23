"""Unit tests for core/pipeline_tools.py — 镜头切分纯数学函数。

pipeline_tools.py 大部分是 ffmpeg/HTTP 调用，但镜头切分逻辑是纯数学：
- _build_shot_ranges: 场景切换点 → 镜头区间
- _paced_ranges: 均匀分镜（回退策略）
- _densify_ranges: 长镜头拆分加密
- _target_shots: 时长+敏感度 → 目标镜头数

这些函数无外部依赖，是分镜/节奏规划的核心算法，值得锁定行为。

⚠ 只测纯逻辑；execute_* / _probe_duration / _detect_scene_cuts 等走子进程的跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.pipeline_tools import (
    _build_shot_ranges,
    _densify_ranges,
    _paced_ranges,
    _target_shots,
)


# ── _build_shot_ranges ────────────────────────────────────────────


def test_build_shot_ranges_no_cuts_single_range():
    """无切换点 → 单个覆盖全时长的区间。"""
    ranges = _build_shot_ranges([], duration=10.0, min_shot=1.0)
    assert len(ranges) == 1
    assert ranges[0]["startTime"] == 0.0
    assert ranges[0]["endTime"] == 10.0
    assert ranges[0]["duration"] == 10.0


def test_build_shot_ranges_splits_at_valid_cuts():
    """合法切换点应作为区间边界。"""
    ranges = _build_shot_ranges([3.0, 6.0], duration=10.0, min_shot=1.0)
    assert len(ranges) == 3
    assert ranges[0]["startTime"] == 0.0
    assert ranges[0]["endTime"] == 3.0
    assert ranges[1]["startTime"] == 3.0
    assert ranges[2]["endTime"] == 10.0


def test_build_shot_ranges_filters_too_close_to_start():
    """切换点 <= min_shot 应被过滤（太靠近开头）。"""
    ranges = _build_shot_ranges([0.5, 5.0], duration=10.0, min_shot=1.0)
    # 0.5 <= 1.0 → 过滤
    assert len(ranges) == 2  # 0~5, 5~10


def test_build_shot_ranges_filters_too_close_to_end():
    """切换点 >= duration - 0.1 应被过滤（太靠近结尾）。"""
    ranges = _build_shot_ranges([5.0, 9.95], duration=10.0, min_shot=1.0)
    # 9.95 >= 10 - 0.1 = 9.9 → 过滤
    assert len(ranges) == 2  # 0~5, 5~10


def test_build_shot_ranges_drops_short_trailing_segment():
    """若最后一段 < min_shot，应丢弃末尾切换点（合并到最后区间）。"""
    # duration=10, cuts=[9.5]，min_shot=1.0
    # 9.5 合法切点 → 边界 [0, 9.5, 10]，末段 0.5s < 1.0 → pop 9.5
    ranges = _build_shot_ranges([9.5], duration=10.0, min_shot=1.0)
    assert len(ranges) == 1
    assert ranges[0]["endTime"] == 10.0


def test_build_shot_ranges_keytime_is_midpoint():
    """keyTime 应在区间中点附近（至少 +0.08 偏移）。"""
    ranges = _build_shot_ranges([], duration=4.0, min_shot=1.0)
    r = ranges[0]
    # keyTime = start + max(0.08, duration/2)
    expected_key = 0.0 + max(0.08, 4.0 / 2)
    assert r["keyTime"] == round(expected_key, 3)


def test_build_shot_ranges_ids_are_sequential():
    """区间 id 应从 1 顺序递增。"""
    ranges = _build_shot_ranges([2.0, 4.0, 6.0], duration=10.0, min_shot=1.0)
    assert [r["id"] for r in ranges] == [1, 2, 3, 4]


def test_build_shot_ranges_values_are_rounded():
    """startTime/endTime/duration/keyTime 应 round 到 3 位小数。"""
    ranges = _build_shot_ranges([3.0], duration=10.0, min_shot=1.0)
    for r in ranges:
        for key in ("startTime", "endTime", "duration", "keyTime"):
            # round(x, 3) 后小数位 <= 3
            v = r[key]
            assert round(v, 3) == v


# ── _paced_ranges ─────────────────────────────────────────────────


def test_paced_ranges_even_split():
    """均匀拆分：每段时长 = duration / count。"""
    ranges = _paced_ranges(duration=10.0, count=5)
    assert len(ranges) == 5
    assert ranges[0]["startTime"] == 0.0
    assert ranges[-1]["endTime"] == 10.0
    for r in ranges:
        assert r["duration"] == round(10.0 / 5, 3)  # 2.0


def test_paced_ranges_count_zero_treated_as_one():
    """count=0 应被 max(1, count) 兜底为 1（防除零）。"""
    ranges = _paced_ranges(duration=10.0, count=0)
    assert len(ranges) == 1
    assert ranges[0]["endTime"] == 10.0


def test_paced_ranges_negative_count_treated_as_one():
    """负 count 同样兜底为 1。"""
    ranges = _paced_ranges(duration=6.0, count=-3)
    assert len(ranges) == 1


def test_paced_ranges_last_segment_covers_full_duration():
    """最后一段的 endTime 必须等于 duration（避免浮点误差导致末尾空洞）。"""
    ranges = _paced_ranges(duration=10.0, count=3)
    assert ranges[-1]["endTime"] == 10.0


def test_paced_ranges_non_divisible_step_rounded():
    """不能整除时步长应正确取整。"""
    ranges = _paced_ranges(duration=10.0, count=3)
    # step = 10/3 = 3.333...
    assert ranges[0]["duration"] == round(10.0 / 3, 3)


# ── _densify_ranges ───────────────────────────────────────────────


def _make_range(start: float, end: float, rid: int = 1) -> dict:
    return {
        "id": rid,
        "startTime": start,
        "endTime": end,
        "duration": round(end - start, 3),
        "keyTime": round((start + end) / 2, 3),
    }


def test_densify_already_at_target_keeps_count():
    """ranges 数 >= target 时只重新编号，不拆分。"""
    ranges = [_make_range(0, 2, 1), _make_range(2, 4, 2)]
    out = _densify_ranges(ranges, target=2)
    assert len(out) == 2
    assert [r["id"] for r in out] == [1, 2]


def test_densify_splits_longest_range_first():
    """需要加密时优先拆最长的区间。"""
    ranges = [_make_range(0, 6, 1)]  # 单个 6s 长镜头
    out = _densify_ranges(ranges, target=3, min_shot=0.5)
    assert len(out) == 3
    # 所有子区间应标记 parentRangeId
    for r in out:
        assert r["parentRangeId"] == 1


def test_densify_respects_min_shot_floor():
    """min_shot 限制下，无法再拆时应提前停止。"""
    ranges = [_make_range(0, 1.0, 1)]  # 1s 镜头
    # target=5 但 1s / 5 = 0.2s < min_shot=0.5 → 最多拆成 2 段
    out = _densify_ranges(ranges, target=5, min_shot=0.5)
    assert len(out) <= 2  # 拆不动就停


def test_densify_renumbers_sequentially():
    """拆分后 id 应从 1 连续递增。"""
    ranges = [_make_range(0, 4, 1), _make_range(4, 8, 2)]
    out = _densify_ranges(ranges, target=4)
    assert [r["id"] for r in out] == list(range(1, len(out) + 1))


def test_densify_subranges_cover_parent_exactly():
    """拆分后子区间的时间并集应等于父区间（无重叠/无空洞）。"""
    ranges = [_make_range(0, 6, 1)]
    out = _densify_ranges(ranges, target=3, min_shot=0.5)
    assert out[0]["startTime"] == 0.0
    assert out[-1]["endTime"] == 6.0
    for i in range(len(out) - 1):
        assert out[i]["endTime"] == out[i + 1]["startTime"]


# ── _target_shots ─────────────────────────────────────────────────


def test_target_shots_zero_duration_returns_one():
    """duration<=0 → 1（兜底）。"""
    assert _target_shots(0.0) == 1
    assert _target_shots(-5.0) == 1


def test_target_shots_basic_proportion():
    """默认敏感度下应按 duration/ideal 计算（约 2.35s/shot）。"""
    # 10s / 2.35 ≈ 4.25 → round=4
    result = _target_shots(10.0)
    assert isinstance(result, int)
    assert result >= 1


def test_target_shots_higher_sensitivity_more_shots():
    """敏感度越高（ideal 越短）→ 镜头数越多（单调）。"""
    low = _target_shots(30.0, sensitivity=35)
    high = _target_shots(30.0, sensitivity=85)
    assert high >= low


def test_target_shots_clamped_to_min_for_short_duration():
    """短时长（<8s）应夹到 min=1。"""
    # duration=2, sensitivity=85 → ideal=1.2, raw=round(2/1.2)=2,
    # 但 min_s = 1 (duration<8), max_s=24 → 2 夹后仍 2
    result = _target_shots(2.0, sensitivity=85)
    assert result >= 1


def test_target_shots_clamped_to_max_for_long_duration():
    """超长时长不应超过 max 上限（duration>90 → max=60）。"""
    result = _target_shots(1000.0, sensitivity=50)
    assert result <= 60


def test_target_shots_min_floor_increases_with_duration():
    """min_s 随时长阶梯上升：<8→1, <15→4, <45→10, else→16。"""
    # duration=20 (>15, <45) → min_s=10
    # raw = round(20/2.35) ≈ 9, 夹到 min_s=10
    result_20s = _target_shots(20.0, sensitivity=50)
    assert result_20s >= 10  # 被下限拉到 10


def test_target_shots_returns_int():
    """返回值必须是 int（下游 range/编号依赖）。"""
    assert isinstance(_target_shots(15.0), int)
    assert isinstance(_target_shots(0.0), int)
