"""
Base Runtime — 所有能力运行时的基类
======================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityRuntimeType(str, Enum):
    GENERAL = "general"
    DEBUG_ANALYZE = "debug_analyze"
    CODE_PATCH = "code_patch"
    ARCHITECTURE = "architecture"
    RESEARCH = "research"
    CREATIVE = "creative"
    SECURITY = "security"

    @classmethod
    def from_mode(cls, mode: str) -> CapabilityRuntimeType:
        """从 IntelligenceMode 映射到 Runtime 类型"""
        mapping = {
            "FAST": cls.GENERAL,
            "BALANCED": cls.GENERAL,
            "DEEP": cls.GENERAL,  # 实际由 router 细分
            "SAFE": cls.SECURITY,
            "RESEARCH": cls.RESEARCH,
            "CREATIVE": cls.CREATIVE,
        }
        return mapping.get(mode, cls.GENERAL)


class RuntimeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class RuntimeContext:
    """运行时上下文"""

    request: str
    mode: str = "BALANCED"
    runtime_type: CapabilityRuntimeType = CapabilityRuntimeType.GENERAL
    files: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    # 可选运行时依赖（由上层注入）
    toolbus: Any = None
    budget: Any = None
    guard: Any = None
    trace_store: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request[:100],
            "mode": self.mode,
            "runtime_type": self.runtime_type.value,
            "file_count": len(self.files),
        }


class BaseRuntime:
    """所有 Runtime 的基类"""

    def __init__(self, name: str):
        self.name = name
        self._status = RuntimeStatus.PENDING

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        """执行运行时逻辑（子类重写）"""
        raise NotImplementedError

    def can_handle(self, request: str, mode: str) -> bool:
        """判断是否能处理该请求（子类重写）"""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status.value}
