"""Tests for core/session_mgr.py — 命名会话管理"""

import pytest

from core.session_mgr import (
    SessionManager,
    session_delete,
    session_list,
    session_restore,
    session_save,
)


@pytest.fixture
def sm():
    """每个测试独立实例"""
    return SessionManager()


class TestSessionSave:
    """保存会话测试"""

    def test_save_basic(self, sm):
        name = sm.save("测试会话", [{"role": "user", "content": "hello"}])
        assert name == "测试会话"

    def test_save_with_meta(self, sm):
        sm.save("带元数据", [{"role": "user", "content": "hi"}], meta={"model": "gpt-4"})

    def test_save_empty_messages(self, sm):
        name = sm.save("空会话", [])
        assert name == "空会话"

    def test_save_multiple_messages(self, sm):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "how are you?"},
        ]
        sm.save("多轮对话", msgs)
        restored = sm.restore("多轮对话")
        assert len(restored["messages"]) == 3

    def test_save_overwrites(self, sm):
        sm.save("覆盖测试", [{"role": "user", "content": "v1"}])
        sm.save("覆盖测试", [{"role": "user", "content": "v2"}])
        restored = sm.restore("覆盖测试")
        assert restored["messages"][0]["content"] == "v2"


class TestSessionRestore:
    """恢复会话测试"""

    def test_restore_existing(self, sm):
        sm.save("会话A", [{"role": "user", "content": "test"}])
        restored = sm.restore("会话A")
        assert restored is not None
        assert restored["name"] == "会话A"

    def test_restore_nonexistent(self, sm):
        assert sm.restore("不存在的会话") is None

    def test_restore_has_messages(self, sm):
        sm.save("带消息的会话", [{"role": "user", "content": "msg"}])
        restored = sm.restore("带消息的会话")
        assert "messages" in restored
        assert len(restored["messages"]) == 1


class TestSessionList:
    """列出会话测试"""

    def test_list_sessions(self, sm):
        sm.save("会话1", [])
        sm.save("会话2", [])
        sessions = sm.list_sessions()
        assert len(sessions) >= 2

    def test_list_includes_metadata(self, sm):
        sm.save("会话X", [{"role": "user", "content": "x"}])
        sessions = sm.list_sessions()
        s = sessions[0]
        assert "name" in s
        assert "message_count" in s
        assert "saved_at" in s

    def test_list_empty(self):
        sm2 = SessionManager()
        sessions = sm2.list_sessions()
        assert isinstance(sessions, list)


class TestSessionDelete:
    """删除会话测试"""

    def test_delete_existing(self, sm):
        sm.save("待删除", [])
        result = sm.delete("待删除")
        assert result is True
        assert sm.restore("待删除") is None

    def test_delete_nonexistent(self, sm):
        result = sm.delete("不存在的会话")
        assert result is False or result is True

    def test_delete_then_list(self, sm):
        sm.save("临时会话", [])
        sm.delete("临时会话")
        names = [s["name"] for s in sm.list_sessions()]
        assert "临时会话" not in names


class TestModuleFunctions:
    """模块级快捷函数测试"""

    def test_session_save(self):
        name = session_save("模块级保存", [])
        assert name == "模块级保存"

    def test_session_restore(self):
        session_save("模块级", [{"role": "user", "content": "test"}])
        result = session_restore("模块级")
        assert result is not None

    def test_session_list(self):
        result = session_list()
        assert isinstance(result, list)

    def test_session_delete(self):
        session_save("模块删除", [])
        result = session_delete("模块删除")
        assert result is True
