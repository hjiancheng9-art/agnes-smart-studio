"""
Confirm Manager — TUI confirm 超时/取消/默认策略
=================================================
解决 confirm 弹窗不响应导致 agent 死等问题。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConfirmResult(str, Enum):
    CONFIRMED = "confirmed"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ConfirmRequest:
    """确认请求"""

    tool: str
    message: str
    confirm_id: str = ""
    detail: str = ""
    risk: str = "medium"  # low / medium / high / critical
    timeout_seconds: float = 30.0
    default_action: str = "deny"  # deny / allow / abort
    created_at: float = 0.0
    result: ConfirmResult | None = None
    responded_at: float = 0.0
    _future: asyncio.Future | None = None

    def __post_init__(self):
        if not self.confirm_id:
            self.confirm_id = f"cfm_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.time()

    @property
    def is_resolved(self) -> bool:
        return self.result is not None

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    @property
    def remaining(self) -> float:
        return max(0, self.timeout_seconds - self.elapsed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirm_id": self.confirm_id,
            "tool": self.tool,
            "message": self.message,
            "detail": self.detail[:200],
            "risk": self.risk,
            "timeout_seconds": self.timeout_seconds,
            "remaining": round(self.remaining, 1),
            "default_action": self.default_action,
        }


class ConfirmManager:
    """确认管理器 — 超时自动降级，防止死等"""

    def __init__(self, default_timeout: float = 30.0, default_action: str = "deny"):
        self.default_timeout = default_timeout
        self.default_action = default_action
        self._pending: dict[str, ConfirmRequest] = {}

    def create(
        self,
        tool: str,
        message: str,
        detail: str = "",
        risk: str = "medium",
        timeout_seconds: float | None = None,
        default_action: str | None = None,
    ) -> ConfirmRequest:
        """创建确认请求"""
        req = ConfirmRequest(
            tool=tool,
            message=message,
            detail=detail,
            risk=risk,
            timeout_seconds=timeout_seconds or self.default_timeout,
            default_action=default_action or self.default_action,
        )
        try:
            loop = asyncio.get_running_loop()
            req._future = loop.create_future()
        except RuntimeError:
            req._future = None  # will be set when wait() is called
        self._pending[req.confirm_id] = req
        return req

    async def wait(self, confirm_id: str, on_timeout: str | None = None) -> tuple[ConfirmResult, str]:
        """等待确认结果，带超时自动降级

        Returns:
            (ConfirmResult, reason_string)
        """
        req = self._pending.get(confirm_id)
        if not req:
            return (ConfirmResult.CANCELLED, "confirm not found")

        if req.is_resolved:
            return (req.result or ConfirmResult.CANCELLED, "already resolved")

        try:
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            req._future = future

            result = await asyncio.wait_for(future, timeout=req.timeout_seconds)
            return (ConfirmResult.CONFIRMED if result else ConfirmResult.DENIED, "")
        except asyncio.TimeoutError:
            req.result = ConfirmResult.TIMEOUT
            req.responded_at = time.time()
            action = on_timeout or req.default_action
            logger.warning(f"ConfirmManager: {confirm_id} timed out, default={action}")
            if action == "allow":
                return (ConfirmResult.TIMEOUT, "超时，默认允许")
            return (ConfirmResult.TIMEOUT, f"超时 {req.timeout_seconds:.0f}s，已拒绝")

    def respond(self, confirm_id: str, confirmed: bool) -> bool:
        """响应用户确认"""
        req = self._pending.get(confirm_id)
        if not req:
            return False
        if req.is_resolved:
            return False
        req.result = ConfirmResult.CONFIRMED if confirmed else ConfirmResult.DENIED
        req.responded_at = time.time()
        if req._future:
            req._future.set_result(confirmed)
        return True

    def cancel(self, confirm_id: str) -> bool:
        """取消确认"""
        req = self._pending.get(confirm_id)
        if not req:
            return False
        req.result = ConfirmResult.CANCELLED
        if req._future and not req._future.done():
            req._future.set_result(False)
        return True

    def cancel_all(self) -> int:
        """取消所有挂起确认"""
        count = 0
        for confirm_id in list(self._pending.keys()):
            if self.cancel(confirm_id):
                count += 1
        return count

    def get_pending(self) -> list[ConfirmRequest]:
        return [r for r in self._pending.values() if not r.is_resolved]

    def get(self, confirm_id: str) -> ConfirmRequest | None:
        return self._pending.get(confirm_id)

    def cleanup(self, max_age: float = 300) -> int:
        """清理过期确认"""
        now = time.time()
        to_remove = [cid for cid, r in self._pending.items() if r.is_resolved and now - r.responded_at > max_age]
        for cid in to_remove:
            del self._pending[cid]
        return len(to_remove)


# ── 全局单例 ──
_confirm_manager: ConfirmManager | None = None


def get_confirm_manager() -> ConfirmManager:
    global _confirm_manager
    if _confirm_manager is None:
        _confirm_manager = ConfirmManager()
    return _confirm_manager
