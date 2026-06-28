import http from 'http';
import https from 'https';
import { URL } from 'url';
import net from 'net';

export type DownloadInterceptor = (url: string, headers: Record<string, string>) => void;

interface ProxyOptions {
  port: number;
  onDownload: DownloadInterceptor;
  onPortChange?: (port: number) => void;
}

const DOWNLOAD_EXTENSIONS = [
  // Archives
  '.zip', '.rar', '.7z', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.xz', '.bz2', '.gz', '.lz4', '.zst',
  // Installers
  '.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm', '.apk', '.ipa', '.appx',
  // Developer
  '.whl', '.jar', '.war', '.dll', '.so', '.dylib', '.wasm',
  // Video
  '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m3u8',
  // Audio
  '.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.opus',
  // Disk images
  '.iso', '.img', '.bin',
  // Documents
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  // AI models
  '.safetensors', '.ckpt', '.pt', '.pth', '.onnx', '.gguf', '.ggml', '.tflite',
  // 3D models
  '.glb', '.gltf', '.obj', '.fbx', '.stl',
  // Data
  '.csv', '.json', '.jsonl', '.parquet',
  // Fonts
  '.ttf', '.otf', '.woff', '.woff2',
  // Other
  '.torrent',
];

export class HttpProxyServer {
  private server: http.Server | null = null;
  private port: number;
  private onDownload: DownloadInterceptor;
  private onPortChange?: (port: number) => void;
  private running = false;

  constructor(opts: ProxyOptions) {
    this.port = opts.port;
    this.onDownload = opts.onDownload;
    this.onPortChange = opts.onPortChange;
  }

  start(): number {
    if (this.running) return this.port;

    let tryPort = this.port;
    const maxTries = 10;
    const maxPort = this.port + maxTries - 1;

    // Reusable error handler: avoids accumulating duplicate listeners across
    // retry iterations (the old code re-created the server on EADDRINUSE and
    // re-attached .on('error'), leaking listeners on the previous instance).
    const onError = (err: NodeJS.ErrnoException) => {
      if (err.code === 'EADDRINUSE' && tryPort < maxPort) {
        tryPort++;
        this.server!.removeAllListeners('error');
        this.server!.close();
        // Create a fresh server for the next port attempt
        this.server = http.createServer((req, res) => {
          this.handleRequest(req, res);
        });
        this.server.on('connect', (req2, dup, head2) => {
          this.handleConnect(req2, dup as net.Socket, head2);
        });
        this.server!.listen(tryPort, '127.0.0.1', () => {
          this.port = tryPort;
          this.running = true;
          this.onPortChange?.(this.port);
          console.log(`[nsp] HTTP proxy listening on 127.0.0.1:${this.port}`);
        });
        this.server!.on('error', onError);
      } else {
        console.error('[nsp] Proxy failed to start:', err.message);
        this.running = false;
      }
    };

    this.server = http.createServer((req, res) => {
      this.handleRequest(req, res);
    });

    this.server.on('connect', (req, dup, head) => {
      this.handleConnect(req, dup as net.Socket, head);
    });

    this.server!.on('error', onError);
    this.server!.listen(tryPort, '127.0.0.1', () => {
      this.port = tryPort;
      this.running = true;
      this.onPortChange?.(this.port);
      console.log(`[nsp] HTTP proxy listening on 127.0.0.1:${this.port}`);
    });

    return this.port;
  }

  stop(): void {
    this.running = false;
    if (this.server) {
      this.server.close();
      this.server = null;
    }
  }

  getPort(): number {
    return this.port;
  }

  isRunning(): boolean {
    return this.running;
  }

  private handleRequest(clientReq: http.IncomingMessage, clientRes: http.ServerResponse): void {
    const urlStr = clientReq.url || '';
    if (!urlStr || urlStr === '*') {
      clientRes.writeHead(400);
      clientRes.end();
      return;
    }

    // Parse the target URL
    let targetUrl: URL;
    try {
      targetUrl = new URL(urlStr);
    } catch {
      clientRes.writeHead(400);
      clientRes.end('Invalid URL');
      return;
    }

    // Check if this is a download
    const isDownload = this.isDownloadRequest(targetUrl.pathname);

    if (isDownload) {
      // Intercept -- send to aria2c
      const headers: Record<string, string> = {};
      if (clientReq.headers.cookie) {
        headers['Cookie'] = clientReq.headers.cookie as string;
      }
      if (clientReq.headers['user-agent']) {
        headers['User-Agent'] = clientReq.headers['user-agent'] as string;
      }

      this.onDownload(urlStr, headers);

      // Return HTTP 302 to a local info page, or just close
      clientRes.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
      clientRes.end('Download intercepted by NetSpeedPro');
      return;
    }

    // Forward normally
    this.forwardRequest(clientReq, clientRes, targetUrl);
  }

  private handleConnect(req: http.IncomingMessage, clientSocket: net.Socket, head: Buffer): void {
    // HTTPS traffic via CONNECT is tunnelled blindly — the proxy cannot
    // inspect encrypted payloads. Download interception for HTTPS URLs
    // relies on the clipboard monitor and the companion browser extension
    // (which sees the URL before encryption via the page context).
    const [host, portStr] = (req.url || ':443').split(':');
    const port = parseInt(portStr, 10) || 443;

    const serverSocket = net.connect(port, host, () => {
      clientSocket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      serverSocket.write(head);
      serverSocket.pipe(clientSocket);
      clientSocket.pipe(serverSocket);
    });

    serverSocket.on('error', () => {
      clientSocket.end();
    });

    clientSocket.on('error', () => {
      serverSocket.end();
    });
  }

  private forwardRequest(
    clientReq: http.IncomingMessage,
    clientRes: http.ServerResponse,
    targetUrl: URL
  ): void {
    const options: https.RequestOptions = {
      hostname: targetUrl.hostname,
      port: targetUrl.port || (targetUrl.protocol === 'https:' ? 443 : 80),
      path: targetUrl.pathname + targetUrl.search,
      method: clientReq.method,
      headers: { ...clientReq.headers },
      rejectUnauthorized: false,
    };

    // Remove hop-by-hop headers
    const headers = options.headers as Record<string, unknown>;
    delete headers['proxy-connection'];
    delete headers['proxy-authorization'];

    const requester = targetUrl.protocol === 'https:' ? https.request : http.request;

    const proxyReq = requester(options, (proxyRes) => {
      clientRes.writeHead(proxyRes.statusCode || 200, proxyRes.headers);
      proxyRes.pipe(clientRes);
    });

    proxyReq.on('error', () => {
      try { clientRes.writeHead(502); } catch { /* ignore */ }
      clientRes.end();
    });

    clientReq.pipe(proxyReq);
  }

  private isDownloadRequest(pathname: string): boolean {
    const lower = pathname.toLowerCase();

    for (const ext of DOWNLOAD_EXTENSIONS) {
      if (lower.endsWith(ext)) return true;
    }

    // Path patterns for extensionless download URLs
    if (/\/(download|dl|get|fetch|resolve|raw|releases|blob|archive)\//i.test(lower)) return true;
    if (/\/api\/(download|v\d+\/download|models\/.*\/download)/i.test(lower)) return true;

    return false;
  }
}
