"""Event Bus — CRUX 中枢神经（已吸收 ZCode Session 生命周期 v1）。

七兽互相感知的工具。模块间零耦合，挂载即生效。

事件层级（ZCode Protocol v1 origin）:
  Session 层级:
    session:created      → 新会话创建
    session:resumed      → 恢复历史会话
    session:updated      → 会话配置/元数据更新
    session:title_updated→ AI 自动生成标题
    session:closed       → 会话关闭/归档

  Turn 层级:
    turn:started         → 用户消息发送，新一轮开始
    turn:steer_queued    → 转向请求入队
    turn:steer_drained   → 转向请求消化完毕
    turn:completed       → AI 回复完成
    turn:failed          → 本轮出错

  Message 层级:
    message:upserted     → 消息创建或更新
    message:removed      → 消息删除

  Part 层级（流式）:
    part:started         → 内容片段开始
    part:delta           → 片段增量（流式 token）
    part:upserted        → 片段完成
    part:removed         → 片段移除

  模型/工具层级:
    model:streaming      → 模型流式输出中
    tool:before          → 玄武 Schema 校验  (zcode_dna)
    tool:after           → 朱雀 反思 critique (claude_dna)
    tool:updated         → 工具调用状态变更

  权限层级:
    permission:requested → 请求用户授权
    permission:resolved  → 授权已处理

  输入层级:
    user_input:requested → 请求用户输入
    user_input:resolved  → 用户已输入

  CRUX 扩展层级:
    file:changed         → 青龙 冲击分析     (codex_dna)
    error                → 白虎 容灾自愈     (crux_dna)
    session:start        → 麒麟 记忆加载     (codebuddy_dna)
    session:end          → 麒麟 记忆写入     (codebuddy_dna)
    session:metrics      → Agent 指标快照     (zcode)

Usage:
  from core.event_bus import bus
  bus.on("tool:before", my_validator)
  bus.emit("tool:before", tool_name="write_file", args={...})
"""

from __future__ import annotations

import dataclasses
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("crux.event_bus")

__all__ = [
    "ERROR",
    "FILE_CHANGED",
    "MESSAGE_REMOVED",
    "MESSAGE_UPSERTED",
    "MODEL_STREAMING",
    "PART_DELTA",
    "PART_REMOVED",
    "PART_STARTED",
    "PART_UPSERTED",
    "PERMISSION_REQUESTED",
    "PERMISSION_RESOLVED",
    "SCHEMA_VERSION",
    "SESSION_CLOSED",
    "SESSION_CREATED",
    "SESSION_END",
    "SESSION_METRICS",
    "SESSION_RESUMED",
    "SESSION_START",
    "SESSION_TITLE_UPDATED",
    "SESSION_UPDATED",
    "TOOL_AFTER",
    "TOOL_BEFORE",
    "TOOL_UPDATED",
    "TURN_COMPLETED",
    "TURN_FAILED",
    "TURN_STARTED",
    "TURN_STEER_DRAINED",
    "TURN_STEER_QUEUED",
    "USER_INPUT_REQUESTED",
    "USER_INPUT_RESOLVED",
    "EventBus",
    "SessionMetadata",
    "bus",
]

SCHEMA_VERSION = "crux.zcode-dna.v1"


