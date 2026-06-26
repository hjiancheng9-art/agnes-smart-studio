"""Unit tests for core/image_compare.py — 纯辅助函数（解析/校验/格式化）。

image_compare.py 主体是 Pillow 图像渲染 + 多模态裁判，需重依赖。
本文件只测纯逻辑辅助函数：
- _check_pillow: import 探测（环境相关，轻测）
- _check_images: 数量 2-4 + 文件存在性校验
- _fmt_size: 字节格式化
- _parse_paths: JSON 字符串 / list / 逗号空格分隔的多形态输入
- _parse_judge_response: 从大模型输出抠 JSON（markdown fence / 花括号截取）
- _safe_output_path: 不覆盖已有文件（用 tmp_path + monkeypatch IMAGE_OUT）

渲染函数 _make_side_by_side / _make_diff / execute_compare_* 跳过（需 Pillow + 真实图）。
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.image_compare import (
    _check_images,
    _check_pillow,
    _fmt_size,
    _parse_judge_response,
    _parse_paths,
    _safe_output_path,
)

# ── _check_pillow ─────────────────────────────────────────────────


def test_check_pillow_returns_none_or_error_string():
    """_check_pillow 应返回 None（已装）或错误字符串（未装）。"""
    result = _check_pillow()
    assert result is None or isinstance(result, str)


# ── _check_images ─────────────────────────────────────────────────


def test_check_images_too_few_returns_error():
    """少于 2 张图应报错。"""
    assert _check_images([]) is not None
    assert _check_images(["single.png"]) is not None


def test_check_images_too_many_returns_error(tmp_path):
    """超过 4 张图应报错。"""
    paths = [str(tmp_path / f"{i}.png") for i in range(5)]
    for p in paths:
        Path(p).write_bytes(b"x")
    assert _check_images(paths) is not None


def test_check_images_missing_files_listed(tmp_path):
    """存在的图应通过；不存在的路径应在错误信息里列出。"""
    existing = tmp_path / "a.png"
    existing.write_bytes(b"x")
    err = _check_images([str(existing), str(tmp_path / "ghost.png")])
    assert err is not None
    assert "ghost.png" in err


def test_check_images_valid_pair_returns_none(tmp_path):
    """2 张存在的图 → None（无错误）。"""
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    assert _check_images([str(a), str(b)]) is None


def test_check_images_four_is_max(tmp_path):
    """正好 4 张存在的图 → None（边界）。"""
    paths = []
    for i in range(4):
        p = tmp_path / f"{i}.png"
        p.write_bytes(b"x")
        paths.append(str(p))
    assert _check_images(paths) is None


# ── _fmt_size ─────────────────────────────────────────────────────


def test_fmt_size_bytes():
    """< 1024 → 'NB'。"""
    assert _fmt_size(0) == "0B"
    assert _fmt_size(512) == "512B"
    assert _fmt_size(1023) == "1023B"


def test_fmt_size_kilobytes():
    """1024 <= n < 1MB → 'X.YKB'。"""
    assert _fmt_size(1024) == "1.0KB"
    assert _fmt_size(2048) == "2.0KB"


def test_fmt_size_megabytes():
    """>= 1MB → 'X.YYMB'。"""
    assert _fmt_size(1024 * 1024) == "1.00MB"
    assert _fmt_size(1024 * 1024 * 5) == "5.00MB"


def test_fmt_size_boundary_between_units():
    """单位边界：1023B → KB 区间起点 1024。"""
    assert _fmt_size(1023).endswith("B")
    assert _fmt_size(1024).endswith("KB")


# ── _parse_paths ──────────────────────────────────────────────────


def test_parse_paths_from_list():
    """list 输入直接转 list[str]。"""
    assert _parse_paths(["a.png", "b.png"]) == ["a.png", "b.png"]


def test_parse_paths_from_json_array_string():
    """JSON 数组字符串应被解析。"""
    s = '["a.png", "b.png"]'
    assert _parse_paths(s) == ["a.png", "b.png"]


def test_parse_paths_from_comma_separated_string():
    """非 JSON 的逗号分隔字符串应回退为 split。"""
    assert _parse_paths("a.png, b.png, c.png") == ["a.png", "b.png", "c.png"]


def test_parse_paths_from_space_separated_string():
    """空格分隔字符串也应回退为 split。"""
    assert _parse_paths("a.png b.png") == ["a.png", "b.png"]


def test_parse_paths_from_mixed_separators():
    """逗号+空格混合分隔。"""
    result = _parse_paths("a.png,b.png   c.png")
    assert result == ["a.png", "b.png", "c.png"]


def test_parse_paths_coerces_non_string_elements():
    """非字符串元素应被 str() 转换。"""
    result = _parse_paths([1, 2, 3])
    assert result == ["1", "2", "3"]


def test_parse_paths_empty_string_returns_empty():
    """空字符串 → 空列表。"""
    # 空串 json.loads 失败 → 回退 split → 过滤空 → []
    assert _parse_paths("") == []


# ── _parse_judge_response ─────────────────────────────────────────


def test_parse_judge_response_plain_json():
    """纯 JSON 字符串应直接解析。"""
    raw = '{"winner": "A", "score": 9}'
    data = _parse_judge_response(raw)
    assert data == {"winner": "A", "score": 9}


def test_parse_judge_response_with_markdown_fence():
    """带 ```json fence 的输出应剥除后解析。"""
    raw = '```json\n{"winner": "B"}\n```'
    assert _parse_judge_response(raw) == {"winner": "B"}


def test_parse_judge_response_with_bare_fence():
    """不带 json 标记的 fence 也应剥除。"""
    raw = '```\n{"winner": "C"}\n```'
    assert _parse_judge_response(raw) == {"winner": "C"}


def test_parse_judge_response_extracts_innermost_braces():
    """JSON 前后有说明文字时应截取最外层花括号。"""
    raw = '好的，评分如下：{"winner": "A", "score": 8} 以上是我的判断。'
    assert _parse_judge_response(raw) == {"winner": "A", "score": 8}


def test_parse_judge_response_empty_raises():
    """空输入应抛 ValueError（裁判返回为空）。"""
    with pytest.raises(ValueError):
        _parse_judge_response("")
    with pytest.raises(ValueError):
        _parse_judge_response(None)


def test_parse_judge_response_invalid_json_raises():
    """无法解析的内容应抛 JSONDecodeError。"""
    with pytest.raises(json.JSONDecodeError):
        _parse_judge_response("not json at all, no braces")


def test_parse_judge_response_nested_braces():
    """含嵌套对象的 JSON 应正确解析（最外层花括号截取）。"""
    raw = '{"winner": "A", "scores": {"A": 9, "B": 7}}'
    data = _parse_judge_response(raw)
    assert data["scores"]["A"] == 9


# ── _safe_output_path ─────────────────────────────────────────────


def test_safe_output_path_returns_nonexistent_path(tmp_path, monkeypatch):
    """_safe_output_path 应返回一个不存在的路径（避免覆盖）。"""
    monkeypatch.setattr("core.image_compare.IMAGE_OUT", tmp_path)
    p = _safe_output_path("test", ".png")
    assert not Path(p).exists()
    assert p.endswith(".png")
    assert "test" in Path(p).name


def test_safe_output_path_avoids_collision(tmp_path, monkeypatch):
    """若时间戳路径已存在，应追加 _1 / _2 后缀。"""
    monkeypatch.setattr("core.image_compare.IMAGE_OUT", tmp_path)
    # 第一次拿到路径 P，预先创建它
    p1 = _safe_output_path("dup", ".png")
    Path(p1).write_bytes(b"x")
    # 第二次应拿到不同路径
    p2 = _safe_output_path("dup", ".png")
    assert p1 != p2
    assert not Path(p2).exists()


def test_safe_output_path_preserves_extension(tmp_path, monkeypatch):
    """扩展名应正确保留。"""
    monkeypatch.setattr("core.image_compare.IMAGE_OUT", tmp_path)
    for ext in (".png", ".jpg", ".webp"):
        p = _safe_output_path("x", ext)
        assert p.endswith(ext)
