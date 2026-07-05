"""
V2 Browser Companion Bridge Server

本地 HTTP 服务器，供浏览器扩展轮询任务和回传结果。
浏览器扩展拉取 → 用户操作 → 结果回传 CRUX Studio。

Port: 4366
"""
import json
import uuid
import time
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler

TASKS = []
PENDING_MEDIA = deque(maxlen=200)


class BridgeHandler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        path = self.path

        if path == "/api/browser-companion/tasks/next":
            task = TASKS[0] if TASKS else None
            self._json({"task": task})

        elif path == "/api/browser-companion/health":
            self._json({"status": "ok", "tasks": len(TASKS), "pending_media": len(PENDING_MEDIA)})

        elif path == "/api/browser-companion/tasks":
            self._json({"tasks": TASKS})

        elif path == "/download/pending":
            self._json({"items": list(PENDING_MEDIA)})

        else:
            self._json({"error": "not_found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        path = self.path

        # ── Media detection ──
        if "/media" in path:
            candidates = body.get("candidates", [])
            item = {
                "id": "media-" + uuid.uuid4().hex[:8],
                "received_at": time.time(),
                "page_url": body.get("pageUrl", ""),
                "title": body.get("title", ""),
                "candidates": candidates,
            }
            PENDING_MEDIA.appendleft(item)
            print(f"[MEDIA] {len(candidates)} candidates from {item['page_url'][:60]}")
            for i, c in enumerate(candidates):
                print(f"  [{i}] {c.get('kind','?')} {c.get('url','?')[:80]}")
            self._json({"ok": True, "id": item["id"], "count": len(PENDING_MEDIA)})
            return

        # ── Task result ──
        if "/result" in path:
            parts = [p for p in path.split("/") if p]
            tid = parts[-2] if len(parts) >= 5 else None
            result = body.get("result", body)
            save_path = r"C:\Users\huangjiancheng\agnes-smart-studio\output\browser_result.json"
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({"taskId": tid, "result": result}, f, ensure_ascii=False, indent=2)
            print(f"[RESULT] Task {tid}")
            global TASKS
            TASKS = [t for t in TASKS if t["taskId"] != tid]
            self._json({"ok": True})
            return

        self._json({"error": "not_found"}, 404)

    def log_message(self, *args):
        pass


def add_task(task_dict):
    if "taskId" not in task_dict:
        task_dict["taskId"] = "task-" + uuid.uuid4().hex[:8]
    TASKS.append(task_dict)
    print(f"[ADD] {task_dict['taskId']} -> {task_dict.get('targetUrl')}")


def serve():
    server = HTTPServer(("127.0.0.1", 4366), BridgeHandler)
    print(f"Bridge server on http://127.0.0.1:4366")
    print(f"  GET  /download/pending  — view detected media")
    server.serve_forever()


if __name__ == "__main__":
    serve()
