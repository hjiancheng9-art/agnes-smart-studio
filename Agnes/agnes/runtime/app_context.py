"""应用上下文 — 跨 Feature 共享的状态和依赖。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agnes.client import AgnesClient, AgnesConfig
from agnes.runtime.theme import Theme


@dataclass
class AppContext:
    """应用级共享上下文。

    - client: 全局唯一的 API 客户端（长生命周期）
    - config: 全局配置
    - theme: 应用配色方案
    - shared_state: 跨 Feature 的自定义状态
    """

    client: AgnesClient
    config: AgnesConfig
    theme: Theme | None = None
    shared_state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_default(cls) -> AppContext:
        """从环境变量创建默认上下文。"""
        config = AgnesConfig.from_env()
        client = AgnesClient(config=config)
        return cls(client=client, config=config, theme=Theme())
