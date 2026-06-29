import yt_dlp
import os, sys

url = "https://youtu.be/mqU4krG-Rac"

ydl_opts = {
    'format': 'bestvideo+bestaudio',
    'merge_output_format': 'mp4',
    'outtmpl': os.path.join(os.path.dirname(os.path.abspath(__file__)), '%(title)s.%(ext)s'),
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        print(f"下载完成: {filename}")
except Exception as e:
    print(f"下载失败: {e}", file=sys.stderr)
    sys.exit(1)
