"""FFmpeg engine — HLS/M3U8 stream download."""

from __future__ import annotations

import subprocess
import re


class FFmpegEngine:
    """Download HLS/M3U8 streams using ffmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._proc: subprocess.Popen | None = None

    def download(self, url: str, output: str, headers: dict[str, str] | None = None) -> subprocess.Popen:
        """Start ffmpeg download. Returns Popen for progress tracking."""
        args = [self.ffmpeg_path, "-y", "-i", url]
        if headers:
            for k, v in headers.items():
                args.extend(["-headers", f"{k}: {v}"])
        args.extend(["-c", "copy", output])
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        return self._proc

    @staticmethod
    def parse_progress(line: str) -> dict | None:
        """Parse ffmpeg stderr for progress info."""
        m = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", line)
        if m:
            h, mi, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
            secs = h * 3600 + mi * 60 + s + ms / 100
            return {"type": "time", "seconds": secs}
        m2 = re.search(r"size=\s*(\d+)kB", line)
        if m2:
            return {"type": "size", "kb": int(m2[1])}
        return None

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
