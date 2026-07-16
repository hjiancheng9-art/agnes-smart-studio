#!/usr/bin/env python3
"""CRUX Native Messaging Host — stdin/stdout JSON bridge for browser-companion.

Protocol:
- Read: 4 bytes message length (little-endian uint32) → JSON payload
- Write: same format back to stdout

Replaces HTTP bridge as primary communication channel with Chrome extension.
Supports: task pulling, media detection forwarding, result submission.
"""

import json
import os
import struct
import sys
import threading
import time
import traceback
import urllib.request
from collections import deque
from pathlib import Path

from core.error_sink import catch

HOST_NAME = "com.crux.bridge"
PROTOCOL_VERSION = "1.0"

# ── message I/O ──


def read_message():
    """Read a JSON message from stdin (Native Messaging protocol)."""
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    msg_len = struct.unpack("<I", raw)[0]
    if msg_len > 1024 * 1024:  # 1MB max
        return None
    payload = sys.stdin.buffer.read(msg_len)
    return json.loads(payload.decode("utf-8"))


def write_message(data):
    """Write a JSON message to stdout (Native Messaging protocol)."""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(payload)))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def log(msg):
    """Log to file (stderr goes nowhere in NM, log to file instead)."""
    try:
        log_dir = Path.home() / ".crux" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(str(log_dir / "native_bridge.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception as _es:
        catch(_es, "core/browser-companion/native/native_host", "swallowed")


# ── State ──

PENDING_TASKS = deque(maxlen=50)
PENDING_MEDIA = deque(maxlen=200)
_lock = threading.Lock()

BRIDGE_HTTP = (
    os.environ.get(
        "BROWSER_COMPANION_BRIDGE_HTTP",
        "http://127.0.0.1:4366",
    )
    .strip()
    .rstrip("/")
)
OUTPUT_DIR = Path.home() / "Downloads" / "CRUX"


# ── Handlers ──


def handle_ping(msg):
    return {"type": "pong", "host": HOST_NAME, "version": PROTOCOL_VERSION}


def handle_get_tasks(msg):
    with _lock:
        tasks = list(PENDING_TASKS)
    return {"type": "tasks", "tasks": tasks}


def handle_submit_result(msg):
    task_id = msg.get("taskId", "?")
    result = msg.get("result", {})
    log(f"Result from task {task_id}")
    # Save to file for CRUX to pick up
    result_path = OUTPUT_DIR / ".." / "browser_result.json"
    try:
        with open(str(result_path), "w", encoding="utf-8") as f:
            json.dump({"taskId": task_id, "result": result}, f, ensure_ascii=False, indent=2)
        with _lock:
            # Remove from pending
            PENDING_TASKS[:] = [t for t in PENDING_TASKS if t.get("taskId") != task_id]
    except Exception as e:
        log(f"Save result error: {e}")
    return {"type": "result_ack", "taskId": task_id}


def handle_media_detected(msg):
    candidates = msg.get("candidates", [])
    item = {
        "id": f"media-{os.urandom(4).hex()}",
        "received_at": time.time(),
        "page_url": msg.get("pageUrl", ""),
        "title": msg.get("title", ""),
        "candidates": candidates,
    }
    with _lock:
        PENDING_MEDIA.appendleft(item)
    log(f"Media: {len(candidates)} candidates")
    return {"type": "media_ack", "id": item["id"], "count": len(PENDING_MEDIA)}


def handle_get_pending_media(msg):
    with _lock:
        items = list(PENDING_MEDIA)
    return {"type": "pending_media", "items": items}


def handle_forward_to_crux(msg):
    """Forward a message to CRUX HTTP bridge (for main CRUX to consume)."""
    action = msg.get("action", "")
    try:
        if action == "task/next":
            req = urllib.request.Request(BRIDGE_HTTP + "/api/browser-companion/tasks/next")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            task = data.get("task")
            if task:
                with _lock:
                    PENDING_TASKS.append(task)
            return {"type": "task", "task": task}
        return {"type": "error", "message": f"Unknown action: {action}"}
    except Exception as e:
        log(f"Forward error: {e}")
        return {"type": "error", "message": str(e)}


HANDLERS = {
    "ping": handle_ping,
    "get_tasks": handle_get_tasks,
    "submit_result": handle_submit_result,
    "media_detected": handle_media_detected,
    "get_pending_media": handle_get_pending_media,
    "forward": handle_forward_to_crux,
}


# ── Main loop ──


def main():
    log(f"Native host started (PID: {os.getpid()})")
    write_message({"type": "ready", "host": HOST_NAME, "pid": os.getpid()})

    while True:
        try:
            msg = read_message()
            if msg is None:
                break

            msg_type = msg.get("type", "")
            handler = HANDLERS.get(msg_type)
            if handler:
                try:
                    response = handler(msg)
                    write_message(response)
                except Exception as e:
                    log(f"Handler error: {e} {traceback.format_exc()}")
                    write_message({"type": "error", "message": str(e)})
            else:
                write_message({"type": "error", "message": f"Unknown type: {msg_type}"})

        except json.JSONDecodeError:
            log("Invalid JSON received")
            write_message({"type": "error", "message": "invalid_json"})
        except (BrokenPipeError, EOFError):
            log("Browser disconnected")
            break
        except Exception as e:
            log(f"Fatal: {e} {traceback.format_exc()}")
            break

    log("Native host exiting")


if __name__ == "__main__":
    main()
