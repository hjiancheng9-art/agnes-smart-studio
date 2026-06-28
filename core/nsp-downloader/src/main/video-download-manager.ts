import { ChildProcess, spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import http from 'http';
import https from 'https';
import { URL } from 'url';
import { M3u8RequestContext, resolveM3u8Playlist, HlsKeyInfo } from './m3u8-downloader';
import { downloadVideo } from './video-parser';
import { StoreManager } from './store';

interface VideoTask {
  gid: string;
  status: 'active' | 'complete' | 'error' | 'removed';
  totalLength: string;
  completedLength: string;
  downloadSpeed: string;
  uploadSpeed: string;
  files: Array<{ path: string; length: string; completedLength: string }>;
  errorMessage?: string;
  errorCode?: string;
  progress?: number;
  kind: 'video';
  process?: ChildProcess;
  outputPath: string;
  lastSize: number;
  lastTick: number;
  durationSeconds: number;
  completedSeconds: number;
  mediaUrl: string;
  context: M3u8RequestContext;
  hlsKey: HlsKeyInfo | null;
  attempts: number;
  maxAttempts: 3;
}

export type PublicVideoTask = Omit<
  VideoTask,
  'process' | 'lastSize' | 'lastTick' | 'context' | 'hlsKey' | 'attempts' | 'maxAttempts'
> & {
  referer?: string;
};

function findFfmpegPath(): string {
  const candidates = [
    path.join(process.resourcesPath || '', 'ffmpeg.exe'),
    'C:\\ffmpeg\\bin\\ffmpeg.exe',
    'ffmpeg',
  ];

  for (const candidate of candidates) {
    if (candidate === 'ffmpeg' || fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return 'ffmpeg';
}

function safeVideoName(): string {
  return `video-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.mp4`;
}

function extractMediaUrl(url: string): string {
  const parsed = new URL(url);
  for (const key of ['video', 'url', 'src', 'file', 'play']) {
    const value = parsed.searchParams.get(key);
    if (value && /\.(m3u8|mp4)(\?|$)/i.test(value)) {
      return new URL(value, parsed).toString();
    }
  }

  return parsed.toString();
}

function extractVideoFromPage(url: string): Promise<string | null> {
  return new Promise((resolve, reject) => {
    try {
      const https = require('https');
      const http = require('http');
      const u = new URL(url);
      const mod = u.protocol === 'https:' ? https : http;

      mod.get(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
        }
      }, (resp: any) => {
        let data = '';
        resp.on('data', (chunk: Buffer) => data += chunk);
        resp.on('end', () => {
          // Extract Playerjs configuration
          const playerjsMatch = data.match(/var player = new Playerjs\(\{([^}]+)\}\);/);
          if (playerjsMatch) {
            try {
              const config = JSON.parse('{' + playerjsMatch[1] + '}');
              if (config.file) {
                console.log(`[nsp] Extracted video URL from page: ${config.file}`);
                resolve(config.file);
                return;
              }
            } catch (e) {
              console.error('[nsp] Failed to parse Playerjs config:', e);
            }
          }
          resolve(null);
        });
        resp.on('error', reject);
      });
    } catch (e) {
      console.error('[nsp] Failed to extract video from page:', e);
      resolve(null);
    }
  });
}

function buildHeaderLines(context: M3u8RequestContext): string {
  const lines: string[] = [];
  if (context.cookies) lines.push(`Cookie: ${context.cookies}`);
  if (context.referer) lines.push(`Referer: ${context.referer}`);
  if (context.userAgent) lines.push(`User-Agent: ${context.userAgent}`);
  return lines.length > 0 ? `${lines.join('\r\n')}\r\n` : '';
}

export class VideoDownloadManager {
  private tasks = new Map<string, VideoTask>();
  private store: StoreManager;
  private historyPath: string;

  constructor(store: StoreManager) {
    this.store = store;
    this.historyPath = path.join(os.homedir(), '.nsp-downloader', 'video-tasks.json');
    this.loadHistory();
  }

