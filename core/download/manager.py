"""DownloadManager — orchestrates engines and tracks jobs."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Callable

from core.error_sink import catch

from core.download.models import (
    DownloadKind,
    DownloadRequest,
    DownloadJob,
    new_job_id,
)
from core.download.engines.aria2_engine import Aria2Engine, Aria2Config
from core.download.engines.ffmpeg_engine import FFmpegEngine
from core.download.engines.ytdlp_engine import YtdlpEngine
from core.download.config import load_config

DEFAULT_DIR = os.path.expanduser("~/Downloads/CRUX")


class DownloadManager:
    """Manages download jobs, engine selection, and progress tracking."""

    def __init__(self, download_dir: str | None = None):
        self._cfg = load_config()
        self.download_dir = download_dir or self._cfg.default_dir
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()
        self._aria2 = Aria2Engine(
            Aria2Config(
                rpc_url=self._cfg.aria2.rpc_url,
                rpc_secret=self._cfg.aria2.rpc_secret,
                aria2c_path=self._cfg.aria2.path,
                split=self._cfg.aria2.split,
                max_connection_per_server=self._cfg.aria2.max_connection_per_server,
            )
        )
        self._ffmpeg = FFmpegEngine()
        self._ytdlp = YtdlpEngine()
        self._on_update: Callable | None = None

    def on_update(self, callback: Callable) -> None:
        self._on_update = callback

    def submit(self, req: DownloadRequest) -> DownloadJob:
        kind = req.kind if req.kind != DownloadKind.UNKNOWN else self._detect_kind(req.url)
        job = DownloadJob(
            job_id=new_job_id(),
            url=req.url,
            kind=kind,
            status="queued",
            output_dir=req.output_dir or self.download_dir,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._trigger_update(job)
        self._execute(job, req)
        return job

    def list_jobs(self, limit: int = 20) -> list[DownloadJob]:
        with self._lock:
            all_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
            return all_jobs[:limit]

    def get_job(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status in ("completed", "cancelled"):
                return False
            job.status = "cancelled"
            job.updated_at = datetime.now()
        self._trigger_update(job)
        return True

    def _execute(self, job: DownloadJob, req: DownloadRequest) -> None:
        os.makedirs(job.output_dir, exist_ok=True)
        try:
            if job.kind == DownloadKind.DIRECT:
                self._execute_aria2(job, req)
            elif job.kind == DownloadKind.HLS:
                self._execute_ffmpeg(job, req)
            elif job.kind == DownloadKind.DASH:
                self._execute_ytdlp(job, req)
            else:
                self._execute_aria2(job, req)
        except Exception as e:
            with self._lock:
                job.status = "failed"
                job.error = str(e)
                job.updated_at = datetime.now()
            self._trigger_update(job)

    def _execute_aria2(self, job: DownloadJob, req: DownloadRequest) -> None:
        filename = req.filename
        out = filename or os.path.basename(req.url.split("?")[0]) or None
        gid = self._aria2.add_uri(
            req.url,
            out=out,
            dir=job.output_dir,
            headers=req.headers,
        )
        with self._lock:
            job.status = "running"
            job.engine = "aria2"
            job.gid = gid
            job.updated_at = datetime.now()
        self._trigger_update(job)

        # Poll progress
        for _ in range(3600):
            with self._lock:
                if job.status in ("cancelled", "failed"):
                    return
            try:
                info = self._aria2.tell_status(gid)
                with self._lock:
                    job.total_bytes = int(info.get("totalLength", 0) or 0)
                    job.completed_bytes = int(info.get("completedLength", 0) or 0)
                    job.speed_bps = int(info.get("downloadSpeed", 0) or 0)
                    if info.get("status") == "complete":
                        job.status = "completed"
                        # Find actual output file from response
                        files = info.get("files", [])
                        if files:
                            job.output_path = files[0].get("path")
                        job.updated_at = datetime.now()
                        self._trigger_update(job)
                        return
                    elif info.get("status") == "error":
                        job.status = "failed"
                        job.error = info.get("errorMessage", "unknown aria2 error")
                        job.updated_at = datetime.now()
                        self._trigger_update(job)
                        return
                    job.updated_at = datetime.now()
                self._trigger_update(job)
            except Exception as _es:
                catch(_es, "core/download/manager", "swallowed")
            time.sleep(1)

    def _execute_ffmpeg(self, job: DownloadJob, req: DownloadRequest) -> None:
        filename = req.filename or f"download_{job.job_id}.mp4"
        output = os.path.join(job.output_dir, filename)
        proc = self._ffmpeg.download(req.url, output, headers=req.headers)
        with self._lock:
            job.status = "running"
            job.engine = "ffmpeg"
            job.updated_at = datetime.now()
        self._trigger_update(job)

        for line in iter(proc.stderr.readline, ""):
            with self._lock:
                if job.status == "cancelled":
                    self._ffmpeg.stop()
                    return
            info = FFmpegEngine.parse_progress(line)
            if info and info["type"] == "size":
                with self._lock:
                    job.completed_bytes = info["kb"] * 1024
                    job.updated_at = datetime.now()
                self._trigger_update(job)

        rc = proc.wait()
        with self._lock:
            if rc == 0:
                job.status = "completed"
                job.output_path = output
            else:
                job.status = "failed"
                job.error = f"ffmpeg exit {rc}"
            job.updated_at = datetime.now()
        self._trigger_update(job)

    def _execute_ytdlp(self, job: DownloadJob, req: DownloadRequest) -> None:
        proc = self._ytdlp.download(
            req.url,
            output_dir=job.output_dir,
            filename=req.filename,
            headers=req.headers,
        )
        with self._lock:
            job.status = "running"
            job.engine = "yt-dlp"
            job.updated_at = datetime.now()
        self._trigger_update(job)

        for line in iter(proc.stdout.readline, ""):
            with self._lock:
                if job.status == "cancelled":
                    self._ytdlp.stop()
                    return
            parsed = YtdlpEngine.parse_json_line(line)
            if parsed:
                with self._lock:
                    job.total_bytes = int(parsed.get("total_bytes", 0) or 0)
                    job.completed_bytes = int(parsed.get("downloaded_bytes", 0) or 0)
                    job.speed_bps = int(parsed.get("speed", 0) or 0)
                    job.updated_at = datetime.now()
                self._trigger_update(job)

        rc = proc.wait()
        with self._lock:
            if rc == 0:
                job.status = "completed"
            else:
                job.status = "failed"
                job.error = f"yt-dlp exit {rc}"
            job.updated_at = datetime.now()
        self._trigger_update(job)

    @staticmethod
    def _detect_kind(url: str) -> DownloadKind:
        lower = url.lower()
        if ".m3u8" in lower:
            return DownloadKind.HLS
        if ".mpd" in lower or "dash" in lower:
            return DownloadKind.DASH
        if any(ext in lower for ext in [".mp4", ".zip", ".exe", ".tar.gz", ".7z", ".rar", ".mov", ".webm"]):
            return DownloadKind.DIRECT
        if "youtube" in lower or "youtu.be" in lower or "bilibili" in lower:
            return DownloadKind.DASH
        return DownloadKind.DIRECT

    def _trigger_update(self, job: DownloadJob) -> None:
        if self._on_update:
            try:
                self._on_update(job)
            except Exception as _es:
                catch(_es, "core/download/manager", "swallowed")


# Global singleton
_manager: DownloadManager | None = None


def get_manager() -> DownloadManager:
    global _manager
    if _manager is None:
        _manager = DownloadManager()
    return _manager
