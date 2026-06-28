import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain } from 'electron';
import path from 'path';
import { Aria2Manager } from './aria2-manager';
import { registerIpcHandlers } from './ipc-handlers';
import { ClipboardMonitor } from './clipboard-monitor';
import { HttpProxyServer } from './http-proxy';
import { StoreManager } from './store';
import { VideoDownloadManager } from './video-download-manager';
import { probeMediaUrl } from './m3u8-downloader';
import http from 'http';

const text = {
  showWindow: '\u663e\u793a\u7a97\u53e3',
  hideWindow: '\u9690\u85cf\u7a97\u53e3',
  quit: '\u9000\u51fa',
  undo: '\u64a4\u9500',
  redo: '\u91cd\u505a',
  cut: '\u526a\u5207',
  copy: '\u590d\u5236',
  paste: '\u7c98\u8d34',
  selectAll: '\u5168\u9009',
};

let mainWindow: BrowserWindow | null = null;
let floatWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let aria2Manager: Aria2Manager | null = null;
let videoDownloadManager: VideoDownloadManager | null = null;
let storeManager: StoreManager | null = null;
let clipboardMonitor: ClipboardMonitor | null = null;
let httpServer: http.Server | null = null;
let proxyServer: HttpProxyServer | null = null;
let isQuitting = false;
const recentVideoRequests = new Map<string, number>();
const VIDEO_REQUEST_DEDUPE_MS = 60000;

function getVideoRequestKey(url: string, referer?: string): string {
  return `${referer || ''}|${url}`;
}

function isDuplicateVideoRequest(url: string, referer?: string): boolean {
  const now = Date.now();
  const key = getVideoRequestKey(url, referer);
  const lastSeen = recentVideoRequests.get(key) || 0;

  for (const [requestKey, timestamp] of recentVideoRequests) {
    if (now - timestamp > VIDEO_REQUEST_DEDUPE_MS) {
      recentVideoRequests.delete(requestKey);
    }
  }

  if (now - lastSeen < VIDEO_REQUEST_DEDUPE_MS) {
    return true;
  }

  recentVideoRequests.set(key, now);
  return false;
}

function isSupportedVideoUrl(url: string): boolean {
  return url.toLowerCase().includes('.m3u8');
}

function isUnsupportedDashUrl(url: string): boolean {
  return url.toLowerCase().includes('.mpd');
}

function isAria2SupportedUrl(url: string): boolean {
  return /^(https?|ftp):\/\//i.test(url) || /^(magnet:\?|ed2k:\/\/)/i.test(url);
}

function createTray(): void {
  const iconPath = process.env.NODE_ENV === 'development'
    ? path.join(__dirname, '../../resources/tray-icon.png')
    : path.join(process.resourcesPath!, 'tray-icon.png');
  const icon = nativeImage.createFromPath(iconPath);
  const resized = icon.resize({ width: 16, height: 16 });
  tray = new Tray(resized);
  tray.setToolTip('NetSpeedPro');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: text.showWindow,
      click: () => mainWindow?.show(),
    },
    {
      label: text.hideWindow,
      click: () => mainWindow?.hide(),
    },
    { type: 'separator' },
    {
      label: text.quit,
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => mainWindow?.show());
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 620,
    minWidth: 380,
    minHeight: 400,
    frame: false,
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  }

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  const inputMenu = Menu.buildFromTemplate([
    {
      label: text.undo,
      role: 'undo',
    },
    {
      label: text.redo,
      role: 'redo',
    },
    { type: 'separator' },
    {
      label: text.cut,
      role: 'cut',
    },
    {
      label: text.copy,
      role: 'copy',
    },
    {
      label: text.paste,
      role: 'paste',
    },
    {
      label: text.selectAll,
      role: 'selectAll',
    },
  ]);

  mainWindow.webContents.on('context-menu', (_event, params) => {
    if (params.isEditable) {
      inputMenu.popup({ window: mainWindow || undefined });
    }
  });
}

function createFloatWindow(): void {
  floatWindow = new BrowserWindow({
    width: 240,
    height: 80,
    x: 0,
    y: 0,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, '../preload/float-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.NODE_ENV === 'development') {
    floatWindow.loadURL('http://localhost:5173/float.html');
  } else {
    floatWindow.loadFile(path.join(__dirname, '../renderer/float.html'));
  }

  // Position at bottom-right
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: sw, height: sh } = primaryDisplay.workAreaSize;
  floatWindow.setPosition(sw - 256, sh - 96);
}

