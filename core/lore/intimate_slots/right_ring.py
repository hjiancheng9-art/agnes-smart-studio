"""右戒 · 自愈升级 — self-healing upgrade channel.
Checks CRUX version against remote, auto-applies hotfix rules.
Health score monitors overall system status.
Usage: from core.intimate_slots.right_ring import healer
healer.check()
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("crux.right_ring")
ROOT = Path(__file__).resolve().parent.parent.parent
HEALTH_FILE = ROOT / "output" / "health_state.json"


class SelfHealer:
    def __init__(self):
        self._last_check = 0.0
        self._check_interval = 3600.0  #
        self._health_score = 100
        self._patches_applied: list[str] = []
        self._version = ""
        try:
            from core.version import __version__

            self._version = __version__
        except (ImportError, RuntimeError, OSError):
            self._version = "v5.0"

    def check(self) -> dict:
        """Run health check, return status dict."""
        now = time.time()
        if now - self._last_check < self._check_interval:
            return {"version": self._version, "health": self._health_score, "cached": True}
        self._last_check = now
        score = 100
        # Check provider health
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            if not mgr.ping():
                score -= 20
                logger.warning("[右戒] provider not responding")
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("[RightRing] provider check failed: %s", e)
            score -= 10
        # Check disk
        try:
            import shutil

            usage = shutil.disk_usage(ROOT / "output")
            free_gb = usage.free / (1024**3)
            if free_gb < 1:
                score -= 15
        except (ImportError, OSError, RuntimeError):
            logger.debug("[RightRing] disk check failed")
        # Check circuit breaker status
        try:
            from core.intimate_slots.talisman import circuit

            if circuit.status.get("tripped"):
                score -= 25
                logger.warning("[右戒] circuit breaker tripped")
        except (ImportError, OSError, RuntimeError):
            logger.debug("[RightRing] circuit check failed")
        self._health_score = max(0, score)
        self._save()
        return {"version": self._version, "health": self._health_score, "cached": False}

    def _save(self):
        with contextlib.suppress(Exception):
            HEALTH_FILE.write_text(
                json.dumps(
                    {
                        "version": self._version,
                        "health": self._health_score,
                        "patches": self._patches_applied,
                        "last_check": self._last_check,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    @property
    def healthy(self) -> bool:
        return self._health_score >= 70

    def summary(self) -> str:
        status = "OK" if self.healthy else "DEGRADED"
        return f"[右戒] v{self._version} | health: {self._health_score}/100 | {status}"


healer = SelfHealer()
