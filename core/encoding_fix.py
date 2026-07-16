"""Encoding detection and garbled-text recovery for CRUX Studio.

When external tools produce output in non-UTF-8 encodings (GBK, Shift-JIS,
Latin-1, etc.), CRUX's global ``errors="replace"`` policy silently replaces
undecodable bytes with U+FFFD, destroying the original data forever.

This module provides:

1. **detect_and_decode** — try charset_normalizer + fallback encodings on raw bytes
2. **scan_mojibake** — check text for known garbled-character signatures
3. **fix_garbled** — attempt to reverse encoding corruption heuristically
4. **fix_garbled_bytes** — decode raw bytes with auto-detection + recovery
5. **is_likely_garbled** — quick check whether text looks corrupted

Key design choice:
    When both GBK and Big5 decode the same bytes to valid CJK characters
    (e.g. ``你好世界`` vs ``斕疑岍賜``), we prefer the encoding that matches
    the system locale — GBK on simplified Chinese Windows, Big5 on
    traditional Chinese Windows.

    For already-corrupted text (where raw bytes are lost to ``errors="replace"``),
    recovery is best-effort. Prevention is the real fix — keep raw bytes until
    a correct encoding is found.
"""

from __future__ import annotations

import ctypes
import locale
import re
import sys
from collections.abc import Callable

# ── Mojibake signature characters ──────────────────────────────────────────
# Characters that virtually never appear in valid Chinese text.
# Produced when GBK two-byte sequences are misinterpreted as UTF-8.
_MOJIBAKE_SIGNATURES: frozenset[str] = frozenset(
    "鍥閸鐢纴鏉悆殑掑曠姽娲嬫兜鍙樻崲瀵煎叆瀵煎嚭鎵樼爜鍒楄〃瑙ｆ瀽鍣ㄦā鍧楄〃"
    "閿欒鍖呰緭鍏ラ敊璇姞杞藉櫒鎺у埗鍣ㄥ睍绀哄櫒瀛樺偍鍣ㄧ紪鐮佸櫒瑙ｅ櫒"
    "鍖呰鍣ㄥ姞杞藉櫒鏍稿績鏍囧噯妯″潡璁剧疆鏌ヨ鏍囪瘑鏍煎紡鍖栧櫒杞崲鍣?"
    "缂撳瓨娓呴櫎鎵ц鍣ㄥ彂甯冨櫒瀹夎鍗歌浇绠＄悊鍣ㄧ洃瑙嗗櫒璋冭В鍣ㄥ崗璋冨櫒"
    "瀹夊叏妫€鏌ュ櫒涓婁笅鏂囩獥鍙ｅ苟琛岀紪鐮佽緭鍏ユ硶鍒欒В鏋愬櫒鍖归厤鍣?"
    "瀵煎叆瀵煎嚭閿欒鍖呮墽琛屽櫒鎻掍欢鍔犺浇鏍煎紡鍖栬В鏋?娴佸紡澶勭悊鏍稿績"
)

# High-confidence subset for fast pre-scan.
# NOTE: keep this set TINY and only include characters that virtually never
# appear in valid Chinese text.  Any character here that also occurs in
# normal Chinese will cause false-positive mojibake alerts on every
# subprocess invocation, flooding the activity log.
_MOJIBAKE_FAST: frozenset[str] = frozenset(
    "鍥閸鐢纴鏉悆殑掑曠姽娲嬫兜鍙"
)

# ── System locale detection ──────────────────────────────────────────────

_IS_SIMPLIFIED_CHINESE_SYSTEM: bool | None = None


