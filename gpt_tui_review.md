下面是基于你现在的架构做的 TUI ↔ 后端匹配度诊断。核心判断：

CRUX 现在后端已经很强，但 TUI 必须从“打印流”升级成“事件驱动 UI Runtime”。
否则后端越智能、事件越复杂，TUI 越容易漏消费、卡死、错渲染。
一、3 个最可能导致 TUI 和后端脱节的根因
根因 1：send_stream() 事件协议没有被强类型化

你现在的协议是：

Python
运行
yield (kind, payload)

但如果 kind 没有统一枚举，TUI 很容易出现这些问题：

后端 yield ("intel_analysis", {...})
TUI 只识别 text/status/error
→ 事件被忽略

后端 yield ("confirm", {...})
TUI 没有 await 用户响应
→ agent 死等

后端 yield ("image", {...})
TUI 当普通 text 打印
→ UI 混乱

后端 yield ("error", "xxx")
TUI 期待 payload 是 dict
→ 渲染异常
后端侧修法

新增统一事件定义：

Python
运行
# core/stream_events.py

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StreamKind(str, Enum):
    TEXT = "text"
    DELTA = "delta"
    INFO = "info"
    STATUS = "status"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"
    VIDEO = "video"
    CONFIRM = "confirm"
    INTEL_ANALYSIS = "intel_analysis"
    FINAL = "final"
    HEARTBEAT = "heartbeat"


@dataclass
class StreamEvent:
    kind: StreamKind
    payload: dict[str, Any]

    def as_tuple(self) -> tuple[str, dict[str, Any]]:
        return self.kind.value, self.payload


def normalize_event(event) -> tuple[str, dict[str, Any]]:
    if isinstance(event, StreamEvent):
        return event.as_tuple()

    if not isinstance(event, tuple) or len(event) != 2:
        return StreamKind.ERROR.value, {
            "message": "Invalid stream event",
            "raw": repr(event),
        }

    kind, payload = event

    if not isinstance(kind, str):
        return StreamKind.ERROR.value, {
            "message": "Invalid event kind",
            "raw": repr(event),
        }

    if payload is None:
        payload = {}

    if isinstance(payload, str):
        payload = {"text": payload}

    if not isinstance(payload, dict):
        payload = {"data": payload}

    known = {k.value for k in StreamKind}
    if kind not in known:
        return StreamKind.INFO.value, {
            "message": f"Unknown stream event kind: {kind}",
            "raw": repr(payload),
        }

    return kind, payload

然后所有后端 yield 前都统一：

Python
运行
yield normalize_event(event)
TUI 侧修法

TUI 不要直接 if kind == ... 散落在各处。做一个集中事件分发器：

Python
运行
# ui/stream_consumer.py

class TuiStreamConsumer:
    def __init__(self, app):
        self.app = app

    async def consume(self, stream):
        async for raw_event in stream:
            kind, payload = normalize_event(raw_event)
            await self.dispatch(kind, payload)

    async def dispatch(self, kind: str, payload: dict):
        handler = getattr(self, f"on_{kind}", None)

        if handler is None:
            await self.on_unknown(kind, payload)
            return

        await handler(payload)

    async def on_text(self, payload):
        self.app.append_assistant_text(payload.get("text", ""))

    async def on_delta(self, payload):
        self.app.append_stream_delta(payload.get("text", ""))

    async def on_status(self, payload):
        self.app.set_status(payload.get("message", ""))

    async def on_info(self, payload):
        self.app.append_system_info(payload.get("message", str(payload)))

    async def on_error(self, payload):
        self.app.append_error(payload.get("message", str(payload)))

    async def on_image(self, payload):
        self.app.append_media_card("image", payload)

    async def on_video(self, payload):
        self.app.append_media_card("video", payload)

    async def on_intel_analysis(self, payload):
        self.app.update_intelligence_panel(payload)

    async def on_confirm(self, payload):
        result = await self.app.ask_confirm(payload)
        await self.app.reply_confirm(payload.get("confirm_id"), result)

    async def on_final(self, payload):
        self.app.finish_message(payload)

    async def on_heartbeat(self, payload):
        self.app.mark_backend_alive()

    async def on_unknown(self, kind, payload):
        self.app.append_system_info(f"Unknown event: {kind}")
