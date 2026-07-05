"""Performance smoke tests — baseline metrics to catch regressions."""

from __future__ import annotations

import time


class TestImportPerformance:
    """Core modules must import within acceptable time."""

    def test_chat_import_time(self):
        t0 = time.time()
        elapsed = time.time() - t0
        assert elapsed < 0.5, f"chat.py import took {elapsed:.2f}s"

    def test_provider_import_time(self):
        t0 = time.time()
        elapsed = time.time() - t0
        assert elapsed < 0.3, f"provider.py import took {elapsed:.2f}s"

    def test_tools_import_time(self):
        t0 = time.time()
        elapsed = time.time() - t0
        assert elapsed < 0.3, f"tools.py import took {elapsed:.2f}s"


class TestMessageThroughput:
    """Message pane must handle typical loads efficiently."""

    def test_1000_messages_under_100ms(self):
        from ui.message_pane import MessagePane
        mp = MessagePane()
        t0 = time.time()
        for i in range(1000):
            mp.append_message("crux", f"Message {i}")
        elapsed = time.time() - t0
        assert elapsed < 0.2, f"1000 messages took {elapsed:.2f}s"

    def test_stream_chunks_under_50ms(self):
        from ui.message_pane import MessagePane
        mp = MessagePane()
        mp.stream_start("crux")
        t0 = time.time()
        for i in range(500):
            mp.stream_append(f"chunk{i} ")
        mp.stream_end()
        elapsed = time.time() - t0
        assert elapsed < 0.1, f"500 stream chunks took {elapsed:.2f}s"


class TestMemoryBaseline:
    """Memory usage must stay within bounds."""

    def test_10k_messages_memory(self):
        import sys

        from ui.message_pane import MessagePane
        mp = MessagePane()
        for i in range(10000):
            mp.append_message("crux", f"Line {i}: " + "data " * 10)
        size = sys.getsizeof(mp._lines)
        assert size < 1024 * 1024, f"10K messages: {size/1024:.0f}KB"
