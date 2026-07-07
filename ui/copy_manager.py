"""Copy Manager — 消息复制（基于 MessageStore + ClipboardAdapter）

GPT Review 要求：
- 依赖 MessageStore 而非直接读 _lines
- 使用 ClipboardAdapter 统一剪贴板
- 聚焦状态独立
"""

from ui.input_router import FocusState, get_clipboard
from ui.message_store import Message, MessageStore


def extract_code_blocks(text: str) -> list[dict]:
    """从消息文本中提取代码块。"""
    import re
    blocks = []
    for i, match in enumerate(re.finditer(r"```(\w*)\n(.*?)```", text, re.DOTALL)):
        blocks.append({
            "index": i,
            "language": match.group(1).strip() or "text",
            "code": match.group(2).strip(),
        })
    return blocks


class CopyManager:
    """消息复制管理。"""

    def __init__(self, message_store: MessageStore | None = None):
        self.store = message_store or MessageStore()
        self.clip = get_clipboard()
        self.focus = FocusState()
        self.focus.total = len(self.store)

    def sync_store(self, store: MessageStore) -> None:
        self.store = store
        self.focus.total = len(store)
        if self.focus.index >= self.focus.total:
            self.focus.index = self.focus.total - 1
        if self.focus.total == 0:
            self.focus.enabled = False

    def copy_message(self, msg: Message | None) -> tuple[bool, str]:
        if not msg or not msg.text:
            return False, "无消息可复制"
        return self.clip.copy_and_report(msg.text, "已复制")

    def copy_markdown(self, msg: Message | None) -> tuple[bool, str]:
        if not msg or not msg.text:
            return False, "无消息可复制"
        md = f"**{msg.role}**:\n\n{msg.text}"
        return self.clip.copy_and_report(md, "已复制 Markdown")

    def copy_code_block(self, msg: Message | None, block_index: int = 0) -> tuple[bool, str]:
        if not msg or not msg.text:
            return False, "无消息可复制"
        blocks = msg.code_blocks
        if not blocks:
            return False, "消息中没有代码块"
        if block_index < 0 or block_index >= len(blocks):
            return False, f"只有 {len(blocks)} 个代码块"
        block = blocks[block_index]
        code = block["code"]
        label = f"已复制代码块 [{block['language']}]"
        return self.clip.copy_and_report(code, label)

    def copy_lines(self, msg: Message | None, start: int, end: int) -> tuple[bool, str]:
        if not msg or not msg.text:
            return False, "无消息可复制"
        lines = msg.text.split("\n")
        start = max(0, start)
        end = min(len(lines), end)
        if start >= end:
            return False, "无效行范围"
        selected = "\n".join(lines[start:end])
        return self.clip.copy_and_report(selected, f"已复制行 {start+1}-{end}")

    # ── 聚焦操作 ──

    def copy_focused(self) -> tuple[bool, str]:
        msg = self.store.get(self.focus.index) if self.focus.enabled else self.store.last_assistant()
        return self.copy_message(msg)

    def copy_focused_markdown(self) -> tuple[bool, str]:
        msg = self.store.get(self.focus.index) if self.focus.enabled else self.store.last_assistant()
        return self.copy_markdown(msg)

    def get_focused_msg(self) -> Message | None:
        return self.store.get(self.focus.index) if self.focus.enabled else self.store.last_assistant()

    # ── 命令解析 ──

    def handle_command(self, cmd: str) -> tuple[bool, str]:
        """处理 /copy 命令。返回 (成功, 消息)。"""
        parts = cmd.strip().split()

        if not parts or parts[0] != "/copy":
            return False, "未知命令"

        args = parts[1:] if len(parts) > 1 else []
        target = "last"
        format_type = "text"
        block_index = -1
        line_start = -1
        line_end = -1

        if args:
            p = args[0]
            if p == "last":
                target = "last"
            elif p == "code":
                block_index = int(args[1]) if len(args) > 1 else 0
                target = "last"
            elif ":" in p:
                idx_part, _, range_part = p.partition(":")
                target = int(idx_part)
                if "-" in range_part:
                    s, e = range_part.split("-")
                    line_start = int(s) - 1
                    line_end = int(e)
            elif p.isdigit():
                target = int(p)

        if len(args) > 1:
            if args[1] in ("markdown", "md"):
                format_type = "markdown"
            elif args[1] == "code":
                block_index = int(args[2]) if len(args) > 2 else 0

        # Resolve target
        msg = None
        if target == "last":
            msg = self.store.last_assistant()
        elif isinstance(target, int):
            msg = self.store.get(target)

        if msg is None:
            return False, f"未找到消息: {target}"

        if block_index >= 0:
            return self.copy_code_block(msg, block_index)
        if line_start >= 0 and line_end > line_start:
            return self.copy_lines(msg, line_start, line_end)
        if format_type == "markdown":
            return self.copy_markdown(msg)
        return self.copy_message(msg)
