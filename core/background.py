"""Background task management — TaskList / TaskOutput / TaskStop for CRUX.

移植自 Kimi Code CLI 的后台任务系统：
  task_launch: 启动后台子进程，返回 task_id
  task_list:   枚举活跃/已完成任务
  task_output: 非阻塞获取输出快照（block=True 等待完成）
  task_stop:   终止后台任务

子进程 stdout/stderr 写入 output/background/{task_id}.log。
由 BackgroundManager 线程池管理生命周期。
"""

from __future__ import annotations

import atexit as _atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass

from core.config import OUTPUT_DIR
from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "BACKGROUND_EXECUTOR_MAP",
    "BACKGROUND_TOOL_DEFS",
    "BackgroundManager",
    "BackgroundTask",
    "get_background_manager",
    "reset_background_manager",
]


# ── BackgroundTask dataclass ──────────────────────────────────


@dataclass
class BackgroundTask:
    """Represents a background shell task."""

    id: str
    command: str
    description: str = ""
    status: str = "pending"  # pending | running | done | failed | timed_out | stopped
    pid: int = 0
    exit_code: int | None = None
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    timeout: int = 600  # default 10 min
    output_path: str = ""
    stop_reason: str = ""
    terminal_reason: str = ""  # "timed_out" | "stopped" | ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elapsed"] = round(time.time() - self.started_at, 1) if self.started_at else 0
        return d

    @classmethod
    def from_dict(cls, data: dict) -> BackgroundTask:
        known = cls.__dataclass_fields__
        return cls(**{k: data[k] for k in known if k in data})

    @property
    def is_terminal(self) -> bool:
        return self.status in ("done", "failed", "timed_out", "stopped")


# ── BackgroundManager ─────────────────────────────────────────

_BG_LOG_DIR = OUTPUT_DIR / "background"
_DEFAULT_TIMEOUT = 600  # 10 min