def _detect_system_locale() -> bool:
    """Check if this is a simplified Chinese Windows system.

    Cached — only calls the Win32 API once.
    """
    global _IS_SIMPLIFIED_CHINESE_SYSTEM
    if _IS_SIMPLIFIED_CHINESE_SYSTEM is not None:
        return _IS_SIMPLIFIED_CHINESE_SYSTEM

    # Method 1: Win32 UI language (most reliable on Windows)
    if sys.platform == "win32":
        try:
            lang_id = ctypes.windll.kernel32.GetSystemDefaultUILanguage()
            # LANG_CHINESE_SIMPLIFIED = 0x0804 (2052)
            # LANG_CHINESE = 0x0004 (1028 = traditional, but rarely used as UI)
            if lang_id == 0x0804:
                _IS_SIMPLIFIED_CHINESE_SYSTEM = True
                return True
        except (OSError, AttributeError):
            pass

    # Method 2: Python locale
    try:
        loc = locale.getdefaultlocale()
        if loc and loc[0]:
            lang = loc[0].lower()
            if lang in ("zh_cn", "zh-cn", "zh_sg", "zh-sg", "chinese_simplified"):
                _IS_SIMPLIFIED_CHINESE_SYSTEM = True
                return True
            elif lang in ("zh_tw", "zh-tw", "zh_hk", "zh-hk", "chinese_traditional"):
                _IS_SIMPLIFIED_CHINESE_SYSTEM = False
                return False
    except (ValueError, locale.Error):
        pass

    # Method 3: filesystem encoding
    fsenc = sys.getfilesystemencoding().lower()
    if fsenc in ("gbk", "gb2312", "gb18030", "cp936"):
        _IS_SIMPLIFIED_CHINESE_SYSTEM = True
        return True
    if fsenc in ("big5", "cp950"):
        _IS_SIMPLIFIED_CHINESE_SYSTEM = False
        return False

    # Default: assume not simplified Chinese
    _IS_SIMPLIFIED_CHINESE_SYSTEM = False
    return False


# ── Encoding priority ─────────────────────────────────────────────────────

_SIMPLIFIED_ENCODINGS: list[str] = ["gbk", "gb2312", "gb18030", "cp936"]
_TRADITIONAL_ENCODINGS: list[str] = ["big5", "big5hkscs", "cp950"]
_OTHER_ENCODINGS: list[str] = [
    "latin-1", "cp1252", "shift-jis", "euc-kr", "cp932", "cp949",
]

if _detect_system_locale():
    _FALLBACK_ENCODINGS: list[str] = (
        _SIMPLIFIED_ENCODINGS + _TRADITIONAL_ENCODINGS + _OTHER_ENCODINGS
    )
else:
    _FALLBACK_ENCODINGS: list[str] = (
        _TRADITIONAL_ENCODINGS + _SIMPLIFIED_ENCODINGS + _OTHER_ENCODINGS
    )

# ── Character range utilities ─────────────────────────────────────────────

_SIMPLIFIED_CJK_START = 0x4E00  # 一
_SIMPLIFIED_CJK_END = 0x9FFF    # 鿿
_CJK_EXT_A_START = 0x3400       # 㐀
_CJK_EXT_A_END = 0x4DBF         # 䶿


def _count_chars_in_ranges(
    text: str, ranges: list[tuple[int, int]]
) -> int:
    """Count characters in *text* that fall within the given Unicode ranges."""
    count = 0
    for ch in text:
        cp = ord(ch)
        for lo, hi in ranges:
            if lo <= cp <= hi:
                count += 1
                break
    return count


def _simplified_cjk_count(text: str) -> int:
    """Count characters in the CJK Unified Ideographs block (U+4E00-U+9FFF).

    Both simplified and traditional characters live here, but simplified
    dominates on PRC systems.
    """
    return _count_chars_in_ranges(
        text,
        [
            (_SIMPLIFIED_CJK_START, _SIMPLIFIED_CJK_END),
            (0x3000, 0x303F),  # CJK punctuation
            (0xFF00, 0xFFEF),  # Fullwidth forms
        ],
    )


