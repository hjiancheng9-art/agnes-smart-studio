"""Download tool — /download <url>, /downloads, /download pending commands."""

from __future__ import annotations

import json
import urllib.request

from core.download.manager import get_manager
from core.download.models import DownloadKind, DownloadRequest

BRIDGE_URL = "http://127.0.0.1:4366"


def _progress_bar(pct: float, width: int = 12) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def _fetch_pending_media():
    """Fetch pending media from bridge server."""
    try:
        req = urllib.request.Request(BRIDGE_URL + "/download/pending")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", [])
    except Exception:
        return None


def _submit_download_from_media(candidate, page_url, title):
    """Submit a download from a media candidate."""
    req = DownloadRequest(
        url=candidate.get("url", ""),
        kind=_detect_kind(candidate.get("kind", "")),
        source="browser-detector",
    )
    manager = get_manager()
    job = manager.submit(req)
    return job


def _detect_kind(kind_str: str) -> DownloadKind:
    m = {"m3u8": DownloadKind.HLS, "mp4": DownloadKind.DIRECT,
         "dash": DownloadKind.DASH, "segment": DownloadKind.HLS}
    return m.get(kind_str, DownloadKind.UNKNOWN)


def handle_download_command(text: str, width: int, append_msg, append_err, _log_append) -> bool:
    """Handle /download, /downloads, /download pending commands."""
    parts = text.strip().split(" ", 2)
    cmd = parts[0]

    # ── /downloads — list all jobs ──
    if cmd == "/downloads":
        manager = get_manager()
        jobs = manager.list_jobs(50)

        append_msg("info", f" DOWNLOADS ({len(jobs)})\n")
        append_msg("muted", " JOB ID         STATUS      PROGRESS          SPEED      FILE\n")

        for j in jobs:
            pct = j.progress_pct()
            bar = _progress_bar(pct, 10)
            speed = j.speed_str() if j.status == "running" else ""
            row = f" {j.job_id:<14} {j.status:<10} {pct:>5.1f}%{bar} {speed:<10} {j.url[:40]}\n"
            append_msg("info", row)
        return True

    # ── /download pending — list detected media ──
    if cmd == "/download" and len(parts) > 1 and parts[1] == "pending":
        items = _fetch_pending_media()
        if items is None:
            append_err("Bridge server not running on port 4366")
            return True
        if not items:
            append_msg("info", " PENDING MEDIA\n")
            append_msg("muted", " No media detected yet.\n")
            return True

        # Parse optional index
        idx_arg = parts[2] if len(parts) > 2 else ""
        try:
            item_idx = int(idx_arg)
        except (ValueError, IndexError):
            item_idx = -1  # show all

        # If specific index requested, submit that download
        if item_idx >= 0 and item_idx < len(items):
            item = items[item_idx]
            candidates = item.get("candidates", [])
            if not candidates:
                append_err(f"No candidates in media item {item_idx}")
                return True
            # Pick first candidate with highest confidence
            best = max(candidates, key=lambda c: c.get("confidence", 0))
            job = _submit_download_from_media(best, item.get("page_url", ""), item.get("title", ""))
            _log_append(("↓", "class:activity-info", f"下载已排队: {job.job_id} {best.get('url','')[:48]}"))
            append_msg("info", "已提交下载\n")
            append_msg("muted", f" URL: {best.get('url','')}\n")
            return True

        # Show all pending media
        append_msg("info", f" PENDING MEDIA ({len(items)})\n")
        append_msg("muted", " Use /download pending <n> to download\n\n")
        for i, item in enumerate(items):
            url_preview = item.get("page_url", "")[:40] or "?"
            title = item.get("title", "")[:40] or "?"
            cand_count = len(item.get("candidates", []))
            append_msg("info", f" [{i}] {cand_count} candidates  {url_preview}  {title}\n")
            for ci, c in enumerate(item.get("candidates", [])):
                kind = c.get("kind", "?")
                conf = c.get("confidence", 0)
                curl = c.get("url", "")[:50]
                append_msg("muted", f"      [{ci}] {kind}  confidence {conf:.2f}  {curl}\n")
        return True

    # ── /download <url> — submit a new download ──
    if cmd == "/download":
        if len(parts) < 2 or not parts[1]:
            append_err("Usage: /download <url> [--name filename] [--dir path]")
            return True

        url = parts[1]
        filename = None
        output_dir = None

        tail = parts[2] if len(parts) > 2 else ""
        if "--name" in tail:
            nidx = tail.find("--name")
            rest = tail[nidx + 6:].strip()
            filename = rest.split(" ")[0].strip('"').strip("'")

        if "--dir" in tail:
            didx = tail.find("--dir")
            rest = tail[didx + 5:].strip()
            output_dir = rest.split(" ")[0].strip('"').strip("'")

        req = DownloadRequest(url=url, filename=filename,
                              output_dir=output_dir or None)
        manager = get_manager()
        job = manager.submit(req)
        _log_append(("↓", "class:activity-info", f"下载已排队: {job.job_id} {url[:48]}"))
        append_msg("info", f"已提交下载: {job.job_id}\n")
        append_msg("muted", f" URL: {url}\n")
        append_msg("muted", f" 类型: {job.kind.value}\n")
        if filename:
            append_msg("muted", f" 文件名: {filename}\n")
        return True

    return False
