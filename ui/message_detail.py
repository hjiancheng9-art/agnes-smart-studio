"""Message Detail View — 消息详情全屏覆层

按 o 打开当前聚焦消息的详情视图：
- 独立滚动，不受主聊天流影响
- 显示消息元数据（角色、时间、行数、tokens）
- c 复制全文 / m 复制 Markdown / j 复制 JSON / s 选择行范围
- ↑↓ 滚动 / Esc 返回
"""

from prompt_toolkit.layout.containers import Window, HSplit, Float
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import FormattedText

from ui.copy_manager import (
    MessageIndex, copy_message, copy_message_markdown,
    extract_code_blocks, copy_to_clipboard,
)


def build_detail_formatted(messages: list[tuple[str, str]], msg_index: int,
                           scroll_offset: int = 0) -> FormattedText:
    """构建消息详情视图的格式文本。"""
    if msg_index < 0 or msg_index >= len(messages):
        return FormattedText([("class:error", "消息不存在")])
    
    role, text = messages[msg_index]
    lines = text.split("\n")
    total_lines = len(lines)
    
    result = []
    
    # ── 头部 ──
    result.append(("class:header-bar", f"┌─ Message Detail ─ {role.title()} ─ {total_lines} lines "))
    result.append(("", "\n"))
    
    # ── 操作提示 ──
    result.append(("class:info", " ↑↓ scroll  c复制全文  m复制MD  s选择  Esc返回  "))
    result.append(("", "\n"))
    result.append(("class:header-bar", "├" + "─" * 60))
    result.append(("", "\n"))
    
    # ── 消息内容（含滚偏移） ──
    screen_height = 20  # 大致可见行数
    start_line = max(0, scroll_offset)
    end_line = min(total_lines, start_line + screen_height)
    
    for i in range(start_line, end_line):
        line = lines[i]
        # 行号
        line_num = f"{i+1:4d} "
        result.append(("class:line-number", line_num))
        result.append(("class:message-text", line + "\n"))
    
    # ── 滚动提示 ──
    if end_line < total_lines:
        result.append(("class:info", f"   ... 还有 {total_lines - end_line} 行 （↓继续滚动）"))
        result.append(("", "\n"))
    
    result.append(("class:header-bar", "└" + "─" * 60))
    
    return FormattedText(result)


class MessageDetailScreen:
    """消息详情屏 —— 附属于 TuiAppV2，不独立运行。"""
    
    def __init__(self, app, messages: list[tuple[str, str]], msg_index: int):
        self.app = app
        self.messages = messages
        self.msg_index = msg_index
        self.scroll_offset = 0
        self._active = False
        self._selection_mode = False
        self._sel_start = 0
        self._sel_end = 0
        
        role, text = messages[msg_index] if msg_index < len(messages) else ("", "")
        self.total_lines = text.count("\n") + 1 if text else 0
    
    @property
    def active(self) -> bool:
        return self._active
    
    def open(self):
        """打开详情视图。"""
        self._active = True
        self.scroll_offset = 0
        self.app._ui(self._render)
    
    def close(self):
        """关闭详情视图。"""
        self._active = False
        self.app._log_append(("→", "class:activity-info", "关闭消息详情"))
        self.app._ui(self.app._refresh_status)
    
    def _render(self):
        """渲染详情视图（覆层）。"""
        if not self._active:
            return
        ft = build_detail_formatted(self.messages, self.msg_index, self.scroll_offset)
        # 通过 TUI 的浮动层显示
        try:
            self.app.message_pane._empty_renderer = lambda: ft
            self.app._ui(lambda: None)
        except Exception:
            pass
    
    def handle_key(self, key: str) -> bool:
        """处理按键。返回 True 表示已消费。"""
        if not self._active:
            return False
        
        if key == "escape":
            self.close()
            return True
        
        if key == "up":
            self.scroll_offset = max(0, self.scroll_offset - 1)
            self._render()
            return True
        
        if key == "down":
            self.scroll_offset = min(self.total_lines - 1, self.scroll_offset + 1)
            self._render()
            return True
        
        if key == "pageup":
            self.scroll_offset = max(0, self.scroll_offset - 20)
            self._render()
            return True
        
        if key == "pagedown":
            self.scroll_offset = min(self.total_lines - 20, self.scroll_offset + 20)
            self._render()
            return True
        
        if key == "c":
            # 复制全文
            role, text = self.messages[self.msg_index]
            ok = copy_to_clipboard(text)
            msg = "已复制全文" if ok else "复制失败"
            self.app._log_append(("✓", "class:activity-done", msg))
            return True
        
        if key == "m":
            # 复制 Markdown
            role, text = self.messages[self.msg_index]
            md = f"**{role}**:\n\n{text}"
            ok = copy_to_clipboard(md)
            msg = "已复制 Markdown" if ok else "复制失败"
            self.app._log_append(("✓", "class:activity-done", msg))
            return True
        
        if key == "s":
            # 选择模式
            self._selection_mode = not self._selection_mode
            self.app._log_append(("→", "class:activity-info",
                f"选择模式: {'开启' if self._selection_mode else '关闭'}"))
            return True
        
        return False