function startHttpServer(): void {
  httpServer = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    if (req.method === 'POST' && req.url === '/probe-media') {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', async () => {
        try {
          const { url, cookies, referer, userAgent } = JSON.parse(body);
          const result = await probeMediaUrl(url, {
            cookies: cookies || '',
            referer,
            userAgent,
          });
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: true, ...result }));
        } catch (err: any) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: false, error: err.message }));
        }
      });
      return;
    }

    if (req.method === 'POST' && (req.url === '/add-download' || req.url === '/add-video')) {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', async () => {
        try {
          const { url, cookies, referer, userAgent } = JSON.parse(body);
          if (!url || typeof url !== 'string') {
            throw new Error('\u7f3a\u5c11\u4e0b\u8f7d\u94fe\u63a5');
          }
          if (!isAria2SupportedUrl(url)) {
            throw new Error('\u4e0d\u652f\u6301\u7684\u4e0b\u8f7d\u94fe\u63a5\u683c\u5f0f');
          }

          if (isUnsupportedDashUrl(url)) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: false, error: '\u6682\u4e0d\u652f\u6301 DASH/MPD \u6d41\u4e0b\u8f7d' }));
            return;
          }

          if (isSupportedVideoUrl(url)) {
            if (isDuplicateVideoRequest(url, referer)) {
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ success: true, type: 'video', duplicate: true }));
              return;
            }

            const gid = videoDownloadManager!.start(url, {
              cookies: cookies || '',
              referer,
              userAgent,
            });
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true, type: 'video', gid }));
            return;
          }

          const options: Record<string, unknown> = {};
          if (cookies) {
            options.header = [`Cookie: ${cookies}`];
          }
          if (referer) {
            options.referer = referer;
          }
          if (userAgent) {
            options['user-agent'] = userAgent;
          }
          const gid = await aria2Manager!.addUri([url], options);
          mainWindow?.webContents.send('clipboard:captured', { url, gid });
          mainWindow?.show();
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: true, gid }));
        } catch (err: any) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: false, error: err.message }));
        }
      });
      return;
    }

    res.writeHead(404);
    res.end('Not Found');
  });

  httpServer.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE') {
      console.error('[nsp] HTTP server port 17080 is already in use. Browser extension bridge will be unavailable.');
      return;
    }
    console.error('[nsp] HTTP server failed:', err.message);
  });

  httpServer.listen(17080, '127.0.0.1', () => {
    console.log('[nsp] HTTP server listening on 127.0.0.1:17080');
  });
}

// Update the Windows system proxy. Pass a port to enable (ProxyEnable=1,
// ProxyServer=127.0.0.1:port); pass null to disable (ProxyEnable=0).
// Setting ProxyServer alone does NOT turn the proxy on, so both keys are written.
function setSystemProxyEnabled(port: number | null): void {
  try {
    const { execSync } = require('child_process');
    const internetSettings = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings';
    if (port !== null) {
      execSync(
        `powershell -NoProfile -Command "Set-ItemProperty -Path '${internetSettings}' -Name ProxyServer -Value '127.0.0.1:${port}' -Type String; Set-ItemProperty -Path '${internetSettings}' -Name ProxyEnable -Value 1 -Type DWord"`,
        { timeout: 3000 }
      );
    } else {
      execSync(
        `powershell -NoProfile -Command "Set-ItemProperty -Path '${internetSettings}' -Name ProxyEnable -Value 0 -Type DWord"`,
        { timeout: 3000 }
      );
    }
  } catch {
    // Non-critical: settings UI still reflects in-app proxy state.
  }
}

export function startProxy(): number {
  if (proxyServer?.isRunning()) return proxyServer.getPort();

  const settings = storeManager?.getSettings();
  const startPort = (settings as any)?.proxyPort || 58309;
  proxyServer = new HttpProxyServer({
    port: startPort,
    onDownload: async (url, headers) => {
      if (aria2Manager) {
        const options: Record<string, unknown> = {};
        if (headers['Cookie']) {
          options.header = [`Cookie: ${headers['Cookie']}`];
        }
        const gid = await aria2Manager.addUri([url], options);
        mainWindow?.webContents.send('clipboard:captured', { url, gid, source: 'proxy' });
      }
    },
    onPortChange: (port) => {
      mainWindow?.webContents.send('proxy:portChanged', port);
      // Auto-update Windows system proxy
      setSystemProxyEnabled(port);
    },
  });

  const actualPort = proxyServer.start();
  return actualPort;
}

export function stopProxy(): void {
  proxyServer?.stop();
  // Disable the system proxy we enabled on start
  setSystemProxyEnabled(null);
}

export function isProxyRunning(): boolean {
  return proxyServer?.isRunning() ?? false;
}

app.whenReady().then(async () => {
  try {
    storeManager = new StoreManager();
    aria2Manager = new Aria2Manager(storeManager);
    videoDownloadManager = new VideoDownloadManager(storeManager);
    registerIpcHandlers(aria2Manager, storeManager, videoDownloadManager);

    createWindow();
    createFloatWindow();
    createTray();

    clipboardMonitor = new ClipboardMonitor();
    clipboardMonitor.start((capture) => {
      mainWindow?.webContents.send('clipboard:captured', capture);
    });

    // Float window IPC
    ipcMain.handle('float:showMain', () => {
      mainWindow?.show();
    });
    ipcMain.handle('float:hide', () => {
      floatWindow?.hide();
    });

    startHttpServer();
    await aria2Manager.start();

    // Auto-start proxy if setting is enabled
    const settings = storeManager.getSettings();
    if (settings.proxyAutoStart) {
      startProxy();
    }
  } catch (err: any) {
    console.error('[nsp] App startup failed:', err.message);
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', async () => {
  isQuitting = true;
  clipboardMonitor?.stop();
  proxyServer?.stop();
  httpServer?.close();
  await aria2Manager?.stop();
});