class BackgroundManager:
    """Manages background subprocess tasks with lifecycle tracking."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._max_tasks = 100
        _BG_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ──

    def launch(
        self,
        command: str,
        description: str = "",
        timeout: int = _DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> BackgroundTask:
        """Launch a background shell command. Returns the task object."""
        task_id = uuid.uuid4().hex[:8]
        output_path = str(_BG_LOG_DIR / f"{task_id}.log")
        now = time.time()

        task = BackgroundTask(
            id=task_id,
            command=command,
            description=description or command[:80],
            status="running",
            created_at=now,
            started_at=now,
            timeout=timeout,
            output_path=output_path,
        )

        with self._lock:
            self._tasks[task_id] = task

        # Start subprocess in background thread
        t = threading.Thread(
            target=self._run_task,
            args=(task_id, command, output_path, timeout, cwd),
            daemon=True,
        )
        t.start()

        with self._lock:
            self._threads[task_id] = t

        return task

    def list_tasks(self, active_only: bool = True) -> list[BackgroundTask]:
        """List tasks. active_only: only non-terminal tasks."""
        with self._lock:
            tasks = list(self._tasks.values())
        if active_only:
            return [t for t in tasks if not t.is_terminal]
        return tasks

    def get_task(self, task_id: str) -> BackgroundTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_output(self, task_id: str, block: bool = False, timeout: int = 30) -> dict:
        """Get output snapshot for a task.

        Args:
            task_id: The task ID.
            block: If True, wait for task completion.
            timeout: Max seconds to wait when block=True.

        Returns:
            dict with keys: task (dict), output_preview (str), output_truncated (bool)
        """
        task = self.get_task(task_id)
        if task is None:
            return {"task": None, "output_preview": "", "output_truncated": False, "error": "Task not found"}

        # Block if requested and task is active
        if block and not task.is_terminal:
            with self._lock:
                t = self._threads.get(task_id)
            if t and t.is_alive():
                t.join(timeout=timeout)

        # Refresh task state
        task = self.get_task(task_id)
        if task is None:
            return {"task": None, "output_preview": "", "output_truncated": False}

        # Read output with encoding recovery
        output_preview = ""
        output_truncated = False
        try:
            if os.path.exists(task.output_path):
                with open(task.output_path, "rb") as f:
                    raw_bytes = f.read()
                try:
                    from core.encoding_fix import fix_garbled_bytes

                    text, _, _ = fix_garbled_bytes(raw_bytes)
                except ImportError:
                    text = raw_bytes.decode("utf-8", errors="replace")
                if len(text) > 4000:
                    output_preview = text[-4000:]
                    output_truncated = True
                else:
                    output_preview = text
        except OSError:
            output_preview = "[unable to read output file]"

        return {
            "task": task.to_dict(),
            "output_preview": output_preview,
            "output_truncated": output_truncated,
        }

    def stop(self, task_id: str, reason: str = "Stopped by user") -> bool:
        """Stop a running background task.

        Sends SIGTERM (or taskkill on Windows), then force-kills after 5s.
        Returns True if task was found and stopped.
        """
        task = self.get_task(task_id)
        if task is None:
            return False
        if task.is_terminal:
            return False  # Already finished

        proc = None
        with self._lock:
            proc = self._processes.get(task_id)

        if proc is None:
            return False

        # Graceful terminate
        try:
            if os.name == "nt":
                run_subprocess(["taskkill", "/PID", str(proc.pid), "/T", "/F"], timeout=10)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

        with self._lock:
            t = self._tasks.get(task_id)
            if t:
                t.status = "stopped"
                t.stop_reason = reason
                t.terminal_reason = "stopped"
                t.finished_at = time.time()

        return True

    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Remove terminal tasks older than max_age_hours. Returns count removed."""
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        with self._lock:
            for tid in list(self._tasks.keys()):
                t = self._tasks[tid]
                if t.is_terminal and t.finished_at < cutoff:
                    del self._tasks[tid]
                    self._processes.pop(tid, None)
                    self._threads.pop(tid, None)
                    removed += 1
        return removed

    def shutdown(self) -> None:
        """Stop all running tasks and wait for threads."""
        with self._lock:
            for tid in list(self._tasks.keys()):
                t = self._tasks.get(tid)
                if t and not t.is_terminal:
                    self.stop(tid, "Shutdown")
        # Wait for threads
        with self._lock:
            for _tid, thread in list(self._threads.items()):
                if thread.is_alive():
                    thread.join(timeout=10)

    # ── Internal ──

    def _run_task(
        self,
        task_id: str,
        command: str,
        output_path: str,
        timeout: int,
        cwd: str | None,
    ) -> None:
        """Execute the command in a subprocess, capture output."""
        proc = None
        try:
            with open(output_path, "w", encoding="utf-8", errors="replace") as output_f:
                proc = subprocess.Popen(
                    command,
                    shell=True,  # nosec B602: intentional — runs user-facing background tasks
                    stdout=output_f,
                    stderr=subprocess.STDOUT,
                    cwd=cwd or os.getcwd(),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )

                with self._lock:
                    t = self._tasks.get(task_id)
                    if t:
                        t.pid = proc.pid or 0
                    self._processes[task_id] = proc

                try:
                    exit_code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                    with self._lock:
                        t = self._tasks.get(task_id)
                        if t:
                            t.status = "timed_out"
                            t.terminal_reason = "timed_out"
                            t.finished_at = time.time()
                    return

                with self._lock:
                    t = self._tasks.get(task_id)
                    if t:
                        t.exit_code = exit_code
                        t.status = "done" if exit_code == 0 else "failed"
                        t.finished_at = time.time()
        except (OSError, RuntimeError, ValueError) as e:
            with self._lock:
                t = self._tasks.get(task_id)
                if t:
                    t.status = "failed"
                    t.finished_at = time.time()
                    t.stop_reason = str(e)[:200]


# ── Module-level singleton ──

_bg_manager: BackgroundManager | None = None
_bg_lock = threading.Lock()


def get_background_manager() -> BackgroundManager:
    global _bg_manager
    if _bg_manager is None:
        with _bg_lock:
            if _bg_manager is None:
                _bg_manager = BackgroundManager()
                _atexit.register(_bg_manager.shutdown)
    return _bg_manager


def reset_background_manager() -> None:
    """Test isolation: aggressive shutdown and reset singleton.

    Guarantees a fresh singleton regardless of shutdown() success/failure.
    Clears all internal state and joins worker threads.
    """
    global _bg_manager
    old = _bg_manager
    if old is not None:
        with _bg_lock:
            try:
                old.shutdown()
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)
            old._tasks.clear()
            old._processes.clear()
            for t in getattr(old, "_threads", {}).values():
                try:
                    if t.is_alive():
                        t.join(timeout=1)
                except Exception:
                    logging.getLogger("crux").debug("silent except", exc_info=True)
            old._threads.clear()
    _bg_manager = None


