"""左戒 · 遥测日志 — structured telemetry & audit trail.
Every tool call, every error, every latency spike logged.
Rotating log, structured JSON, auto-summary.
Usage: from core.intimate_slots.left_ring import telemetry
telemetry.log(...)
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent
TELEM_FILE = ROOT / "output" / "telemetry.jsonl"
MAX_RECENT = 100


@dataclass
class TelemetryRecord:
    ts: float = 0
    event: str = ""
    tool: str = ""
    latency: float = 0
    error: str = ""
    provider: str = ""
    tokens: int = 0


class Telemetry:
    def __init__(self):
        self._recent: deque[TelemetryRecord] = deque(maxlen=MAX_RECENT)
        self._counts: dict[str, int] = {"calls": 0, "errors": 0, "tokens": 0}

    def log(self, event: str, tool: str = "", latency: float = 0, error: str = "", provider: str = "", tokens: int = 0):
        rec = TelemetryRecord(
            ts=time.time(), event=event, tool=tool, latency=latency, error=error, provider=provider, tokens=tokens
        )
        self._recent.append(rec)
        self._counts["calls"] += 1
        if error:
            self._counts["errors"] += 1
        self._counts["tokens"] += tokens
        try:
            with open(TELEM_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec.__dict__, ensure_ascii=False) + "\n")
        except (ImportError, OSError, RuntimeError):
            logger.debug("[LeftRing] telem write failed")

    @property
    def error_rate(self) -> float:
        total = self._counts["calls"]
        return self._counts["errors"] / total if total else 0

    @property
    def avg_latency(self) -> float:
        latencies = [r.latency for r in self._recent if r.latency > 0]
        return sum(latencies) / len(latencies) if latencies else 0

    def recent_errors(self, n: int = 5) -> list[dict]:
        return [r.__dict__ for r in self._recent if r.error][-n:]

    def summary(self) -> str:
        return f"[左戒] {self._counts['calls']} calls | {self._counts['errors']} errors ({self.error_rate:.1%}) | {self.avg_latency:.2f}s avg"


telemetry = Telemetry()
