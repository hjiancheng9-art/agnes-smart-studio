"""Copy Manager — 消息复制、聚焦、代码块提取

功能：
- 聚焦上下消息（↑↓）
- c 复制当前聚焦消息全文
- /copy last / /copy <n> / /copy <n>:<start>-<end> / /copy code <n>
- 代码块提取和复制

依赖 pyperclip（已安装）
"""

import pyperclip
import re
from dataclasses import dataclass, field
from typing import Any


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class MessageRef:
    """TUI 消息引用。"""
    index: int = -1           # 在 _lines 中的索引
    role: str = ""            # user / assistant / system
    text: str = ""            # 完整文本
    line_count: int = 0       # 行数
    
    def snippet(self, max_len: int = 60) -> str:
        t = self.text.strip()
        if len(t) <= max_len:
            return t
        return t[:max_len] + "..."


@dataclass
class CodeBlock:
    """代码块引用。"""
    index: int = 0        # 消息内的第几个代码块
    language: str = ""    # 语言标识（python, json, yaml...）
    code: str = ""        # 代码内容
    line_start: int = 0   # 在消息中的起始行
    line_end: int = 0     # 结束行


# ── 代码块提取 ────────────────────────────────────────────

CODE_BLOCK_PATTERN = re.compile(
    r"```(\w*)\n(.*?)```", re.DOTALL
)


def extract_code_blocks(text: str) -> list[CodeBlock]:
    """从消息文本中提取所有代码块。"""
    blocks = []
    for i, match in enumerate(CODE_BLOCK_PATTERN.finditer(text)):
        lang = match.group(1).strip()
        code = match.group(2).strip()
        pre_text = text[:match.start()]
        line_start = pre_text.count("\n") + 1
        line_end = line_start + match.group(0).count("\n")
        blocks.append(CodeBlock(
            index=i,
            language=lang or "text",
            code=code,
            line_start=line_start,
            line_end=line_end,
        ))
    return blocks


def format_code_block(block: CodeBlock) -> str:
    """格式化代码块用于复制（带语言注释）。"""
    if block.language and block.language != "text":
        return f"# {block.language}\n{block.code}"
    return block.code


# ── 消息索引器 ────────────────────────────────────────────

class MessageIndex:
    """从 MessagePane._lines 构建的消息索引。
    
    用法:
        from ui.copy_manager import MessageIndex
        idx = MessageIndex.from_pane(self.message_pane)
        msg = idx.get(-1)  # 最后一条
        msg = idx.get(0)   # 第一条
        msg = idx.nth(2)   # 倒数第 3 条
    """
    
    def __init__(self, messages: list[tuple[str, str]]):
        self._messages: list[MessageRef] = []
        for i, (role, text) in enumerate(messages):
            if role and text:
                self._messages.append(MessageRef(
                    index=i, role=role, text=text,
                    line_count=text.count("\n") + 1,
                ))
    
    @classmethod
    def from_pane(cls, pane) -> "MessageIndex":
        """从 MessagePane 实例构建索引。"""
        lines = getattr(pane, "_lines", [])
        return cls(lines)
    
    def __len__(self) -> int:
        return len(self._messages)
    
    def get(self, index: int) -> MessageRef | None:
        """按正索引获取。"""
        if 0 <= index < len(self._messages):
            return self._messages[index]
        return None
    
    def nth(self, n: int) -> MessageRef | None:
        """按倒数索引获取。n=1 表示倒数第一条。"""
        if n < 1 or n > len(self._messages):
            return None
        return self._messages[-n]
    
    def last_assistant(self) -> MessageRef | None:
        """最后一条 assistant 消息。"""
        for msg in reversed(self._messages):
            if msg.role == "assistant":
                return msg
        return None
    
    def last_user(self) -> MessageRef | None:
        """最后一条 user 消息。"""
        for msg in reversed(self._messages):
            if msg.role == "user":
                return msg
        return None
    
    def all(self) -> list[MessageRef]:
        return list(self._messages)
    
    def total_lines(self) -> int:
        return sum(m.line_count for m in self._messages)


