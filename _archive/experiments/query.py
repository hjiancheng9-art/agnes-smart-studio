#!/usr/bin/env python3
"""CRUX 视频查询工具 — 自动发现 + 状态追踪 + 一键下载

用法:
    python query.py                         # 交互式选择最近视频
    python query.py VIDEO_ID                # 查询指定视频
    python query.py VIDEO_ID --watch        # 自动轮询直到完成
    python query.py VIDEO_ID --watch 10     # 每10秒轮询
    python query.py --list                  # 列出历史视频
"""

import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
HISTORY_FILE = OUTPUT / "history.json"

# ── Rich theme (fallback after UI removal) ──
from rich.console import Console as _RC

console = _RC()
COLORS = {
    "success": "green", "error": "red", "warning": "yellow",
    "primary": "blue", "muted": "dim white", "info": "cyan",
}


def _clean_video_id(raw: str) -> str:
    """清洗 litellm base64 包装的 video_id"""
    if not raw or not raw.startswith("video_"):
        return raw
    try:
        b64 = raw[6:]
        decoded = base64.b64decode(b64).decode("utf-8")
        if "video_id:" in decoded:
            idx = decoded.rfind("video_id:")
            return decoded[idx + len("video_id:") :]
    except (ValueError, UnicodeDecodeError):
        pass
    return raw


def _load_history() -> list[dict]:
    """从 history.json 加载视频任务"""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        records = data.get("records", []) if isinstance(data, dict) else data
        if isinstance(records, dict):
            records = list(records.values())
        return records
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []


def _find_recent_videos(limit: int = 20) -> list[dict]:
    """找到最近有 video_id 的任务"""
    records = _load_history()
    videos = []
    for r in records:
        result = r.get("result", {})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                result = {}

        # video_id 可能在 result.video.video_id 或 result.video_id
        vid = ""
        if isinstance(result, dict):
            video_part = result.get("video", {})
            if isinstance(video_part, dict):
                vid = video_part.get("video_id", "")
            if not vid:
                vid = result.get("video_id", "")

        vid = _clean_video_id(vid)
        if vid and vid.startswith("video_"):
            prompt = r.get("prompt", "") or ""
            # pipeline 类型的 prompt 可能在 result.image 里
            if not prompt and isinstance(result, dict):
                img = result.get("image", {})
                if isinstance(img, dict):
                    prompt = img.get("prompt", "")
            videos.append(
                {
                    "video_id": vid,
                    "prompt": prompt[:60] if prompt else "(no prompt)",
                    "status": "ready",
                    "ts": r.get("created_at", ""),
                    "model": r.get("model", ""),
                }
            )
    videos.sort(key=lambda v: v["ts"])
    return videos[-limit:]  # 最新的在最后


