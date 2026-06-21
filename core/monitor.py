"""Runtime health monitor and data hygiene — proactive system maintenance.

HealthMonitor: records API/tool metrics, triggers alerts on threshold breach.
DataHygiene: automatic rotation of cost_log, history, and stale file cleanup.
"""

import json
import time
import shutil
from pathlib import Path
from collections import deque

__all__ = [
    'DataHygiene', 'HealthMonitor', 'ROOT', 'get_monitor', 'hygiene_run',
]

ROOT = Path(__file__).resolve().parent.parent


class HealthMonitor:
    """Lightweight runtime health tracker with threshold-based alerts."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.api_calls: deque = deque(maxlen=100)
        self.tool_calls: deque = deque(maxlen=100)
        self.alerts: list[dict] = []

    def record_api_call(self, model: str, latency: float, error: str | None = None):
        self.api_calls.append({
            "ts": time.time(), "model": model,
            "latency": round(latency, 3), "error": error,
        })
        self._check_api_health()

    def record_tool_call(self, tool: str, success: bool, latency: float,
                         error: str | None = None):
        self.tool_calls.append({
            "ts": time.time(), "tool": tool,
            "success": success, "latency": round(latency, 3), "error": error,
        })
        self._check_tool_health()

    def _check_api_health(self):
        recent = [c for c in self.api_calls if time.time() - c["ts"] < 300]
        if len(recent) >= 10:
            errors = sum(1 for c in recent if c["error"])
            if errors / len(recent) > 0.5:
                self._alert("api_error_rate",
                    f"{errors}/{len(recent)} API calls failed in last 5 min")

    def _check_tool_health(self):
        recent = [c for c in self.tool_calls if time.time() - c["ts"] < 300]
        if len(recent) >= 10:
            errors = sum(1 for c in recent if not c["success"])
            if errors / len(recent) > 0.5:
                failing = {c["tool"] for c in recent if not c["success"]}
                self._alert("tool_error_rate",
                    f"Tools failing: {', '.join(failing)}")

    def _alert(self, kind: str, message: str):
        self.alerts.append({"ts": time.time(), "kind": kind, "message": message})

    def health_report(self) -> dict:
        recent_api = [c for c in self.api_calls if time.time() - c["ts"] < 300]
        recent_tool = [c for c in self.tool_calls if time.time() - c["ts"] < 300]
        return {
            "api_calls_recent": len(recent_api),
            "api_error_rate": sum(1 for c in recent_api if c["error"]) / max(len(recent_api), 1),
            "tool_calls_recent": len(recent_tool),
            "tool_error_rate": sum(1 for c in recent_tool if not c["success"]) / max(len(recent_tool), 1),
            "alerts": self.alerts[-5:],
        }

    def is_healthy(self) -> bool:
        report = self.health_report()
        return report["api_error_rate"] < 0.3 and report["tool_error_rate"] < 0.3


# Global singleton
_monitor = HealthMonitor()


def get_monitor() -> HealthMonitor:
    return _monitor


class DataHygiene:
    """Automatic rotation and cleanup of data files."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT

    def run(self) -> dict:
        results = {}
        for method in [self._rotate_cost_log, self._rotate_history,
                       self._clean_stale_backups, self._clean_trash_files]:
            name = method.__name__
            try:
                results[name] = method()
            except (OSError, ValueError, RuntimeError) as e:
                results[name] = f"error: {e}"
        return results

    def _rotate_cost_log(self) -> str:
        p = self.root / "output" / "cost_log.jsonl"
        if not p.exists():
            return "not found"
        sz = p.stat().st_size
        if sz > 500_000:  # 500KB
            bak = self.root / "output" / f"cost_log.{int(time.time())}.jsonl.bak"
            shutil.copy2(p, bak)
            lines = p.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) > 5000:
                kept = lines[-2000:]
                p.write_text("\n".join(kept) + "\n", encoding="utf-8")
                return f"rotated: kept {len(kept)} of {len(lines)} lines"
            return "oversized but few lines"
        return f"{sz/1024:.0f}KB OK"

    def _rotate_history(self) -> str:
        p = self.root / "output" / "history.json"
        if not p.exists():
            return "not found"
        sz = p.stat().st_size
        if sz > 5_000_000:
            bak = self.root / "output" / f"history.{int(time.time())}.json.bak"
            shutil.copy2(p, bak)
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) > 1000:
                    data = data[-1000:]
                    p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
                    return f"rotated: kept {len(data)} records"
            except (json.JSONDecodeError, TypeError, KeyError):
                return "rotation failed (invalid JSON)"
            return "oversized but kept"
        return f"{sz/1048576:.1f}MB OK"

    def _clean_stale_backups(self) -> str:
        removed = 0
        cutoff = time.time() - 7 * 86400  # 7 days
        for bak in self.root.rglob("*.bak"):
            try:
                if bak.stat().st_mtime < cutoff:
                    bak.unlink()
                    removed += 1
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return f"removed {removed} stale backups"

    def _clean_trash_files(self) -> str:
        removed = 0
        for trash_name in ("{is_prime(n)}')",):
            p = self.root / trash_name
            if p.exists():
                try:
                    p.unlink()
                    removed += 1
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        return f"removed {removed} trash files"


def hygiene_run() -> dict:
    return DataHygiene().run()