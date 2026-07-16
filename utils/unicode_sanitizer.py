"""
Streaming Unicode Sanitizer — 修复流式文本中被拆开的 UTF-16 代理对。

触发场景:
  1. surrogatepass 解码
  2. UTF-16 流按错误边界切块
  3. 浏览器/CDP/Node 桥接层把代理项单独传给 Python
  4. JSON 流被错误拆分

用法:
  sanitizer = StreamingUnicodeSanitizer()
  for chunk in stream:
      safe_text = sanitizer.feed(chunk)
      if safe_text:
          emit(safe_text)
  safe_text = sanitizer.flush()  # 冲刷残留
"""

from __future__ import annotations


class StreamingUnicodeSanitizer:
    REPLACEMENT = "\ufffd"

    def __init__(self) -> None:
        self._pending_high: str | None = None
        self.repaired_count: int = 0

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

    def feed(self, text: str | None) -> str:
        """输入流式文本块，返回已修复的安全文本。"""
        if not text:
            return ""

        output: list[str] = []

        for char in text:
            code = ord(char)

            if self._pending_high is not None:
                if self._is_low_surrogate(code):
                    # 凑成完整代理对
                    high_code = ord(self._pending_high)
                    try:
                        output.append(self._join_surrogate_pair(high_code, code))
                    except (ValueError, OverflowError):
                        output.append(self.REPLACEMENT)
                    self.repaired_count += 1
                    self._pending_high = None
                    continue
                else:
                    # 高位代理后不是低位代理 → 孤立代理，替换
                    output.append(self.REPLACEMENT)
                    self.repaired_count += 1
                    self._pending_high = None
                    # 继续处理当前字符

            if self._is_high_surrogate(code):
                self._pending_high = char
            elif self._is_low_surrogate(code):
                # 孤立低位代理
                output.append(self.REPLACEMENT)
                self.repaired_count += 1
            else:
                output.append(char)

        return "".join(output)

    def flush(self) -> str:
        """冲刷残留的孤立高位代理。"""
        if self._pending_high is not None:
            self._pending_high = None
            self.repaired_count += 1
            return self.REPLACEMENT
        return ""

    def reset(self) -> None:
        self._pending_high = None
