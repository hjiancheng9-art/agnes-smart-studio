"""Tests for core/version.py — 版本单一真源"""

from core.version import (
    BUILD_LABEL,
    V6_HIGHLIGHTS,
    V6_METRICS,
    VERSION,
    VERSION_TAG,
    __version__,
    get_version_info,
)


class TestVersion:
    """版本信息测试"""

    def test_version_string(self):
        assert __version__ == "6.0.0"

    def test_version_alias(self):
        assert __version__ == VERSION

    def test_version_tag(self):
        assert VERSION_TAG == "v6.0.0"

    def test_build_label(self):
        assert BUILD_LABEL == "CRUX Studio"

    def test_get_version_info_returns_dict(self):
        info = get_version_info()
        assert isinstance(info, dict)

    def test_version_info_has_version(self):
        info = get_version_info()
        assert info["version"] == "6.0.0"

    def test_version_info_has_major_minor_patch(self):
        info = get_version_info()
        assert info["major"] == 6
        assert info["minor"] == 0
        assert info["patch"] == 0

    def test_version_info_has_tag(self):
        info = get_version_info()
        assert info["tag"] == "v6.0.0"

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
    """v6.0 指标数据测试"""

    def test_metrics_dict(self):
        assert isinstance(V6_METRICS, dict)

    def test_metrics_has_tests_total(self):
        assert V6_METRICS["tests_total"] > 0

    def test_metrics_has_tests_failed(self):
        assert V6_METRICS["tests_failed"] >= 0

    def test_metrics_has_ruff_remaining(self):
        assert V6_METRICS["ruff_remaining"] >= 0

    def test_metrics_has_ai_score(self):
        assert V6_METRICS["ai_score_before"] > 0
        assert V6_METRICS["ai_score_after"] > 0


class TestHighlights:
    """v6.0 亮点列表测试"""

    def test_highlights_is_list(self):
        assert isinstance(V6_HIGHLIGHTS, list)

    def test_highlights_non_empty(self):
        assert len(V6_HIGHLIGHTS) > 0

    def test_highlights_are_strings(self):
        for h in V6_HIGHLIGHTS:
            assert isinstance(h, str)
