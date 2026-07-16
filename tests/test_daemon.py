"""WebSocket IPC tests for core/daemon.py — in a separate file."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.daemon import Daemon, StartupDiagnostics


class TestStartupDiagnostics:
    def test_create(self):
        sd = StartupDiagnostics()
        assert sd.events is None or sd.events == []

    def test_mark(self):
        sd = StartupDiagnostics()
        sd.mark("x")
        assert sd.events[0].name == "x"
        assert sd.events[0].elapsed_ms >= 0

    def test_to_dict(self):
        sd = StartupDiagnostics()
        sd.mark("a")
        d = sd.to_dict()
        assert "pid" in d
        assert "events" in d
        assert d["events"][0]["name"] == "a"


class TestDaemonCommands:
    def test_status(self):
        d = Daemon()
        r = json.loads(d._handle_command("status"))
        assert "pid" in r

    def test_attach_detach(self):
        d = Daemon()
        json.loads(d._handle_command("attach"))
        assert d.state.sessions_active == 1
        json.loads(d._handle_command("detach"))
        assert d.state.sessions_active == 0

    def test_startup_log(self):
        d = Daemon()
        r = json.loads(d._handle_command("startup-log"))
        assert len(r["events"]) >= 1
        assert "__init__" in [e["name"] for e in r["events"]]

    def test_unknown_cmd(self):
        d = Daemon()
        r = json.loads(d._handle_command("blah"))
        assert r["ok"] is False


class TestDaemonWebSocket:
    @classmethod
    def setup_class(cls):
        cls.daemon = Daemon()
        cls.daemon._running = True  # keep WS server loop alive
        cls.daemon._start_websocket()
        deadline = time.time() + 5
        while time.time() < deadline:
            port = getattr(cls.daemon, "_ws_port", 0)
            if port > 0:
                cls.ws_port = port
                break
            time.sleep(0.05)
        if cls.ws_port == 0:
            raise RuntimeError("WS not ready in 5s")
        cls.ws_url = f"ws://127.0.0.1:{cls.ws_port}"

    @classmethod
    def teardown_class(cls):
        if cls.daemon:
            cls.daemon._running = False
            cls.daemon._stop_websocket()
            time.sleep(0.15)

    def _ws(self, payload: dict) -> dict:
        import asyncio

        import websockets

        async def doit():
            async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                await ws.send(json.dumps(payload))
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                return json.loads(resp)

        return asyncio.run(doit())

    def test_port(self):
        assert self.ws_port > 0

    def test_status(self):
        r = self._ws({"cmd": "status"})
        assert "pid" in r

    def test_attach_detach(self):
        self._ws({"cmd": "attach"})
        s = self._ws({"cmd": "status"})
        assert s["sessions_active"] >= 1
        self._ws({"cmd": "detach"})

    def test_startup_log(self):
        r = self._ws({"cmd": "startup-log"})
        assert len(r["events"]) >= 1

    def test_invalid_json(self):
        import asyncio

        import websockets

        async def doit():
            async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                await ws.send("{{{bad")
                r = await asyncio.wait_for(ws.recv(), timeout=5)
                assert json.loads(r)["ok"] is False

        asyncio.run(doit())

    def test_concurrent(self):
        import asyncio

        import websockets

        async def client():
            async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                await ws.send(json.dumps({"cmd": "status"}))
                r = await asyncio.wait_for(ws.recv(), timeout=5)
                return json.loads(r)

        async def main():
            a, b = await asyncio.gather(client(), client())
            assert "pid" in a
            assert "pid" in b

        asyncio.run(main())