根因 2：TUI 渲染和后端 stream 消费在同一阻塞路径

典型问题：

后端正在 yield tool status
TUI 正在渲染大段 Rich/Markdown
渲染阻塞 event loop
后端事件堆积
confirm 无法响应
tool 等不到确认
agent 卡住

尤其你有：

多轮 tool_calls
intel_analysis
trace/status
image/video card
confirm
error

如果 TUI 每收到一个 event 就立即同步重绘，很容易卡。

后端侧修法

后端需要定期发 heartbeat，并且不要无限等待 confirm。

Python
运行
# core/confirm_manager.py

import asyncio
import uuid


class ConfirmTimeout(Exception):
    pass


class ConfirmManager:
    def __init__(self):
        self.pending: dict[str, asyncio.Future] = {}

    def create_confirm(self) -> tuple[str, asyncio.Future]:
        confirm_id = f"confirm_{uuid.uuid4().hex[:12]}"
        fut = asyncio.get_event_loop().create_future()
        self.pending[confirm_id] = fut
        return confirm_id, fut

    def resolve(self, confirm_id: str, value: bool):
        fut = self.pending.pop(confirm_id, None)
        if fut and not fut.done():
            fut.set_result(value)

    async def wait(self, confirm_id: str, fut: asyncio.Future, timeout_sec: float = 60):
        try:
            return await asyncio.wait_for(fut, timeout=timeout_sec)
        except asyncio.TimeoutError:
            self.pending.pop(confirm_id, None)
            raise ConfirmTimeout(f"confirm timeout: {confirm_id}")

后端 confirm event：

Python
运行
confirm_id, fut = confirm_manager.create_confirm()

yield ("confirm", {
    "confirm_id": confirm_id,
    "title": "Allow file write?",
    "message": "CRUX wants to modify core/chat.py",
    "timeout_sec": 60,
})

try:
    approved = await confirm_manager.wait(confirm_id, fut, timeout_sec=60)
except ConfirmTimeout:
    yield ("error", {"message": "Confirmation timed out; operation cancelled."})
    return
TUI 侧修法

TUI 要加 事件队列 + 批量刷新，不要每个 event 立即重绘。

Python
运行
# ui/event_queue.py

import asyncio
import time


class TuiEventQueue:
    def __init__(self, app, flush_interval=0.05, max_batch=50):
        self.app = app
        self.queue = asyncio.Queue()
        self.flush_interval = flush_interval
        self.max_batch = max_batch
        self.running = False

    async def push(self, event):
        await self.queue.put(event)

    async def run(self):
        self.running = True

        while self.running:
            batch = []

            start = time.time()

            while len(batch) < self.max_batch:
                timeout = max(0.0, self.flush_interval - (time.time() - start))

                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break

            if batch:
                await self.app.apply_event_batch(batch)
                self.app.invalidate()

TUI 消费 stream 时：

Python
运行
async for event in session.send_stream(message):
    await tui_event_queue.push(event)

这样可以避免：

后端 yield 很快
TUI 渲染很慢
两边互相阻塞
根因 3：长任务没有统一生命周期状态机

现在你的后端链路非常长：

PolicyRouter → RuntimeRouter → Runtime → EvidenceGate → Trace → Learning → Arena

如果 TUI 不知道任务生命周期，就会出现：

状态栏停在 “Thinking...”
工具已经失败但 TUI 还显示运行中
stream 中断但消息没有 close
error 后没有 final
confirm pending 但用户不知道
后端侧修法

每次用户请求必须有 run_id，每个 event 都带：

