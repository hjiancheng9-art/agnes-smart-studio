"""
TUI Confirm Bridge — TUI confirm 结果回传到后端 ConfirmManager
===============================================================
解决：TUI 显示 confirm 弹窗但结果不回传，后端死等 timeout。
"""

from __future__ import annotations

import logging
from typing import Any

from core.confirm_manager import ConfirmManager, ConfirmResult, get_confirm_manager

logger = logging.getLogger(__name__)


class ConfirmBridge:
    """确认桥接 — 连接 TUI confirm 弹窗和后端 ConfirmManager"""

    def __init__(self, confirm_manager: ConfirmManager | None = None):
        self.confirm_manager = confirm_manager or get_confirm_manager()

    def resolve(self, confirm_id: str, approved: bool) -> bool:
        """TUI 侧调用：用户点了确认/拒绝"""
        success = self.confirm_manager.respond(confirm_id, approved)
        if success:
            logger.info(f"ConfirmBridge: {confirm_id} resolved -> {'approved' if approved else 'denied'}")
        else:
            logger.warning(f"ConfirmBridge: {confirm_id} not found or already resolved")
        return success

    def cancel(self, confirm_id: str) -> bool:
        """TUI 侧调用：用户关闭弹窗"""
        return self.confirm_manager.cancel(confirm_id)

    def get_pending(self) -> list[dict[str, Any]]:
        """获取所有待处理的确认（供 TUI 渲染）"""
        return [req.to_dict() for req in self.confirm_manager.get_pending()]

    def auto_deny_timeout(self, confirm_id: str) -> dict[str, Any]:
        """超时自动拒绝（返回处理结果供 TUI 更新 UI）"""
        import asyncio

        try:
            result, reason = asyncio.run(self.confirm_manager.wait(confirm_id))
            return {
                "confirm_id": confirm_id,
                "result": result.value,
                "reason": reason,
                "approved": result == ConfirmResult.CONFIRMED,
            }
        except Exception as e:
            return {
                "confirm_id": confirm_id,
                "result": "error",
                "reason": str(e),
                "approved": False,
            }
