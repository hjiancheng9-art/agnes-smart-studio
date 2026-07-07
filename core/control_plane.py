"""Control Plane — TUI 的控制通道与消息状态管理

GPT 规格核心设计：
- 用户输入有两个通道：普通 message_queue + 高优先级 control_queue
- 消息状态机：draft → pending → committed → consumed → retracted
- 运行状态机：idle → running → pausing → paused → cancelling → cancelled
- 撤销窗口：2 秒 pending，Ctrl+Z 无副作用撤销
- 取消当前 run：Esc 暂停，Ctrl+C 取消，Ctrl+C×2 退出

使用方式：
    from core.control_plane import control, ControlEvent, MessageState

    # 发送带 pending 窗口的消息
    msg_id = control.send_message("帮我改代码")

    # 检查是否有 control event
    event = control.poll()
    if event:
        handle(event)

    # 工具声明中断性
    @control.interruptible("cooperative")
    def my_tool(): ...
"""

import enum
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

# ── 枚举 ──────────────────────────────────────────────────


class MessageState(enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    COMMITTED = "committed"
    CONSUMED = "consumed"
    RETRACTED = "retracted"

    def __str__(self):
        return self.value


class RunState(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

    def __str__(self):
        return self.value


class ControlEventType(enum.Enum):
    INTERRUPT = "interrupt"  # "停一下"
    PAUSE = "pause"  # 暂停当前 run
    CANCEL = "cancel"  # 取消当前 run
    PRIORITY_MESSAGE = "priority_message"  # 先处理插话
    RETRACT = "retract"  # 撤回消息
    CORRECTION = "correction"  # 修改当前 goal
    MODIFY_GOAL = "modify_goal"  # 修改 goal 合约
    RESUME = "resume"  # 恢复暂停的 run

    def __str__(self):
        return self.value


InterruptMode = Literal["cooperative", "kill_process", "not_interruptible"]


# ── 数据结构 ──────────────────────────────────────────────


@dataclass
class StagedMessage:
    """待发送消息 — 带状态机和撤销窗口。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = ""
    state: MessageState = MessageState.DRAFT
    created_at: float = field(default_factory=time.time)
    committed_at: float = 0.0
    consumed_at: float = 0.0
    retracted_at: float = 0.0

    def commit(self):
        self.state = MessageState.COMMITTED
        self.committed_at = time.time()

    def consume(self):
        self.state = MessageState.CONSUMED
        self.consumed_at = time.time()

    def retract(self):
        self.state = MessageState.RETRACTED
        self.retracted_at = time.time()

    def pending_elapsed(self) -> float:
        """进入 pending 状态的时长（秒）。"""
        if self.state == MessageState.PENDING:
            return time.time() - self.created_at
        return 0.0


@dataclass
class ControlEvent:
    """控制事件 — 比普通消息更高优先级。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: ControlEventType = ControlEventType.INTERRUPT
    priority: int = 1  # 越大越优先
    target_run_id: str = ""
    payload: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    handled: bool = False

    def __lt__(self, other):
        # 用于优先队列：高 priority 先处理
        return self.priority > other.priority


@dataclass
class ToolInterruptibility:
    """工具的可中断性声明。"""

    tool_name: str = ""
    mode: InterruptMode = "cooperative"
    cancel_fn: Callable | None = None  # 如何取消
    timeout_grace: float = 5.0  # 取消后的最大等待秒数


# ── 控制队列 ──────────────────────────────────────────────


class ControlQueue:
    """控制事件队列 — 优先级队列，agent 执行循环每步检查。"""

    def __init__(self):
        self._events: list[ControlEvent] = []
        self._lock = threading.Lock()

    def push(self, event: ControlEvent | None = None, **kwargs) -> ControlEvent:
        """添加控制事件。返回事件对象。"""
        if event is None:
            event = ControlEvent(**kwargs)
        with self._lock:
            self._events.append(event)
            # 按优先级排序（高优先在前）
            self._events.sort(key=lambda e: -e.priority)
        return event

    def poll(self) -> ControlEvent | None:
        """获取最高优先级的未处理事件。"""
        with self._lock:
            if not self._events:
                return None
            event = self._events.pop(0)
        event.handled = True
        return event

    def peek(self) -> ControlEvent | None:
        """查看最高优先事件但不移除。"""
        with self._lock:
            return self._events[0] if self._events else None

    def has_events(self) -> bool:
        return len(self._events) > 0

    def clear(self):
        with self._lock:
            self._events.clear()

    def remove(self, event_id: str) -> bool:
        """移除指定事件。"""
        with self._lock:
            for i, e in enumerate(self._events):
                if e.id == event_id:
                    self._events.pop(i)
                    return True
        return False


# ── Pending Outbox（撤销窗口） ───────────────────────────


class PendingOutbox:
    """待发送消息管理器 — 2 秒撤销窗口。"""

    UNDO_WINDOW_MS = 2000  # 2 秒

    def __init__(self):
        self._pending: dict[str, StagedMessage] = {}
        self._lock = threading.Lock()
        self._on_commit: Callable[[StagedMessage], None] | None = None

    def on_commit(self, callback: Callable[[StagedMessage], None]):
        """设置消息确认提交后的回调（真正发送到 agent）。"""
        self._on_commit = callback

    def stage(self, text: str) -> StagedMessage:
        """创建待发送消息，进入 pending 状态。"""
        msg = StagedMessage(text=text, state=MessageState.PENDING)
        with self._lock:
            self._pending[msg.id] = msg
        return msg

    def commit(self, msg_id: str) -> bool:
        """确认提交消息（撤销窗口过期）。"""
        with self._lock:
            msg = self._pending.pop(msg_id, None)
        if msg is None:
            return False
        msg.commit()
        if self._on_commit:
            self._on_commit(msg)
        return True

    def retract(self, msg_id: str) -> bool:
        """撤销 pending 消息。"""
        with self._lock:
            msg = self._pending.pop(msg_id, None)
        if msg is None:
            return False
        msg.retract()
        return True

    def get_pending(self) -> list[StagedMessage]:
        """获取所有 pending 中的消息。"""
        with self._lock:
            return list(self._pending.values())

    def has_pending(self) -> bool:
        return len(self._pending) > 0

    def tick(self) -> list[StagedMessage]:
        """时钟滴答：自动提交过期的 pending 消息。返回新提交的消息列表。"""
        now = time.time()
        committed: list[StagedMessage] = []
        with self._lock:
            expired = [
                mid for mid, msg in self._pending.items() if (now - msg.created_at) * 1000 >= self.UNDO_WINDOW_MS
            ]
            for mid in expired:
                msg = self._pending.pop(mid)
                msg.commit()
                committed.append(msg)
        for msg in committed:
            if self._on_commit:
                self._on_commit(msg)
        return committed


# ── 运行状态管理器 ──────────────────────────────────────


class RunStateManager:
    """跟踪当前 run 的状态。"""

    STATE_TRANSITIONS = {
        RunState.IDLE: [RunState.RUNNING],
        RunState.RUNNING: [RunState.PAUSING, RunState.CANCELLING, RunState.COMPLETED],
        RunState.PAUSING: [RunState.PAUSED, RunState.RUNNING],
        RunState.PAUSED: [RunState.RUNNING, RunState.CANCELLING],
        RunState.CANCELLING: [RunState.CANCELLED],
        RunState.CANCELLED: [RunState.IDLE],
        RunState.COMPLETED: [RunState.IDLE],
    }

    def __init__(self):
        self._state = RunState.IDLE
        self._run_id: str = ""
        self._lock = threading.Lock()
        self._on_state_change: Callable[[RunState, RunState], None] | None = None
        self._on_pending_control: Callable[[], None] | None = None

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_running(self) -> bool:
        return self._state in (RunState.RUNNING, RunState.PAUSING)

    @property
    def is_cancelling(self) -> bool:
        return self._state in (RunState.CANCELLING, RunState.CANCELLED)

    @property
    def is_paused(self) -> bool:
        return self._state == RunState.PAUSED

    @property
    def is_idle(self) -> bool:
        return self._state == RunState.IDLE

    def on_state_change(self, callback: Callable[[RunState, RunState], None]):
        self._on_state_change = callback

    def on_pending_control(self, callback: Callable[[], None]):
        """设置控制事件待处理时的回调（TUI 用来更新显示）。"""
        self._on_pending_control = callback

    def transition_to(self, new_state: RunState) -> bool:
        """尝试状态转换。"""
        with self._lock:
            allowed = self.STATE_TRANSITIONS.get(self._state, [])
            if new_state not in allowed:
                return False
            old = self._state
            self._state = new_state
        if self._on_state_change:
            self._on_state_change(old, new_state)
        return True

    def request_pause(self) -> bool:
        """请求暂停：running → pausing"""
        return self.transition_to(RunState.PAUSING)

    def request_cancel(self) -> bool:
        """请求取消：running → cancelling"""
        return self.transition_to(RunState.CANCELLING)

    def resume(self) -> bool:
        """恢复：paused → running"""
        return self.transition_to(RunState.RUNNING)

    def start_run(self, run_id: str = "") -> bool:
        """开始新 run。"""
        if self._state == RunState.IDLE and self.transition_to(RunState.RUNNING):
            self._run_id = run_id or str(uuid.uuid4())[:8]
            return True
        return False

    def complete_run(self) -> bool:
        """完成当前 run。"""
        if self.transition_to(RunState.COMPLETED):
            self._run_id = ""
            self.transition_to(RunState.IDLE)
            return True
        return False

    def check_control(self, control_queue: ControlQueue) -> ControlEvent | None:
        """执行循环中调用：检查 control event 并自动转换状态。"""
        if not control_queue.has_events():
            if self._state == RunState.PAUSING:
                self._state = RunState.PAUSED
            return None

        event = control_queue.poll()
        if event:
            if event.type in (ControlEventType.INTERRUPT, ControlEventType.PAUSE):
                self._state = RunState.PAUSING if self._state == RunState.RUNNING else self._state
            elif event.type == ControlEventType.CANCEL:
                self._state = RunState.CANCELLING if self._state in (RunState.RUNNING, RunState.PAUSED) else self._state
        return event


# ── 工具中断性注册表 ────────────────────────────────────


class ToolInterruptRegistry:
    """工具可中断性注册表。"""

    def __init__(self):
        self._tools: dict[str, ToolInterruptibility] = {}

    def register(self, tool: ToolInterruptibility | None = None, **kwargs):
        """注册工具的可中断性。"""
        t = tool if tool else ToolInterruptibility(**kwargs)
        self._tools[t.tool_name] = t
        return t

    def get(self, tool_name: str) -> ToolInterruptibility:
        """获取工具的中断模式，默认 cooperative。"""
        return self._tools.get(tool_name, ToolInterruptibility(tool_name=tool_name, mode="cooperative"))

    def interruptible(self, mode: InterruptMode = "cooperative"):
        """装饰器：声明工具的可中断性。"""

        def decorator(func):
            name = getattr(func, "__name__", str(func))
            self._tools[name] = ToolInterruptibility(tool_name=name, mode=mode)
            return func

        return decorator


# ── 全局实例 ──────────────────────────────────────────────


class ControlPlane:
    """Control Plane — TUI 控制通道的总管理器。"""

    def __init__(self):
        self.queue = ControlQueue()
        self.outbox = PendingOutbox()
        self.runs = RunStateManager()
        self.tools = ToolInterruptRegistry()
        self._message_history: list[StagedMessage] = []
        self._lock = threading.Lock()

        # 默认工具可中断性声明
        self._register_default_tools()

    def _register_default_tools(self):
        """注册 CRUX 默认工具的可中断性。"""
        defaults = {
            "pip_install": ("kill_process", 10.0),
            "generate_image": ("not_interruptible", 0.0),
            "generate_video": ("not_interruptible", 0.0),
            "comfyui_submit_workflow": ("not_interruptible", 0.0),
            "run_bash": ("kill_process", 5.0),
            "run_python": ("kill_process", 5.0),
            "patch_file": ("cooperative", 2.0),
            "execute_plan": ("cooperative", 5.0),
            "self_heal": ("cooperative", 5.0),
            "agent_swarm": ("cooperative", 10.0),
            "multi_agent": ("cooperative", 10.0),
            "web_fetch": ("kill_process", 5.0),
            "task_launch": ("not_interruptible", 0.0),
            "browser_screenshot": ("cooperative", 3.0),
        }
        for tool_name, (mode, grace) in defaults.items():
            self.tools.register(
                tool_name=tool_name,
                mode=mode,
                timeout_grace=grace,
            )

    # ── 消息生命周期 ──

    def send_message(self, text: str) -> StagedMessage:
        """发送消息（先进入 pending，2 秒后自动提交）。

        返回 StagedMessage，可用来在窗口期内撤销。
        """
        msg = self.outbox.stage(text)
        with self._lock:
            self._message_history.append(msg)
        return msg

    def send_now(self, text: str) -> StagedMessage:
        """立即发送消息（跳过 pending 窗口）。"""
        msg = self.outbox.stage(text)
        self.outbox.commit(msg.id)
        return msg

    def retract(self, msg_id: str) -> bool:
        """撤销消息（仅在 pending 状态有效）。"""
        return self.outbox.retract(msg_id)

    def tick(self) -> list[StagedMessage]:
        """时钟滴答：自动提交过期的 pending 消息。"""
        return self.outbox.tick()

    # ── 控制事件快捷方法 ──

    def interrupt(self, reason: str = "") -> ControlEvent:
        return self.queue.push(type=ControlEventType.INTERRUPT, payload={"reason": reason})

    def cancel_run(self, reason: str = "") -> ControlEvent:
        return self.queue.push(type=ControlEventType.CANCEL, priority=2, payload={"reason": reason})

    def pause_run(self, reason: str = "") -> ControlEvent:
        return self.queue.push(type=ControlEventType.PAUSE, payload={"reason": reason})

    def priority_message(self, text: str) -> ControlEvent:
        """发送优先插话消息。"""
        return self.queue.push(
            type=ControlEventType.PRIORITY_MESSAGE,
            priority=3,
            payload={"text": text},
        )

    # ── 查询 ──

    def get_pending_timer(self) -> float:
        """获取当前 pending 消息的剩余时间（秒），0 表示无 pending。"""
        pending = self.outbox.get_pending()
        if not pending:
            return 0.0
        elapsed = (time.time() - pending[0].created_at) * 1000
        remaining = max(0.0, self.outbox.UNDO_WINDOW_MS - elapsed) / 1000
        return remaining

    def get_pending_text(self) -> str:
        """获取当前 pending 消息的文本。"""
        pending = self.outbox.get_pending()
        return pending[0].text if pending else ""

    def get_status_line(self) -> str:
        """获取状态行文本（供 TUI 底部显示）。"""
        parts = []

        # Run state
        rs = self.runs.state
        if rs == RunState.RUNNING:
            parts.append("执行中")
        elif rs == RunState.PAUSED:
            parts.append("已暂停")
        elif rs == RunState.CANCELLING:
            parts.append("正在取消")
        elif rs == RunState.PAUSING:
            parts.append("暂停中")

        # Pending message
        timer = self.get_pending_timer()
        if timer > 0:
            parts.append(f"待发送 {timer:.1f}s [Ctrl+Z 撤销]")

        if parts:
            return " | ".join(parts)
        return "空闲"


# ── 全局单例 ──────────────────────────────────────────────
_control: ControlPlane | None = None


def get_control() -> ControlPlane:
    global _control
    if _control is None:
        _control = ControlPlane()
    return _control


def control() -> ControlPlane:
    """快捷获取全局 Control Plane 实例。"""
    return get_control()
