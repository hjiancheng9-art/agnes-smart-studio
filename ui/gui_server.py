"""
CRUX GUI Cockpit Server v4 — Clean rewrite with external HTML template
"""
import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.protocol import Event, EventType, get_bus

WS_CLIENTS: set = set()

# Load HTML from template file
_html_path = os.path.join(os.path.dirname(__file__), "gui_template.html")
with open(_html_path, encoding="utf-8") as f:
    HTML = f.read()


async def http_handler(reader, writer):
    try:
        await asyncio.wait_for(reader.read(4096), timeout=5)
    except:
        writer.close()
        return
    body = HTML.encode('utf-8')
    resp = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "\r\n"
    ).encode() + body
    try:
        writer.write(resp)
        await writer.drain()
    except:
        pass
    finally:
        try: writer.close()
        except: pass


async def ws_handler(websocket):
    WS_CLIENTS.add(websocket)
    print(f"  WS: 客户端已连接 (共 {len(WS_CLIENTS)})")
    try:
        # 发初始状态
        bus = get_bus()
        if bus.latest_state:
            await websocket.send(json.dumps({
                'type': 'state.snapshot', 'data': bus.latest_state.to_dict()
            }, ensure_ascii=False))
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'chat.input':
                    d = data.get('data', {})
                    get_bus().publish(Event(
                        EventType.MESSAGE_SENT.value,
                        {'role': d.get('role', 'user'), 'content': d.get('content', '')},
                        source='gui'
                    ))
            except json.JSONDecodeError:
                pass
    except:
        pass
    finally:
        WS_CLIENTS.discard(websocket)
        print(f"  WS: 客户端断开 (剩余 {len(WS_CLIENTS)})")


async def broadcast_loop():
    bus = get_bus()
    last_idx = 0
    while True:
        await asyncio.sleep(0.3)
        history = getattr(bus, '_history', [])
        if not history:
            continue
        for i in range(last_idx, len(history)):
            evt = history[i]
            msg = json.dumps({
                'type': evt.type if hasattr(evt,'type') else str(evt.get('type','')),
                'data': evt.data if hasattr(evt,'data') else {},
                'source': evt.source if hasattr(evt,'source') else 'engine',
            }, ensure_ascii=False)
            dead = set()
            for client in list(WS_CLIENTS):
                try:
                    await client.send(msg)
                except:
                    dead.add(client)
            WS_CLIENTS.difference_update(dead)
        last_idx = len(history)


async def engine_heartbeat():
    """定期推送状态给 GUI"""
    while True:
        await asyncio.sleep(2.0)
        try:
            bus = get_bus()
            state = bus.latest_state
            if state:
                bus.publish(Event(
                    EventType.DASHBOARD_UPDATE.value,
                    state.to_dict(),
                    source='engine'
                ))
            # 系统指标
            try:
                import psutil
                bus.publish(Event(
                    EventType.SYSTEM_METRICS.value, {
                        'cpu_pct': psutil.cpu_percent(interval=None),
                        'memory_pct': psutil.virtual_memory().percent,
                        'disk_pct': psutil.disk_usage('/').percent,
                    },
                    source='engine'
                ))
            except:
                pass
        except:
            pass



# ── 消息引擎：处理 GUI 发来的聊天消息 ──
async def message_engine():
    """Subscribe to MESSAGE_SENT events and generate responses."""
    bus = get_bus()
    last_id = 0
    session = None
    while True:
        await asyncio.sleep(0.3)
        history = getattr(bus, "_history", [])
        if not history or len(history) <= last_id:
            continue
        for i in range(last_id, len(history)):
            evt = history[i]
            if not hasattr(evt, "type"):
                continue
            if evt.type != EventType.MESSAGE_SENT.value:
                continue
            content = ""
            if hasattr(evt, "data") and isinstance(evt.data, dict):
                content = evt.data.get("content", "")
            if not content:
                continue
            if session is None:
                try:
                    from core.chat import ChatSession
                    from core.client import CruxClient
                    client = CruxClient()
                    session = ChatSession(client=client)
                except Exception as e:
                    bus.publish(Event(
                        EventType.MESSAGE_RECEIVED.value,
                        {"role": "assistant", "content": f"收到: {content}\n\n（提示：AI 模型未就绪 - {e}）"},
                        source="engine"
                    ))
                    continue
            try:
                reply = ""
                for kind, payload in session.send_stream(content):
                    if kind == "text":
                        reply += payload
                if reply:
                    bus.publish(Event(
                        EventType.MESSAGE_RECEIVED.value,
                        {"role": "assistant", "content": reply},
                        source="engine"
                    ))
                else:
                    bus.publish(Event(
                        EventType.MESSAGE_RECEIVED.value,
                        {"role": "assistant", "content": f"收到: {content}\n\n（模型未返回有效内容）"},
                        source="engine"
                    ))
            except Exception as e:
                bus.publish(Event(
                    EventType.MESSAGE_RECEIVED.value,
                    {"role": "assistant", "content": f"处理出错: {e}"},
                    source="engine"
                ))
        last_id = len(history)

async def main(port=9733):
    from websockets.server import serve

    # 初始状态
    bus = get_bus()
    bus.update_state(
        model="CRUX Studio v5.0 (deepseek-v4-flash)",
        streaming=False, thinking=False,
        context_pct=0.0, active_agents=0,
        tool_status="idle", comfyui_online=False,
    )
    bus.publish(Event(EventType.SESSION_STARTED.value,
        {"model": "CRUX Studio v6.0", "status": "ready", 
                     "version_info": get_version_info()}, source='engine'))

    http_server = await asyncio.start_server(http_handler, '0.0.0.0', port)
    ws_server = await serve(ws_handler, '0.0.0.0', port + 1)
    broadcast_task = asyncio.create_task(broadcast_loop())
    engine_task = asyncio.create_task(message_engine())
    heartbeat_task = asyncio.create_task(engine_heartbeat())

    print(f"\n{'='*50}")
    print("  CRUX 工作室 — 图形驾驶舱 v4")
    print(f"  HTTP: http://127.0.0.1:{port}")
    print(f"  WS:   ws://127.0.0.1:{port+1}")
    print(f"  Model: {get_bus().latest_state.model}")
    print(f"{'='*50}\n")

    await asyncio.gather(
        http_server.wait_closed(),
        ws_server.wait_closed(),
        broadcast_task,
        heartbeat_task,
        engine_task,
    )
if __name__ == '__main__':
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == '--port' else 9733
    asyncio.run(main(port))
