"""
Aria2 Bridge — 多线程下载引擎。

从 nsp-downloader 抽取 aria2 核心，接入 CRUX Studio。
用于下载大模型权重、数据集、大文件。16线程加速，支持断点续传。

Usage:
    from core.aria2_bridge import get_bridge
    bridge = get_bridge()
    gid = bridge.download("https://huggingface.co/.../model.safetensors")
    status = bridge.status(gid)
    bridge.stop()

RPC: JSON-RPC over HTTP, port 6801 (避免和 nsp-downloader 的 6800 冲突)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("crux.aria2")
ROOT = Path(__file__).resolve().parent.parent
ARIA2_PATH = ROOT / "core" / "resources" / "aria2c.exe"
DEFAULT_DIR = ROOT / "downloads"

__all__ = ["Aria2Bridge", "get_bridge", "DownloadTask"]


@dataclass
class DownloadTask:
    gid: str
    url: str
    status: str = "waiting"  # waiting | active | paused | complete | error | removed
    total_length: int = 0
    completed_length: int = 0
    download_speed: int = 0
    progress: float = 0.0
    files: list[dict] = field(default_factory=list)
    error_message: str = ""
    label: str = ""

    @classmethod
    def from_aria2(cls, data: dict) -> DownloadTask:
        completed = int(data.get("completedLength", 0))
        total = int(data.get("totalLength", 0))
        progress = (completed / total * 100) if total > 0 else 0.0
        files = data.get("files", [])
        # Extract URL from files or first URI
        url = ""
        if files and len(files) > 0:
            uris = files[0].get("uris", [])
            if uris:
                url = uris[0].get("uri", "")
        return cls(
            gid=data.get("gid", ""),
            url=url,
            status=data.get("status", "unknown"),
            total_length=total,
            completed_length=completed,
            download_speed=int(data.get("downloadSpeed", 0)),
            progress=round(progress, 1),
            files=files,
            error_message=data.get("errorMessage", ""),
        )


class Aria2Bridge:
    _instance: Aria2Bridge | None = None

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._rpc_port = 6801
        self._rpc_secret = os.environ.get("CRUX_ARIA2_SECRET", "crux-aria2-secret")
        self._running = False
        self._lock = threading.Lock()
        self._download_dir = str(DEFAULT_DIR)
        self._session_file = str(
            ROOT / "output" / "aria2_session.json"
        )

    # ── public API ────────────────────────────────────────

    def start(
        self,
        download_dir: str | None = None,
        max_connections: int = 16,
        max_concurrent: int = 5,
        speed_limit: int = 0,  # KB/s, 0=unlimited
    ) -> bool:
        """启动 aria2c 后台进程。幂等，已启动则直接返回 True。"""
        with self._lock:
            if self._running:
                return True

            if not ARIA2_PATH.exists():
                logger.error(f"aria2c not found at {ARIA2_PATH}")
                return False

            if download_dir:
                self._download_dir = download_dir
            os.makedirs(self._download_dir, exist_ok=True)

            # Ensure session file exists (aria2 --input-file requires it)
            session_dir = os.path.dirname(self._session_file)
            os.makedirs(session_dir, exist_ok=True)
            if not os.path.exists(self._session_file):
                with open(self._session_file, "w") as f:
                    f.write("")

            args = [
                str(ARIA2_PATH),
                f"--dir={self._download_dir}",
                f"--split={max_connections}",
                f"--max-connection-per-server={max_connections}",
                f"--max-concurrent-downloads={max_concurrent}",
                "--min-split-size=1M",
                "--continue=true",
                "--file-allocation=none",
                "--disk-cache=32M",
                "--enable-rpc=true",
                f"--rpc-listen-port={self._rpc_port}",
                "--rpc-allow-origin-all=true",
                "--rpc-listen-all=false",  # only localhost
                f"--rpc-secret={self._rpc_secret}",
                f"--save-session={self._session_file}",
                f"--input-file={self._session_file}",
                "--save-session-interval=10",
                "--check-certificate=false",
                "--console-log-level=warn",
                "--quiet",
            ]

            if speed_limit > 0:
                args.append(f"--max-overall-download-limit={speed_limit}K")

            try:
                self._process = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                # Wait for RPC ready
                if self._wait_ready(15):
                    self._running = True
                    logger.info(f"[Aria2] Ready on port {self._rpc_port}")
                    return True
                else:
                    self._process.kill()
                    self._process = None
                    logger.error("[Aria2] Failed to start within timeout")
                    return False
            except (OSError, subprocess.SubprocessError) as e:
                logger.exception(f"[Aria2] Start failed: {e}")
                return False

    def stop(self) -> None:
        """安全关闭 aria2c（保存会话后退出）。"""
        with self._lock:
            if not self._running:
                return
            try:
                self._rpc("aria2.shutdown")
            except (requests.RequestException, OSError, RuntimeError):
                pass
            if self._process:
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None
            self._running = False
            logger.info("[Aria2] Stopped")

    def download(
        self,
        url: str,
        filename: str | None = None,
        referer: str = "",
        cookies: str = "",
        user_agent: str = "",
        label: str = "",
    ) -> str:
        """添加下载任务，返回 gid（全局唯一任务ID）。

        Args:
            url: 下载链接 (http/https/ftp/magnet/ed2k)
            filename: 可选，指定输出文件名
            referer: 可选，HTTP Referer
            cookies: 可选，Cookie 字符串
            user_agent: 可选，自定义 User-Agent
            label: 可选，任务标签（用于追踪）

        Returns:
            gid: 任务ID，用于后续查询/控制
        """
        if not self._running:
            self.start()

        options: dict[str, Any] = {}
        headers = []
        if cookies:
            headers.append(f"Cookie: {cookies}")
        if referer:
            options["referer"] = referer
        if user_agent:
            options["user-agent"] = user_agent
        if filename:
            options["out"] = filename
        if headers:
            options["header"] = headers

        gid = self._rpc("aria2.addUri", [[url], options])

        if label and hasattr(self, "_labels"):
            self._labels[gid] = label

        return gid

    def pause(self, gid: str) -> None:
        """暂停任务。"""
        self._rpc("aria2.pause", [gid])

    def resume(self, gid: str) -> None:
        """恢复任务。"""
        self._rpc("aria2.unpause", [gid])

    def remove(self, gid: str) -> None:
        """删除任务（保留已下载文件）。"""
        self._rpc("aria2.remove", [gid])

    def force_remove(self, gid: str) -> None:
        """强制删除任务（删除已下载文件）。不报错如果任务已不存在。"""
        try:
            self._rpc("aria2.forceRemove", [gid])
        except RuntimeError as e:
            if "not found" in str(e).lower():
                pass  # already removed, fine
            else:
                raise

    def status(self, gid: str) -> DownloadTask:
        """查询单个任务状态。"""
        data = self._rpc("aria2.tellStatus", [gid])
        return DownloadTask.from_aria2(data)

    def list_active(self) -> list[DownloadTask]:
        """列出所有活动任务。"""
        items = self._rpc("aria2.tellActive")
        return [DownloadTask.from_aria2(item) for item in items]

    def list_all(self) -> list[DownloadTask]:
        """列出所有任务（活动+等待+已停止）。"""
        all_tasks = []
        all_tasks.extend(self.list_active())
        try:
            waiting = self._rpc("aria2.tellWaiting", [0, 1000])
            all_tasks.extend([DownloadTask.from_aria2(item) for item in waiting])
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            pass
        try:
            stopped = self._rpc("aria2.tellStopped", [0, 1000])
            all_tasks.extend([DownloadTask.from_aria2(item) for item in stopped])
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            pass
        return all_tasks

    def clear_completed(self) -> None:
        """清理已完成/失败的任务记录。"""
        self._rpc("aria2.purgeDownloadResult")

    @property
    def alive(self) -> bool:
        """aria2c 是否存活。"""
        if not self._running:
            return False
        try:
            self._rpc("aria2.getVersion")
            return True
        except (requests.RequestException, json.JSONDecodeError, RuntimeError):
            return False

    # ── internals ──────────────────────────────────────────

    def _rpc(self, method: str, params: list | None = None) -> Any:
        """JSON-RPC 调用，最多重试1次。"""
        url = f"http://127.0.0.1:{self._rpc_port}/jsonrpc"
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": str(int(time.time() * 1000)),
            "method": method,
            "params": [f"token:{self._rpc_secret}", *(params or [])],
        })

        last_error = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    url, data=body,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(data["error"].get("message", "RPC error"))
                return data["result"]
            except requests.ConnectionError as e:
                last_error = e
                if attempt == 0:
                    time.sleep(0.5)
                    continue
            except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
                last_error = e

        raise RuntimeError(f"aria2 RPC failed: {last_error}")

    def _wait_ready(self, timeout: int) -> bool:
        """等待 RPC 就绪。"""
        start = time.time()
        while time.time() - start < timeout:
            if self._process and self._process.poll() is not None:
                return False  # process died
            try:
                self._rpc("aria2.getVersion")
                return True
            except (requests.RequestException, json.JSONDecodeError):
                time.sleep(0.5)
        return False


def get_bridge() -> Aria2Bridge:
    """获取全局 Aria2Bridge 单例（延迟初始化）。"""
    if Aria2Bridge._instance is None:
        Aria2Bridge._instance = Aria2Bridge()
    return Aria2Bridge._instance
