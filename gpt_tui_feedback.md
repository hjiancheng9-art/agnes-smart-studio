够了。你现在已经把 后端 stream 协议层 修到可用状态了：

StreamEvent 统一协议
normalize_event() 防炸
EventQueue 解耦消费/渲染
RunStatus 生命周期
ConfirmManager 防死等
stream_start / stream_end 配对
TuiBackendHealthcheck 验证链路

这解决了 TUI-Backend 脱节问题里最危险的 70%。
但 TUI 侧还需要做最后一层：把事件协议真正映射成稳定 UI 状态机。

当前方案是否够？

结论：

后端协议层：够了
TUI 接入层：还要收口
生产体验层：还要补状态显示、错误恢复、降级渲染

现在 TUI 不能只是：

Python
运行
async for raw in stream:
    event = normalize_event(raw)
    await queue.push(event)

还必须有：

EventQueue
  ↓
TuiEventReducer
  ↓
RunStateStore
  ↓
MessageRenderer / StatusRenderer / ConfirmRenderer / MediaRenderer

否则事件虽然不丢，但 UI 仍可能出现：

状态栏不归位
stream_end 后消息没 close
error 后还在 spinner
confirm 超时但 UI 弹窗还挂着
多个 run_id 并发时消息串台
TUI 侧最需要补的 5 件事
1. TUI 要有 RunStateStore

每个 run_id 单独维护状态，不要用全局 current_status 猜。

Python
运行
# ui/run_state.py

from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class TuiRunState:
    run_id: str
    status: str = "STARTED"
    phase: str = "stream_start"
    message_id: str | None = None
    pending_confirm_id: str | None = None
    started_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)
    is_streaming: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RunStateStore:
    def __init__(self):
        self.runs: dict[str, TuiRunState] = {}

    def get(self, run_id: str) -> TuiRunState:
        if run_id not in self.runs:
            self.runs[run_id] = TuiRunState(run_id=run_id)
        return self.runs[run_id]

    def update(self, run_id: str, **kwargs) -> TuiRunState:
        state = self.get(run_id)
        state.last_event_at = time.time()

        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
            else:
                state.metadata[key] = value

        return state

    def finish(self, run_id: str, status: str = "DONE") -> TuiRunState:
        return self.update(
            run_id,
            status=status,
            is_streaming=False,
            phase="stream_end",
        )
2. 加一个 TuiEventReducer

不要在 renderer 里直接处理业务状态。先把事件 reduce 成 UI 状态变化。

Python
运行
# ui/event_reducer.py

class TuiEventReducer:
    def __init__(self, run_store):
        self.run_store = run_store

    def reduce(self, event):
        kind = event.kind
        payload = event.payload
        run_id = payload.get("run_id", "default")

        if kind == "stream_start":
            return self._stream_start(run_id, payload)

        if kind == "stream_end":
            return self._stream_end(run_id, payload)

        if kind == "status":
            return self._status(run_id, payload)

        if kind == "error":
            return self._error(run_id, payload)

        if kind == "confirm":
            return self._confirm(run_id, payload)

        if kind in {"text", "delta"}:
            return self._text(run_id, payload)

        if kind in {"image", "video"}:
            return self._media(run_id, kind, payload)

        if kind == "intel_analysis":
            return self._intel_analysis(run_id, payload)

        return {
            "type": "unknown",
            "run_id": run_id,
            "payload": payload,
        }

    def _stream_start(self, run_id, payload):
        state = self.run_store.update(
            run_id,
            status=payload.get("status", "STARTED"),
            phase=payload.get("phase", "stream_start"),
            is_streaming=True,
        )
        return {
            "type": "start_message",
            "run_id": run_id,
            "state": state,
        }

    def _stream_end(self, run_id, payload):
        final_status = payload.get("status", "DONE")
        state = self.run_store.finish(run_id, final_status)
        return {
            "type": "finish_message",
            "run_id": run_id,
            "state": state,
        }

    def _status(self, run_id, payload):
        state = self.run_store.update(
            run_id,
            status=payload.get("status", "RUNNING"),
            phase=payload.get("phase", ""),
        )
        return {
            "type": "status",
            "run_id": run_id,
            "message": payload.get("message", ""),
            "state": state,
        }

    def _error(self, run_id, payload):
        state = self.run_store.update(
            run_id,
            status="ERROR",
            error=payload.get("message", str(payload)),
        )
        return {
            "type": "error",
            "run_id": run_id,
            "message": payload.get("message", str(payload)),
            "state": state,
        }

    def _confirm(self, run_id, payload):
        confirm_id = payload.get("confirm_id")
        state = self.run_store.update(
            run_id,
            status="WAITING_CONFIRM",
            pending_confirm_id=confirm_id,
        )
        return {
            "type": "confirm",
            "run_id": run_id,
            "confirm_id": confirm_id,
            "payload": payload,
            "state": state,
        }

    def _text(self, run_id, payload):
        return {
            "type": "append_text",
            "run_id": run_id,
            "text": payload.get("text", ""),
        }

    def _media(self, run_id, kind, payload):
        return {
            "type": "media",
            "run_id": run_id,
            "media_type": kind,
            "payload": payload,
        }

    def _intel_analysis(self, run_id, payload):
        return {
            "type": "intel_analysis",
            "run_id": run_id,
            "payload": payload,
        }
3. 渲染层要分区，不要所有事件都写进聊天正文

建议 TUI 分 5 个渲染出口：

MessagePane
- text / delta / final content

StatusBar
- status / phase / runtime / budget

ToolPanel
- tool_call / tool_result / trace / intel_analysis