# ── Tool definitions ──────────────────────────────────────────

BACKGROUND_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "task_launch",
            "description": (
                "启动后台任务执行 shell 命令。"
                "返回 task_id，可通过 task_list / task_output / task_stop 管理。"
                "适用于长时间运行的命令（构建、生成视频、下载等）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    },
                    "description": {
                        "type": "string",
                        "description": "简短描述（用于列表显示）",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时秒数，默认 600（10 分钟）",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录，默认当前目录",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": ("列出后台任务及其状态。默认只列出活跃（非终结）任务；传 active_only=false 可查看全部。"),
            "parameters": {
                "type": "object",
                "properties": {
                    "active_only": {
                        "type": "boolean",
                        "description": "是否只列出活跃任务，默认 true",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_output",
            "description": ("获取后台任务的输出快照。默认非阻塞（立即返回当前输出）；block=true 时等待任务完成。"),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "任务 ID",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "是否等待任务完成，默认 false",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "block=true 时的最大等待秒数，默认 30",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_stop",
            "description": "停止正在运行的后台任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "要停止的任务 ID",
                    },
                    "reason": {
                        "type": "string",
                        "description": "停止原因",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
]


# ── Executor functions ────────────────────────────────────────


def _exec_task_launch(**kwargs) -> str:
    mgr = get_background_manager()
    task = mgr.launch(
        command=kwargs["command"],
        description=kwargs.get("description", ""),
        timeout=kwargs.get("timeout", _DEFAULT_TIMEOUT),
        cwd=kwargs.get("cwd"),
    )
    return json.dumps(task.to_dict(), ensure_ascii=False)


def _exec_task_list(**kwargs) -> str:
    mgr = get_background_manager()
    active_only = kwargs.get("active_only", True)
    if isinstance(active_only, str):
        active_only = active_only.lower() not in ("false", "0", "no")
    tasks = mgr.list_tasks(active_only=active_only)
    if not tasks:
        return "暂无后台任务。"
    return json.dumps(
        [t.to_dict() for t in tasks],
        ensure_ascii=False,
        indent=2,
    )


def _exec_task_output(**kwargs) -> str:
    mgr = get_background_manager()
    block = kwargs.get("block", False)
    if isinstance(block, str):
        block = block.lower() in ("true", "1", "yes")
    timeout = kwargs.get("timeout", 30)

    result = mgr.get_output(
        task_id=kwargs["task_id"],
        block=block,
        timeout=timeout,
    )

    if result["task"] is None:
        return f"[错误] 任务未找到: {kwargs['task_id']}"

    task = result["task"]
    lines = [
        f"任务: {task['id']}",
        f"状态: {task['status']}",
        f"描述: {task.get('description', '')}",
        f"耗时: {task.get('elapsed', 0)}s",
    ]
    if task.get("exit_code") is not None:
        lines.append(f"退出码: {task['exit_code']}")
    if task.get("stop_reason"):
        lines.append(f"停止原因: {task['stop_reason']}")
    if task.get("terminal_reason"):
        lines.append(f"终结原因: {task['terminal_reason']}")

    output = result.get("output_preview", "")
    truncated = result.get("output_truncated", False)

    if output:
        lines.append("\n--- 输出预览 ---")
        lines.append(output)
        if truncated:
            lines.append("\n[输出已截断，完整日志见 output/background/]")

    return "\n".join(lines)


def _exec_task_stop(**kwargs) -> str:
    mgr = get_background_manager()
    ok = mgr.stop(
        task_id=kwargs["task_id"],
        reason=kwargs.get("reason", "Stopped by user"),
    )
    if ok:
        return f"任务 {kwargs['task_id']} 已停止。"
    return f"任务 {kwargs['task_id']} 未找到或已结束。"


BACKGROUND_EXECUTOR_MAP = {
    "task_launch": _exec_task_launch,
    "task_list": _exec_task_list,
    "task_output": _exec_task_output,
    "task_stop": _exec_task_stop,
}
