"""Tests for core/encoding.py — 编码设置"""

from core.encoding import setup


class TestEncodingSetup:
    def test_setup_returns_none(self):
        result = setup()
        assert result is None

    def test_setup_idempotent(self):
        setup()
        setup()  # 不应崩溃
        assert True
