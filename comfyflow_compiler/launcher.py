"""ComfyFlow Compiler — ComfyUI 启动器

自动查找、拉起、监测 ComfyUI 进程。"""

from __future__ import annotations
import os
import sys
import time
import signal
import subprocess
import socket
import re
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field


@dataclass
class ComfyUIStatus:
    running: bool = False
    pid: Optional[int] = None
    port: int = 8188
    url: str = ""
    api_url: str = ""
    process: Optional[subprocess.Popen] = None
    error: Optional[str] = None
    log_tail: List[str] = field(default_factory=list)


class ComfyUILauncher:
    """
    ComfyUI 启动器 — 查找、启动、监测、关闭。
    """

    def __init__(self, comfyui_path: Optional[str] = None):
        self.comfyui_path = self._resolve_path(comfyui_path)
        self.python_exe = self._find_python()
        self.main_script = self.comfyui_path / "main.py" if self.comfyui_path else None
        self.status = ComfyUIStatus()

    # =========================================================================
    # 查找 ComfyUI
    # =========================================================================

    @staticmethod
    def _resolve_path(path: Optional[str]) -> Optional[Path]:
        if path:
            p = Path(path)
            if p.exists():
                return p.resolve()
            return None

        # 自动扫描常见位置
        candidates = [
            Path("D:/ComfyUI"),
            Path("E:/ComfyUI"),
            Path("C:/ComfyUI"),
            Path("C:/Program Files/ComfyUI"),
            Path.home() / "ComfyUI",
            Path.home() / "Documents/ComfyUI",
            Path("./ComfyUI"),
            Path("../ComfyUI"),
        ]
        # 再加一条：搜桌面
        desktop = Path.home() / "Desktop" / "ComfyUI"
        if desktop.exists():
            candidates.insert(0, desktop)

        for p in candidates:
            resolved = p.resolve()
            if resolved.exists() and (resolved / "main.py").exists():
                return resolved

        # 最后碰运气：搜索整个 D 盘根目录下的 ComfyUI 文件夹
        # （耗时操作，跳过）
        return None

    @staticmethod
    def _find_python() -> str:
        """找到合适的 Python 解释器（优先 ComfyUI 自带的）"""
        # 1. 检查 comfyui 环境中的 python
        comfy_envs = [
            Path("D:/ComfyUI/python_embeded/python.exe"),
            Path("D:/ComfyUI/venv/Scripts/python.exe"),
            Path("D:/ComfyUI/.venv/Scripts/python.exe"),
        ]
        for env in comfy_envs:
            if env.exists():
                return str(env)

        # 2. 检查系统 python
        for candidate in ["python", "python3", "py"]:
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return candidate
            except Exception:
                continue

        return "python"

    # =========================================================================
    # 端口检测
    # =========================================================================

    @staticmethod
    def _port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _find_free_port(start: int = 8188, max_try: int = 20) -> int:
        for port in range(start, start + max_try):
            if not ComfyUILauncher._port_in_use(port):
                return port
        return start + max_try

    # =========================================================================
    # 核心启动
    # =========================================================================

    def launch(self, port: int = 8188, quiet: bool = True,
               extra_args: Optional[List[str]] = None,
               wait_until_ready: bool = True, timeout: int = 60) -> ComfyUIStatus:
        """
        启动 ComfyUI。

        Args:
            port: 监听端口（默认 8188）
            quiet: 是否隐藏终端窗口
            extra_args: 额外参数，如 ["--lowvram", "--cpu"]
            wait_until_ready: 是否等待直到就绪
            timeout: 等待就绪的超时秒数

        Returns:
            ComfyUIStatus: 启动状态
        """
        # 检查是否已在运行
        if self._port_in_use(port):
            self.status.running = True
            self.status.port = port
            self.status.url = f"http://127.0.0.1:{port}"
            self.status.api_url = f"http://127.0.0.1:{port}/prompt"
            self.status.error = None
            return self.status

        # 检查 ComfyUI 路径
        if not self.comfyui_path or not self.main_script or not self.main_script.exists():
            self.status.error = f"ComfyUI 未找到。请确保 main.py 存在"
            return self.status

        # 构建启动命令
        cmd = [
            str(self.python_exe),
            str(self.main_script),
            "--port", str(port),
            "--listen", "127.0.0.1",
        ]
        if quiet:
            cmd.append("--windows-standalone-build")  # Windows 隐藏控制台

        if extra_args:
            cmd.extend(extra_args)

        try:
            # 启动进程
            startupinfo = None
            if sys.platform == "win32" and quiet:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.Popen(
                cmd,
                cwd=str(self.comfyui_path),
                stdout=subprocess.PIPE if quiet else None,
                stderr=subprocess.STDOUT,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if (sys.platform == "win32" and quiet) else 0,
            )

            self.status.process = proc
            self.status.pid = proc.pid
            self.status.port = port
            self.status.url = f"http://127.0.0.1:{port}"
            self.status.api_url = f"http://127.0.0.1:{port}/prompt"

            # 等待就绪
            if wait_until_ready:
                self._wait_for_ready(port, timeout)

            return self.status

        except Exception as e:
            self.status.error = f"启动失败: {e}"
            return self.status

    def _wait_for_ready(self, port: int, timeout: int):
        """等待 ComfyUI 就绪（端口可通）"""
        start = time.time()
        last_log_update = 0
        while time.time() - start < timeout:
            if self._port_in_use(port):
                # 额外确认 API 可响应
                try:
                    import urllib.request
                    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
                    if resp.status == 200:
                        self.status.running = True
                        self._read_log_tail()
                        return
                except Exception:
                    pass

            # 读日志
            if self.status.process and self.status.process.stdout:
                now = time.time()
                if now - last_log_update > 2:
                    self._read_log_tail()
                    last_log_update = now

            time.sleep(1)

        # 超时
        self._read_log_tail()
        self.status.error = f"ComfyUI 启动超时 ({timeout}秒)"
        self.status.running = self._port_in_use(port)

    def _read_log_tail(self):
        """读取进程日志最后几行"""
        if not self.status.process or not self.status.process.stdout:
            return
        try:
            lines = []
            while True:
                line = self.status.process.stdout.readline()
                if not line:
                    break
                lines.append(line.decode("utf-8", errors="ignore").strip())
            if lines:
                self.status.log_tail = lines[-20:]
                # 检查是否有错误
                for line in lines:
                    if "Traceback" in line or "Error" in line or "错误" in line:
                        if not self.status.error:
                            self.status.error = line
        except Exception:
            pass

    # =========================================================================
    # 进程管理
    # =========================================================================

    def stop(self):
        """关闭 ComfyUI"""
        if self.status.process and self.status.process.poll() is None:
            if sys.platform == "win32":
                self.status.process.terminate()
                try:
                    self.status.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.status.process.kill()
            else:
                os.kill(self.status.process.pid, signal.SIGTERM)
            self.status.running = False
            self.status.process = None
            return True
        return False

    def is_running(self) -> bool:
        """检查 ComfyUI 是否在运行"""
        if self.status.process and self.status.process.poll() is not None:
            self.status.running = False
            return False
        if self.status.port and self._port_in_use(self.status.port):
            self.status.running = True
            return True
        return self.status.running

    def restart(self, port: int = 8188, quiet: bool = True,
                extra_args: Optional[List[str]] = None,
                timeout: int = 60) -> ComfyUIStatus:
        """重启 ComfyUI"""
        self.stop()
        time.sleep(2)
        return self.launch(port, quiet, extra_args, True, timeout)

    # =========================================================================
    # 实用方法
    # =========================================================================

    def get_api_url(self) -> str:
        return f"http://127.0.0.1:{self.status.port}/prompt"

    def send_workflow(self, workflow_json: dict) -> dict:
        """发送工作流到 ComfyUI 执行"""
        import urllib.request
        import json

        payload = json.dumps(workflow_json).encode("utf-8")
        req = urllib.request.Request(
            self.get_api_url(),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def find_all_installations() -> List[Path]:
        """扫描系统找到所有 ComfyUI 安装"""
        found = []
        roots = [
            Path("D:/"),
            Path("E:/"),
            Path("C:/"),
            Path.home() / "Desktop",
            Path.home() / "Documents",
        ]
        for root in roots:
            if not root.exists():
                continue
            try:
                for item in root.iterdir():
                    if item.name.lower() == "comfyui" and item.is_dir():
                        if (item / "main.py").exists():
                            found.append(item.resolve())
            except PermissionError:
                pass
        return found


# =============================================================================
# 快速入口
# =============================================================================

def launch_comfyui(comfyui_path: Optional[str] = None,
                   port: int = 8188,
                   quiet: bool = True,
                   wait: bool = True) -> ComfyUIStatus:
    """一键启动 ComfyUI"""
    launcher = ComfyUILauncher(comfyui_path)
    return launcher.launch(port=port, quiet=quiet, wait_until_ready=wait)