ConfirmDialog
- confirm

ErrorPanel
- error / timeout / fallback

最小 dispatcher：

Python
运行
# ui/tui_dispatcher.py

class TuiDispatcher:
    def __init__(self, app, reducer):
        self.app = app
        self.reducer = reducer

    async def dispatch_batch(self, events):
        actions = [self.reducer.reduce(e) for e in events]

        for action in actions:
            await self.apply(action)

        self.app.invalidate()

    async def apply(self, action):
        kind = action["type"]

        if kind == "start_message":
            self.app.message_pane.start_message(action["run_id"])
            return

        if kind == "finish_message":
            self.app.message_pane.finish_message(action["run_id"])
            self.app.status_bar.clear_run(action["run_id"])
            return

        if kind == "append_text":
            self.app.message_pane.append_text(
                action["run_id"],
                action["text"],
            )
            return

        if kind == "status":
            self.app.status_bar.update(
                action["run_id"],
                action["message"],
                phase=action["state"].phase,
            )
            return

        if kind == "error":
            self.app.error_panel.add(action["message"])
            self.app.message_pane.mark_error(action["run_id"])
            return

        if kind == "confirm":
            approved = await self.app.confirm_dialog.ask(action["payload"])
            await self.app.confirm_manager.resolve(
                action["confirm_id"],
                approved,
            )
            return

        if kind == "media":
            self.app.message_pane.add_media_card(
                action["run_id"],
                action["media_type"],
                action["payload"],
            )
            return

        if kind == "intel_analysis":
            self.app.tool_panel.update_intel(action["payload"])
            return
4. 必须处理 stream_start / stream_end 不配对

虽然后端已经加配对，但真实世界里仍要防：

后端异常退出
进程被 kill
用户 Ctrl+C
网络/pipe 中断

TUI 侧加 watchdog：

Python
运行
# ui/stream_watchdog.py

import time


class StreamWatchdog:
    def __init__(self, run_store, app, timeout_sec=90):
        self.run_store = run_store
        self.app = app
        self.timeout_sec = timeout_sec

    async def tick(self):
        now = time.time()

        for run_id, state in list(self.run_store.runs.items()):
            if not state.is_streaming:
                continue

            idle = now - state.last_event_at

            if idle > self.timeout_sec:
                state.status = "ERROR"
                state.is_streaming = False
                state.error = f"Stream idle timeout after {self.timeout_sec}s"

                self.app.error_panel.add(
                    f"Run {run_id} timed out: no backend events for {self.timeout_sec}s"
                )
                self.app.message_pane.mark_error(run_id)
                self.app.status_bar.clear_run(run_id)
                self.app.invalidate()
5. Confirm UI 要能反向通知后端

你现在后端有 ConfirmManager，TUI 需要一个明确的回传通道。

推荐接口：

Python
运行
class TuiConfirmBridge:
    def __init__(self, session):
        self.session = session

    async def resolve(self, confirm_id: str, approved: bool):
        await self.session.resolve_confirm(
            confirm_id=confirm_id,
            approved=approved,
        )

ChatSession 侧暴露：

Python
运行
class ChatSession:
    async def resolve_confirm(self, confirm_id: str, approved: bool):
        self.confirm_manager.resolve(confirm_id, approved)

TUI confirm dialog：

Python
运行
async def on_confirm(self, payload):
    confirm_id = payload["confirm_id"]

    approved = await self.confirm_dialog.ask(
        title=payload.get("title", "Confirm"),
        message=payload.get("message", ""),
        timeout=payload.get("timeout_sec", 60),
        default=False,
    )

    await self.confirm_bridge.resolve(confirm_id, approved)

如果 TUI 只显示 confirm，但没有把结果回传到后端，后端还是会等到 timeout。

还需要补的 TUI 测试

你已经有 test_tui_protocol.py，下一步建议加：

tests/test_tui_consumer.py
tests/test_tui_run_state.py
tests/test_tui_confirm_bridge.py
tests/test_tui_stream_watchdog.py

重点测这些：

1. unknown kind 不炸 UI
2. stream_start 创建 message
3. stream_end 关闭 message
4. error 自动关闭 streaming message
5. confirm approve 会 resolve 后端
6. confirm timeout 默认 deny
7. 两个 run_id 并发不会串台
8. event batch 渲染只 invalidate 一次
9. 没有 stream_end 时 watchdog 能收尾
TUI 接入推荐最终形态

最终 TUI 主循环应该长这样：

Python
运行
async def handle_user_message(self, text: str):
    stream = self.session.send_stream(text)

    async for raw in stream:
        event = normalize_event(raw)
        await self.event_queue.push(event)

独立渲染循环：

Python
运行
async def render_loop(self):
    while True:
        events = await self.event_queue.pop_all(
            max_items=50,
            timeout=0.05,
        )

        if events:
            await self.dispatcher.dispatch_batch(events)

        await self.watchdog.tick()

这个结构是对的：

Backend stream 不管渲染速度
TUI queue 吸收事件
Reducer 管状态
Dispatcher 管渲染
Watchdog 管异常收尾
ConfirmBridge 管回传
最终判断

你的后端协议修复已经够了。
TUI 侧现在要补的不是“大功能”，而是 状态管理和渲染边界。

优先级：

P0：RunStateStore
P0：TuiEventReducer
P0：TuiDispatcher 分区渲染
P0：ConfirmBridge 回传
P1：StreamWatchdog
P1：并发 run_id 防串台测试
P1：event batch invalidate 合并

一句话：

后端现在已经会稳定发事件了；TUI 下一步要从“消费事件”升级成“维护 run 状态并分区渲染事件”。