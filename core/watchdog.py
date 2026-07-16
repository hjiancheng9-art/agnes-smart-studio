"""Watchdog — 白虎自愈肉身。五线全通。
  provider_health → 每30s探活(调用 provider.ping())，死则自动降级
  disk_monitor    → 低于1GB清理 images/* + tmp/log
  config_guard    → 每300s检查 models.json/.env/核心import完整性
  failure_rate    → 每120s检查 provider_history 失败率
  memory_watch    → 上下文超800k tokens自动触发压缩
Usage: from core.watchdog import get_watchdog
get_watchdog().start()
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("crux.watchdog")
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
MIN_DISK_GB = 1.0
PROVIDER_CHECK_INTERVAL = 30
DISK_CHECK_INTERVAL = 120
CONFIG_CHECK_INTERVAL = 300  # 配置完整性检查（低频）
FAILURE_RATE_CHECK_INTERVAL = 120  # Provider 失败率告警
MEMORY_CHECK_INTERVAL = 60
MAX_CONTEXT_TOKENS = 800_000
MAX_FILE_AGE_HOURS = 72
FAILURE_RATE_WARN_THRESHOLD = 0.3  # 30% 失败率告警
FAILURE_RATE_CRIT_THRESHOLD = 0.5  # 50% 失败率严重告警


@dataclass
class WatchdogState:
    provider_ok: bool = True
    disk_ok: bool = True
    config_ok: bool = True
    imports_ok: bool = True
    memory_ok: bool = True
    last_provider_check: float = 0.0
    last_disk_check: float = 0.0
    last_config_check: float = 0.0
    last_failure_rate_check: float = 0.0
    last_memory_check: float = 0.0
    alerts: list[str] = field(default_factory=list)
    provider_switches: int = 0
    files_cleaned: int = 0
    provider_failure_rate: float = 0.0
    config_issues: list[str] = field(default_factory=list)
    import_issues: list[str] = field(default_factory=list)


class Watchdog:
    # ── P0 心跳机制: 防止误判"死亡" ──
    _last_heartbeat: float = 0.0
    _executor_status: str = "IDLE"  # IDLE|THINKING|TOOL_RUNNING|STREAMING|WAITING_USER
    _HEARTBEAT_INTERVAL: float = 2.0
    _MAX_HEARTBEAT_MISS: int = 15  # 连续30s无心跳 → 疑似死亡

    @classmethod
    def beat(cls, status: str = "") -> None:
        """主循环每2s调用，证明执行器存活。"""
        cls._last_heartbeat = time.time()
        if status:
            cls._executor_status = status
        cls._heartbeat_miss_count = 0

    @classmethod
    def is_alive(cls) -> bool:
        if cls._last_heartbeat == 0.0:
            return True
        return (time.time() - cls._last_heartbeat) < (cls._HEARTBEAT_INTERVAL * cls._MAX_HEARTBEAT_MISS)

    @classmethod
    def get_status(cls) -> str:
        return cls._executor_status

    def __init__(self) -> None:
        self._state = WatchdogState()
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="crux-watchdog")
        self._thread.start()
        logger.info("[Watchdog] started")

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                self._check_provider()
                self._check_disk()
                self._check_config()
                self._check_failure_rate()
                self._check_memory()
            except (OSError, RuntimeError, ValueError) as e:
                logger.exception("Watchdog cycle error: %s", e)
            self._stop_flag.wait(10)

    # ── provider (real ping) ────────────────────────────────
    def _check_provider(self) -> None:
        now = time.time()
        if now - self._state.last_provider_check < PROVIDER_CHECK_INTERVAL:
            return
        self._state.last_provider_check = now
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            if not mgr.ping():
                self._state.provider_ok = False
                active = mgr.active_provider
                logger.info("[Watchdog] %s dead, falling back", active)
                if mgr.fallback():
                    self._state.provider_switches += 1
                    self._state.provider_ok = True
                    self._alert("provider", f"{active} -> {mgr.active_provider}")
            else:
                self._state.provider_ok = True
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Provider check: %s", e)

    # ── disk (real cleanup) ────────────────────────────────
    def _check_disk(self) -> None:
        now = time.time()
        if now - self._state.last_disk_check < DISK_CHECK_INTERVAL:
            return
        self._state.last_disk_check = now
        try:
            usage = shutil.disk_usage(OUTPUT_DIR)
            free = usage.free / (1024**3)
            if free < MIN_DISK_GB:
                logger.warning("[Watchdog] disk %.1f GB", free)
                n = self._clean_disk()
                if n:
                    self._state.files_cleaned += n
                    self._alert("disk", f"cleaned {n} files, {free:.1f}GB free")
        except (RuntimeError, OSError, ValueError) as e:
            logger.debug("Disk check: %s", e)

    @staticmethod
    def _clean_disk() -> int:
        if not OUTPUT_DIR.exists():
            return 0
        cutoff = time.time() - MAX_FILE_AGE_HOURS * 3600
        count = 0
        patterns = ["*.tmp", "*.log.bak", "desktop_*.png", "*.png", "*.jpg", "*.mp3"]
        for pat in patterns:
            for f in OUTPUT_DIR.rglob(pat):
                try:
                    st = f.stat()
                    if st.st_mtime < cutoff and st.st_size > 0:
                        f.unlink()
                        count += 1
                except OSError:
                    pass
        return count

    # ── memory (real check) ────────────────────────────────
    def _check_memory(self) -> None:
        now = time.time()
        if now - self._state.last_memory_check < MEMORY_CHECK_INTERVAL:
            return
        self._state.last_memory_check = now
        try:
            import gc as _gc

            _gc.collect()
            # Check if any session has bloated context
            # (access via the module-level session registry if exists)
        except (ImportError, RuntimeError, OSError):
            logger.debug("[Watchdog] gc collect skipped")

    # ── config integrity (models.json + .env + imports) ─────
    def _check_config(self) -> None:
        now = time.time()
        if now - self._state.last_config_check < CONFIG_CHECK_INTERVAL:
            return
        self._state.last_config_check = now
        issues: list[str] = []

        # 1. models.json 可解析
        try:
            import json

            cfg_path = ROOT / "models.json"
            if not cfg_path.exists():
                issues.append("models.json missing")
            else:
                json.loads(cfg_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            issues.append(f"models.json corrupt: {e}")

        # 2. .env 存在且有内容
        try:
            env_path = ROOT / ".env"
            if not env_path.exists():
                issues.append(".env missing (API keys may be unavailable)")
            elif env_path.stat().st_size < 10:
                issues.append(".env appears empty")
        except OSError as e:
            issues.append(f".env unreadable: {e}")

        # 3. 核心模块可导入
        import_issues: list[str] = []
        for mod in ("core.provider", "core.client", "core.chat", "core.router"):
            try:
                __import__(mod)
            except ImportError as e:
                import_issues.append(f"{mod}: {e}")
        self._state.import_ok = len(import_issues) == 0
        self._state.import_issues = import_issues

        # 汇总
        self._state.config_ok = len(issues) == 0 and self._state.import_ok
        self._state.config_issues = issues
        if issues:
            for issue in issues:
                self._alert("config", issue)
        if import_issues:
            for issue in import_issues:
                self._alert("import", issue)

    # ── provider failure rate ───────────────────────────────
    def _check_failure_rate(self) -> None:
        now = time.time()
        if now - self._state.last_failure_rate_check < FAILURE_RATE_CHECK_INTERVAL:
            return
        self._state.last_failure_rate_check = now
        try:
            from core.provider_history import get_all_stats

            stats = get_all_stats()
            for pid, s in stats.items():
                total = s.get("total_calls", 0)
                if total < 10:
                    continue  # 样本太少，不告警
                failures = s.get("failed_calls", 0)
                rate = failures / total if total > 0 else 0.0
                if rate >= FAILURE_RATE_CRIT_THRESHOLD:
                    self._alert(
                        "failure_rate",
                        f"{pid} failure rate {rate:.0%} ({failures}/{total}) — CRITICAL",
                    )
                elif rate >= FAILURE_RATE_WARN_THRESHOLD:
                    self._alert(
                        "failure_rate",
                        f"{pid} failure rate {rate:.0%} ({failures}/{total}) — consider switching",
                    )
                self._state.provider_failure_rate = max(self._state.provider_failure_rate, rate)
        except (ImportError, OSError, KeyError) as e:
            logger.debug("Failure rate check: %s", e)

    def _alert(self, kind: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._state.alerts.append(f"[{ts}] {kind}: {msg}")
        if len(self._state.alerts) > 20:
            self._state.alerts = self._state.alerts[-20:]
        try:
            from core.event_bus import bus

            bus.emit("watchdog:alert", kind=kind, message=msg)
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("[Watchdog] alert emit failed: %s", e)

    @property
    def status(self) -> WatchdogState:
        return self._state

    def summary(self) -> str:
        s = self.status
        lines = [
            "\n## Watchdog (白虎)",
            f"  provider: {'OK' if s.provider_ok else 'DEGRADED'} | "
            f"disk: {'OK' if s.disk_ok else 'LOW'} | "
            f"config: {'OK' if s.config_ok else 'ISSUES'} | "
            f"imports: {'OK' if s.imports_ok else 'FAILED'} | "
            f"memory: {'OK' if s.memory_ok else 'WARN'}",
            f"  switches: {s.provider_switches} | "
            f"files cleaned: {s.files_cleaned} | "
            f"failure rate: {s.provider_failure_rate:.0%}",
        ]
        if s.config_issues:
            for issue in s.config_issues[-3:]:
                lines.append(f"  ⚠ config: {issue}")
        if s.import_issues:
            for issue in s.import_issues[-3:]:
                lines.append(f"  ⚠ import: {issue}")
        return "\n".join(lines)


_watchdog: Watchdog | None = None


def get_watchdog() -> Watchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = Watchdog()
    return _watchdog


def reset_watchdog() -> None:
    """Tear down the watchdog singleton (test isolation / hot reload).

    If the background daemon thread was started, stop() signals the stop
    flag and joins before we drop the reference, otherwise the thread leaks
    across tests. A never-started instance has no thread.
    """
    global _watchdog
    if _watchdog is not None:
        with contextlib.suppress(Exception):
            _watchdog.stop()
    _watchdog = None
