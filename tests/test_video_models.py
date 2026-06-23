"""Unit tests for core/video_models.py — 视频模型能力注册表与查询工具。

video_models.py 是纯数据 + 纯逻辑模块（无 IO/网络/子进程），
定义 VIDEO_MODELS 全局约束表与查询函数。被 AGENTS.md 标注为
"工作启动前必须先锁定模型 → 查表获取时长"的核心契约。

覆盖：
- VIDEO_MODELS 数据完整性（必要字段、时长>0 的视频模型集合）
- get_model_capability 命中/未命中
- list_video_models 过滤（跳过纯图片模型、按 mode 过滤）
- auto_select_model 时长切分计算（向上取整、边界、preferred 优先级、KeyError）
- execute_video_model_info JSON 序列化（命中/未命中/全部）
- 工具定义与执行器映射
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.video_models import (
    VIDEO_MODELS,
    VIDEO_MODEL_EXECUTOR_MAP,
    VIDEO_MODEL_TOOL_DEFS,
    auto_select_model,
    execute_video_model_info,
    get_model_capability,
    list_video_models,
)


# ── VIDEO_MODELS 数据完整性 ────────────────────────────────────────


@pytest.fixture(scope="module")
def video_model_ids():
    """所有 max_duration_s > 0 的模型 ID（真正的视频模型）。"""
    return {mid for mid, m in VIDEO_MODELS.items() if m["max_duration_s"] > 0}


def test_video_models_has_required_fields():
    """每个模型必须含 display_name / provider / max_duration_s / modes。"""
    required = {"display_name", "provider", "max_duration_s", "modes"}
    for mid, info in VIDEO_MODELS.items():
        missing = required - set(info)
        assert not missing, f"模型 {mid} 缺字段: {missing}"


def test_video_models_modes_are_lists():
    """modes 字段必须是 list（用于 `in` 过滤）。"""
    for mid, info in VIDEO_MODELS.items():
        assert isinstance(info["modes"], list), f"{mid}.modes 不是 list"


def test_video_models_durations_non_negative():
    """max_duration_s 不应为负（0 表示纯图片模型）。"""
    for mid, info in VIDEO_MODELS.items():
        assert info["max_duration_s"] >= 0, f"{mid} 时长为负"


def test_video_models_known_video_entries_present():
    """关键视频模型应在表中（防止误删）。"""
    for mid in ("agnes-video-v2.0", "kling", "jimeng", "runway", "veo"):
        assert mid in VIDEO_MODELS, f"缺失核心视频模型: {mid}"


def test_video_models_pure_image_models_have_zero_duration():
    """纯图片模型（dalle/gemini）max_duration_s 必须为 0。"""
    assert VIDEO_MODELS["dalle"]["max_duration_s"] == 0
    assert VIDEO_MODELS["gemini"]["max_duration_s"] == 0


# ── get_model_capability ──────────────────────────────────────────


def test_get_model_capability_hit_returns_dict():
    """命中返回模型 dict（浅拷贝引用即可，调用方不应原地改）。"""
    cap = get_model_capability("kling")
    assert cap is not None
    assert cap["display_name"]  # 非空


def test_get_model_capability_miss_returns_none():
    """未命中返回 None（非抛异常）。"""
    assert get_model_capability("not-a-real-model") is None


# ── list_video_models ─────────────────────────────────────────────


def test_list_video_models_no_filter_excludes_pure_image():
    """无过滤时返回全部视频模型，但跳过 max_duration_s<=0 的纯图片模型。"""
    items = list_video_models()
    assert len(items) > 0
    # 不应出现纯图片模型
    ids = {it["id"] for it in items}
    assert "dalle" not in ids
    assert "gemini" not in ids
    # 应包含核心视频模型
    assert "agnes-video-v2.0" in ids


def test_list_video_models_item_shape():
    """每条记录应含 id/display_name/provider/max_duration_s/default_duration_s/modes/note。"""
    items = list_video_models()
    sample = items[0]
    expected_keys = {"id", "display_name", "provider", "max_duration_s",
                     "default_duration_s", "modes", "note"}
    assert expected_keys <= set(sample)


def test_list_video_models_mode_filter():
    """mode_filter='image_to_video' 只返回支持该模式的模型。"""
    items = list_video_models("image_to_video")
    assert len(items) > 0
    for it in items:
        assert "image_to_video" in it["modes"]


def test_list_video_models_unknown_mode_returns_empty():
    """未知 mode_filter 应返回空列表（不报错）。"""
    assert list_video_models("not_a_real_mode") == []


# ── auto_select_model ─────────────────────────────────────────────


def test_auto_select_model_ceil_logic():
    """calls_needed 用 round(d/max + 0.4) 向上取整。

    10s 总时长 / 5s 上限 = 2.0 + 0.4 = 2.4 → round=2 calls。
    """
    result = auto_select_model(10.0)  # 默认 agnes-video-v2.0 (5s)
    assert result["model"] == "agnes-video-v2.0"
    assert result["max_per_call_s"] == 5.0
    assert result["calls_needed"] == 2
    assert result["segment_duration_s"] == 5.0


def test_auto_select_model_preferred_override():
    """preferred 指定已知模型时优先用之（即使时长更短）。"""
    result = auto_select_model(30.0, preferred="kling")  # kling=10s
    assert result["model"] == "kling"
    assert result["max_per_call_s"] == 10.0
    assert result["calls_needed"] == 3  # 30/10=3.0+0.4=3.4 → 3


def test_auto_select_model_preferred_unknown_falls_back():
    """preferred 指定未知模型时，能力数据回退到 agnes 默认。

    注意当前实现契约（潜在不一致）：返回值的 `model` 字段仍回显原始 preferred
    字符串（line 234 `preferred or "agnes-video-v2.0"`），但 max_per_call_s /
    calls_needed 用的是 agnes(5s) 的数据。即字段名与数据来源不统一。
    若未来修正此不一致，本断言应改为 `== "agnes-video-v2.0"`。
    """
    result = auto_select_model(10.0, preferred="ghost-model")
    # 能力数据走 agnes 默认（5s 上限）
    assert result["max_per_call_s"] == 5.0
    assert result["calls_needed"] == 2
    # model 字段回显 preferred（当前实现行为，非 agnes）
    assert result["model"] == "ghost-model"


def test_auto_select_model_single_call_when_short():
    """总时长 <= 单段上限时只需 1 次调用（max(1, ...) 下限）。"""
    result = auto_select_model(3.0)
    assert result["calls_needed"] == 1
    assert result["segment_duration_s"] == 3.0


def test_auto_select_model_segment_capped_at_max():
    """segment_duration_s 不超过 max_per_call_s（min(max_per, ...)）。"""
    result = auto_select_model(2.0)
    assert result["segment_duration_s"] <= result["max_per_call_s"]


def test_auto_select_model_preferred_pure_image_falls_back_duration_to_5():
    """preferred 选到纯图片模型（max_duration_s=0）时 max_per 回退到 5.0。"""
    result = auto_select_model(10.0, preferred="dalle")  # dalle=0s
    # dalle 时长为 0，触发 `if max_per <= 0: max_per = 5.0`
    assert result["max_per_call_s"] == 5.0
    assert result["calls_needed"] == 2


def test_auto_select_model_returns_total_duration_echo():
    """返回值应回显 total_duration_s（调用方核对）。"""
    result = auto_select_model(12.5)
    assert result["total_duration_s"] == 12.5


def test_auto_select_model_empty_registry_raises():
    """VIDEO_MODELS 为空时（理论上不会发生）应抛 KeyError。

    通过临时清空表来模拟（用 monkeypatch 保护全局状态）。
    """
    import core.video_models as vm
    original = vm.VIDEO_MODELS
    vm.VIDEO_MODELS = {}
    try:
        with pytest.raises(KeyError):
            auto_select_model(10.0)
    finally:
        vm.VIDEO_MODELS = original


# ── execute_video_model_info ──────────────────────────────────────


def test_execute_video_model_info_known_returns_success_json():
    """已知 model_id 返回 success=True 的 JSON。"""
    out = execute_video_model_info("kling")
    data = json.loads(out)
    assert data["success"] is True
    assert data["model_id"] == "kling"
    assert "display_name" in data
    assert "max_duration_s" in data


def test_execute_video_model_info_unknown_returns_error_json():
    """未知 model_id 返回 success=False 的 JSON（含可用 ID 列表）。"""
    out = execute_video_model_info("ghost-model")
    data = json.loads(out)
    assert data["success"] is False
    assert "error" in data
    assert "available_ids" in data
    # 可用 ID 列表不应含纯图片模型
    assert "dalle" not in data["available_ids"]


def test_execute_video_model_info_no_arg_lists_all():
    """不传 model_id 时列出全部视频模型。"""
    out = execute_video_model_info()
    data = json.loads(out)
    assert data["success"] is True
    assert data["total_models"] > 0
    assert isinstance(data["models"], list)
    assert "summary" in data


def test_execute_video_model_info_pure_image_id_treated_as_known():
    """纯图片模型 ID（如 dalle）在 VIDEO_MODELS 中存在 → 返回 success=True。

    注意：list_video_models 会跳过它，但 get_model_capability 仍能命中。
    """
    out = execute_video_model_info("dalle")
    data = json.loads(out)
    assert data["success"] is True
    assert data["max_duration_s"] == 0


# ── 工具定义与执行器映射 ──────────────────────────────────────────


def test_video_model_tool_defs_well_formed():
    """TOOL_DEFS 应是 function 工具定义列表。"""
    assert isinstance(VIDEO_MODEL_TOOL_DEFS, list)
    assert len(VIDEO_MODEL_TOOL_DEFS) >= 1
    for td in VIDEO_MODEL_TOOL_DEFS:
        assert td["type"] == "function"
        assert "name" in td["function"]
        assert "parameters" in td["function"]


def test_executor_map_dispatches_video_model_info():
    """EXECUTOR_MAP 应能通过工具名分发到 execute_video_model_info。"""
    fn = VIDEO_MODEL_EXECUTOR_MAP.get("video_model_info")
    assert fn is not None
    out = fn(model_id="kling")
    assert json.loads(out)["success"] is True


def test_executor_map_dispatches_with_no_kwargs():
    """不传 kwargs 时应也能分发（kw.get 兜底为空串 → 列全部）。"""
    fn = VIDEO_MODEL_EXECUTOR_MAP["video_model_info"]
    out = fn()
    assert json.loads(out)["success"] is True
