"""Aria2 engine — JSON-RPC for direct URL downloads."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass

from core.error_sink import catch


@dataclass
class Aria2Config:
    rpc_url: str = "http://127.0.0.1:6800/jsonrpc"
    rpc_secret: str | None = None
    aria2c_path: str = "aria2c"
    split: int = 8
    max_connection_per_server: int = 8


class Aria2Engine:
    """aria2 download engine via JSON-RPC."""

    def __init__(self, config: Aria2Config | None = None):
        self.config = config or Aria2Config()
        self._proc: subprocess.Popen | None = None

    def ensure_daemon(self) -> None:
        if self._is_alive():
            return
        args = [
            self.config.aria2c_path,
            "--enable-rpc=true",
            "--rpc-listen-all=false",
            "--rpc-listen-port=6800",
            "--continue=true",
            f"--max-connection-per-server={self.config.max_connection_per_server}",
            f"--split={self.config.split}",
            "--min-split-size=1M",
        ]
        if self.config.rpc_secret:
            args.append(f"--rpc-secret={self.config.rpc_secret}")
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.3)

    def add_uri(
        self, url: str, *, out: str | None = None, dir: str | None = None, headers: dict[str, str] | None = None
    ) -> str:
        """Add a download URI. Returns gid."""
        self.ensure_daemon()
        options = {}
        if out:
            options["out"] = out
        if dir:
            options["dir"] = dir
        if headers:
            options["header"] = [f"{k}: {v}" for k, v in headers.items()]
        params = [[url], options]
        return self._rpc("aria2.addUri", params)

    def tell_status(self, gid: str) -> dict:
        return self._rpc(
            "aria2.tellStatus",
            [
                gid,
                ["status", "totalLength", "completedLength", "downloadSpeed", "files", "errorMessage"],
            ],
        )

    def pause(self, gid: str) -> None:
        self._rpc("aria2.pause", [gid])

    def unpause(self, gid: str) -> None:
        self._rpc("aria2.unpause", [gid])

    def remove(self, gid: str) -> None:
        self._rpc("aria2.remove", [gid])

    def shutdown(self) -> None:
        try:
            self._rpc("aria2.shutdown", [])
        except Exception as _es:
            catch(_es, "core/download/engines/aria2_engine", "swallowed")
        if self._proc:
            self._proc.terminate()
            self._proc = None

    def _rpc(self, method: str, params: list):
        if self.config.rpc_secret:
            params = [f"token:{self.config.rpc_secret}", *params]
        payload = {"jsonrpc": "2.0", "id": "crux-dl", "method": method, "params": params}
        req = urllib.request.Request(
            self.config.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data["result"]

    def _is_alive(self) -> bool:
        try:
            self._rpc("aria2.getVersion", [])
            return True
        except Exception:
            return False
