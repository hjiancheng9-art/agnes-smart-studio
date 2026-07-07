"""
V2 Bridge Server — 浏览器扩展后端 (port 4366)
CRUX AI 通过此服务驱动浏览器扩展，操控 ChatGPT/Gemini 等页面。
"""
import json
import threading
import time
import uuid

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 任务存储 (内存)
_tasks: dict[str, dict] = {}  # taskId -> task
_task_queue: list[str] = []   # FIFO queue of taskIds
_lock = threading.Lock()

# ============================================================
# CRUX → Bridge: 派发任务
# ============================================================

@app.route("/api/browser-companion/tasks/push", methods=["POST"])
def push_task():
    """CRUX 推送一个新任务"""
    data = request.get_json(force=True) or {}
    task_id = data.get("taskId") or str(uuid.uuid4())[:8]
    provider = data.get("provider", "chatgpt")
    prompt = data.get("prompt", "")
    url = data.get("url", "")

    task = {
        "taskId": task_id,
        "provider": provider,
        "prompt": prompt,
        "url": url or _default_url(provider),
        "status": "pending",
        "result": None,
        "createdAt": time.time(),
    }

    with _lock:
        _tasks[task_id] = task
        _task_queue.append(task_id)

    print(f"[Bridge] Task pushed: {task_id} → {provider}: {prompt[:80]}...")
    return jsonify({"ok": True, "task": task})


def _default_url(provider: str) -> str:
    return {
        "chatgpt": "https://chatgpt.com/",
        "gemini": "https://gemini.google.com/",
        "kling": "https://klingai.com/",
        "jimeng": "https://jimeng.jianying.com/",
        "runway": "https://runwayml.com/",
        "luma": "https://lumalabs.ai/",
    }.get(provider, "https://chatgpt.com/")


# ============================================================
# Extension → Bridge: 拉取任务 / 提交结果
# ============================================================

@app.route("/api/browser-companion/tasks/next", methods=["GET"])
def pull_next_task():
    """扩展拉取下一个待处理任务"""
    with _lock:
        if _task_queue:
            task_id = _task_queue.pop(0)
            task = _tasks.get(task_id)
            if task:
                task["status"] = "dispatched"
                print(f"[Bridge] Task dispatched: {task_id}")
                return jsonify({"task": task})
        return jsonify({"task": None})


@app.route("/api/browser-companion/tasks/<task_id>/status", methods=["POST"])
def update_status(task_id):
    """扩展报告任务状态"""
    data = request.get_json(force=True) or {}
    status = data.get("status") or data.get("payload", {}).get("status", "unknown")
    with _lock:
        if task_id in _tasks:
            _tasks[task_id]["status"] = status
            _tasks[task_id]["note"] = data.get("payload", {}).get("note", "")
            print(f"[Bridge] Task {task_id} status: {status}")
    return jsonify({"ok": True})


@app.route("/api/browser-companion/tasks/<task_id>/result", methods=["POST"])
def submit_result(task_id):
    """扩展回传任务结果"""
    data = request.get_json(force=True) or {}
    with _lock:
        if task_id in _tasks:
            _tasks[task_id]["result"] = data
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["completedAt"] = time.time()
            print(f"[Bridge] Task {task_id} COMPLETED: {json.dumps(data, ensure_ascii=False)[:200]}")
    return jsonify({"ok": True})


# ============================================================
# CRUX → Bridge: 查询状态
# ============================================================

@app.route("/api/browser-companion/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return jsonify({"error": "not found"}), 404
        return jsonify({"task": task})


@app.route("/api/browser-companion/tasks", methods=["GET"])
def list_tasks():
    with _lock:
        return jsonify({"tasks": list(_tasks.values()), "queue": list(_task_queue)})


@app.route("/api/browser-companion/status", methods=["GET"])
def bridge_status():
    with _lock:
        return jsonify({
            "total": len(_tasks),
            "pending": sum(1 for t in _tasks.values() if t["status"] == "pending"),
            "dispatched": sum(1 for t in _tasks.values() if t["status"] == "dispatched"),
            "completed": sum(1 for t in _tasks.values() if t["status"] == "completed"),
            "queue_len": len(_task_queue),
        })


if __name__ == "__main__":
    print("[Bridge] V2 Bridge Server starting on http://127.0.0.1:4366 ...")
    app.run(host="127.0.0.1", port=4366, debug=False)
