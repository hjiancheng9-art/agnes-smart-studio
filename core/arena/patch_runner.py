"""
Patch Runner — 在沙箱中运行补丁并收集结果
============================================
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .schemas import ArenaPatch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.routing_signals import SIGNAL_REGISTRY

logger = logging.getLogger(__name__)


class PatchRunner:
    """补丁运行器 — 在隔离沙箱中应用并测试补丁"""

    def __init__(self):
        self._signal_backups: dict[str, float] = {}
        self._sandbox_active = False

    def apply_patch(self, patch: ArenaPatch) -> bool:
        """在沙箱中应用补丁"""
        self._sandbox_active = True
        patch_dict = patch.patch

        if patch_dict.get("type") == "signal_weight_adjust":
            return self._apply_signal_adjustment(patch_dict.get("target_signals", []))

        if patch_dict.get("type") == "signal_weight_direct":
            return self._apply_direct_weight(patch_dict)

        return False

    def _apply_signal_adjustment(self, adjustments: list[dict[str, Any]]) -> bool:
        applied = False
        for adj in adjustments:
            signal_name = adj.get("signal", "")
            action = adj.get("action", "")
            delta = adj.get("delta", 0.0)

            for entry in SIGNAL_REGISTRY:
                if entry.name == signal_name:
                    # 备份原始权重
                    if signal_name not in self._signal_backups:
                        self._signal_backups[signal_name] = entry.weight

                    if action == "increase":
                        entry.weight += delta
                    elif action == "decrease":
                        entry.weight = max(1.0, entry.weight - delta)
                    applied = True
                    logger.info(f"PatchRunner: 调整信号 '{signal_name}' → {entry.weight}")
                    break

        return applied

    def _apply_direct_weight(self, patch: dict[str, Any]) -> bool:
        signal_name = patch.get("signal_name", "")
        new_weight = patch.get("new_weight", 1.0)

        for entry in SIGNAL_REGISTRY:
            if entry.name == signal_name:
                if signal_name not in self._signal_backups:
                    self._signal_backups[signal_name] = entry.weight
                entry.weight = new_weight
                logger.info(f"PatchRunner: 直接设置信号 '{signal_name}' → {new_weight}")
                return True

        return False

    def rollback(self) -> int:
        """回滚所有修改"""
        count = 0
        for name, original_weight in self._signal_backups.items():
            for entry in SIGNAL_REGISTRY:
                if entry.name == name:
                    entry.weight = original_weight
                    count += 1
                    break
        self._signal_backups.clear()
        self._sandbox_active = False
        logger.info(f"PatchRunner: 回滚 {count} 个信号权重")
        return count

    def is_sandbox_active(self) -> bool:
        return self._sandbox_active
