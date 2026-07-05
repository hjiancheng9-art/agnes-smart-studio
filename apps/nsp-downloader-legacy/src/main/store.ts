import fs from 'fs';
import path from 'path';
import os from 'os';

interface AppSettings {
  downloadDir: string;
  maxConnections: number;
  maxConcurrentTasks: number;
  maxDownloadSpeed: number;
  maxUploadSpeed: number;
  enableDht: boolean;
  dhtPort: number;
  seedRatio: number;
  seedTime: number;
  language: string;
  proxyAutoStart: boolean;
  proxyPort: number;
}

const DEFAULT_SETTINGS: AppSettings = {
  downloadDir: '',
  maxConnections: 16,
  maxConcurrentTasks: 5,
  maxDownloadSpeed: 0,
  maxUploadSpeed: 0,
  enableDht: true,
  dhtPort: 6881,
  seedRatio: 1.0,
  seedTime: 60,
  language: 'zh-CN',
  proxyAutoStart: false,
  proxyPort: 58309,
};

export class StoreManager {
  private filePath: string;
  private cache: AppSettings;

  constructor() {
    const configDir = path.join(os.homedir(), '.nsp-downloader');
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { recursive: true });
    }
    this.filePath = path.join(configDir, 'config.json');
    this.cache = this.load();

    if (!this.cache.downloadDir) {
      const sep = path.sep;
      this.cache.downloadDir = path.join(os.homedir(), 'Downloads', 'nsp');
      this.save();
    }
  }

  getSettings(): AppSettings {
    return { ...this.cache };
  }

  updateSettings(partial: Partial<AppSettings>): AppSettings {
    Object.assign(this.cache, partial);
    this.save();
    return { ...this.cache };
  }

  private load(): AppSettings {
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, 'utf8');
        return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
      }
    } catch {
      // Corrupted config, use defaults
    }
    return { ...DEFAULT_SETTINGS };
  }

  private save(): void {
    try {
      fs.writeFileSync(this.filePath, JSON.stringify(this.cache, null, 2), 'utf8');
    } catch {
      // Silent fail -- will retry on next save
    }
  }
}
