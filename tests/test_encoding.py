"""Tests for core.encoding, core.notify, core.session_mgr."""

import sys
import subprocess



# ── core.encoding ────────────────────────────────────────────────────────


class TestEncodingSetup:
    """UTF-8 encoding setup functions work on all platforms."""

    def test_setup_win32_console_returns_bool(self):
        from core.encoding import _setup_win32_console
        result = _setup_win32_console()
        # On Windows returns True; on non-Windows returns False
        assert isinstance(result, bool)

    def test_setup_win32_console_idempotent(self):
        from core.encoding import _setup_win32_console
        r1 = _setup_win32_console()
        r2 = _setup_win32_console()
        assert r1 == r2

    def test_reconfigure_stdio_no_crash(self):
        from core.encoding import _reconfigure_stdio
        _reconfigure_stdio()  # should not raise

    def test_setup_no_crash(self):
        from core.encoding import setup
        setup()  # should not raise

    def test_subprocess_patched(self):
        from core.encoding import setup
        setup()
        # Verify subprocess.run has been patched with encoding default
        r = subprocess.run(
            [sys.executable, "-c", "import sys; print('ok')"],
            capture_output=True,
        )
        assert r.returncode == 0
        assert "ok" in r.stdout  # type: ignore[operator]  # setup() 注入 encoding=utf-8，运行时 stdout 为 str


# ── core.session_mgr ─────────────────────────────────────────────────────


class TestSessionManager:
    """Session save/restore/list/delete."""

    def test_create_manager(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        assert mgr.dir.exists()

    def test_save_and_restore(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        messages = [{"role": "user", "content": "hello"}]
        name = mgr.save("test_session", messages, meta={"key": "val"})
        assert name == "test_session"

        data = mgr.restore("test_session")
        assert data is not None
        assert data["name"] == "test_session"
        assert len(data["messages"]) == 1
        assert data["meta"]["key"] == "val"

    def test_restore_nonexistent(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        assert mgr.restore("no_such_session") is None

    def test_list_sessions(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        mgr.save("s1", [{"role": "user", "content": "a"}])
        mgr.save("s2", [{"role": "user", "content": "b"}])
        sessions = mgr.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert "s1" in names
        assert "s2" in names

    def test_delete_session(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        mgr.save("del_me", [{"role": "user", "content": "x"}])
        assert mgr.delete("del_me") is True
        assert mgr.delete("del_me") is False

    def test_list_corrupted_skips(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        mgr.save("good", [{"role": "user", "content": "ok"}])
        # Write corrupted JSON
        bad_file = mgr.dir / "bad.json"
        bad_file.write_text("{invalid json", encoding="utf-8")
        sessions = mgr.list_sessions()
        assert len(sessions) == 1  # only "good"

    def test_safe_name_sanitization(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        name = mgr.save("../../etc/passwd", [])
        assert "/" not in name

    def test_convenience_functions(self, tmp_path):
        from core.session_mgr import SessionManager
        mgr = SessionManager(root=tmp_path)
        # Patch global
        import core.session_mgr as sm
        sm._session_mgr = mgr
        sm.session_save("fn_test", [{"role": "user", "content": "hi"}])
        data = sm.session_restore("fn_test")
        assert data is not None
        lst = sm.session_list()
        assert len(lst) == 1
        sm.session_delete("fn_test")
        assert sm.session_list() == []
