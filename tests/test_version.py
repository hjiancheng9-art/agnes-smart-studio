"""Tests for core/version.py — 版本单一来源

设计原则：不硬编码具体版本号，避免每次发版都要改测试。
改为校验版本格式、内部一致性、以及 get_version_info() 的契约。
"""

import re

from core.version import (
    BUILD_LABEL,
    V6_HIGHLIGHTS,
    V6_METRICS,
    VERSION,
    VERSION_TAG,
    __version__,
    get_version_info,
)

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class TestVersion:
    """版本信息测试"""

    def test_version_is_semver(self):
        assert _SEMVER_RE.match(__version__), f"非法版本号: {__version__}"

    def test_version_alias(self):
        assert __version__ == VERSION

    def test_version_tag_matches_version(self):
        assert f"v{__version__}" == VERSION_TAG

    def test_build_label(self):
        assert BUILD_LABEL == "CRUX Studio"

    def test_get_version_info_returns_dict(self):
        info = get_version_info()
        assert isinstance(info, dict)

    def test_version_info_matches_version(self):
        info = get_version_info()
        assert info["version"] == __version__

    def test_version_info_major_minor_patch_consistent(self):
        info = get_version_info()
        major, minor, patch = (int(x) for x in __version__.split("."))
        assert info["major"] == major
        assert info["minor"] == minor
        assert info["patch"] == patch

    def test_version_info_tag_consistent(self):
        info = get_version_info()
        assert info["tag"] == VERSION_TAG

    def test_version_info_has_label(self):
        info = get_version_info()
        assert info["label"] == "CRUX Studio"

    def test_version_info_has_metrics(self):
        info = get_version_info()
        assert "metrics" in info
        assert isinstance(info["metrics"], dict)

    def test_version_info_has_highlights(self):
        info = get_version_info()
        assert "highlights" in info
        assert isinstance(info["highlights"], list)
        assert len(info["highlights"]) > 0


class TestMetrics:
    """指标数据契约测试（只校验存在且类型/取值合理，不锁定具体键名以外的字段）"""

    def test_metrics_dict(self):
        assert isinstance(V6_METRICS, dict)

    def test_metrics_has_tests_total(self):
        assert V6_METRICS["tests_total"] > 0

    def test_metrics_has_tests_failed(self):
        assert V6_METRICS["tests_failed"] >= 0

    def test_metrics_values_are_non_negative_ints(self):
        for key, value in V6_METRICS.items():
            assert isinstance(value, int), f"{key} 应为 int，实际 {type(value).__name__}"
            assert value >= 0, f"{key} 应 >= 0，实际 {value}"


class TestHighlights:
    """亮点列表测试"""

    def test_highlights_is_list(self):
        assert isinstance(V6_HIGHLIGHTS, list)

    def test_highlights_non_empty(self):
        assert len(V6_HIGHLIGHTS) > 0

    def test_highlights_are_strings(self):
        for h in V6_HIGHLIGHTS:
            assert isinstance(h, str)