def _query(client: httpx.Client, video_id: str) -> dict | None:
    """查询单个视频状态"""
    try:
        r = client.get(
            "https://apihub.agnes-ai.com/agnesapi",
            params={"video_id": video_id},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except (httpx.HTTPError, OSError):
        pass
    return None


def _download(url: str, save_path: str) -> bool:
    """下载视频文件（不带认证头，CDN 不需要）"""
    try:
        r = httpx.get(url, timeout=120, follow_redirects=True)
        if r.status_code == 200:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(r.content)
            return True
    except (httpx.HTTPError, OSError) as e:
        console.print(f"  [{COLORS['error']}]Download exception: {e}[/]")
    return False


def _format_status(data: dict) -> str:
    """格式化视频状态为一行"""
    status = data.get("status", "?")
    progress = data.get("progress", 0)
    emoji = {"completed": "✅", "failed": "❌", "processing": "🔄", "queued": "⏳"}.get(status, "❓")
    line = f"  {emoji} {status:12} {progress:3.0f}%"
    if data.get("seconds"):
        line += f"  {data['seconds']}s"
    if data.get("size"):
        line += f"  {data['size']}"
    return line


# ════════════════════════════════════════════════
# 交互模式
# ════════════════════════════════════════════════


def _interactive(client: httpx.Client):
    """交互式查询最近视频"""
    videos = _find_recent_videos()
    if not videos:
        console.print(f"\n  [{COLORS['warning']}]No video tasks in history[/]\n")
        return

    console.print(f"\n  [bold]Recent video tasks ({len(videos)}):[/]\n")
    for i, v in enumerate(videos, 1):
        console.print(f"  [{COLORS['primary']}]{i}[/]  {v['prompt'][:50]}")
        console.print(f"     [{COLORS['muted']}]{v['video_id'][:50]}...[/]")
        console.print(f"     [{COLORS['muted']}]{v['ts'][:19]}[/]")
        console.print()

    console.print(f"  [{COLORS['primary']}]0[/]  Exit")
    console.print(f"  [{COLORS['primary']}]v <ID>[/] Enter video_id directly")
    console.print()

    choice = input(f"  Choose (1-{len(videos)}): ").strip()

    if choice == "0" or not choice:
        return

    if choice.startswith("v ") or choice.startswith("video_"):
        vid = _clean_video_id(choice[2:] if choice.startswith("v ") else choice)
        _query_and_display(client, vid)
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(videos):
            _query_and_display(client, videos[idx]["video_id"])
    except ValueError:
        console.print(f"  [{COLORS['error']}]Invalid choice[/]")


def _query_and_display(client: httpx.Client, video_id: str, watch: bool = False, interval: int = 5):
    """查询并显示结果，可选轮询"""
    vid = _clean_video_id(video_id)
    console.print(f"\n  [{COLORS['muted']}]Query: {vid[:60]}...[/]\n")

    if watch:
        console.print(f"  [{COLORS['muted']}]Polling (every {interval}s), Ctrl+C to stop...[/]\n")
        try:
            while True:
                data = _query(client, vid)
                if data:
                    print(f"\r{_format_status(data)}", end="", flush=True)
                    status = data.get("status", "")
                    if status in ("completed", "failed"):
                        print()
                        _handle_result(data, vid)
                        return
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print(f"\n  [{COLORS['warning']}]Polling stopped[/]")
    else:
        data = _query(client, vid)
        if data:
            print(_format_status(data))
            print()
            _handle_result(data, vid)
        else:
            console.print(f"  [{COLORS['error']}]Query failed[/]")


def _handle_result(data: dict, video_id: str):
    """处理查询结果——提示下载"""
    status = data.get("status", "")
    if status == "completed":
        url = data.get("video_url") or data.get("remixed_from_video_id", "")
        if url and url.startswith("http"):
            console.print(f"  [{COLORS['success']}]Video completed![/]")
            console.print(f"  [{COLORS['primary']}]Download? [y/n][/] ", end="")
            dl = input().strip().lower()
            if dl == "y":
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = str(OUTPUT / "videos" / f"vid_{ts}.mp4")
                console.print(f"  [{COLORS['muted']}]Downloading...[/]")
                if _download(url, path):
                    console.print(f"  [{COLORS['success']}]Saved: {path}[/]")
                else:
                    console.print(f"  [{COLORS['error']}]Download failed[/]")
            else:
                console.print(f"  [{COLORS['muted']}]Video URL: {url}[/]")
        else:
            console.print(f"  [{COLORS['warning']}]No download link[/]")
    elif status == "failed":
        err = data.get("error", "Unknown error")
        console.print(f"  [{COLORS['error']}]Generation failed: {err}[/]")
    else:
        console.print(f"  [{COLORS['warning']}]Still processing, add --watch for auto-polling[/]")


# ════════════════════════════════════════════════
# CLI 模式
# ════════════════════════════════════════════════


def main():
    console.print(f"\n  [bold {COLORS['primary']}]CRUX Video Query[/]\n")

    # Load config
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("CRUX_API_KEY") or os.getenv("AGNES_API_KEY", "")
    if not api_key:
        console.print(f"  [{COLORS['error']}]CRUX_API_KEY not set[/]\n")
        sys.exit(1)

    with httpx.Client(headers={"Authorization": f"Bearer {api_key}"}) as client:
        args = sys.argv[1:]
        video_id = None
        watch = False
        interval = 5
        list_only = False

        i = 0
        while i < len(args):
            a = args[i]
            if a == "--watch":
                watch = True
                if i + 1 < len(args) and args[i + 1].isdigit():
                    i += 1
                    interval = int(args[i])
            elif a == "--list":
                list_only = True
            elif a.startswith("video_") or not a.startswith("-"):
                video_id = _clean_video_id(a)
            i += 1

        if list_only:
            videos = _find_recent_videos(20)
            console.print(f"  [bold]History ({len(videos)}):[/]\n")
            for v in videos:
                console.print(f"  [{COLORS['primary']}]{v['video_id'][:50]}...[/]")
                console.print(f"  [{COLORS['muted']}]{v['prompt'][:60]}[/]")
                console.print(f"  [{COLORS['muted']}]{v['ts'][:19]}[/]\n")
            return

        if video_id:
            _query_and_display(client, video_id, watch=watch, interval=interval)
        else:
            _interactive(client)

    client.close()


if __name__ == "__main__":
    main()
