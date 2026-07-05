import { ChildProcess, spawn } from 'child_process';
import path from 'path';
import { StoreManager } from './store';

interface Aria2Status {
  gid: string;
  status: string;
  totalLength: string;
  completedLength: string;
  downloadSpeed: string;
  uploadSpeed: string;
  files: Array<{ path: string; length: string; completedLength: string }>;
  errorCode?: string;
  errorMessage?: string;
}

export class Aria2Manager {
  private process: ChildProcess | null = null;
  private store: StoreManager;
  private rpcPort = 6800;
  private rpcSecret = 'nsp-secret-token';
  private stopping = false;
  private restartAttempts = 0;
  private maxRestartAttempts = 3;
  private restartDelay = 2000;

  constructor(store: StoreManager) {
    this.store = store;
  }

  get aria2Path(): string {
    const candidates = [
      path.join(process.resourcesPath || '', 'aria2c.exe'),
      path.join(__dirname, '../../resources/aria2c.exe'),
      path.join(__dirname, '../../../resources/aria2c.exe'),  // project-level core/resources
      'aria2c',
    ];
    for (const c of candidates) {
      if (c === 'aria2c' || require('fs').existsSync(c)) return c;
    }
    return 'aria2c';
  }

  async start(): Promise<void> {
    if (this.process) return;
    this.stopping = false;

    const settings = this.store.getSettings();

    // Use higher split/connection defaults for modern bandwidth.
    // settings values act as floor; we boost them to at least 16.
    const split = Math.max(settings.maxConnections || 16, 16);
    const perServer = Math.max(settings.maxConnections || 16, 16);
    const concurrent = Math.max(settings.maxConcurrentTasks || 5, 5);

    const args = [
      `--dir=${settings.downloadDir}`,
      `--split=${split}`,
      `--max-connection-per-server=${perServer}`,
      `--max-concurrent-downloads=${concurrent}`,
      '--min-split-size=512K',
      '--continue=true',
      '--file-allocation=none',
      '--disk-cache=64M',
      '--max-tries=5',
      '--retry-wait=3',
      '--connect-timeout=15',
      '--timeout=30',
      '--allow-overwrite=false',
      '--auto-file-renaming=false',
      '--enable-rpc=true',
      `--rpc-listen-port=${this.rpcPort}`,
      '--rpc-allow-origin-all=true',
      '--rpc-listen-all=true',
      `--rpc-secret=${this.rpcSecret}`,
      '--check-certificate=false',
      '--console-log-level=warn',
      '--quiet',
    ];

    // Speed limits (0 = unlimited)
    if (settings.maxDownloadSpeed > 0) {
      args.push(`--max-overall-download-limit=${settings.maxDownloadSpeed}K`);
    }
    if (settings.maxUploadSpeed > 0) {
      args.push(`--max-overall-upload-limit=${settings.maxUploadSpeed}K`);
    }

    // BT / DHT settings
    if (settings.enableDht) {
      args.push('--enable-dht=true');
      args.push('--enable-dht6=false');
      args.push(`--dht-listen-port=${settings.dhtPort}`);
      args.push('--dht-message-timeout=10');
      // Bootstrap nodes for faster DHT boot
      args.push('--bt-tracker=udp://tracker.opentrackr.org:1337/announce,udp://open.demonii.com:1337/announce,udp://tracker.torrent.eu.org:451/announce,udp://explodie.org:6969/announce,udp://tracker.internetwarriors.net:1337/announce,udp://tracker.leechers-paradise.org:6969/announce');
    }
    args.push('--enable-peer-exchange=true');
    args.push('--bt-enable-lpd=true');
    args.push('--bt-max-peers=55');
    args.push('--bt-request-peer-speed-limit=100K');
    if (settings.seedRatio > 0) {
      args.push(`--seed-ratio=${settings.seedRatio}`);
    }
    args.push(`--seed-time=${settings.seedTime}`);

    this.process = spawn(this.aria2Path, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    this.process.stdout?.on('data', (data: Buffer) => {
      console.log('[aria2]', data.toString());
    });

    this.process.stderr?.on('data', (data: Buffer) => {
      console.error('[aria2 err]', data.toString());
    });

    this.process.on('error', (err) => {
      console.error('[aria2] Failed to start:', err.message);
      this.process = null;
      this.tryRestart();
    });

    this.process.on('exit', (code) => {
      console.log('[aria2] Exited with code:', code);
      this.process = null;
      this.tryRestart();
    });

    // Wait for RPC to be ready
    await this.waitForReady();
  }

  async stop(): Promise<void> {
    if (!this.process) return;
    this.stopping = true;
    try {
      await this.rpcCall('aria2.shutdown');
    } catch {
      // Force kill if RPC fails
      this.process.kill();
    }
    this.process = null;
  }

  async restart(): Promise<void> {
    this.restartAttempts = 0;
    this.stopping = true;
    await this.stop();
    this.stopping = false;
    await this.start();
  }

  private async tryRestart(): Promise<void> {
    if (this.stopping) return;
    if (this.restartAttempts >= this.maxRestartAttempts) {
      console.error('[aria2] Max restart attempts reached, giving up.');
      return;
    }
    this.restartAttempts++;
    console.log(`[aria2] Auto-restarting (attempt ${this.restartAttempts}/${this.maxRestartAttempts}) in ${this.restartDelay}ms...`);
    await new Promise((r) => setTimeout(r, this.restartDelay));
    try {
      await this.start();
      console.log('[aria2] Auto-restart succeeded.');
      this.restartAttempts = 0;
    } catch (err: any) {
      console.error('[aria2] Auto-restart failed:', err.message);
      await this.tryRestart();
    }
  }

  async addUri(urls: string[], options: Record<string, unknown> = {}): Promise<string> {
    // Magnet links should use addUri (aria2 handles them natively)
    return this.rpcCall('aria2.addUri', [urls, options]);
  }

  async addTorrent(torrentFile: string, options: Record<string, unknown> = {}): Promise<string> {
    const fs = require('fs');
    const content = fs.readFileSync(torrentFile);
    return this.rpcCall('aria2.addTorrent', [content.toString('base64'), [], options]);
  }

  async pause(gid: string): Promise<void> {
    await this.rpcCall('aria2.pause', [gid]);
  }

  async unpause(gid: string): Promise<void> {
    await this.rpcCall('aria2.unpause', [gid]);
  }

  async remove(gid: string): Promise<void> {
    await this.rpcCall('aria2.remove', [gid]);
  }

  async forceRemove(gid: string): Promise<void> {
    await this.rpcCall('aria2.forceRemove', [gid]);
  }

  async tellStatus(gid: string): Promise<Aria2Status> {
    return this.rpcCall('aria2.tellStatus', [gid]);
  }

  async tellActive(): Promise<Aria2Status[]> {
    return this.rpcCall('aria2.tellActive');
  }

  async tellWaiting(offset: number, num: number): Promise<Aria2Status[]> {
    return this.rpcCall('aria2.tellWaiting', [offset, num]);
  }

  async tellStopped(offset: number, num: number): Promise<Aria2Status[]> {
    return this.rpcCall('aria2.tellStopped', [offset, num]);
  }

  async purgeDownloadResult(): Promise<void> {
    await this.rpcCall('aria2.purgeDownloadResult');
  }

  private async rpcCall(method: string, params: unknown[] = []): Promise<any> {
    const url = `http://localhost:${this.rpcPort}/jsonrpc`;
    const body = JSON.stringify({
      jsonrpc: '2.0',
      id: Date.now().toString(),
      method,
      params: [`token:${this.rpcSecret}`, ...params],
    });

    let lastError: Error | null = null;
    // Retry once on transient network errors
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
        });

