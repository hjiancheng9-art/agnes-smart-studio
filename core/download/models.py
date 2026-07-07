"""Download data models — request, job, and status types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class DownloadKind(str, Enum):
    DIRECT = "direct"  # MP4, ZIP, EXE — aria2
    HLS = "hls"  # M3U8 — ffmpeg
    DASH = "dash"  # DASH — yt-dlp
    UNKNOWN = "unknown"


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class DownloadRequest:
    """A request to download something."""

    url: str
    kind: DownloadKind = DownloadKind.UNKNOWN
    output_dir: str | None = None
    filename: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    cookies_ref: str | None = None
    source: str = "manual"
    root_trace_id: str | None = None


@dataclass
class DownloadJob:
    """A tracked download job."""

    job_id: str
    url: str
    kind: DownloadKind
    status: JobStatus = "queued"
    engine: str = ""
    gid: str | None = None
    output_dir: str | None = None
    output_path: str | None = None
    total_bytes: int = 0
    completed_bytes: int = 0
    speed_bps: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def progress_pct(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, self.completed_bytes / self.total_bytes * 100.0)

    def speed_str(self) -> str:
        if self.speed_bps >= 1_000_000:
            return f"{self.speed_bps / 1_000_000:.1f}MB/s"
        elif self.speed_bps >= 1_000:
            return f"{self.speed_bps / 1_000:.0f}KB/s"
        return f"{self.speed_bps}B/s"

    def summary(self) -> str:
        pct = self.progress_pct()
        if self.status == "queued":
            return f"⏳ 排队中: {self.url[:48]}"
        elif self.status == "running":
            return f"↓ {pct:.0f}% {self.speed_str()} {self.url[:40]}"
        elif self.status == "completed":
            return f"✓ 完成: {self.output_path or self.url[:48]}"
        elif self.status == "failed":
            return f"✗ 失败: {self.error or self.url[:48]}"
        elif self.status == "cancelled":
            return f"■ 已取消: {self.url[:48]}"
        return f"• {self.status}: {self.url[:48]}"


def new_job_id() -> str:
    return f"dl-{uuid.uuid4().hex[:8]}"
