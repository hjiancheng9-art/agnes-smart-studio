"""一键流视频生成智能体 — 管道工具定义与执行器

Showrunner 总控脑调度这些工具完成端到端视频生产。
工具分为两类：
  - 思考型：由 Agnes 直接通过推理完成（分类、决策、文案重创、拆分镜等）
  - 执行型：需要实际代码操作（提取关键帧、保存文件、调用 API 等）
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# ── 项目输出根目录 ──
OUTPUT_ROOT = Path(__file__).parent.parent / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


# ============================================================
#  管道工具定义（OpenAI function calling 格式）
# ============================================================

PIPELINE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "extract_video_keyframes",
            "description": "从本地视频文件中提取关键帧画面。返回提取的关键帧文件路径列表和视频元信息。提取后在下一步用 AI 视觉理解关键帧内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {
                        "type": "string",
                        "description": "本地视频文件的完整路径"
                    },
                    "max_frames": {
                        "type": "integer",
                        "description": "最多提取的关键帧数量，默认 12",
                        "default": 12
                    },
                    "interval_seconds": {
                        "type": "number",
                        "description": "每隔多少秒取一帧，不指定则均匀采样",
                        "default": None
                    }
                },
                "required": ["video_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_project_manifest",
            "description": "将当前项目的资产清单、分镜脚本、文案等内容保存为结构化 JSON 文件，用于生产进度跟踪和恢复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "项目名称，用于创建输出目录"
                    },
                    "manifest": {
                        "type": "object",
                        "description": "项目清单 JSON 对象，包含 phase/stage/assets/shots 等字段"
                    }
                },
                "required": ["project_name", "manifest"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_file_exists",
            "description": "检查指定文件路径是否存在，用于验证资产是否已生成或导入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要检查的文件路径"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "列出当前项目的输出目录中的所有文件，用于进度检查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "项目名称"
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url_content",
            "description": "获取在线 URL 的内容信息，用于处理视频链接类型的输入。返回页面标题、描述和可用的媒体信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要获取内容的在线 URL"
                    }
                },
                "required": ["url"]
            }
        }
    }
]


# ============================================================
#  工具执行器
# ============================================================

def execute_extract_keyframes(video_path: str, max_frames: int = 12,
                               interval_seconds: Optional[float] = None) -> str:
    """从视频中提取关键帧

    使用 ffprobe 获取视频信息，使用 ffmpeg 提取均匀采样帧。
    如果没有 ffmpeg，返回错误提示。
    """
    video = Path(video_path)
    if not video.exists():
        return json.dumps({"error": f"视频文件不存在: {video_path}", "success": False}, ensure_ascii=False)

    # 检查 ffmpeg 是否可用
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return json.dumps({
            "error": "未找到 ffmpeg。请安装 ffmpeg 以启用视频关键帧提取功能。",
            "success": False,
            "hint": "可通过 `winget install ffmpeg` 或 `brew install ffmpeg` 安装"
        }, ensure_ascii=False)

    # 获取视频信息
    try:
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video)
        ], capture_output=True, text=True, timeout=15)
        info = json.loads(probe.stdout) if probe.returncode == 0 else {}
    except Exception:
        info = {}

    # 获取时长
    duration = 0
    if info:
        fmt = info.get("format", {})
        duration = float(fmt.get("duration", 0))
        # 如果是视频流，从 streams 中获取更准确的时长
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                d = stream.get("duration")
                if d:
                    duration = max(duration, float(d))
                break

    if duration <= 0:
        return json.dumps({
            "error": "无法确定视频时长，可能不是有效视频文件",
            "success": False
        }, ensure_ascii=False)

    # 计算采样间隔
    if interval_seconds and interval_seconds > 0:
        interval = interval_seconds
    else:
        interval = max(1, duration / max_frames)

    # 创建输出目录
    project = video.stem.replace(" ", "_")
    out_dir = OUTPUT_ROOT / "keyframes" / project
    out_dir.mkdir(parents=True, exist_ok=True)

    # 提取关键帧
    frame_paths = []
    timestamps = []
    t = interval  # 从 interval 开始，避免第一帧通常是黑屏

    while t < duration - 0.1 and len(frame_paths) < max_frames:
        out_path = out_dir / f"frame_{len(frame_paths):03d}_t{t:.1f}s.jpg"
        result = subprocess.run([
            "ffmpeg", "-y", "-ss", str(t), "-i", str(video),
            "-vframes", "1", "-q:v", "2", str(out_path)
        ], capture_output=True, text=True, timeout=30)

        if out_path.exists() and out_path.stat().st_size > 100:
            frame_paths.append(str(out_path))
            timestamps.append(round(t, 1))
        t += interval

    return json.dumps({
        "success": True,
        "video_path": str(video),
        "duration_seconds": round(duration, 1),
        "resolution": f"{info.get('streams', [{}])[0].get('width', '?')}x{info.get('streams', [{}])[0].get('height', '?')}" if info else "unknown",
        "frame_count": len(frame_paths),
        "sample_interval": round(interval, 1),
        "frames": [
            {"path": p, "timestamp": t}
            for p, t in zip(frame_paths, timestamps)
        ]
    }, ensure_ascii=False)


def execute_save_manifest(project_name: str, manifest: dict) -> str:
    """保存项目清单"""
    safe_name = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out_dir = OUTPUT_ROOT / "projects" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 添加时间戳
    from datetime import datetime
    manifest["saved_at"] = datetime.now().isoformat()
    manifest["project_name"] = project_name

    file_path = out_dir / "manifest.json"
    file_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return json.dumps({
        "success": True,
        "project_name": project_name,
        "manifest_path": str(file_path),
        "output_dir": str(out_dir)
    }, ensure_ascii=False)


def execute_check_file(file_path: str) -> str:
    """检查文件是否存在"""
    p = Path(file_path)
    exists = p.exists()
    result = {
        "exists": exists,
        "path": str(p.absolute()),
        "is_file": p.is_file() if exists else False,
    }
    if exists and p.is_file():
        result["size_bytes"] = p.stat().st_size
        result["extension"] = p.suffix
    return json.dumps(result, ensure_ascii=False)


def execute_list_files(project_name: str) -> str:
    """列出项目文件"""
    safe_name = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out_dir = OUTPUT_ROOT / "projects" / safe_name

    if not out_dir.exists():
        return json.dumps({
            "project_name": project_name,
            "exists": False,
            "files": []
        }, ensure_ascii=False)

    files = []
    for f in sorted(out_dir.rglob("*")):
        if f.is_file():
            files.append({
                "path": str(f.relative_to(out_dir)),
                "size_bytes": f.stat().st_size,
                "extension": f.suffix
            })

    return json.dumps({
        "project_name": project_name,
        "exists": True,
        "total_files": len(files),
        "files": files
    }, ensure_ascii=False)


def execute_fetch_url(url: str) -> str:
    """获取 URL 内容信息"""
    try:
        import httpx
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        content_type = resp.headers.get("content-type", "")

        result = {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": content_type,
            "content_length": len(resp.content),
            "is_video": any(t in content_type for t in ["video/", "application/octet-stream"]),
            "is_html": "text/html" in content_type,
        }

        # 如果是 HTML 页面，尝试提取标题
        if result["is_html"]:
            import re
            text = resp.text[:5000]
            title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE)
            if title_match:
                result["page_title"] = title_match.group(1).strip()

            # 提取 meta description
            desc_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
                text, re.IGNORECASE
            )
            if desc_match:
                result["page_description"] = desc_match.group(1).strip()

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "url": url,
            "error": str(e),
            "success": False
        }, ensure_ascii=False)


# ============================================================
#  工具名称 → 执行函数 映射表
# ============================================================

EXECUTOR_MAP = {
    "extract_video_keyframes": lambda **kw: execute_extract_keyframes(
        video_path=kw.get("video_path", ""),
        max_frames=kw.get("max_frames", 12),
        interval_seconds=kw.get("interval_seconds")
    ),
    "save_project_manifest": lambda **kw: execute_save_manifest(
        project_name=kw.get("project_name", "untitled"),
        manifest=kw.get("manifest", {})
    ),
    "check_file_exists": lambda **kw: execute_check_file(
        file_path=kw.get("file_path", "")
    ),
    "list_project_files": lambda **kw: execute_list_files(
        project_name=kw.get("project_name", "")
    ),
    "fetch_url_content": lambda **kw: execute_fetch_url(
        url=kw.get("url", "")
    ),
}
