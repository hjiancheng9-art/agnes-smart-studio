"""V2 Browser Companion Bridge Server - 连接Edge浏览器中的插件"""
import json
import uuid
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# 任务存储（全局）
TASKS = []
TASKS.append({
    "taskId": "task-chatgpt-read-" + uuid.uuid4().hex[:8],
    "type": "read_chat",
    "targetUrl": "https://chatgpt.com",
    "prompt": "请读取当前ChatGPT页面上的对话内容，包括所有用户的提问和GPT的回复。",
    "instruction": "从当前ChatGPT页面获取完整对话历史，返回格式为JSON数组，每项含role和content字段。",
    "source": "crux-studio"
})

def save_result(tid, result):
    result_path = r"C:\Users\huangjiancheng\agnes-smart-studio\output\v2_bridge_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({"taskId": tid, "result": result}, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] 结果已保存到 {result_path}")
    print(f"[RESULT] {json.dumps(result, ensure_ascii=False)[:500]}")

def remove_task(tid):
    global TASKS
    TASKS = [t for t in TASKS if t["taskId"] != tid]

class V2BridgeHandler(BaseHTTPRequestHandler):
    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def do_OPTIONS(self):
        self._json_response({})
    
    def do_GET(self):
        if self.path == "/api/browser-companion/tasks/next":
            task = TASKS[0] if TASKS else None
            self._json_response({"task": task})
            if task:
                print(f"[PULL] 插件拉取了任务: {task['taskId']}")
        elif self.path == "/api/browser-companion/health":
            self._json_response({"status": "ok", "tasks_queued": len(TASKS)})
        elif self.path == "/api/browser-companion/tasks":
            self._json_response({"tasks": TASKS})
        else:
            self._json_response({"error": "not_found"}, 404)
    
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        
        path = self.path
        
        if path == "/api/browser-companion/tasks/create":
            task = {
                "taskId": body.get("taskId", "task-" + uuid.uuid4().hex[:8]),
                "type": body.get("type", "custom"),
                "targetUrl": body.get("targetUrl", "https://chatgpt.com"),
                "prompt": body.get("prompt", ""),
                "instruction": body.get("instruction", ""),
                "source": "crux-studio"
            }
            TASKS.append(task)
            print(f"[CREATE] 新任务创建: {task['taskId']} -> {task.get('targetUrl')}")
            self._json_response({"ok": True, "task": task})
            return
        
        if "/status" in path:
            parts = [p for p in path.split("/") if p]
            tid = parts[-2] if len(parts) >= 5 else None
            status = body.get("status", body)
            print(f"[STATUS] Task {tid}: {status}")
            self._json_response({"ok": True})
        
        elif "/result" in path:
            parts = [p for p in path.split("/") if p]
            tid = parts[-2] if len(parts) >= 5 else None
            result = body.get("result", body)
            print(f"\n{'='*60}")
            print(f"[RESULT] Task {tid} 收到结果!")
            print(f"{'='*60}")
            save_result(tid, result)
            remove_task(tid)
            print(f"[DONE] 剩余任务: {len(TASKS)}")
            self._json_response({"ok": True})
        
        elif "/error" in path:
            parts = [p for p in path.split("/") if p]
            tid = parts[-2] if len(parts) >= 5 else None
            print(f"[ERROR] Task {tid}: {body}")
            self._json_response({"ok": True})
        
        else:
            self._json_response({"error": "not_found"}, 404)
    
    def log_message(self, format, *args):
        pass

def main():
    server = HTTPServer(("127.0.0.1", 4366), V2BridgeHandler)
    print(f"{'='*50}")
    print(f"  V2 Browser Companion Bridge Server")
    print(f"  http://127.0.0.1:4366")
    print(f"{'='*50}")
    print(f"  已预置 1 个任务：读取ChatGPT对话")
    print(f"  请在Edge插件中点击 [Pull task] 拉取")
    print(f"{'='*50}")
    server.serve_forever()

if __name__ == "__main__":
    main()
