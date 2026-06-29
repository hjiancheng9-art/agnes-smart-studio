#!/usr/bin/env python3
"""
yt-dlp 增强下载器 — 断点续传 / 多线程 / 字幕 / 格式选择
用法: python yt_downloader.py <URL> [选项]
"""

import yt_dlp
import argparse
import sys
import os


def build_opts(args):
    """根据参数构建 yt-dlp 配置"""
    format_str = args.format or "bestvideo[height<=2160]+bestaudio/best[height<=2160]"

    postprocessors = []
    if args.extract_audio:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": args.audio_format,
            "preferredquality": str(args.audio_quality),
        })
    elif args.remux:
        postprocessors.append({"key": "FFmegRemuxVideo", "preferedformat": args.remux})

    return {
        "format": format_str,
        "outtmpl": args.output or "%(title).100s [%(id)s].%(ext)s",
        "merge_output_format": args.merge or "mp4",
        "writesubtitles": args.subtitles,
        "writeautomaticsub": args.auto_subs,
        "subtitleslangs": args.sub_langs.split(",") if args.sub_langs else ["en", "zh-Hans"],
        "embedsubs": args.embed_subs,
        "concurrent_fragments": args.threads or 8,
        "retries": args.retries or 10,
        "fragment_retries": 10,
        "continuedl": True,            # 断点续传
        "noprogress": args.quiet,
        "quiet": args.quiet,
        **({"postprocessors": postprocessors} if postprocessors else {}),
        "cookiefile": args.cookies if args.cookies else None,
        "proxy": args.proxy if args.proxy else None,
        "sleep_interval": args.throttle or 0,
        "max_sleep_interval": (args.throttle or 0) * 2,
        "throttledratelimit": args.ratelimit if args.ratelimit else None,
        "extractor_retries": 3,
        "ignoreerrors": args.ignore_errors,
        "playliststart": args.playlist_start,
        "playlistend": args.playlist_end,
        "cachedir": args.cache_dir or None,
    }


def main():
    p = argparse.ArgumentParser(description="yt-dlp 增强下载器", add_help=True)

    p.add_argument("url", nargs="+", help="视频 URL（支持多个）")

    # 格式控制
    p.add_argument("-f", "--format", help="格式选择（默认 4K 以下最佳）")
    p.add_argument("-m", "--merge", default="mp4", help="合并容器格式: mp4/mkv/webm")
    p.add_argument("--remux", help="混流到指定容器（不重新编码）")

    # 音频提取
    p.add_argument("-x", "--extract-audio", action="store_true", help="仅提取音频")
    p.add_argument("--audio-format", default="mp3", help="音频编码: mp3/m4a/opus/flac")
    p.add_argument("--audio-quality", type=int, default=192, help="音频比特率 (kbps)")

    # 字幕
    p.add_argument("--subtitles", action="store_true", help="下载手动字幕")
    p.add_argument("--auto-subs", action="store_true", help="下载自动生成字幕")
    p.add_argument("--sub-langs", default="en,zh-Hans", help="字幕语言，逗号分隔")
    p.add_argument("--embed-subs", action="store_true", help="嵌入字幕到视频")

    # 性能 & 网络
    p.add_argument("-t", "--threads", type=int, default=8, help="并发分片数（默认8）")
    p.add_argument("--retries", type=int, default=10, help="重试次数（默认10）")
    p.add_argument("--ratelimit", help="限速，如 5M / 500K")
    p.add_argument("--throttle", type=float, help="请求间隔秒数（防 ban）")
    p.add_argument("--proxy", help="代理地址，如 socks5://127.0.0.1:1080")
    p.add_argument("--cookies", help="cookies 文件路径（解决登录/年龄限制）")

    # 输出控制
    p.add_argument("-o", "--output", help="输出模板（默认：标题 [ID].扩展名）")
    p.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    p.add_argument("--cache-dir", help="自定义缓存目录")

    # 播放列表
    p.add_argument("--playlist-start", type=int, help="播放列表起始序号")
    p.add_argument("--playlist-end", type=int, help="播放列表结束序号")
    p.add_argument("--ignore-errors", action="store_true", help="播放列表中单个失败继续下一个")

    # 仅信息
    p.add_argument("--info", action="store_true", help="仅显示视频信息，不下载")
    p.add_argument("--json", action="store_true", help="以 JSON 输出视频信息")

    args = p.parse_args()

    if args.info:
        _show_info(args)
        return

    opts = build_opts(args)
    _download(args.url, opts)


def _show_info(args):
    """仅获取并展示视频信息"""
    import json as jmod
    opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for url in args.url:
            try:
                info = ydl.extract_info(url, download=False)
                if args.json:
                    print(jmod.dumps(info, indent=2, ensure_ascii=False, default=str))
                else:
                    _print_info(info)
            except Exception as e:
                print(f"[跳过] {url}: {e}", file=sys.stderr)


def _print_info(info):
    """格式化打印视频信息"""
    dur = info.get("duration", 0)
    mins, secs = divmod(dur, 60)
    hrs, mins = divmod(mins, 60)
    duration = f"{hrs}h{mins:02d}m{secs:02d}s" if hrs else f"{mins:02d}m{secs:02d}s"

    print(f"标题   : {info.get('title', 'N/A')}")
    print(f"ID     : {info.get('id', 'N/A')}")
    print(f"时长   : {duration}")
    print(f"上传者 : {info.get('uploader', 'N/A')}")
    print(f"频道   : {info.get('channel', 'N/A')}")
    print(f"分辨率 : {info.get('resolution', 'N/A')}")
    print(f"格式   : {info.get('ext', 'N/A')}")
    print(f"大小   : {_human_size(info.get('filesize_approx'))}")
    print(f"播放量 : {info.get('view_count', 'N/A'):,}" if info.get('view_count') else "")
    print("-" * 50)


def _human_size(size_bytes):
    if not size_bytes:
        return "N/A"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _download(urls, opts):
    """执行下载"""
    with yt_dlp.YoutubeDL(opts) as ydl:
        for url in urls:
            try:
                print(f"▶ 下载中: {url}")
                ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                print(f"✘ 下载失败: {e}", file=sys.stderr)
            except KeyboardInterrupt:
                print("\n⏸ 用户中断（已下载部分保留，支持断点续传）")
                sys.exit(0)

    print("✔ 全部完成。")


if __name__ == "__main__":
    main()
