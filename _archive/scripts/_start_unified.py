"""
CRUX Studio — 双形态统一启动器
================================
同一进程内同时启动 GUI 服务器 + TUI 终端会话，
共享同一个 EventBus，状态实时同步。

用法:
    python _start_unified.py              # GUI + TUI 同时启动 (共享总线)
    python _start_gui.py                  # 仅 GUI (独立进程)
    python ui/tui_v2.py                   # 仅 TUI (独立进程)
    
双进程模式: 各自有独立 EventBus，不互通。
统一模式:   同一进程，共享总线，实时同步。
"""
import asyncio
import os
import sys
import threading

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.protocol import Event, EventType, get_bus


def run_tui_in_thread():
    """Run TUI in a separate thread with its own event loop."""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    _asyncio.set_event_loop(loop)

    # Import TUI (this will share the in-process protocol bus singleton)
    from ui.tui_v2 import TuiAppV2

    # Create and run the app
    try:
        app = TuiAppV2()
        app.run()
    except Exception as e:
        print(f"TUI error: {e}")
    finally:
        loop.close()


async def run_gui(port=9733):
    """Start GUI server in current event loop."""
    from ui.gui_server import main as gui_main
    await gui_main(port=port)


async def main():
    mode = "both"
    if len(sys.argv) > 1:
        mode = sys.argv[1].lstrip('-').lower()

    port = 9733
    if len(sys.argv) > 2:
        port = int(sys.argv[2])

    if mode == "gui":
        await run_gui(port)
    elif mode == "tui":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        run_tui_in_thread()
        loop.run_forever()
    else:  # both — unified mode
        # Warm up the protocol bus
        bus = get_bus()
        bus.update_state(
            model="CRUX Studio v5.0 (deepseek-v4-flash)",
            streaming=False,
            thinking=False,
            context_pct=0.0,
            active_agents=0,
            tool_status="idle",
            comfyui_online=False,
        )
        bus.publish(Event(
            EventType.SESSION_STARTED.value,
            {"model": "CRUX Studio v5.0", "status": "ready"},
            source="engine"
        ))

        print(f"\n{'='*55}")
        print("  🐉 CRUX Studio — 双形态统一模式")
        print("")
        print(f"  GUI: http://127.0.0.1:{port}")
        print("  TUI: 终端会话已启动")
        print("  Bus: 💚 共享 EventBus，状态实时同步")
        print(f"{'='*55}\n")

        # Start TUI in thread
        tui_thread = threading.Thread(target=run_tui_in_thread, daemon=True)
        tui_thread.start()

        # Start GUI in asyncio
        await run_gui(port)


if __name__ == '__main__':
    asyncio.run(main())
