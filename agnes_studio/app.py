"""
Agnes 多模态工作室 — Flask 后端
提供图片生成 / 视频生成 / 视频查询 API
"""

import logging
import os
from pathlib import Path

from agnes_client import (
    IMAGE_SIZE_PRESETS,
    VIDEO_DURATION_PRESETS,
    VIDEO_RESOLUTION_PRESETS,
    AgnesClient,
    AgnesConfig,
)
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
CORS(app, origins=[r"http://127\.0\.0\.1:\d+", r"http://localhost:\d+"])
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("agnes-studio")


def get_client() -> AgnesClient:
    api_key = os.environ.get("AGNES_API_KEY", "")
    return AgnesClient(AgnesConfig(api_key=api_key))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


@app.route("/api/config")
def api_config():
    return jsonify(
        {
            "image_sizes": IMAGE_SIZE_PRESETS,
            "video_resolutions": VIDEO_RESOLUTION_PRESETS,
            "video_durations": VIDEO_DURATION_PRESETS,
            "video_models": {
                "v2-fast": {"label": "v2.0 Fast", "value": "agnes-video-v2-fast"},
                "v2-pro": {"label": "v2.0 Pro", "value": "agnes-video-v2-pro"},
                "v1": {"label": "v1 兼容", "value": "agnes-video-v1"},
            },
            "has_api_key": bool(os.environ.get("AGNES_API_KEY")),
        }
    )


@app.route("/api/image/generate", methods=["POST"])
def api_image_generate():
    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "请输入提示词"}), 400

    client = get_client()
    size = data.get("size", "1024x1024")
    if data.get("custom_width") and data.get("custom_height"):
        size = f"{data['custom_width']}x{data['custom_height']}"

    image_url = data.get("image_url", "").strip()

    if image_url:
        log.info("图生图: %s, size=%s", prompt[:50], size)
        result = client.image_to_image(
            prompt=prompt,
            image_url=image_url,
            size=size,
            strength=data.get("strength", 0.7),
            seed=data.get("seed"),
        )
    else:
        log.info("文生图: %s, size=%s", prompt[:50], size)
        result = client.text_to_image(
            prompt=prompt,
            size=size,
            quality=data.get("quality", "standard"),
            style=data.get("style", "vivid"),
            seed=data.get("seed"),
        )
    return _format_response(result, "image")


@app.route("/api/video/generate", methods=["POST"])
def api_video_generate():
    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "请输入提示词"}), 400

    client = get_client()
    image_url = data.get("image_url", "").strip()
    model = data.get("model", "agnes-video-v2-fast")

    if image_url:
        log.info("图生视频: %s, model=%s", prompt[:50], model)
        result = client.image_to_video(
            prompt=prompt,
            image_url=image_url,
            model=model,
            width=data.get("width", 1280),
            height=data.get("height", 720),
            duration=data.get("duration", 5),
            fps=data.get("fps", 24),
            seed=data.get("seed"),
        )
    else:
        log.info("文生视频: %s, model=%s", prompt[:50], model)
        result = client.text_to_video(
            prompt=prompt,
            model=model,
            width=data.get("width", 1280),
            height=data.get("height", 720),
            duration=data.get("duration", 5),
            fps=data.get("fps", 24),
            seed=data.get("seed"),
            negative_prompt=data.get("negative_prompt", ""),
        )
    return _format_response(result, "video")


@app.route("/api/video/query", methods=["POST"])
def api_video_query():
    data = request.get_json() or {}
    video_id = data.get("video_id", "").strip()
    if not video_id:
        return jsonify({"error": "请输入 video_id"}), 400

    client = get_client()
    log.info("查询视频: %s", video_id)
    result = client.query_video(video_id)
    return _format_response(result, "video_query")


@app.route("/api/set-key", methods=["POST"])
def api_set_key():
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    if api_key:
        os.environ["AGNES_API_KEY"] = api_key
        return jsonify({"ok": True, "message": "API Key 已设置"})
    return jsonify({"error": "API Key 不能为空"}), 400


def _format_response(result: dict, kind: str) -> dict:
    if result.get("error"):
        return {"ok": False, "error": result["error"], "raw": result}

    images = []
    if "data" in result:
        for item in result["data"]:
            if "url" in item:
                images.append(item["url"])
            elif "b64_json" in item:
                images.append(f"data:image/png;base64,{item['b64_json']}")

    video_id = result.get("video_id") or result.get("id") or result.get("task_id")

    return {
        "ok": True,
        "kind": kind,
        "images": images,
        "video_id": video_id,
        "status": result.get("status", "unknown"),
        "video_url": result.get("url") or result.get("video_url"),
        "raw": result,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    print("\n  🔥 Agnes 多模态工作室 v2.0")
    print(f"  📍 http://127.0.0.1:{port}")
    print(f"  🔑 API Key: {'已配置' if os.environ.get('AGNES_API_KEY') else '未配置'}")
    print()
    app.run(host="0.0.0.0", port=port, debug=True)
