import { contextBridge, ipcRenderer } from 'electron';

export interface ClipboardCaptureEvent {
  url: string;
  timestamp: number;
  source: 'clipboard';
}

export interface ElectronAPI {
  download: {
    add: (url: string, options?: Record<string, unknown>) => Promise<string>;
    selectTorrent: () => Promise<string | null>;
    pause: (gid: string) => Promise<void>;
    resume: (gid: string) => Promise<void>;
    retry: (gid: string) => Promise<boolean>;
    delete: (gid: string) => Promise<void>;
    clearFinished: () => Promise<boolean>;
    openFolder: () => Promise<boolean>;
    getActive: () => Promise<unknown[]>;
    getWaiting: (offset: number, num: number) => Promise<unknown[]>;
    getStopped: (offset: number, num: number) => Promise<unknown[]>;
    getStatus: (gid: string) => Promise<unknown>;
  };
  settings: {
    get: () => Promise<Record<string, unknown>>;
    update: (partial: Record<string, unknown>) => Promise<Record<string, unknown>>;
    selectDir: () => Promise<string | null>;
  };
  cookie: {
    import: (browser: 'chrome' | 'edge', domain?: string) => Promise<{
      header: string;
      count: number;
    }>;
  };
  window: {
    minimize: () => void;
    close: () => void;
  };
  aria2: {
    restart: () => Promise<void>;
  };
  clipboard: {
    onCapture: (callback: (event: ClipboardCaptureEvent) => void) => () => void;
  };
  proxy: {
    start: () => Promise<number>;
    stop: () => Promise<boolean>;
    status: () => Promise<boolean>;
    onPortChange: (callback: (port: number) => void) => () => void;
  };
  video: {
    parse: (url: string) => Promise<{ title: string; url: string; formats: Array<{ id: string; ext: string; resolution: string; filesize: number; note: string; hasVideo: boolean; hasAudio: boolean; kind?: string }>; thumbnail?: string; duration?: number }>;
    getDirectUrl: (videoUrl: string, formatId: string) => Promise<string>;
    download: (videoUrl: string, formatId: string) => Promise<string>;
  };
}

const api: ElectronAPI = {
  download: {
    add: (url, options) => ipcRenderer.invoke('download:add', url, options),
    selectTorrent: () => ipcRenderer.invoke('download:selectTorrent'),
    pause: (gid) => ipcRenderer.invoke('download:pause', gid),
    resume: (gid) => ipcRenderer.invoke('download:resume', gid),
    retry: (gid) => ipcRenderer.invoke('download:retry', gid),
    delete: (gid) => ipcRenderer.invoke('download:delete', gid),
    clearFinished: () => ipcRenderer.invoke('download:clearFinished'),
    openFolder: () => ipcRenderer.invoke('download:openFolder'),
    getActive: () => ipcRenderer.invoke('download:getActive'),
    getWaiting: (offset, num) => ipcRenderer.invoke('download:getWaiting', offset, num),
    getStopped: (offset, num) => ipcRenderer.invoke('download:getStopped', offset, num),
    getStatus: (gid) => ipcRenderer.invoke('download:getStatus', gid),
  },
  settings: {
    get: () => ipcRenderer.invoke('settings:get'),
    update: (partial) => ipcRenderer.invoke('settings:update', partial),
    selectDir: () => ipcRenderer.invoke('settings:selectDir'),
  },
  cookie: {
    import: (browser, domain) => ipcRenderer.invoke('cookie:import', browser, domain),
  },
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    close: () => ipcRenderer.invoke('window:close'),
  },
  aria2: {
    restart: () => ipcRenderer.invoke('aria2:restart'),
  },
  clipboard: {
    onCapture: (callback) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ClipboardCaptureEvent) => callback(data);
      ipcRenderer.on('clipboard:captured', handler);
      return () => ipcRenderer.removeListener('clipboard:captured', handler);
    },
  },
  proxy: {
    start: () => ipcRenderer.invoke('proxy:start'),
    stop: () => ipcRenderer.invoke('proxy:stop'),
    status: () => ipcRenderer.invoke('proxy:status'),
    onPortChange: (callback: (port: number) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, port: number) => callback(port);
      ipcRenderer.on('proxy:portChanged', handler);
      return () => ipcRenderer.removeListener('proxy:portChanged', handler);
    },
  },
  video: {
    parse: (url) => ipcRenderer.invoke('video:parse', url),
    getDirectUrl: (videoUrl, formatId) => ipcRenderer.invoke('video:getDirectUrl', videoUrl, formatId),
    download: (videoUrl, formatId) => ipcRenderer.invoke('video:download', videoUrl, formatId),
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
