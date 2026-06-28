import { ipcMain, dialog, BrowserWindow, shell } from 'electron';
import { Aria2Manager } from './aria2-manager';
import { StoreManager } from './store';
import { CookieExtractor, BrowserType } from './cookie-extractor';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { startProxy, stopProxy, isProxyRunning } from './index';
import { VideoDownloadManager } from './video-download-manager';
import { parseVideoUrl, getDirectUrl, downloadVideo } from './video-parser';

const cookieExtractor = new CookieExtractor();

function isSupportedDownloadUrl(url: string): boolean {
  return /^(https?|ftp):\/\//i.test(url) || /^(magnet:\?|ed2k:\/\/)/i.test(url);
}

export function registerIpcHandlers(
  aria2: Aria2Manager,
  store: StoreManager,
  videoDownloads: VideoDownloadManager
): void {
  // Download operations
  // Download: select local torrent file
  ipcMain.handle('download:selectTorrent', async () => {
    const win = BrowserWindow.getFocusedWindow();
    if (!win) return null;
    const result = await dialog.showOpenDialog(win, {
      filters: [{ name: 'Torrent Files', extensions: ['torrent'] }],
      properties: ['openFile'],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    const torrentPath = result.filePaths[0];
    const gid = await aria2.addTorrent(torrentPath, {});
    return gid;
  });

  ipcMain.handle('download:add', async (_event, url: string, options?: Record<string, unknown>) => {
    // Extract referer from fragment: url#referer=xxx
    let realUrl: string = url;
    let referer: string = (options?.referer as string) || '';
    let hashIdx: number = url.indexOf('#referer=');
    if (hashIdx > 0) {
      referer = decodeURIComponent(url.substring(hashIdx + 9));
      realUrl = url.substring(0, hashIdx);
    }

    if (!isSupportedDownloadUrl(realUrl)) {
      throw new Error(
        /^[a-zA-Z0-9._-]+\.(zip|rar|7z|exe|msi|mp4|mkv|mp3|pdf|apk|iso|torrent|dmg|pkg|deb|rpm)$/i.test(realUrl)
          ? '\u770b\u8d77\u6765\u4f60\u7c98\u8d34\u4e86\u6587\u4ef6\u540d\uff0c\u8bf7\u7c98\u8d34\u5b8c\u6574\u7684\u4e0b\u8f7d\u94fe\u63a5\uff08\u5982 https://…\uff09'
          : '\u4e0d\u652f\u6301\u7684\u4e0b\u8f7d\u94fe\u63a5\uff0c\u8bf7\u7c98\u8d34 HTTP/HTTPS/FTP/\u78c1\u529b \u94fe\u63a5'
      );
    }

    const opts: Record<string, unknown> = { ...(options || {}), referer: referer };

    if (realUrl.toLowerCase().includes('.mpd')) {
      throw new Error('\u6682\u4e0d\u652f\u6301 DASH/MPD \u6d41\u4e0b\u8f7d');
    }

    // Route m3u8/HLS streams to ffmpeg-based video downloader
    if (realUrl.toLowerCase().includes('.m3u8')) {
      return videoDownloads.start(realUrl, {
        cookies: opts.cookies as string | undefined,
        referer: opts.referer as string | undefined,
        userAgent: opts.userAgent as string | undefined,
      });
    }

    // Build aria2 options: convert cookies to header format if needed
    const aria2Opts: Record<string, unknown> = { ...opts };
    if (aria2Opts.cookies && !aria2Opts.header) {
      aria2Opts.header = [`Cookie: ${aria2Opts.cookies}`];
      delete aria2Opts.cookies;
    }
    // Map camelCase options to aria2's expected kebab-case keys
    if (aria2Opts.userAgent) {
      aria2Opts['user-agent'] = aria2Opts.userAgent;
      delete aria2Opts.userAgent;
    }

    // Magnet and ed2k links: aria2 handles them natively via addUri
    const gid = await aria2.addUri([realUrl], aria2Opts);
    return gid;
  });

  ipcMain.handle('download:pause', async (_event, gid: string) => {
    await aria2.pause(gid);
  });

  ipcMain.handle('download:resume', async (_event, gid: string) => {
    await aria2.unpause(gid);
  });

  ipcMain.handle('download:delete', async (_event, gid: string) => {
    if (videoDownloads.stop(gid)) return;
    await aria2.forceRemove(gid);
  });

  // Retry a failed video (e.g. interrupted by app restart or transient error).
  // aria2 tasks resume via download:resume; this is for ffmpeg-driven video tasks.
  ipcMain.handle('download:retry', async (_event, gid: string) => {
    return videoDownloads.retry(gid);
  });

  ipcMain.handle('download:clearFinished', async () => {
    videoDownloads.clearFinished();
    await aria2.purgeDownloadResult();
    return true;
  });

  ipcMain.handle('download:openFolder', async () => {
    const dir = store.getSettings().downloadDir;
    await shell.openPath(dir);
    return true;
  });

  ipcMain.handle('download:getActive', async () => {
    const videoTasks = videoDownloads.list().filter((task) => task.status === 'active');
    try {
      return [...videoTasks, ...(await aria2.tellActive())];
    } catch {
      return videoTasks;
    }
  });

  ipcMain.handle('download:getWaiting', async (_event, offset: number, num: number) => {
    return aria2.tellWaiting(offset, num);
  });

  ipcMain.handle('download:getStopped', async (_event, offset: number, num: number) => {
    const videoTasks = videoDownloads.list().filter((task) => task.status !== 'active');
    try {
      return [...videoTasks, ...(await aria2.tellStopped(offset, num))];
    } catch {
      return videoTasks;
    }
  });

  ipcMain.handle('download:getStatus', async (_event, gid: string) => {
    const videoTask = videoDownloads.get(gid);
    if (videoTask) return videoTask;
    return aria2.tellStatus(gid);
  });

  // Settings
  ipcMain.handle('settings:get', async () => {
    return store.getSettings();
  });

  ipcMain.handle('settings:update', async (_event, partial: Record<string, unknown>) => {
    return store.updateSettings(partial);
  });

  ipcMain.handle('settings:selectDir', async () => {
    const win = BrowserWindow.getFocusedWindow();
    if (!win) return null;
    const result = await dialog.showOpenDialog(win, {
      properties: ['openDirectory'],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  });

  // Cookie extraction
  ipcMain.handle('cookie:import', async (_event, browser: BrowserType, domain?: string) => {
    const cookies = await cookieExtractor.extract(browser, domain);
    return {
      header: cookieExtractor.formatAsHeader(cookies),
      count: cookies.length,
    };
  });

  // Window controls
  ipcMain.handle('window:minimize', () => {
    BrowserWindow.getFocusedWindow()?.minimize();
  });

  ipcMain.handle('window:close', () => {
    BrowserWindow.getFocusedWindow()?.close();
  });

  // aria2 engine
  ipcMain.handle('aria2:restart', async () => {
    await aria2.restart();
  });

  // HTTP proxy
  ipcMain.handle('proxy:start', () => {
    const port = startProxy();
    return port;
  });

  ipcMain.handle('proxy:stop', () => {
    stopProxy();
    return true;
  });

  ipcMain.handle('proxy:status', () => {
    return isProxyRunning();
  });

  // Video parsing
  ipcMain.handle('video:parse', async (_event, url: string, cookies?: string) => {
    return await parseVideoUrl(url, cookies || '');
  });

  ipcMain.handle('video:getDirectUrl', async (_event, videoUrl: string, formatId: string) => {
    return await getDirectUrl(videoUrl, formatId);
  });

  ipcMain.handle('video:download', async (event, videoUrl: string, formatId: string, cookies?: string) => {
    const settings = store.getSettings();
    const outputDir = settings.downloadDir || path.join(os.homedir(), 'Downloads', 'nsp');
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // Direct media files (mp4/mkv/etc) — use aria2 for fast multi-thread download.
    // yt-dlp is only needed for platform URLs (YouTube, B站, TikTok, etc).
    if (formatId === 'direct' || formatId === 'default' || formatId === 'best-with-audio') {
      const isDirect = /\.(mp4|webm|mkv|avi|ts|m4a|mp3|flv|mov|wmv|m4v|3gp|ogg|opus|aac|wav|flac)(\?|$)/i.test(videoUrl);
      if (isDirect) {
        const fileName = (() => {
          try { return decodeURIComponent(path.basename(new URL(videoUrl).pathname)); } catch { return 'video.mp4'; }
        })();
        const filePath = path.join(outputDir, fileName);
        const win = BrowserWindow.fromWebContents(event.sender);

        // Try aria2 first, fall back to direct Node.js HTTP download
        try {
          const options: Record<string, unknown> = { out: fileName, dir: outputDir };
          if (cookies) options.header = [`Cookie: ${cookies}`];
          const gid = await aria2.addUri([videoUrl], options);

          let lastPct = 0;
          await new Promise<void>((resolve, reject) => {
            const poll = setInterval(async () => {
              try {
                const status = await aria2.tellStatus(gid);
                const total = parseInt(status.totalLength, 10) || 0;
                const done = parseInt(status.completedLength, 10) || 0;
                const pct = total > 0 ? Math.round((done / total) * 100) : 0;
                const speed = parseInt(status.downloadSpeed, 10) || 0;
                if (pct !== lastPct && win) {
                  lastPct = pct;
                  win.webContents.send('video:downloadProgress', {
                    pct: String(pct),
                    speed: speed > 0 ? `${(speed / 1024 / 1024).toFixed(1)} MB/s` : '',
                    eta: '',
                  });
                }
                if (status.status === 'complete') { clearInterval(poll); resolve(); }
                if (status.status === 'error' || status.status === 'removed') {
                  clearInterval(poll);
                  reject(new Error(status.errorMessage || 'Download failed'));
                }
              } catch { /* keep polling */ }
            }, 500);
          });
        } catch {
          // aria2 not available — download directly via Node.js http
          await downloadFileDirect(videoUrl, filePath, cookies, (pct, speed) => {
            if (win) win.webContents.send('video:downloadProgress', { pct: String(pct), speed, eta: '' });
          });
        }

        return filePath;
      }
    }

    // Platform URLs — use yt-dlp
    const win = BrowserWindow.fromWebContents(event.sender);
    const filePath = await downloadVideo(videoUrl, formatId, outputDir, cookies, (pct, speed, eta) => {
      if (win) {
        win.webContents.send('video:downloadProgress', { pct, speed, eta });
      }
    });

    return filePath;
  });
}

/**
 * Fallback direct HTTP download when aria2 is not available.
 * Uses Node.js built-in http/https with progress reporting.
 */
async function downloadFileDirect(
  url: string,
  destPath: string,
  cookies: string | undefined,
  onProgress: (pct: number, speed: string) => void,
): Promise<void> {
  const http = require('http');
  const https = require('https');
  const fs = require('fs');

  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const mod = u.protocol === 'https:' ? https : http;
    const headers: Record<string, string> = {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    };
    if (cookies) headers['Cookie'] = cookies;

    const req = mod.get({
      protocol: u.protocol,
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      headers,
      rejectUnauthorized: false,
    }, (resp: any) => {
      const total = parseInt(resp.headers['content-length'], 10) || 0;
      let downloaded = 0;
      let lastTick = Date.now();
      let lastSize = 0;

      const file = fs.createWriteStream(destPath);
      resp.pipe(file);

      resp.on('data', (chunk: Buffer) => {
        downloaded += chunk.length;
        const now = Date.now();
        if (now - lastTick > 200) {
          const speed = ((downloaded - lastSize) / ((now - lastTick) / 1000));
          const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
          onProgress(pct, speed > 0 ? `${(speed / 1024 / 1024).toFixed(1)} MB/s` : '');
          lastTick = now;
          lastSize = downloaded;
        }
      });

      file.on('finish', () => { file.close(); onProgress(100, ''); resolve(); });
      file.on('error', reject);
      resp.on('error', reject);
    });

    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}
