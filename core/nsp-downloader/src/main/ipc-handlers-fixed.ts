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
import { getProxyConfig, testProxy, getProxyStatus } from './network-proxy';

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
    let realUrl: string = url;
    let referer: string = (options?.referer as string) || '';
    let hashIdx: number = url.indexOf('#referer=');
    if (hashIdx > 0) {
      referer = decodeURIComponent(url.substring(hashIdx + 9));
      realUrl = url.substring(0, hashIdx);
    }

    if (!isSupportedDownloadUrl(realUrl)) {
      throw new Error(
        /^[a-zA-Z0-9.~%!$&'()*+,;=:@/-]/.test(realUrl)
          ? '粘贴了文件名，请粘贴完整的下载链接（如 https://…）'
          : '不支持的下载链接，请粘贴 HTTP/HTTPS/FTP/磁力 链接'
      );
    }

    const opts: Record<string, unknown> = { ...(options || {}), referer };

    if (realUrl.toLowerCase().includes('.mpd')) {
      throw new Error('暂不支持 DASH/MPD 下载');
    }

    if (realUrl.toLowerCase().includes('.m3u8')) {
      return videoDownloads.start(realUrl, {
        cookies: opts.cookies as string | undefined,
        referer: opts.referer as string | undefined,
        userAgent: opts.userAgent as string | undefined,
      });
    }

    const aria2Opts: Record<string, unknown> = { ...opts };
    if (aria2Opts.cookies && !aria2Opts.header) {
      aria2Opts.header = [`Cookie: ${aria2Opts.cookies}`];
      delete aria2Opts.cookies;
    }

    if (aria2Opts.userAgent) {
      aria2Opts['user-agent'] = aria2Opts.userAgent;
      delete aria2Opts.userAgent;
    }

    const gid = await aria2.addUri([realUrl], aria2Opts);
    return gid;
  });

  ipcMain.handle('download:pause', async (_event, gid: string) => {
    await aria2.pause(gid);
  });

  ipcMain.handle('download:resume', async (_event, gid: string) => {
    await aria2.unpause(gid);
  });

  ipcMain.handle('download:stop', async (_event, gid: string) => {
    if (videoDownloads.stop(gid)) return;
    await aria2.forceRemove(gid);
  });

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

  // Video download - FIXED VERSION
  ipcMain.handle('video:download', async (event, videoUrl: string, formatId: string, cookies?: string) => {
    const settings = store.getSettings();
    const outputDir = settings.downloadDir || path.join(os.homedir(), 'Downloads', 'nsp');

    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    if (formatId === 'direct' || formatId === 'default' || formatId === 'best-with-audio') {
      const isDirect = /\.(mp4|webm|mkv|avi|ts|m4a|mp3|flv|mov|wmv|m4v|3gp|ogg|opus|aac|wav|flac)(\?|$)/i.test(videoUrl);

      if (isDirect) {
        const fileName = (() => {
          try {
            return decodeURIComponent(path.basename(new URL(videoUrl).pathname));
          } catch {
            return 'video.mp4';
          }
        })();
        const filePath = path.join(outputDir, fileName);
        const win = BrowserWindow.fromWebContents(event.sender);

        try {
          const options: Record<string, unknown> = {
            out: fileName,
            dir: outputDir,
          };
          if (cookies) options.header = [`Cookie: ${cookies}`];
          const gid = await aria2.addUri([videoUrl], options);

          let lastPct = 0;
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

              if (status.status === 'complete') {
                clearInterval(poll);
                if (win) win.webContents.send('video:downloadProgress', { pct: '100', speed: '', eta: '' });
                if (win) win.webContents.send('video:downloadComplete', { filePath });
                return;
              }

              if (status.status === 'error' || status.status === 'removed') {
                clearInterval(poll);
                if (win) win.webContents.send('video:downloadProgress', { pct: String(pct), speed: '', eta: '' });
                reject(new Error(status.errorMessage || 'Download failed'));
                return;
              }

              if (status.status === 'active') {
                if (win) win.webContents.send('video:downloadProgress', { pct: String(pct), speed, eta: '' });
              }
            } catch (err: any) {
              clearInterval(poll);
              reject(new Error(`aria2 error: ${err.message}`));
            }
          }, 500);

          return;
        } catch (aria2Error: any) {
          console.error('[nsp] aria2 fallback needed:', aria2Error.message);
        }
      }
    }

    if (formatId === 'best-with-audio') {
      try {
        const filePath = await downloadVideo(videoUrl, formatId, outputDir, cookies, (pct, speed, eta) => {
          if (win) win.webContents.send('video:downloadProgress', { pct: String(pct), speed, eta });
        });
        if (win) win.webContents.send('video:downloadComplete', { filePath });
        return;
      } catch (ytDlpError: any) {
        console.error('[nsp] yt-dlp error:', ytDlpError.message);
      }
    }

    return downloadVideo(videoUrl, formatId, outputDir, cookies, (pct, speed, eta) => {
      if (win) win.webContents.send('video:downloadProgress', { pct: String(pct), speed, eta });
    });
  });

  // Network Proxy operations
  ipcMain.handle('proxy:getConfig', async () => {
    return getProxyConfig();
  });

  ipcMain.handle('proxy:getStatus', async () => {
    return getProxyStatus();
  });

  ipcMain.handle('proxy:test', async (_event, url: string = 'https://www.google.com') => {
    return await testProxy(url);
  });

  ipcMain.handle('proxy:clearCache', async () => {
    clearProxyCache();
    return true;
  });
}