JSON
{
  "run_id": "...",
  "phase": "...",
  "status": "running|done|error|cancelled",
  "message": "..."
}

定义任务生命周期：

Python
运行
class RunStatus(str, Enum):
    STARTED = "started"
    ROUTING = "routing"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"
    TOOL_RUNNING = "tool_running"
    FINALIZING = "finalizing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

后端每个复杂任务至少 yield：

Python
运行
yield ("status", {"run_id": run_id, "phase": "started", "message": "Started"})
yield ("status", {"run_id": run_id, "phase": "routing", "message": "Routing task"})
yield ("status", {"run_id": run_id, "phase": "runtime", "message": "DebugAnalyzeRuntime"})
yield ("status", {"run_id": run_id, "phase": "tool_running", "message": "Running code search"})
yield ("final", {"run_id": run_id, "content": final_text})

异常时必须 yield：

Python
运行
yield ("error", {"run_id": run_id, "message": repr(exc)})
yield ("final", {"run_id": run_id, "content": "任务失败，已安全停止。"})
TUI 侧修法

TUI 维护 RunState：

Python
运行
# ui/run_state.py

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunState:
    run_id: str
    status: str = "started"
    phase: str = "started"
    message_id: str | None = None
    pending_confirm_id: str | None = None
    last_event_ts: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RunStateStore:
    def __init__(self):
        self.runs: dict[str, RunState] = {}

    def get_or_create(self, run_id: str) -> RunState:
        if run_id not in self.runs:
            self.runs[run_id] = RunState(run_id=run_id)
        return self.runs[run_id]

    def update(self, run_id: str, **kwargs):
        run = self.get_or_create(run_id)

        for k, v in kwargs.items():
            setattr(run, k, v)

        return run

TUI 处理 status：

Python
运行
async def on_status(self, payload):
    run_id = payload.get("run_id", "default")
    run = self.run_store.update(
        run_id,
        status=payload.get("status", "running"),
        phase=payload.get("phase", ""),
        last_event_ts=time.time(),
    )

    self.app.set_status(payload.get("message", ""))

这样 TUI 就不会“只靠文本猜状态”。

二、TUI 侧具体修复清单
1. 加事件协议兼容层

TUI 消费任何 event 前都调用：

Python
运行
kind, payload = normalize_event(raw_event)

保证：

payload 永远是 dict
kind 永远是已知字符串或 fallback info/error
未知事件不会炸 UI
2. 加 EventQueue，避免渲染阻塞后端

不要：

Python
运行
async for event in stream:
    render(event)

改成：

Python
运行
async for event in stream:
    await queue.push(event)

由独立 UI loop 批量刷新。

3. confirm 必须有超时、取消和默认行为

TUI confirm 弹窗必须支持：

Enter = approve
Esc = reject
Ctrl+C = cancel task
timeout = reject

TUI 侧：