# ── 复制操作 ──────────────────────────────────────────────

def copy_to_clipboard(text: str) -> bool:
    """复制文本到剪贴板。返回是否成功。"""
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def copy_message(msg: MessageRef) -> tuple[bool, str]:
    """复制消息全文。返回 (成功, 摘要)。"""
    if not msg or not msg.text:
        return False, "无消息可复制"
    ok = copy_to_clipboard(msg.text)
    snippet = msg.snippet(80)
    if ok:
        return True, f"已复制: {snippet}"
    return False, f"复制失败: {snippet}"


def copy_message_markdown(msg: MessageRef) -> tuple[bool, str]:
    """复制消息为 Markdown 格式。"""
    if not msg or not msg.text:
        return False, "无消息可复制"
    prefix = "> " if msg.role == "user" else ""
    md = f"**{msg.role}**:\n\n{prefix}{msg.text}"
    ok = copy_to_clipboard(md)
    return ok, f"已复制 Markdown: {msg.snippet(80)}"


def copy_code_block(msg: MessageRef, block_index: int = 0) -> tuple[bool, str]:
    """复制消息中的第 N 个代码块。"""
    if not msg or not msg.text:
        return False, "无消息可复制"
    blocks = extract_code_blocks(msg.text)
    if not blocks:
        return False, "消息中没有代码块"
    if block_index < 0 or block_index >= len(blocks):
        return False, f"只有 {len(blocks)} 个代码块，索引 {block_index} 无效"
    block = blocks[block_index]
    code = format_code_block(block)
    ok = copy_to_clipboard(code)
    return ok, f"已复制代码块 [{block.language}]: {code[:60]}..."


def copy_lines(msg: MessageRef, start: int, end: int) -> tuple[bool, str]:
    """复制消息的指定行范围。"""
    if not msg or not msg.text:
        return False, "无消息可复制"
    lines = msg.text.split("\n")
    start = max(0, start)
    end = min(len(lines), end)
    if start >= end:
        return False, "无效行范围"
    selected = "\n".join(lines[start:end])
    ok = copy_to_clipboard(selected)
    return ok, f"已复制行 {start+1}-{end}: {selected[:60]}..."


# ── Parse /copy command ───────────────────────────────────

def parse_copy_command(cmd: str) -> dict:
    """解析 /copy 命令，返回参数字典。
    
    支持:
        /copy last                    → 最后一条 assistant
        /copy 42                      → 第 42 条消息
        /copy 42:10-80                → 第 42 条 10-80 行
        /copy last markdown           → 最后一条 Markdown
        /copy 42 markdown             → 第 42 条 Markdown
        /copy code 2                  → 第 2 个代码块
        /copy last code 0             → 最后一条的第0个代码块
    """
    parts = cmd.strip().split()
    result = {"target": "last", "format": "text", "block_index": -1,
              "line_start": -1, "line_end": -1}
    
    if not parts:
        return result
    
    # First arg: target
    p = parts[0]
    if p == "last":
        result["target"] = "last"
    elif p == "code":
        result["target"] = "last"
        result["block_index"] = int(parts[1]) if len(parts) > 1 else 0
        return result
    elif ":" in p:
        # format: 42:10-80
        idx_part, _, range_part = p.partition(":")
        result["target"] = int(idx_part)
        if "-" in range_part:
            s, e = range_part.split("-")
            result["line_start"] = int(s) - 1  # 1-based → 0-based
            result["line_end"] = int(e)
    elif p.isdigit():
        result["target"] = int(p)
    else:
        return result  # fallback to last
    
    # Second arg: format or block index
    if len(parts) > 1:
        p2 = parts[1]
        if p2 == "markdown" or p2 == "md":
            result["format"] = "markdown"
        elif p2 == "code":
            result["block_index"] = int(parts[2]) if len(parts) > 2 else 0
    
    return result


