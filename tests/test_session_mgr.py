"""Tests for core.session_mgr — named persistent sessions."""



class TestSessionManager:
    def _make_manager(self, tmp_path):
        from core.session_mgr import SessionManager
        return SessionManager(root=tmp_path)

    def test_save_and_restore(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        name = mgr.save("test_session", messages, meta={"topic": "greeting"})
        restored = mgr.restore(name)
        assert restored is not None
        assert restored["name"] == "test_session"
        assert len(restored["messages"]) == 2
        assert restored["meta"]["topic"] == "greeting"

    def test_restore_nonexistent(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.restore("nope") is None

    def test_list_sessions(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.save("session1", [{"role": "user", "content": "a"}])
        mgr.save("session2", [{"role": "user", "content": "b"}])
        sessions = mgr.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert "session1" in names
        assert "session2" in names

    def test_list_sessions_includes_metadata(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr.save("test", [{"role": "user", "content": "hi"}], meta={"key": "val"})
        sessions = mgr.list_sessions()
        assert sessions[0]["meta"]["key"] == "val"
        assert sessions[0]["message_count"] == 1

    def test_delete_session(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        name = mgr.save("to_delete", [{"role": "user", "content": "x"}])
        assert mgr.delete(name) is True
        assert mgr.restore(name) is None
        assert mgr.delete("nope") is False

    def test_save_sanitizes_name(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        name = mgr.save("path/with/slashes\\and\\backslashes", [])
        assert "/" not in name
        assert "\\" not in name

    def test_save_truncates_long_name(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        long_name = "x" * 200
        name = mgr.save(long_name, [])
        assert len(name) <= 80

    def test_list_corrupted_file(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        sessions_dir = tmp_path / "output" / "sessions_data"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "bad.json").write_text("not json{{{", encoding="utf-8")
        sessions = mgr.list_sessions()
        # Should skip corrupted file without raising
        assert len(sessions) == 0


class TestGlobalFunctions:
    def test_session_save(self, tmp_path, monkeypatch):
        from core import session_mgr as sm
        mgr = sm.SessionManager(root=tmp_path)
        monkeypatch.setattr(sm, "_session_mgr", mgr)
        name = sm.session_save("test", [{"role": "user", "content": "hi"}])
        assert name == "test"

    def test_session_restore(self, tmp_path, monkeypatch):
        from core import session_mgr as sm
        mgr = sm.SessionManager(root=tmp_path)
        monkeypatch.setattr(sm, "_session_mgr", mgr)
        sm.session_save("test", [{"role": "user", "content": "hi"}])
        result = sm.session_restore("test")
        assert result is not None

    def test_session_list(self, tmp_path, monkeypatch):
        from core import session_mgr as sm
        mgr = sm.SessionManager(root=tmp_path)
        monkeypatch.setattr(sm, "_session_mgr", mgr)
        sm.session_save("a", [{"role": "user", "content": "1"}])
        sm.session_save("b", [{"role": "user", "content": "2"}])
        result = sm.session_list()
        assert len(result) == 2

    def test_session_delete(self, tmp_path, monkeypatch):
        from core import session_mgr as sm
        mgr = sm.SessionManager(root=tmp_path)
        monkeypatch.setattr(sm, "_session_mgr", mgr)
        name = sm.session_save("del", [{"role": "user", "content": "x"}])
        assert sm.session_delete(name) is True
