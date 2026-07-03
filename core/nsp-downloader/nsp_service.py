"""NSP 简易下载服务 - 接收 URL 直接用 ffmpeg 下载"""
import http.server
import json
import os
import subprocess

FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"
DOWNLOAD_DIR = os.path.expanduser(r"~\Downloads\nsp")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        data = json.loads(body)
        url = data.get('url', '')
        referer = data.get('referer', '')

        print(f"\n>>> 下载: {url[:100]}...")

        # 生成文件名
        name = f"video_{int(__import__('time').time())}.mp4"
        out = os.path.join(DOWNLOAD_DIR, name)

        # 构建 ffmpeg 命令（不用 aac_adtstoasc，部分 HLS 流不需要）
        cmd = [FFMPEG, '-y', '-hide_banner', '-loglevel', 'error',
               '-stats', '-progress', 'pipe:1',
               '-headers', f'Referer: {referer}\r\n',
               '-i', url, '-c', 'copy', '-movflags', '+faststart', out]

        print(f"   保存到: {out}")

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # 保存到 server 实例的属性字典，供进程清理（防止 Windows 僵尸进程）
            _procs = getattr(self.server, '_download_procs', None)
            if _procs is None:
                _procs = {}
                self.server._download_procs = _procs
            _procs[proc.pid] = proc
            # 非阻塞，让 ffmpeg 后台跑
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'file': out,
                'pid': proc.pid
            }).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())

    def log_message(self, format, *args):
        print(f"  [{args[0]}] {args[1]} {args[2]}")

if __name__ == '__main__':
    port = 17081
    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    print(f'NSP Download Service on http://127.0.0.1:{port}')
    print(f'保存目录: {DOWNLOAD_DIR}')
    print('按 Ctrl+C 停止')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
