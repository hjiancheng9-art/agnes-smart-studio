"""Download configuration — ~/.crux/download/config.toml

Migrated from nsp-downloader's electron-store.
"""

from __future__ import annotations

import os
import configparser
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".crux" / "download"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Aria2Settings:
    enabled: bool = True
    path: str = "aria2c"
    rpc_url: str = "http://127.0.0.1:6800/jsonrpc"
    rpc_secret: str | None = None
    split: int = 8
    max_connection_per_server: int = 8


@dataclass
class FFmpegSettings:
    path: str = "ffmpeg"


@dataclass
class YtdlpSettings:
    path: str = "yt-dlp"


@dataclass
class DownloadConfig:
    default_dir: str = str(Path.home() / "Downloads" / "CRUX")
    max_concurrent: int = 3
    engine_direct: str = "aria2"
    engine_hls: str = "ffmpeg"
    engine_dash: str = "ytdlp"
    cookies_mode: str = "browser-companion"
    aria2: Aria2Settings = field(default_factory=Aria2Settings)
    ffmpeg: FFmpegSettings = field(default_factory=FFmpegSettings)
    ytdlp: YtdlpSettings = field(default_factory=YtdlpSettings)


def load_config() -> DownloadConfig:
    """Load config from ~/.crux/download/config.toml.
    Returns defaults if file doesn't exist.
    """
    cfg = DownloadConfig()
    if not CONFIG_FILE.exists():
        return cfg

    parser = configparser.ConfigParser()
    try:
        parser.read(str(CONFIG_FILE), encoding="utf-8")
    except Exception:
        return cfg

    if parser.has_section("download"):
        sec = parser["download"]
        cfg.default_dir = sec.get("default_dir", cfg.default_dir)
        cfg.max_concurrent = sec.getint("max_concurrent", cfg.max_concurrent)
        cfg.engine_direct = sec.get("engine_direct", cfg.engine_direct)
        cfg.engine_hls = sec.get("engine_hls", cfg.engine_hls)
        cfg.engine_dash = sec.get("engine_dash", cfg.engine_dash)
        cfg.cookies_mode = sec.get("cookies_mode", cfg.cookies_mode)

    if parser.has_section("aria2"):
        sec = parser["aria2"]
        cfg.aria2.enabled = sec.getboolean("enabled", cfg.aria2.enabled)
        cfg.aria2.path = sec.get("path", cfg.aria2.path)
        cfg.aria2.rpc_url = sec.get("rpc_url", cfg.aria2.rpc_url)
        cfg.aria2.split = sec.getint("split", cfg.aria2.split)
        cfg.aria2.max_connection_per_server = sec.getint(
            "max_connection_per_server", cfg.aria2.max_connection_per_server
        )

    if parser.has_section("ffmpeg"):
        cfg.ffmpeg.path = parser["ffmpeg"].get("path", cfg.ffmpeg.path)

    if parser.has_section("ytdlp"):
        cfg.ytdlp.path = parser["ytdlp"].get("path", cfg.ytdlp.path)

    return cfg


def save_config(cfg: DownloadConfig) -> None:
    """Save config to ~/.crux/download/config.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()

    parser["download"] = {
        "default_dir": cfg.default_dir,
        "max_concurrent": str(cfg.max_concurrent),
        "engine_direct": cfg.engine_direct,
        "engine_hls": cfg.engine_hls,
        "engine_dash": cfg.engine_dash,
        "cookies_mode": cfg.cookies_mode,
    }
    parser["aria2"] = {
        "enabled": str(cfg.aria2.enabled),
        "path": cfg.aria2.path,
        "rpc_url": cfg.aria2.rpc_url,
        "split": str(cfg.aria2.split),
        "max_connection_per_server": str(cfg.aria2.max_connection_per_server),
    }
    parser["ffmpeg"] = {"path": cfg.ffmpeg.path}
    parser["ytdlp"] = {"path": cfg.ytdlp.path}

    with open(str(CONFIG_FILE), "w", encoding="utf-8") as f:
        parser.write(f)


def migrate_from_electron_store(source_path: str | None = None) -> bool:
    """One-time migration from nsp-downloader's electron-store JSON.
    Returns True if migration happened.
    """
    if not source_path or not os.path.exists(source_path):
        return False

    try:
        import json

        with open(source_path, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return False

    cfg = load_config()
    # Map old electron-store keys to new config
    key_map = {
        "download.path": ("download", "default_dir"),
        "aria2.path": ("aria2", "path"),
        "aria2.split": ("aria2", "split"),
        "ffmpeg.path": ("ffmpeg", "path"),
    }
    changed = False
    parser = configparser.ConfigParser()
    parser.read(str(CONFIG_FILE)) if CONFIG_FILE.exists() else None

    for old_key, (section, option) in key_map.items():
        if old_key in old:
            val = old[old_key]
            if not parser.has_section(section):
                parser.add_section(section)
            parser[section][option] = str(val)
            changed = True

    if changed:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(str(CONFIG_FILE), "w", encoding="utf-8") as f:
            parser.write(f)

    return changed
