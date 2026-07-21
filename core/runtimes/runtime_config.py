"""
Runtime Config — CRUX Capability Runtime 灰度发布控制
=====================================================
控制 7 个 Runtime 的启停，先开低风险 Runtime，逐步放量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeConfig:
    """Runtime 灰度发布配置"""

    enabled: bool = True
    rollout: dict[str, bool] = field(
        default_factory=lambda: {
            "general": True,
            "debug_analyze": True,
            "architecture": True,
            "creative": True,
            "research": True,
            "code_patch": False,
            "security": False,
        }
    )

    def is_runtime_enabled(self, name: str) -> bool:
        """检查某个 Runtime 是否启用"""
        return self.enabled and self.rollout.get(name, False)

    def enable(self, name: str) -> None:
        if name in self.rollout:
            self.rollout[name] = True

    def disable(self, name: str) -> None:
        if name in self.rollout:
            self.rollout[name] = False

    def get_active(self) -> list[str]:
        return [k for k, v in self.rollout.items() if v]

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "rollout": dict(self.rollout),
            "active_count": len(self.get_active()),
        }