def execute_copy(messages: list[tuple[str, str]], cmd: str) -> tuple[bool, str]:
    """执行 /copy 命令。返回 (成功, 显示消息)。"""
    idx = MessageIndex(messages)
    params = parse_copy_command(cmd)
    
    target = params["target"]
    
    # Resolve target
    msg = None
    if target == "last":
        msg = idx.last_assistant()
    elif isinstance(target, int):
        msg = idx.get(target)
    
    if msg is None:
        return False, f"未找到目标消息: {target}"
    
    # Execute
    if params["block_index"] >= 0:
        return copy_code_block(msg, params["block_index"])
    if params["line_start"] >= 0 and params["line_end"] > params["line_start"]:
        return copy_lines(msg, params["line_start"], params["line_end"])
    if params["format"] == "markdown":
        return copy_message_markdown(msg)
    return copy_message(msg)


# ── 消息聚焦管理器（供 TUI 键盘导航） ────────────────────

@dataclass
class FocusState:
    """消息聚焦状态。"""
    enabled: bool = False
    index: int = -1           # 当前聚焦的消息索引
    total_messages: int = 0
    
    def focus_next(self) -> int:
        """聚焦下一条消息。"""
        if not self.enabled:
            self.enabled = True
            self.index = max(0, self.total_messages - 1)
        else:
            self.index = min(self.total_messages - 1, self.index + 1)
        return self.index
    
    def focus_prev(self) -> int:
        """聚焦上一条消息。"""
        if not self.enabled:
            self.enabled = True
            self.index = max(0, self.total_messages - 1)
        else:
            self.index = max(0, self.index - 1)
        return self.index
    
    def is_focused(self, msg_index: int) -> bool:
        return self.enabled and self.index == msg_index


class CopyManager:
    """TUI 复制管理——整合消息聚焦、复制命令、代码块提取。"""
    
    def __init__(self):
        self.focus = FocusState()
        self._last_copy_result: tuple[bool, str] = (False, "")
    
    @property
    def last_copy_ok(self) -> bool:
        return self._last_copy_result[0]
    
    @property
    def last_copy_msg(self) -> str:
        return self._last_copy_result[1]
    
    def update_message_count(self, count: int):
        self.focus.total_messages = count
        if self.focus.index >= count:
            self.focus.index = count - 1
        if count == 0:
            self.focus.enabled = False
    
    def focus_up(self) -> MessageRef | None:
        """聚焦上一条消息。"""
        idx = MessageIndex(self._current_messages)
        self.focus.focus_prev()
        return idx.get(self.focus.index)
    
    def focus_down(self) -> MessageRef | None:
        """聚焦下一条消息。"""
        self.focus.focus_next()
        idx = MessageIndex(self._current_messages)
        return idx.get(self.focus.index)
    
    def set_messages(self, messages: list[tuple[str, str]]):
        self._current_messages = messages
        self.update_message_count(len(messages))
    
    def copy_focused(self) -> tuple[bool, str]:
        """复制当前聚焦的消息。"""
        idx = MessageIndex(self._current_messages)
        msg = idx.get(self.focus.index) if self.focus.enabled else idx.last_assistant()
        result = copy_message(msg) if msg else (False, "无消息可复制")
        self._last_copy_result = result
        return result
    
    def copy_focused_markdown(self) -> tuple[bool, str]:
        """复制当前聚焦消息为 Markdown。"""
        idx = MessageIndex(self._current_messages)
        msg = idx.get(self.focus.index) if self.focus.enabled else idx.last_assistant()
        result = copy_message_markdown(msg) if msg else (False, "无消息可复制")
        self._last_copy_result = result
        return result
    
    def handle_command(self, cmd: str, messages: list[tuple[str, str]]) -> tuple[bool, str]:
        """处理 /copy 命令。"""
        result = execute_copy(messages, cmd)
        self._last_copy_result = result
        return result
