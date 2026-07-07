"""CopyManager 单元测试 — 基于 MessageStore"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestCopyManager:
    def test_sync_store(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "q")
        store.append("assistant", "a")
        cm = CopyManager(store)
        assert cm.focus.total == 2

    def test_copy_focused_last_assistant(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hello")
        store.append("assistant", "world")
        cm = CopyManager(store)
        ok, msg = cm.copy_focused()
        assert ok
        assert "world" in msg

    def test_copy_focused_no_messages(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        cm = CopyManager(MessageStore())
        ok, msg = cm.copy_focused()
        assert not ok

    def test_copy_markdown(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "**bold**")
        cm = CopyManager(store)
        ok, msg = cm.copy_focused_markdown()
        assert ok
        assert "Markdown" in msg

    def test_copy_code_block(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "```python\nx = 1\n```")
        cm = CopyManager(store)
        ok, msg = cm.copy_focused()
        ok2, msg2 = cm.handle_command("/copy code 0")
        assert ok2

    def test_copy_code_block_invalid_index(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "no code here")
        cm = CopyManager(store)
        ok, msg = cm.handle_command("/copy code 5")
        assert not ok

    def test_copy_lines_range(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "a\nb\nc\nd\ne")
        cm = CopyManager(store)
        ok, _ = cm.handle_command("/copy 0:1-3")
        assert ok

    def test_handle_command_copy_last(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "final answer")
        cm = CopyManager(store)
        ok, msg = cm.handle_command("/copy last")
        assert ok
        assert "final answer" in msg

    def test_handle_command_copy_last_markdown(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "# title")
        cm = CopyManager(store)
        ok, msg = cm.handle_command("/copy last markdown")
        assert ok
        assert "Markdown" in msg

    def test_handle_command_target_not_found(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hi")
        cm = CopyManager(store)
        ok, msg = cm.handle_command("/copy 99")
        assert not ok

    def test_focus_navigation_with_copy(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "q1")
        store.append("assistant", "a1")
        store.append("user", "q2")
        store.append("assistant", "a2")
        cm = CopyManager(store)
        cm.focus.next()  # index=3
        cm.focus.prev()  # index=2
        msg = cm.get_focused_msg()
        assert msg.text == "q2"

    def test_handle_command_copy_by_index(self):
        from ui.copy_manager import CopyManager
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("assistant", "msg0")
        store.append("assistant", "msg1")
        cm = CopyManager(store)
        ok, msg = cm.handle_command("/copy 0")
        assert ok
        assert "msg0" in msg


class TestExtractCodeBlocks:
    def test_python_bash(self):
        from ui.copy_manager import extract_code_blocks
        blocks = extract_code_blocks("```python\nx=1\n```\n```bash\nls\n```")
        assert len(blocks) == 2

    def test_no_code_blocks(self):
        from ui.copy_manager import extract_code_blocks
        blocks = extract_code_blocks("no code here")
        assert blocks == []

    def test_code_block_without_lang(self):
        from ui.copy_manager import extract_code_blocks
        blocks = extract_code_blocks("```\njust text\n```")
        assert len(blocks) == 1
        assert blocks[0]["language"] == "text"
