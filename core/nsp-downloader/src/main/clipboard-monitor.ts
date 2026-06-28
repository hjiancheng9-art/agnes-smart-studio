import { clipboard } from 'electron';

export interface ClipboardCapture {
  url: string;
  timestamp: number;
  source: 'clipboard';
}

const DOWNLOAD_EXTENSIONS = [
  // Archives
  '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.lz4', '.zst', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz',
  // Installers / packages
  '.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm', '.apk', '.ipa', '.appx', '.appxbundle',
  // Developer packages
  '.whl', '.jar', '.war', '.ear', '.dll', '.so', '.dylib', '.wasm',
  // Video
  '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m3u8',
  // Audio
  '.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.opus', '.wma',
  // Disk images
  '.iso', '.img', '.bin', '.vhd', '.vhdx', '.vmdk',
  // Documents
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
  // Design
  '.psd', '.ai', '.sketch', '.fig', '.xd', '.eps', '.svg',
  // AI models (critical for HuggingFace / Civitai / ModelScope)
  '.safetensors', '.ckpt', '.pt', '.pth', '.onnx', '.gguf', '.ggml', '.tflite', '.h5', '.pb', '.mar', '.mlmodel', '.mlpackage',
  // 3D models
  '.glb', '.gltf', '.obj', '.fbx', '.stl', '.3mf', '.usdz',
  // Data files
  '.csv', '.tsv', '.json', '.jsonl', '.yaml', '.yml', '.xml', '.parquet', '.avro', '.arrow',
  // Fonts
  '.ttf', '.otf', '.woff', '.woff2',
  // Other
  '.torrent', '.nzb',
];

const DRIVE_DOMAINS = [
  // Chinese cloud drives
  'pan.baidu.com',
  'aliyundrive.com',
  'pan.quark.cn',
  '115.com',
  'yun.139.com',
  'pan.xunlei.com',
  'cloud.189.cn',
  // International cloud drives
  'drive.google.com',
  'onedrive.live.com',
  '1drv.ms',
  'dropbox.com',
  'mega.nz',
  'mediafire.com',
  'box.com',
  // AI model hubs
  'huggingface.co',
  'civitai.com',
  'modelscope.cn',
  'tensorflow.org',
  'pytorch.org',
  'ollama.com',
  // Package registries (not github.com — too broad; covered by path patterns)
  'pypi.org',
  'files.pythonhosted.org',
  'registry.npmjs.org',
  // Data platforms
  'kaggle.com',
];

export class ClipboardMonitor {
  private lastContent = '';
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private onCapture: ((capture: ClipboardCapture) => void) | null = null;

  constructor() {
    this.lastContent = '';
  }

  start(onCapture: (capture: ClipboardCapture) => void): void {
    this.onCapture = onCapture;
    this.lastContent = clipboard.readText();

    this.intervalId = setInterval(() => {
      this.poll();
    }, 800);
  }

  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.onCapture = null;
  }

  private poll(): void {
    const text = clipboard.readText().trim();
    if (!text || text === this.lastContent) return;
    this.lastContent = text;

    const url = this.extractUrl(text);
    if (!url) return;

    if (!this.isDownloadUrl(url)) return;

    this.onCapture?.({ url, timestamp: Date.now(), source: 'clipboard' });
  }

  private extractUrl(text: string): string | null {
    const special = text.match(/(magnet:\?[^\s]+|ed2k:\/\/[^\s]+|thunder:\/\/[^\s]+)/i);
    if (special) return this.normalizeThunderUrl(special[0]);

    // Match http/https URLs
    const match = text.match(/https?:\/\/[^\s<>"{}|\\^`[\]]+/i);
    return match ? match[0] : null;
  }

  private normalizeThunderUrl(url: string): string {
    if (!/^thunder:\/\//i.test(url)) return url;

    try {
      const encoded = url.replace(/^thunder:\/\//i, '');
      const decoded = Buffer.from(encoded, 'base64').toString('utf8');
      const match = decoded.match(/^AA(.+)ZZ$/);
      return match ? match[1] : url;
    } catch {
      return url;
    }
  }

  private isDownloadUrl(url: string): boolean {
    let pathname = '';
    try {
      pathname = new URL(url).pathname;
    } catch { /* keep empty */ }
    const lower = url.toLowerCase();
    const lowerPath = pathname.toLowerCase();

    if (/^(magnet:\?|ed2k:\/\/|thunder:\/\/)/i.test(lower)) return true;

    // Check file extensions in the path
    for (const ext of DOWNLOAD_EXTENSIONS) {
      if (lowerPath.endsWith(ext)) return true;
    }

    // Check drive & model hub domains
    for (const domain of DRIVE_DOMAINS) {
      if (lower.includes(domain)) return true;
    }

    // Path patterns for extensionless download URLs
    if (/[?&](download|dl|get|fetch|pull)=/i.test(lower)) return true;
    if (/\/(download|dl|file|get|fetch)\//i.test(lower)) return true;
    // HuggingFace / GitHub / GitLab raw & resolve paths
    if (/\/(resolve|raw|releases|blob|archive)\//i.test(lower)) return true;
    // API download endpoints
    if (/\/api\/(download|v\d+\/download|models\/.*\/download)/i.test(lower)) return true;

    return false;
  }
}