@dataclass
class SessionMetadata:
    """ZCode Protocol v1 会话元数据（完整 Schema 结构）。

    ZCode Gene 1 (Schema-versioned) + Gene 6 (Event lifecycle) 的融合产物。
    每次 session:created / session:resumed / session:updated 事件都携带此对象。
    """

    id: str = ""
    name: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    usage_count: int = 0
    last_active: float | None = None
    model_provider: str | None = None
    total_turns: int = 0
    tags: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> SessionMetadata:
        """从 session_mgr 的会话字典恢复元数据。"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            usage_count=data.get("usage_count", 0),
            last_active=data.get("last_active"),
            model_provider=data.get("model_provider"),
            total_turns=data.get("total_turns", 0),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict:
        """序列化为普通字典（用于持久化/事件负载）。"""
        return dataclasses.asdict(self)

    def touch(self) -> None:
        """标记活跃：更新 last_active 和 usage_count。"""
        import time

        self.last_active = time.time()
        self.usage_count += 1
        self.updated_at = time.time()

    def validate(self) -> tuple[bool, list[str]]:
        """Gene 3: Zod-style 边界校验。"""
        errors = []
        if not self.id:
            errors.append("id is required")
        if self.usage_count < 0:
            errors.append("usage_count must be >= 0")
        if self.total_turns < 0:
            errors.append("total_turns must be >= 0")
        if self.schema_version != SCHEMA_VERSION:
            errors.append(f"schema_version must be {SCHEMA_VERSION}, got {self.schema_version}")
        return (len(errors) == 0, errors)


# ZCode Protocol v1 事件名常量
SESSION_CREATED = "session:created"
SESSION_RESUMED = "session:resumed"
SESSION_UPDATED = "session:updated"
SESSION_TITLE_UPDATED = "session:title_updated"
SESSION_CLOSED = "session:closed"
SESSION_METRICS = "session:metrics"

TURN_STARTED = "turn:started"
TURN_STEER_QUEUED = "turn:steer_queued"
TURN_STEER_DRAINED = "turn:steer_drained"
TURN_COMPLETED = "turn:completed"
TURN_FAILED = "turn:failed"

MESSAGE_UPSERTED = "message:upserted"
MESSAGE_REMOVED = "message:removed"

PART_STARTED = "part:started"
PART_DELTA = "part:delta"
PART_UPSERTED = "part:upserted"
PART_REMOVED = "part:removed"

MODEL_STREAMING = "model:streaming"
TOOL_BEFORE = "tool:before"
TOOL_AFTER = "tool:after"
TOOL_UPDATED = "tool:updated"

# Tool call lifecycle events
TOOL_CALL_COMPLETE = "tool_call:complete"
TOOL_CALL_FAILED = "tool_call:failed"
TOOL_CALL_START = "tool_call:start"
TOOL_CALL_TIMEOUT = "tool_call:timeout"

PERMISSION_REQUESTED = "permission:requested"
PERMISSION_RESOLVED = "permission:resolved"

USER_INPUT_REQUESTED = "user_input:requested"
USER_INPUT_RESOLVED = "user_input:resolved"

# CRUX 扩展事件
FILE_CHANGED = "file:changed"
ERROR = "error"
SESSION_START = "session:start"
SESSION_END = "session:end"


class EventBus:
    """发布-订阅中枢。同步触发，保证顺序。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        self._once_handlers: dict[str, list[Callable[..., Any]]] = defaultdict(list)
        # Agent 指标追踪（ZCode origin）
        self._metrics: dict[str, int | float | None] = {
            "total_sessions": 0,
            "total_turns": 0,
            "tool_call_count": 0,
            "tool_error_rate": 0.0,
            "model_error_rate": 0.0,
            "avg_time_to_first_token_ms": None,
            "avg_turn_duration_ms": None,
            "cache_hit_rate": 0.0,
            "cache_read_tokens": 0,
            "active_days": 0,
        }

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """注册持久监听器。"""
        self._handlers[event].append(handler)

    def once(self, event: str, handler: Callable[..., Any]) -> None:
        """注册一次性监听器，触发后自动移除。"""
        self._once_handlers[event].append(handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """移除监听器。"""
        self._handlers[event] = [h for h in self._handlers[event] if h is not handler]
        self._once_handlers[event] = [h for h in self._once_handlers[event] if h is not handler]

    def emit(self, event: str, **kwargs: Any) -> None:
        """同步触发事件。所有处理器同步执行，异常不中断后续处理器。

        自动追踪 session/turn/tool 指标。
        """
        # 指标自动追踪
        if event in (SESSION_CREATED, SESSION_RESUMED):
            self._metrics["total_sessions"] = int(self._metrics["total_sessions"]) + 1  # pyright: ignore[reportArgumentType]
        elif event == TURN_STARTED:
            self._metrics["total_turns"] = int(self._metrics["total_turns"]) + 1  # pyright: ignore[reportArgumentType]
        elif event == TURN_FAILED:
            # 简单的错误率追踪
            pass
        elif event == TOOL_UPDATED:
            self._metrics["tool_call_count"] = int(self._metrics["tool_call_count"]) + 1  # pyright: ignore[reportArgumentType]

        handlers = self._handlers.get(event, []) + self._once_handlers.pop(event, [])
        for handler in handlers:
            try:
                handler(**kwargs)
            except (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError, AttributeError):
                logger.exception("Event handler failed: %s → %s", event, handler.__name__)

    def get_metrics(self) -> dict[str, int | float | None]:
        """返回当前 Agent 指标快照（ZCode origin）。"""
        return dict(self._metrics)

    def reset_metrics(self) -> None:
        """重置 Agent 指标。"""
        for k in self._metrics:
            if isinstance(self._metrics[k], int):
                self._metrics[k] = 0
            elif isinstance(self._metrics[k], float):
                self._metrics[k] = 0.0
            else:
                self._metrics[k] = None

    def clear(self) -> None:
        """清空所有监听器（测试用）。"""
        self._handlers.clear()
        self._once_handlers.clear()


# 全局中枢
bus = EventBus()
