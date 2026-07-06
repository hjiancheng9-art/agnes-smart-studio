"""Message Detail View — 基于 MessageStore 的消息详情

o 打开详情 → ↑↓滚动 → c复制/m复制MD/Esc返回
"""

from ui.message_store import Message, MessageStore
from ui.copy_manager import extract_code_blocks
from ui.input_router import get_clipboard


class MessageDetailScreen:
    """消息详情视图。"""

    def __init__(self, message_store: MessageStore, msg_index: int):
        self.store = message_store
        self.msg_index = msg_index
        self.scroll_offset = 0
        self._active = False
        self._on_close: list = []

        msg = self.store.get(msg_index)
        self.total_lines = msg.line_count if msg else 0
        self.msg = msg

    @property
    def active(self) -> bool:
        return self._active

    def on_close(self, callback):
        self._on_close.append(callback)

    def open(self) -> None:
        if not self.msg:
            return
        self._active = True
        self.scroll_offset = 0

    def close(self) -> None:
        self._active = False
        for cb in self._on_close:
            try:
                cb()
            except Exception:
                pass

    def build_formatted(self) -> list:
        """构建详情视图的格式文本（供 prompt_toolkit 使用）。"""
        if not self.msg:
            return [("class:error", "消息不存在")]

        lines = self.msg.text.split("\n")
        result = []

        result.append(("class:header-bar",
            f"┌─ Message Detail ─ {self.msg.role.title()} ─ {self.total_lines} lines "))
        result.append(("", "\n"))
        result.append(("class:info",
            " ↑↓scroll  c复制全文  m复制MD  Esc返回  "))
        result.append(("", "\n"))
        result.append(("class:header-bar", "├" + "─" * 60))
        result.append(("", "\n"))

        screen_height = 20
        start = max(0, self.scroll_offset)
        end = min(self.total_lines, start + screen_height)

        for i in range(start, end):
            line = lines[i] if i < len(lines) else ""
            result.append(("class:line-number", f"{i+1:4d} "))
            text = (line[:160] + ("…" if len(line) > 160 else "")) + "\n"
            result.append(("", text))

        if end < self.total_lines:
            result.append(("class:info", f"   ... 还有 {self.total_lines - end} 行 (↓继续)"))
            result.append(("", "\n"))

        result.append(("class:header-bar", "└" + "─" * 60))
        return result

    def handle_key(self, key: str) -> bool:
        if not self._active:
            return False

        if key == "escape":
            self.close()
            return True

        if key == "up":
            self.scroll_offset = max(0, self.scroll_offset - 1)
            return True

        if key == "down":
            self.scroll_offset = min(self.total_lines - 1, self.scroll_offset + 1)
            return True

        if key == "pageup":
            self.scroll_offset = max(0, self.scroll_offset - 20)
            return True

        if key == "pagedown":
            self.scroll_offset = min(self.total_lines - 20, self.scroll_offset + 20)
            return True

        if key == "c":
            clip = get_clipboard()
            clip.copy(self.msg.text)
            return True

        if key == "m":
            clip = get_clipboard()
            clip.copy(f"**{self.msg.role}**:\n\n{self.msg.text}")
            return True

        return False
