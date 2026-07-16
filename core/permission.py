"""Permission mode system — YOLO / AUTO / MANUAL tiered approval.

移植自 Kimi Code CLI 的权限分级理念：
  YOLO:  所有工具直接执行，无需确认
  AUTO:  仅高危工具（HIGH_RISK_TOOLS）需要确认
  MANUAL: 所有写操作类工具都需要确认

与 core/constraints.py 共享 HIGH_RISK_TOOLS / is_tool_high_risk() 作为
判断基础，不重复定义规则。
"""

from __future__ import annotations

import enum
import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.permission")


class PermissionMode(enum.Enum):
    YOLO = "yolo"
    AUTO = "auto"
    MANUAL = "manual"


class PermissionManager:
    """统一权限管理器 — 三级模式 + 记忆化确认。

    用法:
        pm = get_permission_manager()
        pm.set_mode(PermissionMode.AUTO)
        if pm.needs_confirmation("git_push", {"force": True}):
            # 需要用户确认
            ...
    """

    def __init__(self) -> None:
        self._mode: PermissionMode = PermissionMode.AUTO
        self._lock = threading.Lock()
        # 记忆化确认: tool_name → bool（True=已确认，跳过后续询问）
        # key: tool_name 或 f"{tool_name}:{operation_hash}"
        self._remembered: dict[str, bool] = {}
        # 手动确认钩子（CLI/UI 注入）
        self._confirm_hook: Callable[[str, dict], bool] | None = None
        # 模式变更回调
        self._on_mode_change: Callable[[PermissionMode], None] | None = None

    # ── 模式管理 ──

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def set_mode(self, mode: PermissionMode) -> None:
        with self._lock:
            old = self._mode
            self._mode = mode
        if old != mode and self._on_mode_change:
            self._on_mode_change(mode)

    def get_mode_name(self) -> str:
        return self._mode.value

    # ── 确认判断 ──

    def needs_confirmation(self, tool_name: str, args: dict | None = None) -> bool:
        """判断工具调用是否需要用户确认。

        Args:
            tool_name: 工具名
            args: 工具参数（可选，用于危险参数检测）

        Returns:
            True 表示需要确认，False 表示可直接执行。
        """
        args = args or {}

        # YOLO 模式：永不确认
        if self._mode == PermissionMode.YOLO:
            return False

        # 检查记忆化确认（同一工具已确认过）
        with self._lock:
            if self._remembered.get(tool_name):
                return False

        from core.constraints import CONFIRMABLE_TOOLS, is_tool_high_risk

        if self._mode == PermissionMode.AUTO:
            # AUTO：仅高危工具需要确认
            return is_tool_high_risk(tool_name, args)

        if self._mode == PermissionMode.MANUAL:
            # MANUAL：所有写入类工具都需要确认
            if tool_name in CONFIRMABLE_TOOLS:
                return True
            # 非写入工具但可能是高危
            return is_tool_high_risk(tool_name, args)

        return False

    # ── 确认钩子 ──

    def set_confirm_hook(self, hook: Callable[[str, dict], bool] | None) -> None:
        """注入确认钩子（CLI/UI 层调用）。

        hook(tool_name, args) → True=用户同意, False=拒绝
        """
        self._confirm_hook = hook

    def request_confirmation(self, tool_name: str, args: dict) -> bool:
        """通过钩子请求用户确认。无钩子时默认拒绝（安全优先）。"""
        if self._confirm_hook:
            return self._confirm_hook(tool_name, args)
        # 无钩子时打印警告并拒绝
        logger.warning("工具 '%s' 需要确认，但无确认钩子注入。已拒绝。", tool_name)
        return False

    # ── 记忆化 ──

    def remember(self, tool_name: str, allowed: bool = True) -> None:
        """记住对某工具的确认决策（会话内有效）。"""
        with self._lock:
            self._remembered[tool_name] = allowed

    def forget(self, tool_name: str) -> None:
        """清除对某工具的记忆。"""
        with self._lock:
            self._remembered.pop(tool_name, None)

    def forget_all(self) -> None:
        with self._lock:
            self._remembered.clear()

    # ── 模式变更回调 ──

    def on_mode_change(self, callback: Callable[[PermissionMode], None] | None) -> None:
        self._on_mode_change = callback

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self._mode.value,
                "remembered_count": len(self._remembered),
            }


# ── 模块级单例 ──

_permission_manager: PermissionManager | None = None
_pm_lock = threading.Lock()


def get_permission_manager() -> PermissionManager:
    global _permission_manager
    if _permission_manager is None:
        with _pm_lock:
            if _permission_manager is None:
                _permission_manager = PermissionManager()
    return _permission_manager


def reset_permission_manager() -> None:
    """测试隔离用：重置单例。"""
    global _permission_manager
    _permission_manager = None
