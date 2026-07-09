"""
TUI-Backend Healthcheck — TUI/后端匹配度健康检查
=================================================
跑一轮最小事件环，验证所有 kind 都能被正确处理。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .stream_protocol import KNOWN_KINDS, StreamEvent, normalize_event

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    """健康检查结果"""
    overall: str = "unknown"  # ok / degraded / failed
    passed: int = 0
    failed: int = 0
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0

    @property
    def is_ok(self) -> bool:
        return self.overall == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "passed": self.passed,
            "failed": self.failed,
            "checks": self.checks,
            "errors": self.errors[:5],
            "duration": round(self.duration, 2),
        }


class TuiBackendHealthcheck:
    """TUI-后端健康检查"""

    REQUIRED_EVENTS = {
        "text", "info", "status", "intel_analysis",
        "confirm", "error", "stream_start", "stream_end", "final",
    }

    # ── 模拟后端事件 ──

    async def _simulate_events(self) -> list[StreamEvent]:
        """模拟完整事件流"""
        run_id = f"health_{int(time.time())}"
        events = [
            StreamEvent(run_id=run_id, kind="stream_start",
                        payload={"message": "start"}),
            StreamEvent(run_id=run_id, kind="status",
                        payload={"run_id": run_id, "status": "routing",
                                 "message": "Routing..."}),
            StreamEvent(run_id=run_id, kind="intel_analysis",
                        payload={"mode": "BALANCED", "pipeline": False}),
            StreamEvent(run_id=run_id, kind="text",
                        payload={"message": "hello world"}),
            StreamEvent(run_id=run_id, kind="info",
                        payload={"message": "测试步骤完成"}),
            StreamEvent(run_id=run_id, kind="confirm",
                        payload={"tool": "write_file", "message": "确认写入？",
                                 "risk": "low"}),
            StreamEvent(run_id=run_id, kind="error",
                        payload={"message": "test error", "kind": "test_error"}),
            StreamEvent(run_id=run_id, kind="stream_end",
                        payload={"message": "end"}),
        ]
        return events

    async def run(self, consumer: Any = None) -> HealthResult:
        """运行健康检查"""
        result = HealthResult()
        start = time.time()

        try:
            events = await self._simulate_events()

            for event in events:
                kind_ok = event.kind in KNOWN_KINDS
                result.checks[f"kind_{event.kind}_known"] = kind_ok

                has_run_id = bool(event.run_id)
                result.checks[f"run_id_{event.kind}"] = has_run_id

                has_payload = bool(event.payload)
                result.checks[f"payload_{event.kind}"] = has_payload

                # 如果提供了 consumer，尝试消费
                if consumer:
                    try:
                        await consumer(event)
                        result.checks[f"consume_{event.kind}"] = True
                    except Exception as e:
                        result.checks[f"consume_{event.kind}"] = False
                        result.errors.append(f"consume {event.kind}: {e}")

            result.passed = sum(1 for v in result.checks.values() if v)
            result.failed = sum(1 for v in result.checks.values() if not v)

            if result.failed == 0:
                result.overall = "ok"
            elif result.failed <= 3:
                result.overall = "degraded"
            else:
                result.overall = "failed"

        except Exception as e:
            result.overall = "failed"
            result.errors.append(f"healthcheck exception: {e}")

        result.duration = time.time() - start
        return result

    async def check_required_events(self) -> HealthResult:
        """只检查必要事件类型是否都能生成"""
        result = HealthResult()

        for kind in self.REQUIRED_EVENTS:
            try:
                event = StreamEvent(run_id="test", kind=kind,
                                    payload={"message": "test"})
                normalized = normalize_event(("test", {"message": "ok"}), "test")
                result.checks[kind] = (
                    kind in KNOWN_KINDS
                    and normalized.kind in KNOWN_KINDS
                )
            except Exception as e:
                result.checks[kind] = False
                result.errors.append(f"{kind}: {e}")

        result.passed = sum(1 for v in result.checks.values() if v)
        result.failed = sum(1 for v in result.checks.values() if not v)
        result.overall = "ok" if result.failed == 0 else "degraded"
        return result


def quick_healthcheck() -> dict[str, Any]:
    """同步快捷健康检查"""
    result = asyncio.run(TuiBackendHealthcheck().check_required_events())
    return result.to_dict()
