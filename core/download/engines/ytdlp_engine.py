"""yt-dlp engine — DASH and complex site downloads."""

from __future__ import annotations

import json
import subprocess


class YtdlpEngine:
    """Download via yt-dlp (YouTube, DASH, complex sites)."""

    def __init__(self, ytdlp_path: str = "yt-dlp"):
        self.ytdlp_path = ytdlp_path
        self._proc: subprocess.Popen | None = None

    def download(
        self, url: str, output_dir: str = ".", filename: str | None = None, headers: dict[str, str] | None = None
    ) -> subprocess.Popen:
        """Start yt-dlp download."""
        args = [self.ytdlp_path, url, "-o", f"{output_dir}/%(title)s.%(ext)s"]
        if filename:
            args = [self.ytdlp_path, url, "-o", f"{output_dir}/{filename}"]
        if headers:
            for k, v in headers.items():
                args.extend(["--add-header", f"{k}:{v}"])
        args.extend(["--progress-template", "json"])
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return self._proc

    @staticmethod
    def parse_json_line(line: str) -> dict | None:
        try:
            return json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