  start(url: string, context: M3u8RequestContext): string {
    const mediaUrl = extractMediaUrl(url);
    const settings = this.store.getSettings();
    const downloadDir = settings.downloadDir || path.join(os.homedir(), 'Downloads', 'nsp');
    if (!fs.existsSync(downloadDir)) {
      fs.mkdirSync(downloadDir, { recursive: true });
    }
    const gid = `video-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const outputPath = path.join(downloadDir, safeVideoName());
    const now = Date.now();
    const task: VideoTask = {
      gid,
      status: 'active',
      totalLength: '0',
      completedLength: '0',
      downloadSpeed: '0',
      uploadSpeed: '0',
      files: [{ path: outputPath, length: '0', completedLength: '0' }],
      kind: 'video',
      outputPath,
      lastSize: 0,
      lastTick: now,
      durationSeconds: 0,
      completedSeconds: 0,
      mediaUrl,
      context,
      hlsKey: null,
      attempts: 0,
      maxAttempts: 3,
    };
    this.tasks.set(gid, task);
    this.saveHistory();

    // Check if this is a page URL and try to extract video
    if (this.isValidPageUrl(url)) {
      extractVideoFromPage(url).then(pageVideoUrl => {
        if (pageVideoUrl) {
          console.log(`[nsp] Extracted video URL from page: ${pageVideoUrl}`);
          task.mediaUrl = pageVideoUrl;
        }
        const isHls = mediaUrl.toLowerCase().includes('.m3u8');
        if (isHls) {
          this.runFfmpeg(task).catch(() => {});
        } else {
          this.runFfmpeg(task);
        }
        this.prepareM3u8Task(mediaUrl, context, task).catch(() => {});
      });
    } else {
      const isHls = mediaUrl.toLowerCase().includes('.m3u8');
      if (isHls) {
        this.runAria2Hls(task).catch(() => {
          this.runFfmpeg(task);
        });
      } else {
        this.runFfmpeg(task);
      }
      this.prepareM3u8Task(mediaUrl, context, task).catch(() => {});
    }
    return gid;
  }

  private async runAria2Hls(task: VideoTask): Promise<void> {
    // This is a placeholder for aria2 HLS download
    // For now, we'll fallback to ffmpeg
    throw new Error('Aria2 HLS download not implemented, falling back to ffmpeg');
  }

  private async prepareM3u8Task(url: string, context: M3u8RequestContext, task: VideoTask): Promise<void> {
    try {
      const playlist = await resolveM3u8Playlist(url, context);
      task.durationSeconds = playlist.durationSeconds;
      if (playlist.key && playlist.key.keyData) {
        task.hlsKey = playlist.key;
      }
    } catch (e) {
      console.error('[nsp] Failed to prepare M3U8 task:', e);
    }
  }

  private updateFileStats(task: VideoTask): void {
    const now = Date.now();
    const size = fs.existsSync(task.outputPath) ? fs.statSync(task.outputPath).size : 0;
    const elapsedSeconds = Math.max((now - task.lastTick) / 1000, 0);

    if (task.status === 'active') {
      const speed = Math.max(0, Math.round((size - task.lastSize) / elapsedSeconds));
      task.downloadSpeed = `${speed} B/s`;
    }

    task.completedLength = String(size);
    if (task.durationSeconds > 0) {
      const progress = Math.min(task.completedSeconds / task.durationSeconds, 1);
      task.progress = Math.max(1, Math.round(progress * 100));
    }

    task.files = [{ path: task.outputPath, length: '0', completedLength: String(size) }];
    task.lastSize = size;
    task.lastTick = now;
  }

  private updateProgressFromFfmpeg(task: VideoTask, chunk: string): void {
    for (const line of chunk.split(/\r?\n/)) {
      if (!line.startsWith('out_time_ms=')) continue;
      const micros = parseInt(line.slice('out_time_ms='.length), 10);
      if (Number.isFinite(micros) && micros >= 0) {
        task.completedSeconds = micros / 1000000;
      }
    }
  }

  private isValidPageUrl(url: string): boolean {
    try {
      const u = new URL(url);
      const pathname = u.pathname.toLowerCase();
      return /^https?:\/\/.+\.(html|php|aspx|jsp)$/i.test(url) &&
             !/(m3u8|mpd|mp4|m4s|ts)(\?|$)/i.test(pathname);
    } catch {
      return false;
    }
  }

  private async runFfmpeg(task: VideoTask): Promise<void> {
    const isHls = task.mediaUrl.toLowerCase().includes('.m3u8');
    const ffArgs = this.buildFfmpegArgs(task.mediaUrl, task.context, task.outputPath, task.hlsKey);
    const child = spawn(findFfmpegPath(), ffArgs, { stdio: ['ignore', 'ignore', 'pipe'] });
    task.process = child;

    child.stderr.on('data', (data: Buffer) => {
      const chunk = data.toString('utf8');
      this.updateProgressFromFfmpeg(task, chunk);
      this.updateFileStats(task);
      this.saveHistory();
    });

    child.on('close', (code) => {
      task.process = undefined;
      if (code === 0) {
        task.status = 'complete';
        task.progress = 100;
      } else {
        task.status = 'error';
        task.errorMessage = `ffmpeg exited with code ${code}`;
      }
      this.updateFileStats(task);
      this.saveHistory();
    });

    child.on('error', (err) => {
      task.process = undefined;
      task.status = 'error';
      task.errorMessage = `ffmpeg failed: ${err.message}`;
      this.saveHistory();
    });
  }

  private buildFfmpegArgs(mediaUrl: string, context: M3u8RequestContext, outputPath: string, hlsKey?: HlsKeyInfo | null): string[] {
    const isHls = mediaUrl.toLowerCase().includes('.m3u8');
    const args = [
      '-hide_banner',
      '-nostats',
      '-progress', 'pipe:2',
      '-loglevel', 'warning',
      '-rw_timeout', '10000000',
      '-reconnect', '1',
      '-reconnect_streamed', '1',
      '-reconnect_at_eof', '1',
      '-reconnect_on_network_error', '1',
      '-reconnect_delay_max', '10',
    ];

    if (isHls) {
      args.push('-protocol_whitelist', 'file,http,https,tcp,tls,crypto,data');
    }

    if (!isHls && hlsKey && hlsKey.keyData && hlsKey.method === 'AES-128') {
      args.push('-decryption_key', hlsKey.keyData.toString('hex'));
      if (hlsKey.iv) {
        args.push('-decryption_iv', hlsKey.iv.toString('hex'));
      }
    }

    const headers = buildHeaderLines(context);
    if (headers) {
      args.push('-headers', headers);
    }

    args.push('-i', mediaUrl);

    if (isHls) {
      args.push('-c', 'copy', '-bsf:a', 'aac_adtstoasc');
    } else {
      args.push('-c', 'copy');
    }

    args.push('-movflags', '+faststart', outputPath);
    return args;
  }

  private saveHistory(): void {
    try {
      const dir = path.dirname(this.historyPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      const records = Array.from(this.tasks.values())
        .filter((task) => task.status !== 'removed')
        .map((task) => this.toPublicTask(task))
        .slice(0, 100);
      fs.writeFileSync(this.historyPath, JSON.stringify(records, null, 2), 'utf8');
    } catch (e) {
      console.error('[nsp] Failed to save history:', e);
    }
  }

  private loadHistory(): void {
    try {
      if (!fs.existsSync(this.historyPath)) {
        return;
      }
      const raw = fs.readFileSync(this.historyPath, 'utf8');
      const tasks = JSON.parse(raw) as PublicVideoTask[];
      for (const task of tasks) {
        if (!task.gid || !task.outputPath) {
          continue;
        }
        const wasActive = task.status === 'active';
        const context: M3u8RequestContext = {
          cookies: undefined,
          referer: task.referer,
          userAgent: undefined,
        };

        this.tasks.set(task.gid, {
          ...task,
          status: wasActive ? 'error' : task.status,
          errorMessage: wasActive ? '应用重启导致中断，点击重试' : task.errorMessage,
          errorCode: wasActive ? 'restart' : task.errorCode,
          process: undefined,
          lastSize: 0,
          lastTick: Date.now(),
          durationSeconds: task.durationSeconds || 0,
          completedSeconds: task.completedSeconds || 0,
          mediaUrl: task.mediaUrl || '',
          context,
          hlsKey: null,
          attempts: 0,
          maxAttempts: 3,
        });
      }
    } catch (e) {
      console.error('[nsp] Failed to load history:', e);
    }
  }

  private toPublicTask(task: VideoTask): PublicVideoTask {
    const { process, lastSize, lastTick, context, hlsKey, attempts, maxAttempts } = task;
    return {
      gid: task.gid,
      status: task.status,
      totalLength: task.totalLength,
      completedLength: task.completedLength,
      downloadSpeed: task.downloadSpeed,
      uploadSpeed: task.uploadSpeed,
      files: task.files,
      errorMessage: task.errorMessage,
      errorCode: task.errorCode,
      progress: task.progress,
      kind: task.kind,
      outputPath: task.outputPath,
      durationSeconds: task.durationSeconds,
      completedSeconds: task.completedSeconds,
      mediaUrl: task.mediaUrl,
      referer: task.context.referer,
    };
  }

  retry(gid: string): boolean {
    const task = this.tasks.get(gid);
    if (!task || task.status === 'removed') {
      return false;
    }
    if (!task.mediaUrl || task.process) {
      return false;
    }
    task.status = 'active';
    task.progress = 0;
    task.attempts = 0;
    task.errorMessage = undefined;
    task.errorCode = undefined;
    task.completedSeconds = 0;
    this.runFfmpeg(task);
    this.saveHistory();
    return true;
  }
}