# Regex: matches likely-valid characters in CJK text
_VALID_CHAR = re.compile(
    r"[\x00-\x7f"
    r"　-〿"     # CJK punctuation
    r"一-鿿"     # CJK Unified
    r"㐀-䶿"     # CJK Ext A
    r"＀-￯"     # Fullwidth
    r" -⁯"     # General punctuation
    r"豈-﫿"     # CJK Compat
    r"]"
)


def _is_mostly_valid(text: str, threshold: float = 0.92) -> bool:
    """Check if most characters are in expected ranges."""
    if not text:
        return True
    valid = sum(1 for ch in text if _VALID_CHAR.match(ch))
    return (valid / max(len(text), 1)) >= threshold


# ── Garbled detection ─────────────────────────────────────────────────────


def scan_mojibake(text: str) -> list[tuple[int, str]]:
    """Scan *text* for mojibake signature characters.

    Returns a list of (position, char_hex) tuples for each hit.
    """
    hits: list[tuple[int, str]] = []
    for i, ch in enumerate(text):
        if ch in _MOJIBAKE_FAST:
            hits.append((i, f"U+{ord(ch):04X}"))
    return hits


def is_likely_garbled(text: str) -> bool:
    """Quick check: does *text* contain mojibake signature characters?

    False positives are extremely rare — these characters are almost never
    used in valid Chinese text.
    """
    if not text:
        return False
    return any(ch in _MOJIBAKE_FAST for ch in text)


def is_likely_double_encoded(text: str) -> bool:
    """Check if *text* looks like UTF-8 bytes mis-decoded as Latin-1."""
    if not text:
        return False
    try:
        recovered = text.encode("latin-1").decode("utf-8")
        simplified = _simplified_cjk_count(recovered)
        return simplified > 3 and _is_mostly_valid(recovered)
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False


# ── Score text for encoding selection ─────────────────────────────────────


def _score_text(text: str, replacement_count: int) -> float:
    """Score text quality. Higher = better. Used to select best encoding.

    Scoring factors:
    - Heavy penalty for replacement chars (U+FFFD)
    - Medium penalty for mojibake signature chars
    - Bonus for simplified Chinese CJK (preferred on PRC systems)
    - Bonus for valid-looking text
    """
    if not text:
        return 0.0

    score = 1.0
    score -= replacement_count * 0.35
    mojibake_count = sum(1 for ch in text if ch in _MOJIBAKE_FAST)
    score -= mojibake_count * 0.25

    simplified = _simplified_cjk_count(text)
    if simplified > 0:
        # Cap bonus so long texts don't skew results
        score += min(simplified * 0.015, 0.4)

    if _is_mostly_valid(text):
        score += 0.2

    return max(score, 0.0)


# ── Charset detection ─────────────────────────────────────────────────────


def _detect_with_charset_lib(raw: bytes) -> str | None:
    """Try charset_normalizer or chardet to detect encoding.

    On simplified Chinese Windows, charset_normalizer often misdetects
    short GBK text as Big5 because both produce valid CJK characters.
    We apply locale-aware validation.
    """
    detected = None

    # charset_normalizer (more accurate, actively maintained)
    try:
        from charset_normalizer import from_bytes

        results = from_bytes(raw)
        if results:
            best = results.best()
            if best and best.encoding and best.encoding != "ascii":
                detected = best.encoding
    except ImportError:
        pass

    # chardet fallback
    if not detected:
        try:
            import chardet

            result = chardet.detect(raw)
            if result and result.get("encoding") and result.get("confidence", 0) > 0.6:
                if result["encoding"] != "ascii":
                    detected = result["encoding"]
        except ImportError:
            pass

    if not detected:
        return None

    detected_lower = detected.lower()

    # Validate: on simplified Chinese systems, reject Big5/CP949 misdetections
    # of GBK text (both decode same bytes to different CJK chars)
    is_simplified = _detect_system_locale()

    if is_simplified and detected_lower in (
        "big5", "big5hkscs", "cp950", "cp949", "euc-kr",
    ):
        # On simplified Chinese systems, Big5/CP949 often misdetect GBK text.
        # Verify: if GBK also produces valid output, prefer it.
        try:
            gbk_text = raw.decode("gbk")
            if _is_mostly_valid(gbk_text) and not is_likely_garbled(gbk_text):
                return "gbk"
        except UnicodeDecodeError:
            pass

    if not is_simplified and detected_lower in ("gbk", "gb2312", "gb18030", "cp936"):
        try:
            big5_text = raw.decode("big5")
            if _is_mostly_valid(big5_text) and not is_likely_garbled(big5_text):
                return "big5"
        except UnicodeDecodeError:
            pass

    return detected


