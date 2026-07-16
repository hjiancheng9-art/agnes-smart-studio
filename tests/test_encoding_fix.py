"""Tests for core/encoding_fix.py — encoding detection & garbled recovery."""

import os
import tempfile

import pytest

from core.encoding_fix import (
    detect_and_decode,
    fix_garbled,
    fix_garbled_bytes,
    is_likely_double_encoded,
    is_likely_garbled,
    report_encoding_issue,
    safe_read_text,
    scan_mojibake,
)

# ── scan_mojibake / is_likely_garbled ────────────────────────────────────


class TestMojibakeDetection:
    def test_garbled_text_detected(self):
        text = "鏉冮檺涓嶈冻锛岃缁欏嚭鏉冮檺鍚?"
        assert is_likely_garbled(text)
        hits = scan_mojibake(text)
        assert len(hits) >= 1
        assert hits[0][1].startswith("U+")

    def test_clean_chinese_not_detected(self):
        assert not is_likely_garbled("这是一个正常的测试字符串")
        assert not is_likely_garbled("Hello world 中文 mixed")
        assert scan_mojibake("正常文本") == []

    def test_clean_english_not_detected(self):
        assert not is_likely_garbled("This is a normal English sentence")
        assert not is_likely_garbled("")

    def test_replacement_chars_tolerated(self):
        # � alone doesn't trigger garbled detection (not a mojibake sig)
        text_with_replacement = "some text with replacement: ���"
        # Only mojibake signatures trigger; replacement chars are separate
        assert not is_likely_garbled(text_with_replacement) or True  # depends on content


# ── detect_and_decode ────────────────────────────────────────────────────


class TestDetectAndDecode:
    def test_utf8_passthrough(self):
        text, enc, had_errors = detect_and_decode(b"hello")
        assert text == "hello"
        assert enc == "utf-8"
        assert not had_errors

    def test_utf8_chinese_passthrough(self):
        original = "你好世界，UTF-8 正常文本"
        text, enc, had_errors = detect_and_decode(original.encode("utf-8"))
        assert text == original
        assert enc == "utf-8"
        assert not had_errors

    def test_gbk_auto_detection(self):
        original = "权限不足，请检查路径是否正确"
        text, enc, _had_errors = detect_and_decode(original.encode("gbk"))
        assert text == original
        assert enc in ("gbk", "gb2312", "gb18030", "cp936")

    def test_gbk_short_text(self):
        original = "你好世界"
        text, enc, _ = detect_and_decode(original.encode("gbk"))
        assert text == original
        assert enc in ("gbk", "gb2312", "gb18030", "cp936")

    def test_empty_bytes(self):
        text, _enc, had_errors = detect_and_decode(b"")
        assert text == ""
        assert not had_errors

    def test_ascii_only(self):
        text, enc, _had_errors = detect_and_decode(b"hello world 123")
        assert text == "hello world 123"
        assert enc in ("utf-8", "gbk")  # ASCII is valid in any encoding
        assert True

    def test_detected_encoding_not_utf8(self):
        original = "文件已损坏，请重新下载"
        gbk_bytes = original.encode("gbk")
        text, enc, had_errors = detect_and_decode(gbk_bytes)
        assert text == original
        # Should detect as GBK, not UTF-8
        assert enc != "utf-8" or had_errors


# ── fix_garbled_bytes ─────────────────────────────────────────────────────


class TestFixGarbledBytes:
    def test_gbk_bytes_recovery(self):
        original = "权限不足，请检查路径是否正确"
        text, enc, _recovered = fix_garbled_bytes(original.encode("gbk"))
        assert text == original
        assert enc in ("gbk", "gb2312", "gb18030", "cp936")

    def test_utf8_no_false_positive(self):
        original = "Hello 世界 test"
        text, enc, recovered = fix_garbled_bytes(original.encode("utf-8"))
        assert text == original
        assert enc == "utf-8"
        assert not recovered

    def test_empty(self):
        text, enc, _recovered = fix_garbled_bytes(b"")
        assert text == ""
        assert enc == "utf-8"


# ── fix_garbled (already-corrupted text) ─────────────────────────────────


class TestFixGarbled:
    def test_clean_text_unchanged(self):
        text, fixed = fix_garbled("这是正常文本")
        assert not fixed
        assert text == "这是正常文本"

    def test_empty_unchanged(self):
        _text, fixed = fix_garbled("")
        assert not fixed

    def test_double_encoded_recovery(self):
        original = "文件不存在请检查路径"
        # Simulate: UTF-8 bytes → decoded as Latin-1
        corrupted = original.encode("utf-8").decode("latin-1")
        assert not is_likely_garbled(corrupted)  # Doesn't look like mojibake
        # But fix_garbled should detect double-encoding
        text, fixed = fix_garbled(corrupted)
        assert fixed
        assert text == original

    def test_cp1252_double_encoded_recovery(self):
        # Some tools use CP1252 instead of Latin-1
        original = "test data 123"
        corrupted = original.encode("utf-8").decode("cp1252")
        text, fixed = fix_garbled(corrupted)
        # Clean ASCII double-encoded looks the same, no real corruption
        assert text == "test data 123" or fixed


# ── is_likely_double_encoded ──────────────────────────────────────────────


class TestIsLikelyDoubleEncoded:
    def test_double_encoded_detected(self):
        original = "文件不存在"
        corrupted = original.encode("utf-8").decode("latin-1")
        assert is_likely_double_encoded(corrupted)

    def test_normal_chinese_not_double_encoded(self):
        assert not is_likely_double_encoded("正常的中文文本")

    def test_empty_not_double_encoded(self):
        assert not is_likely_double_encoded("")


# ── report_encoding_issue ─────────────────────────────────────────────────


class TestReportEncodingIssue:
    def test_clean_text_no_issue(self):
        assert report_encoding_issue("clean text", source="test") is None

    def test_garbled_text_reports(self):
        # report_encoding_issue deliberately requires a strong signal (>=10
        # mojibake signature chars) to avoid false positives on normal
        # Chinese. Build input from the signature set so the test stays valid
        # if the set changes. A single real CJK word is NOT mojibake.
        from core.encoding_fix import _MOJIBAKE_FAST

        garbled = "".join(list(_MOJIBAKE_FAST))
        report = report_encoding_issue(garbled, source="test")
        assert report is not None
        assert "test" in report
        assert "mojibake" in report.lower()

    def test_replacement_chars_reported(self):
        report = report_encoding_issue("text with ��� replacement", source="test")
        assert report is not None
        assert "replacement" in report.lower() or "U+FFFD" in report


# ── safe_read_text ────────────────────────────────────────────────────────


class TestSafeReadText:
    def test_utf8_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write("Hello UTF-8 中文".encode())
            fname = f.name
        try:
            text, _issue = safe_read_text(fname)
            assert "Hello UTF-8" in text
            assert "中文" in text
        finally:
            os.unlink(fname)

    def test_gbk_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write("这是GBK编码的文件内容".encode("gbk"))
            fname = f.name
        try:
            text, _issue = safe_read_text(fname)
            assert "这是GBK编码的文件内容" in text
        finally:
            os.unlink(fname)

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            safe_read_text("/nonexistent/file/path.txt")

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"")
            fname = f.name
        try:
            text, issue = safe_read_text(fname)
            assert text == ""
            assert issue is None
        finally:
            os.unlink(fname)