Python
运行
async def ask_confirm(self, payload):
    confirm_id = payload["confirm_id"]
    timeout = payload.get("timeout_sec", 60)

    try:
        return await asyncio.wait_for(
            self.confirm_dialog.ask(payload),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        self.append_error("Confirmation timed out.")
        return False
4. 错误渲染要分区，不要污染 assistant 正文

TUI 应该有 4 类显示区：

assistant message 区：最终回答 / streaming text
status 区：短状态
tool panel：工具调用 / trace / runtime
error panel：异常 / fallback

不要把所有东西都 append 到 assistant message。

5. 对 streaming message 做 close/finalize

每个 assistant 消息要有状态：

streaming
done
error
cancelled

后端异常时，TUI 也必须 close 当前 message：

Python
运行
async def on_error(self, payload):
    self.app.append_error(payload.get("message", "Unknown error"))
    self.app.close_current_streaming_message(status="error")
三、后端侧具体修复清单
1. send_stream() 必须保证 finally 收尾
Python
运行
async def send_stream(self, message: str):
    run_id = new_run_id()

    try:
        yield ("status", {"run_id": run_id, "phase": "started", "message": "Started"})

        async for event in self.intelligence_hook.run(message, run_id=run_id):
            yield normalize_event(event)

        yield ("final", {"run_id": run_id, "status": "done"})

    except asyncio.CancelledError:
        yield ("error", {"run_id": run_id, "message": "Task cancelled"})
        yield ("final", {"run_id": run_id, "status": "cancelled"})
        raise

    except Exception as exc:
        yield ("error", {"run_id": run_id, "message": repr(exc)})
        yield ("final", {"run_id": run_id, "status": "error"})
2. 工具调用必须统一超时

不要让任何 tool 无限挂起。

Python
运行
async def call_tool_with_timeout(toolbus, name, payload, timeout_sec=120):
    try:
        return await asyncio.wait_for(
            toolbus.call(name, payload),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Tool timeout: {name}",
            "timeout_sec": timeout_sec,
        }

并 yield：

Python
运行
yield ("error", {
    "run_id": run_id,
    "kind": "tool_timeout",
    "tool": name,
    "message": f"{name} timed out after {timeout_sec}s",
})
3. confirm 必须后端可取消

如果 confirm 没响应，后端不能死等：

Python
运行
approved = await confirm_manager.wait(confirm_id, fut, timeout_sec=60)

超时：

Python
运行
yield ("status", {
    "run_id": run_id,
    "phase": "confirm_timeout",
    "message": "Confirmation timed out; cancelled operation.",
})
4. 多轮 tool_calls 后必须压缩历史

你现在已经有 Intelligence Pipeline，最容易膨胀的是：

tool_call
tool_result
trace
critic finding
repair result
web evidence

后端要加 message compaction：

Python
运行
class HistoryCompactor:
    def compact_tool_history(self, messages, max_tool_events=20):
        compacted = []
        tool_events = []

        for msg in messages:
            if msg.get("role") == "tool":
                tool_events.append(msg)
            else:
                compacted.append(msg)

        if len(tool_events) <= max_tool_events:
            return messages

        summary = self.summarize_tool_events(tool_events[:-max_tool_events])

        return compacted + [
            {
                "role": "system",
                "content": f"[Compacted tool history]\n{summary}",
            }
        ] + tool_events[-max_tool_events:]

更直接的规则：

保留最近 20 个 tool event
旧 tool event 变成摘要
image/video payload 不进入 LLM history，只存 artifact ref
trace 不进入 LLM history，只存 trace_run_id
5. CDP 断线要有自动重连

后端包装 CDP 工具：

Python
运行
class CdpClientManager:
    def __init__(self, factory):
        self.factory = factory
        self.client = None

    async def get(self):
        if self.client is None or not await self.is_alive():
            self.client = await self.factory.connect()
        return self.client

    async def is_alive(self):
        try:
            if self.client is None:
                return False
            await asyncio.wait_for(self.client.ping(), timeout=2)
            return True
        except Exception:
            return False

    async def call(self, method, *args, **kwargs):
        client = await self.get()

        try:
            return await client.call(method, *args, **kwargs)
        except Exception:
            self.client = await self.factory.connect()
            return await self.client.call(method, *args, **kwargs)

TUI 收到 CDP 重连事件：

Python
运行
yield ("status", {
    "phase": "cdp_reconnect",
    "message": "Browser connection lost; reconnecting...",
})
四、最小可用 TUI-backend 健康检查方案

你需要一个 healthcheck stream，不是普通函数。

因为真正的问题在 stream event 消费链路。

后端：healthcheck_stream()
Python
运行
# core/tui_healthcheck.py

import asyncio
import uuid


async def healthcheck_stream():
    run_id = f"health_{uuid.uuid4().hex[:8]}"

    yield ("status", {
        "run_id": run_id,
        "phase": "health_start",
        "message": "Healthcheck started",
    })

    await asyncio.sleep(0.05)

    yield ("text", {
        "run_id": run_id,
        "text": "TUI text event OK\n",
    })

    await asyncio.sleep(0.05)

    yield ("info", {
        "run_id": run_id,
        "message": "Info event OK",
    })

    await asyncio.sleep(0.05)

    yield ("status", {
        "run_id": run_id,
        "phase": "tool_mock",
        "message": "Mock tool running",
    })

    await asyncio.sleep(0.05)

    yield ("intel_analysis", {
        "run_id": run_id,
        "runtime": "debug_analyze",
        "mode": "DEEP",
        "trace_run_id": "trace_mock",
        "evidence_quality": "strong",
    })

    await asyncio.sleep(0.05)

    yield ("confirm", {
        "run_id": run_id,
        "confirm_id": f"{run_id}_confirm",
        "title": "Healthcheck confirm",
        "message": "Press confirm to test TUI confirm path.",
        "timeout_sec": 10,
    })

    await asyncio.sleep(0.05)

    yield ("image", {
        "run_id": run_id,
        "artifact_id": "mock_image",
        "path": "mock://image",
        "caption": "Image event OK",
    })

    await asyncio.sleep(0.05)

    yield ("error", {
        "run_id": run_id,
        "message": "Mock recoverable error event OK",
    })

    await asyncio.sleep(0.05)

    yield ("final", {
        "run_id": run_id,
        "status": "done",
        "content": "Healthcheck completed",
    })
TUI 侧健康检查 runner
Python
运行
class TuiBackendHealthcheck:
    REQUIRED_EVENTS = {
        "status",
        "text",
        "info",
        "intel_analysis",
        "confirm",
        "image",
        "error",
        "final",
    }

    def __init__(self, consumer):
        self.consumer = consumer
        self.seen = set()
        self.errors = []

    async def run(self, stream):
        async for raw_event in stream:
            kind, payload = normalize_event(raw_event)
            self.seen.add(kind)

            try:
                await self.consumer.dispatch(kind, payload)
            except Exception as exc:
                self.errors.append({
                    "kind": kind,
                    "error": repr(exc),
                })

        missing = self.REQUIRED_EVENTS - self.seen

        return {
            "ok": not missing and not self.errors,
            "seen": sorted(self.seen),
            "missing": sorted(missing),
            "errors": self.errors,
        }
健康检查输出

TUI 命令：

/health tui

输出：

TUI Backend Healthcheck
-----------------------
status          OK
text            OK
info            OK
intel_analysis  OK
confirm         OK
image           OK
error           OK
final           OK

Result: PASS

失败示例：

TUI Backend Healthcheck
-----------------------
status          OK
text            OK
info            OK
intel_analysis  MISSING
confirm         ERROR: timeout
image           OK
error           OK
final           MISSING

Result: FAIL
Likely cause:
- TUI consumer does not handle intel_analysis
- confirm dialog did not resolve
- final event not emitted after error
五、最应该优先修的 5 件事

按优先级：

P0-1：统一 StreamEvent 协议 + normalize_event()
P0-2：TUI StreamConsumer 集中分发所有 kind
P0-3：confirm 超时 + 取消 + 后端不死等
P0-4：TUI EventQueue 批量刷新，避免渲染阻塞 stream
P0-5：/health tui 健康检查流

然后再做：

P1-1：tool timeout 全局包装
P1-2：CDP 自动重连
P1-3：tool history compaction
P1-4：error/final 强制收尾
P1-5：Runtime trace 显示面板
最终判断

你现在最容易出 bug 的地方不是 Intelligence Pipeline 本身，而是：

后端事件越来越丰富
TUI 仍然像普通文本流一样消费

所以核心修复方向是：

把 TUI 从“文本渲染器”
升级成
“事件驱动的前端 Runtime”

一句话结论：

先统一事件协议，再做 TUI 消费器，再加健康检查；这三件事做好，TUI 和后端脱节问题会少掉 70%。