# ── Decode with detection ─────────────────────────────────────────────────


def detect_and_decode(
    raw: bytes,
    preferred: str = "utf-8",
    *,
    use_chardet: bool = True,
) -> tuple[str, str, bool]:
    """Decode *raw* bytes, trying multiple encodings.

    Returns:
        (text, encoding_used, had_errors)

    Strategy:
    1. Try preferred encoding (UTF-8) strictly
    2. Try charset_normalizer auto-detection with locale validation
    3. Fall back through encoding chain (simplified-first on PRC systems)
    4. Return best result by scoring
    """
    if not raw:
        return ("", preferred, False)

    # Step 1: Try preferred encoding strictly
    try:
        text = raw.decode(preferred)
        return (text, preferred, False)
    except UnicodeDecodeError:
        pass

    # Step 2: charset detection
    if use_chardet:
        detected = _detect_with_charset_lib(raw)
        if detected:
            try:
                text = raw.decode(detected)
                if not is_likely_garbled(text):
                    return (text, detected, True)
            except (UnicodeDecodeError, LookupError):
                pass

    # Step 3: Try all fallback encodings, pick best by score
    return _best_encoding_decode(raw, preferred)


def _best_encoding_decode(
    raw: bytes, preferred: str
) -> tuple[str, str, bool]:
    """Try fallback encodings, return best by heuristic scoring."""
    text_replaced = raw.decode(preferred, errors="replace")
    replacement_count = text_replaced.count("�")

    best_text = text_replaced
    best_enc = preferred
    best_score = _score_text(text_replaced, replacement_count)

    for enc in _FALLBACK_ENCODINGS:
        if enc == preferred:
            continue
        try:
            text = raw.decode(enc)
            score = _score_text(text, 0)
            if score > best_score:
                best_text = text
                best_enc = enc
                best_score = score
        except (UnicodeDecodeError, LookupError):
            try:
                text = raw.decode(enc, errors="replace")
                repl = text.count("�")
                score = _score_text(text, repl)
                if score > best_score:
                    best_text = text
                    best_enc = enc
                    best_score = score
            except LookupError:
                continue

    had_errors = best_text.count("�") > 0
    return (best_text, best_enc, had_errors)


# ── Garbled text recovery ─────────────────────────────────────────────────


