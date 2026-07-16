"""Streaming Unicode Sanitizer — 修复流式文本中被拆开的 UTF-16 代理对。

场景：
- LLM 流式输出 emoji/CJK 时，单字符可能在两个 chunk 之间被拆成高位/低位代理对
- CDP/浏览器桥接层可能使用 UTF-16 边界切割
- JSON 流被错误拆分

```python
sanitizer = StreamingUnicodeSanitizer()
sanitizer.feed("\ud83d")      # 高位代理 → 暂存
sanitizer.feed("\ude00 😀")   # 低位到达 → 拼接为 😀
assert sanitizer.repaired_count == 1
```
"""

from __future__ import annotations


class StreamingUnicodeSanitizer:
    """有状态流式 Unicode 清洗器。

    约定：高位代理在 chunk 末尾时暂存，等下一个 chunk 的低位代理到达后再拼接。
    孤立的高位/低位代理替换为 U+FFFD。
    """

    REPLACEMENT = "\ufffd"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count: int = 0

    # ── 静态工具 ──

    @staticmethod
    def _is_high_surrogate(code: int) -> bool:
        return 0xD800 <= code <= 0xDBFF

    @staticmethod
    def _is_low_surrogate(code: int) -> bool:
        return 0xDC00 <= code <= 0xDFFF

    @staticmethod
    def _join_surrogate_pair(high: int, low: int) -> str:
        codepoint = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
        return chr(codepoint)

    # ── 流式接口 ──

    def feed(self, text: str | None) -> str:
        """喂入一段文本，返回清洗后的 safe 文本（不含孤立的代理项）。"""
        if not text:
            return ""

        output: list[str] = []
        for char in text:
            code = ord(char)

            # 1) 上一个 chunk 暂存了高位代理 → 期望当前字符是低位代理
            if self._pending_high is not None:
                high_code = ord(self._pending_high)
                if self._is_low_surrogate(code):
                    output.append(self._join_surrogate_pair(high_code, code))
                    self._pending_high = None
                    self.repaired_count += 1
                    continue
                # 高位代理孤立：替换为 �
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                self._pending_high = None
                # 继续处理当前字符

            # 2) 高位代理 → 暂存到下一块
            if self._is_high_surrogate(code):
                self._pending_high = char
                continue

            # 3) 孤立的低位代理 → 替换
            if self._is_low_surrogate(code):
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
                continue

            # 4) 普通字符
            output.append(char)

        return "".join(output)

    def finish(self) -> str:
        """流结束：清空所有暂存状态。如有孤立高位代理，返回 �。"""
        if self._pending_high is None:
            return ""
        self._pending_high = None
        self.repaired_count += 1
        return self.REPLACEMENT
