"""MessageStore — 替代 _lines 作为消息主数据源

GPT Review M1 要求：
- 每条消息有 id/role/text/rendered_lines/timestamp
- 流式消息一行一行追加
- 代码块缓存
- 按行号反查消息
"""

import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Message:
    """单条消息。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: str = ""
    text: str = ""
    rendered_lines: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    is_streaming: bool = False
    token_count: int = 0

    @property
    def line_count(self) -> int:
        return len(self.rendered_lines) or (self.text.count("\n") + 1)

    @property
    def code_blocks(self) -> list[dict]:
        """惰性提取代码块。"""
        import re
        blocks = []
        for i, match in enumerate(re.finditer(r"```(\w*)\n(.*?)```", self.text, re.DOTALL)):
            blocks.append({
                "index": i,
                "language": match.group(1).strip() or "text",
                "code": match.group(2).strip(),
            })
        return blocks

    def snippet(self, max_len: int = 60) -> str:
        t = self.text.strip()
        if len(t) <= max_len:
            return t
        return t[:max_len] + "..."

    def get_lines(self, start: int = 0, end: int | None = None) -> str:
        lines = self.text.split("\n")
        return "\n".join(lines[start:end])


class MessageStore:
    """消息存储 — 集中管理所有消息。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._messages: list[Message] = []
        self._stream_msg: Message | None = None

    # ── 读 ──

    @property
    def messages(self) -> list[Message]:
        with self._lock:
            return list(self._messages)

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)

    def get(self, index: int) -> Message | None:
        with self._lock:
            if 0 <= index < len(self._messages):
                return self._messages[index]
            return None

    def nth(self, n: int) -> Message | None:
        """倒数第 n 条。"""
        with self._lock:
            if n < 1 or n > len(self._messages):
                return None
            return self._messages[-n]

    def last_assistant(self) -> Message | None:
        with self._lock:
            for msg in reversed(self._messages):
                if msg.role == "assistant":
                    return msg
            return None

    def last_user(self) -> Message | None:
        with self._lock:
            for msg in reversed(self._messages):
                if msg.role == "user":
                    return msg
            return None

    def find_by_line(self, line_number: int) -> tuple[Message | None, int]:
        """按渲染行号反查消息。返回 (message, offset_in_message)。"""
        with self._lock:
            offset = 0
            for msg in self._messages:
                lc = msg.line_count
                if offset <= line_number < offset + lc:
                    return msg, line_number - offset
                offset += lc
            return None, 0

    @property
    def total_lines(self) -> int:
        with self._lock:
            return sum(m.line_count for m in self._messages)

    # ── 写 ──

    def append(self, role: str, text: str) -> Message:
        """追加一条完整消息。"""
        msg = Message(role=role, text=text)
        with self._lock:
            self._messages.append(msg)
        return msg

    def start_stream(self, role: str) -> Message:
        """开始流式消息。"""
        msg = Message(role=role, is_streaming=True)
        with self._lock:
            self._messages.append(msg)
            self._stream_msg = msg
        return msg

    def stream_chunk(self, text: str) -> Message | None:
        """追加流式片段。"""
        with self._lock:
            if self._stream_msg is None:
                return None
            self._stream_msg.text += text
            return self._stream_msg

    def end_stream(self) -> Message | None:
        """结束流式消息。"""
        with self._lock:
            if self._stream_msg is None:
                return None
            self._stream_msg.is_streaming = False
            msg = self._stream_msg
            self._stream_msg = None
            return msg

    def clear(self):
        with self._lock:
            self._messages.clear()
            self._stream_msg = None

    def as_plain_tuples(self) -> list[tuple[str, str]]:
        """兼容旧 _lines 格式。"""
        return [(m.role, m.text) for m in self.messages]