def fix_garbled(text: str) -> tuple[str, bool]:
    """Attempt to recover already-corrupted text (best-effort).

    Only works for specific corruption patterns where raw bytes can be
    reconstructed from the corrupted text. Does NOT work when the original
    bytes were irreversibly replaced by ``errors="replace"``.

    Returns:
        (fixed_text, was_fixed)
    """
    if not text:
        return (text, False)

    has_mojibake = is_likely_garbled(text)
    has_replacements = "�" in text
    has_double = is_likely_double_encoded(text)

    if not has_mojibake and not has_replacements and not has_double:
        return (text, False)

    original_score = _score_text(text, text.count("�"))
    candidates: list[tuple[str, float]] = [(text, original_score)]

    # Strategy 1: Double-encoding reversal (Latin-1 → UTF-8)
    # Happens when: UTF-8 bytes → read as Latin-1 → written as UTF-8
    # Only works when all chars fit in Latin-1 range (U+0000-U+00FF)
    try:
        recovered = text.encode("latin-1").decode("utf-8")
        if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
            score = _score_text(recovered, 0)
            candidates.append((recovered, score))
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Strategy 2: CP1252 → UTF-8 (another double-encoding path)
    try:
        recovered = text.encode("cp1252").decode("utf-8")
        if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
            score = _score_text(recovered, 0)
            candidates.append((recovered, score))
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Strategy 3: Latin-1 → GBK (Chinese Windows specific)
    try:
        recovered = text.encode("latin-1").decode("gbk")
        if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
            score = _score_text(recovered, 0)
            candidates.append((recovered, score))
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Strategy 4: CP1252 → GBK
    try:
        recovered = text.encode("cp1252").decode("gbk")
        if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
            score = _score_text(recovered, 0)
            candidates.append((recovered, score))
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Strategy 5: GBK→UTF-8 corruption reversal
    # Re-encode mojibake chars as UTF-8 bytes, then decode as GBK.
    # Fragile — works only when no bytes were lost to errors="replace".
    if has_mojibake and not has_replacements:
        recovered = _reverse_gbk_utf8_corruption(text)
        if recovered:
            score = _score_text(recovered, 0)
            candidates.append((recovered, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_text, best_score = candidates[0]

    if best_score > original_score + 0.1:
        return (best_text, True)
    return (text, False)


def _reverse_gbk_utf8_corruption(text: str) -> str | None:
    """Reverse GBK-bytes-decoded-as-UTF-8 corruption.

    Each mojibake character represents a 3-byte UTF-8 sequence that was
    originally 1.5 GBK two-byte characters. Re-encode each char to bytes
    and decode the stream as GBK.

    Only works when ALL original GBK bytes formed valid UTF-8 sequences
    (no replacement chars). If any bytes were lost, returns None.
    """
    try:
        recovered_bytes = bytearray()
        for ch in text:
            if ch == "�":
                return None
            if ord(ch) < 128:
                recovered_bytes.append(ord(ch))
            else:
                # Encode as UTF-8 to recover the original byte sequence
                encoded = ch.encode("utf-8")
                recovered_bytes.extend(encoded)

        # Try simplified Chinese decodings first
        for enc in _SIMPLIFIED_ENCODINGS:
            try:
                recovered = bytes(recovered_bytes).decode(enc)
                if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
                    return recovered
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue

        # Try traditional
        for enc in _TRADITIONAL_ENCODINGS:
            try:
                recovered = bytes(recovered_bytes).decode(enc)
                if _is_mostly_valid(recovered) and not is_likely_garbled(recovered):
                    return recovered
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue

        return None
    except Exception:
        return None


def fix_garbled_bytes(raw: bytes) -> tuple[str, str, bool]:
    """Decode raw bytes with auto-detection and recovery.

    This is the primary entry point for handling external tool output.
    Always prefer this over ``.decode("utf-8", errors="replace")``.

    Returns:
        (text, encoding_used, was_recovered)
    """
    text, encoding, _ = detect_and_decode(raw)

    if is_likely_garbled(text) or "�" in text:
        fixed, was_fixed = fix_garbled(text)
        if was_fixed:
            return (fixed, encoding, True)

    return (text, encoding, False)


# ── Reporting ──────────────────────────────────────────────────────────────


def report_encoding_issue(
    text: str,
    source: str = "unknown",
    *,
    logger: Callable[[str], None] | None = None,
) -> str | None:
    """Check text for encoding issues. Returns diagnostic message or None.

    Call this after decoding to detect and log issues before they propagate.
    """
    issues: list[str] = []
    replacement_count = text.count("�")
    if replacement_count > 0:
        issues.append(f"{replacement_count} replacement char(s) (U+FFFD)")

    hits = scan_mojibake(text)
    # Only report mojibake when the signal is strong enough:
    # - many hits standalone (>=10), or
    # - moderate hits (>=3) WITH replacement chars present
    # A single CJK character that happens to be in the signature set
    # (e.g. 兜 U+515C) in normal Chinese output is NOT mojibake.
    if len(hits) >= 10 or (len(hits) >= 3 and replacement_count > 0):
        chars_shown = [h[1] for h in hits[:5]]
        more = f" +{len(hits) - 5} more" if len(hits) > 5 else ""
        issues.append(
            f"{len(hits)} mojibake signature(s): {', '.join(chars_shown)}{more}"
        )

    if is_likely_double_encoded(text):
        issues.append("likely double-encoded (UTF-8 → Latin-1 → UTF-8)")

    if not issues:
        return None

    report = f"[EncodingIssue] source={source}: " + "; ".join(issues)
    if logger:
        logger(report)
    return report


def safe_read_text(
    path: str,
    *,
    encoding: str = "utf-8",
    report: bool = True,
) -> tuple[str, str | None]:
    """Read a file with encoding detection. Returns (text, issue_or_None)."""
    import os

    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with open(path, "rb") as f:
        raw = f.read()

    text, _, _ = detect_and_decode(raw, preferred=encoding)

    if is_likely_garbled(text) or "�" in text:
        fixed, was_fixed = fix_garbled(text)
        if was_fixed:
            text = fixed

    issue = report_encoding_issue(text, source=f"file:{path}") if report else None
    return (text, issue)


# ── Quick self-test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"System locale: simplified Chinese = {_detect_system_locale()}")
    print(f"Encoding order: {_FALLBACK_ENCODINGS[:6]}...")
    print()

    # Test 1: Known mojibake
    test_garbled = "鏉冮檺涓嶈冻锛岃缁欏嚭鏉冮檺鍚?"
    print(f"Test 1 - known mojibake: is_garbled={is_likely_garbled(test_garbled)}")
    print(f"  Hits: {scan_mojibake(test_garbled)}")
    fixed, was_fixed = fix_garbled(test_garbled)
    print(f"  fix_garbled: fixed={was_fixed} → {fixed[:80]!r}")

    # Test 2: Clean text
    test_clean = "这是一个正常的测试字符串"
    print(f"\nTest 2 - clean text: is_garbled={is_likely_garbled(test_clean)}")
    print(f"  fix_garbled: {fix_garbled(test_clean)}")

    # Test 3: GBK bytes → auto-detect (THE IMPORTANT TEST)
    for label, gbk_text in [
        ("short", "你好世界"),
        ("medium", "权限不足，请给出权限名称"),
        ("long", "这是一个测试字符串，用于验证编码自动检测功能是否正常工作"),
    ]:
        raw = gbk_text.encode("gbk")
        text, enc, _ = detect_and_decode(raw)
        ok = "OK" if text == gbk_text else f"FAIL (got {text!r})"
        print(f"\nTest 3 ({label}): encoding={enc}, {ok}")

    # Test 4: Clean UTF-8 should pass through
    test_utf8 = "Hello, UTF-8 with 中文 mixed in"
    text4, enc4, _ = detect_and_decode(test_utf8.encode("utf-8"))
    print(f"\nTest 4 - clean UTF-8: encoding={enc4}, text={text4[:60]}")

    # Test 5: Double-encoded text (UTF-8 bytes → Latin-1 decode)
    test5_original = "文件不存在请检查路径"
    double = test5_original.encode("utf-8").decode("latin-1")
    print(f"\nTest 5 - double-encoded: is_double={is_likely_double_encoded(double)}")
    print(f"  Corrupted: {double!r}")
    fixed5, was_fixed5 = fix_garbled(double)
    print(f"  fix_garbled: fixed={was_fixed5} → {fixed5!r}")
    if was_fixed5 and fixed5 == test5_original:
        print("  OK - recovered correctly")
    elif was_fixed5:
        print(f"  PARTIAL - got {fixed5!r}, expected {test5_original!r}")

    # Test 6: Report
    print(f"\nTest 6 - report: {report_encoding_issue(test_garbled, source='test')}")

    print("\nAll tests completed.")
