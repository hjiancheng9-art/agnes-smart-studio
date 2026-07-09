"""Tests for core/memory_bridge.py — 跨会话记忆桥接"""

import pytest

from core.memory_bridge import MemoryBridge


@pytest.fixture
def mb():
    return MemoryBridge()


class TestMemoryBridge:
    def test_remember_and_recall(self, mb):
        """记忆和回忆"""
        fact_id = mb.remember("CRUX 使用 Python 编写", entity="project")
        assert fact_id is not None
        results = mb.recall("CRUX")
        assert isinstance(results, list)

    def test_recall_empty(self, mb):
        results = mb.recall("不存在的记忆")
        assert isinstance(results, list)

    def test_extract_key_facts(self, mb):
        facts = mb.extract_key_facts(
            [
                {"role": "user", "content": "帮我重构登录模块"},
                {"role": "assistant", "content": "好的，我来重构"},
            ]
        )
        assert isinstance(facts, list)

    def test_extract_empty_messages(self, mb):
        facts = mb.extract_key_facts([])
        assert isinstance(facts, list)

    def test_inject_context(self, mb):
        messages = [{"role": "user", "content": "hello"}]
        mb.inject_context(messages, "用户输入")
        assert len(messages) >= 1

    def test_flush(self, mb):
        mb.flush()
        assert True  # 不应崩溃

    def test_remember_with_metadata(self, mb):
        fact_id = mb.remember("重要记忆", entity="test", metadata={"source": "unit_test"})
        assert fact_id is not None

    def test_recall_returns_dicts(self, mb):
        mb.remember("测试数据", entity="test")
        results = mb.recall("测试", entity="test")
        assert isinstance(results, list)
        if results:
            assert isinstance(results[0], dict)
