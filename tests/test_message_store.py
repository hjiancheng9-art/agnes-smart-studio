"""MessageStore + Message 单元测试"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestMessage:
    def test_create_message(self):
        from ui.message_store import Message
        msg = Message(role="user", text="hello")
        assert msg.role == "user"
        assert msg.text == "hello"
        assert not msg.is_streaming
        assert msg.line_count == 1
        assert msg.id

    def test_message_snippet(self):
        from ui.message_store import Message
        msg = Message(role="assistant", text="a" * 100)
        assert len(msg.snippet(60)) <= 63  # 60 + "..."
        assert "..." in msg.snippet(60)

    def test_message_code_blocks(self):
        from ui.message_store import Message
        msg = Message(role="assistant", text="text\n```python\nprint(1)\n```\nmore\n```bash\nls\n```")
        blocks = msg.code_blocks
        assert len(blocks) == 2
        assert blocks[0]["language"] == "python"
        assert blocks[0]["code"] == "print(1)"
        assert blocks[1]["language"] == "bash"
        assert blocks[1]["code"] == "ls"

    def test_message_no_code_blocks(self):
        from ui.message_store import Message
        msg = Message(role="user", text="just plain text")
        assert msg.code_blocks == []

    def test_message_get_lines(self):
        from ui.message_store import Message
        msg = Message(role="user", text="line1\nline2\nline3")
        assert msg.get_lines(0, 2) == "line1\nline2"
        assert msg.get_lines(1, 3) == "line2\nline3"


class TestMessageStore:
    def test_append_and_get(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hello")
        store.append("assistant", "hi there")
        assert len(store) == 2
        assert store.get(0).role == "user"
        assert store.get(1).role == "assistant"

    def test_nth(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "a")
        store.append("assistant", "b")
        assert store.nth(1).text == "b"
        assert store.nth(2).text == "a"
        assert store.nth(5) is None

    def test_last_assistant_and_user(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "q1")
        store.append("assistant", "a1")
        store.append("user", "q2")
        assert store.last_assistant().text == "a1"
        assert store.last_user().text == "q2"

    def test_last_assistant_none(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "q1")
        assert store.last_assistant() is None

    def test_stream(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        msg = store.start_stream("assistant")
        assert msg.is_streaming
        assert msg.role == "assistant"
        store.stream_chunk("hello ")
        store.stream_chunk("world")
        end = store.end_stream()
        assert not end.is_streaming
        assert end.text == "hello world"

    def test_find_by_line(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "line1\nline2")          # 2 lines
        store.append("assistant", "line3\nline4\nline5")  # 3 lines
        msg, offset = store.find_by_line(1)
        assert msg.text == "line1\nline2"
        assert offset == 1
        msg2, off2 = store.find_by_line(3)
        assert msg2.text == "line3\nline4\nline5"
        assert off2 == 1

    def test_find_by_line_out_of_range(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hi")
        msg, offset = store.find_by_line(100)
        assert msg is None

    def test_total_lines(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "a\nb\nc")
        store.append("assistant", "d\ne")
        assert store.total_lines == 5

    def test_as_plain_tuples(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hello")
        store.append("assistant", "world")
        tuples = store.as_plain_tuples()
        assert tuples == [("user", "hello"), ("assistant", "world")]

    def test_clear(self):
        from ui.message_store import MessageStore
        store = MessageStore()
        store.append("user", "hi")
        store.clear()
        assert len(store) == 0
        assert store.last_assistant() is None