        const data = await resp.json();
        if (data.error) {
          throw new Error(data.error.message);
        }
        return data.result;
      } catch (err: any) {
        lastError = err;
        if (attempt === 0 && (err.code === 'ECONNREFUSED' || err.code === 'ECONNRESET')) {
          await new Promise((r) => setTimeout(r, 200));
          continue;
        }
        throw err;
      }
    }
    throw lastError || new Error('aria2 RPC \u8c03\u7528\u5931\u8d25');
  }

  private async waitForReady(timeout = 15000): Promise<void> {
    const start = Date.now();
    let lastError: string | null = null;
    while (Date.now() - start < timeout) {
      try {
        await this.rpcCall('aria2.getVersion');
        return;
      } catch (err: any) {
        lastError = err.message;
        // If aria2c process died, stop waiting
        if (!this.process) {
          throw new Error('aria2c \u8fdb\u7a0b\u5728\u5c31\u7eea\u524d\u5f02\u5e38\u9000\u51fa');
        }
        await new Promise((r) => setTimeout(r, 300));
      }
    }
    throw new Error(`aria2c RPC \u542f\u52a8\u8d85\u65f6 (${timeout}ms)\uff0c\u6700\u540e\u9519\u8bef\uff1a${lastError || '\u672a\u77e5'}`);
  }
}
