import { execFile } from 'child_process';
import path from 'path';

interface VideoFormat {
  id: string;
  ext: string;
  resolution: string;
  filesize: number;
  note: string;
  hasVideo: boolean;
  hasAudio: boolean;
  kind?: 'video' | 'audio' | 'media';
}

interface VideoInfo {
  title: string;
  url: string;
  formats: VideoFormat[];
  thumbnail?: string;
  duration?: number;
  httpHeaders?: Record<string, string>;
}

const DESKTOP_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';
const DEFAULT_MEDIA_FORMAT_ID = 'default';
const DEFAULT_VIDEO_FORMAT_ID = 'best-with-audio';
const DEFAULT_AUDIO_FORMAT_ID = 'best-audio';

function getYtdlpPath(): string {
  // Priority: local resources > project-level core/resources > PATH
  const candidates = [
    path.join(process.resourcesPath || '', 'yt-dlp.exe'),
    path.join(__dirname, '../../resources/yt-dlp.exe'),
    path.join(__dirname, '../../../resources/yt-dlp.exe'),  // project-level core/resources
    'yt-dlp',
  ];
  for (const c of candidates) {
    if (c === 'yt-dlp' || require('fs').existsSync(c)) return c;
  }
  return 'yt-dlp';
}

function getFfmpegPath(): string {
  const candidates = [
    path.join(process.resourcesPath || '', 'ffmpeg.exe'),
    path.join(__dirname, '../../resources/ffmpeg.exe'),
    path.join(__dirname, '../../../resources/ffmpeg.exe'),
    'C:\\ffmpeg\\bin\\ffmpeg.exe',
    'ffmpeg',
  ];
  for (const c of candidates) {
    if (c === 'ffmpeg' || require('fs').existsSync(c)) return c;
  }
  return 'ffmpeg';
}

/** True if the URL is a direct media file (mp4/webm/mkv/avi/ts/m4a/mp3/flv/mov). */
function isDirectMediaUrl(url: string): boolean {
  try {
    const u = new URL(url);
    const ext = path.extname(u.pathname).toLowerCase();
    return /^\.(mp4|webm|mkv|avi|ts|m4a|mp3|flv|mov|wmv|m4v|3gp|ogg|opus|aac|wav|flac)$/i.test(ext);
  } catch {
    return false;
  }
}

// Derive a referer from the URL itself — yt-dlp handles platform-specific
// referers natively, we just provide a sensible fallback.
function getRefererForUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.hostname}/`;
  } catch {
    return url;
  }
}

// Common args applied to ALL yt-dlp invocations.
// --impersonate chrome helps bypass basic bot detection everywhere and is harmless.
// Read Windows system proxy from the same registry key we already write to.
// Returns "http://host:port" or undefined. Result cached for process lifetime.
let cachedSystemProxy: string | undefined;
let proxyReadAttempted = false;

function getSystemProxy(): string | undefined {
  if (proxyReadAttempted) return cachedSystemProxy;
  proxyReadAttempted = true;

  try {
    const { execSync } = require('child_process');
    const enableOut = execSync(
      'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable 2>nul',
      { encoding: 'utf8', timeout: 2000 }
    );
    const enableMatch = enableOut.match(/0x([0-9a-fA-F]+)/);
    if (!enableMatch || parseInt(enableMatch[1], 16) === 0) return undefined;

    const serverOut = execSync(
      'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyServer 2>nul',
      { encoding: 'utf8', timeout: 2000 }
    );
    const serverMatch = serverOut.match(/ProxyServer\s+REG_SZ\s+(.+)/);
    if (!serverMatch) return undefined;

    let addr = serverMatch[1].trim();
    // System proxy format is "host:port" — prefix with http://
    if (!/^https?:\/\//i.test(addr)) addr = 'http://' + addr;
    cachedSystemProxy = addr;
    return addr;
  } catch {
    return undefined;
  }
}

function getCommonYtdlpArgs(url: string, proxy?: string): string[] {
  const args = [
    '--no-check-certificate',
    '--user-agent', DESKTOP_USER_AGENT,
    '--referer', getRefererForUrl(url),
    '--add-header', 'Accept-Language: en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
    '--impersonate', 'chrome',
    '--extractor-retries', '3',
    '--socket-timeout', '60',
    '--no-update',
  ];

  // Use explicit proxy, or auto-detect system proxy
  const effectiveProxy = proxy || getSystemProxy();
  if (effectiveProxy) {
    args.push('--proxy', effectiveProxy);
  }

  return args;
}

function buildCookieArgs(cookies?: string): string[] {
  if (!cookies) return [];
  if (/^(chrome|edge|firefox|brave|chromium|opera|vivaldi)([+:].*)?$/i.test(cookies)) {
    return ['--cookies-from-browser', cookies];
  }
  if (cookies.endsWith('.txt') || cookies.endsWith('.cookies')) {
    return ['--cookies', cookies];
  }
  return [];
}

// Cookie fallback chain: try browser cookies for ALL platforms.
// yt-dlp knows which sites need auth — we just give it the tools.
function getCookieFallbacks(): Array<string | undefined> {
  return ['chrome', 'edge', 'firefox', undefined];
}

function formatYtdlpError(err: Error | null, stderr: string): Error {
  const details = stderr.trim().split(/\r?\n/).slice(-8).join('\n').trim();
  return new Error(details || err?.message || 'yt-dlp \u89e3\u6790\u5931\u8d25');
}

function isImageExtension(ext: string | undefined): boolean {
  return /^(jpe?g|png|webp|gif|avif|heic)$/i.test(ext || '');
}

function extensionFromUrl(url: string | undefined): string {
  if (!url) return '';
  try {
    return path.extname(new URL(url).pathname).slice(1);
  } catch {
    return path.extname(url.split('?')[0]).slice(1);
  }
}

function isPhotoLikeInfo(info: any): boolean {
  if (isImageExtension(info?.ext)) return true;
  if (Array.isArray(info?.entries) && info.entries.length > 0) {
    return info.entries.some((entry: any) =>
      isImageExtension(entry?.ext) || isImageExtension(extensionFromUrl(entry?.url))
    );
  }
  return false;
}

function defaultMediaFormat(info: any): VideoFormat {
  const photoLike = isPhotoLikeInfo(info);
  return {
    id: DEFAULT_MEDIA_FORMAT_ID,
    ext: isImageExtension(info?.ext) ? info.ext : 'media',
    resolution: photoLike ? 'images' : 'default',
    filesize: info?.filesize || 0,
    note: photoLike ? 'photo post' : '',
    hasVideo: false,
    hasAudio: false,
    kind: 'media',
  };
}

function defaultVideoFormat(): VideoFormat {
  return {
    id: DEFAULT_VIDEO_FORMAT_ID,
    ext: 'mp4',
    resolution: 'best video + audio',
    filesize: 0,
    note: 'auto',
    hasVideo: true,
    hasAudio: true,
    kind: 'video',
  };
}

function defaultAudioFormat(): VideoFormat {
  return {
    id: DEFAULT_AUDIO_FORMAT_ID,
    ext: 'mp3',
    resolution: 'best audio',
    filesize: 0,
    note: 'auto',
    hasVideo: false,
    hasAudio: true,
    kind: 'audio',
  };
}

function execYtDlp(args: string[], timeout = 120000): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = execFile(getYtdlpPath(), args, {
      maxBuffer: 50 * 1024 * 1024,
      timeout,
    }, (err, stdout, stderr) => {
      // Reject on process error with no output, or if output is just "null"
      if (err && (!stdout || stdout.trim() === 'null')) {
        reject(formatYtdlpError(err, stderr));
        return;
      }
      // Also reject if output is empty or literal null (yt-dlp failed silently)
      const trimmed = (stdout || '').trim();
      if (!trimmed || trimmed === 'null') {
        reject(new Error(stderr.trim().split(/\r?\n/).slice(-3).join(' ') || 'yt-dlp \u65e0\u8f93\u51fa\uff0c\u53ef\u80fd\u9700\u8981\u767b\u5f55\u6216\u5df2\u89e6\u53d1\u53cd\u722c'));
        return;
      }
      resolve(stdout);
    });
  });
}

async function execYtDlpWithCookieFallbacks(baseArgs: string[], url: string, cookies?: string): Promise<string> {
  let lastError : Error | null = null;
  // If explicit cookies provided, try those only
  const fallbacks = cookies ? [cookies] : getCookieFallbacks();

  for (const cookieSource of fallbacks) {
    const cookieArgs = buildCookieArgs(cookieSource);
    try {
      const args = [...baseArgs, ...cookieArgs, url];
      return await execYtDlp(args);
    } catch (err: any) {
      lastError = err;
    }
  }

  throw lastError || new Error('yt-dlp \u89e3\u6790\u5931\u8d25');
}

export async function parseVideoUrl(url: string, cookies?: string): Promise<VideoInfo> {
  // Direct media files don't need yt-dlp — return immediately.
  // This avoids yt-dlp TLS/SSL issues on Windows and is instant.
  if (isDirectMediaUrl(url)) {
    return {
      title: path.basename(new URL(url).pathname) || 'Direct media',
      url,
      formats: [{
        id: 'direct',
        ext: path.extname(new URL(url).pathname).slice(1) || 'mp4',
        resolution: 'direct',
        filesize: 0,
        note: 'Direct download',
        hasVideo: true,
        hasAudio: true,
        kind: 'media',
      }],
    };
  }

  const args = [
    '--dump-single-json',
    '--no-playlist',
    ...getCommonYtdlpArgs(url),
  ];

  const stdout = await execYtDlpWithCookieFallbacks(args, url, cookies);

  let info: any;
  try {
    info = JSON.parse(stdout);
  } catch {
    throw new Error('yt-dlp \u8fd4\u56de\u4e86\u65e0\u6548\u7684 JSON\uff0c\u53ef\u80fd\u9700\u8981\u767b\u5f55\u6216\u94fe\u63a5\u5df2\u5931\u6548');
  }

  if (!info || typeof info !== 'object') {
    throw new Error('yt-dlp \u672a\u80fd\u89e3\u6790\u8be5\u94fe\u63a5\uff0c\u8bf7\u786e\u8ba4\u94fe\u63a5\u6709\u6548\u4e14\u672a\u88ab\u53cd\u722c\u62e6\u622a');
  }

  // Build format list: video formats, audio formats, plus auto-select options
  const videoFormats: VideoFormat[] = [];
  const audioFormats: VideoFormat[] = [];

  if (info.formats) {
    for (const fmt of info.formats) {
      const hasVideo = fmt.vcodec !== 'none';
      const hasAudio = fmt.acodec !== 'none';

      if (hasVideo) {
        const res = fmt.resolution || fmt.format_note || '';
        const label = res + (hasAudio ? '' : ' (no audio)');
        videoFormats.push({
          id: fmt.format_id,
          ext: fmt.ext || 'mp4',
          resolution: label || 'video',
          filesize: fmt.filesize || 0,
          note: fmt.format_note || '',
          hasVideo,
          hasAudio,
          kind: 'video',
        });
      }

      // Collect audio-only formats for music platforms
      if (hasAudio && !hasVideo) {
        const abr = fmt.abr ? `${Math.round(fmt.abr)}k` : fmt.format_note || '';
        audioFormats.push({
          id: fmt.format_id,
          ext: fmt.ext || 'm4a',
          resolution: abr || 'audio',
          filesize: fmt.filesize || 0,
          note: fmt.format_note || '',
          hasVideo: false,
          hasAudio: true,
          kind: 'audio',
        });
      }
    }
  }

  const formats: VideoFormat[] = [];

  // Always offer auto-select entries first
  if (videoFormats.length > 0) {
    formats.push(defaultVideoFormat());
  }
  if (audioFormats.length > 0) {
    formats.push(defaultAudioFormat());
  }

  // Then specific formats
  formats.push(...videoFormats);
  formats.push(...audioFormats);

  if (formats.length === 0) {
    formats.push(defaultMediaFormat(info));
  }

  return {
    title: info.title || path.basename(url),
    url: info.webpage_url || url,
    formats,
    thumbnail: info.thumbnail,
    duration: info.duration,
    httpHeaders: info.http_headers || undefined,
  };
}

export async function getDirectUrl(
  videoUrl: string,
  formatId: string,
  cookies?: string
): Promise<string> {
  const fmt = buildFormatSelector(formatId);
  const args = [
    '-f', fmt,
    '-g',
    '--no-playlist',
    ...getCommonYtdlpArgs(videoUrl),
  ];

  const result = (await execYtDlpWithCookieFallbacks(args, videoUrl, cookies)).trim();
  return result;
}

function buildFormatSelector(formatId: string): string {
  // Audio-only selection for music platforms
  if (formatId === DEFAULT_AUDIO_FORMAT_ID) {
    return 'bestaudio/bestaudio*[abr>0]/bestaudio[acodec!=none]/best';
  }

  // Video + audio combined
  const audioFirstFallback = 'best*[vcodec!=none][acodec!=none]/bestvideo*+bestaudio/bestvideo+bestaudio/best[acodec!=none]/best';

  if (!formatId || formatId === DEFAULT_VIDEO_FORMAT_ID) {
    return audioFirstFallback;
  }

  return `${formatId}+bestaudio/${formatId}[acodec!=none]/${audioFirstFallback}/${formatId}`;
}

function hasAudioStream(filePath: string): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(getFfmpegPath(), [
      '-hide_banner',
      '-v', 'error',
      '-i', filePath,
      '-map', '0:a:0',
      '-t', '0.1',
      '-c', 'copy',
      '-f', 'null',
      '-',
    ], { timeout: 30000 }, (err) => { resolve(!err); });
  });
}

export async function downloadVideo(
  videoUrl: string,
  formatId: string,
  outputDir: string,
  cookies?: string,
  onProgress?: (percent: string, speed: string, eta: string) => void
): Promise<string> {
  // Photo / media posts
  if (formatId === DEFAULT_MEDIA_FORMAT_ID) {
    return await downloadDefaultMedia(videoUrl, outputDir, cookies, onProgress);
  }

  // Audio-only (music platforms)
  if (formatId === DEFAULT_AUDIO_FORMAT_ID) {
    return await downloadAudio(videoUrl, outputDir, cookies, onProgress);
  }

  // Video download with retry chain
  let lastError : Error | null = null;
  const cookieFallbacks = cookies ? [cookies] : getCookieFallbacks();

  for (const attempt of buildDownloadAttempts(videoUrl, formatId)) {
    const args = [
      '-f', attempt.format,
      '--merge-output-format', 'mp4',
      '--remux-video', 'mp4',
      '--ffmpeg-location', getFfmpegPath(),
      '-o', `${outputDir}/%(title)s.%(ext)s`,
      '--no-playlist',
      ...attempt.commonArgs,
      ...(attempt.forceOverwrite ? ['--force-overwrites', '--no-continue'] : []),
      '--newline',
    ];

    for (const cookieSource of cookieFallbacks) {
      try {
        const filePath = await spawnYtDlpDownload(
          [...args, ...buildCookieArgs(cookieSource), videoUrl],
          onProgress
        );
        if (await hasAudioStream(filePath)) {
          return filePath;
        }
        lastError = new Error(`\u4e0b\u8f7d\u7684\u89c6\u9891\u65e0\u97f3\u8f68 (${attempt.name})\uff0c\u6b63\u5728\u91cd\u8bd5…`);
      } catch (err: any) {
        lastError = err;
      }
    }
  }

  throw lastError || new Error('yt-dlp \u4e0b\u8f7d\u5931\u8d25');
}

async function downloadAudio(
  videoUrl: string,
  outputDir: string,
  cookies?: string,
  onProgress?: (percent: string, speed: string, eta: string) => void
): Promise<string> {
  const args = [
    '-f', buildFormatSelector(DEFAULT_AUDIO_FORMAT_ID),
    '--extract-audio',
    '--audio-format', 'mp3',
    '--audio-quality', '0',
    '--ffmpeg-location', getFfmpegPath(),
    '-o', `${outputDir}/%(title)s.%(ext)s`,
    '--no-playlist',
    ...getCommonYtdlpArgs(videoUrl),
    '--newline',
  ];

  let lastError : Error | null = null;
  const cookieFallbacks = cookies ? [cookies] : getCookieFallbacks();

  for (const cookieSource of cookieFallbacks) {
    try {
      return await spawnYtDlpDownload(
        [...args, ...buildCookieArgs(cookieSource), videoUrl],
        onProgress
      );
    } catch (err: any) {
      lastError = err;
    }
  }

  throw lastError || new Error('yt-dlp \u97f3\u9891\u4e0b\u8f7d\u5931\u8d25');
}

interface DownloadAttempt {
  name: string;
  format: string;
  commonArgs: string[];
  forceOverwrite: boolean;
}

function buildDownloadAttempts(videoUrl: string, formatId: string): DownloadAttempt[] {
  const selectedFormat = buildFormatSelector(formatId);
  const automaticFormat = buildFormatSelector(DEFAULT_VIDEO_FORMAT_ID);
  const attempts: DownloadAttempt[] = [
    {
      name: 'selected',
      format: selectedFormat,
      commonArgs: getCommonYtdlpArgs(videoUrl),
      forceOverwrite: false,
    },
  ];

  if (formatId && formatId !== DEFAULT_VIDEO_FORMAT_ID) {
    attempts.push({
      name: 'best-audio-safe',
      format: automaticFormat,
      commonArgs: getCommonYtdlpArgs(videoUrl),
      forceOverwrite: true,
    });
  }

  return attempts;
}

async function downloadDefaultMedia(
  videoUrl: string,
  outputDir: string,
  cookies?: string,
  onProgress?: (percent: string, speed: string, eta: string) => void
): Promise<string> {
  const args = [
    '-o', `${outputDir}/%(title)s/%(playlist_index)s-%(title)s.%(ext)s`,
    ...getCommonYtdlpArgs(videoUrl),
    '--newline',
    '--yes-playlist',
  ];

  let lastError : Error | null = null;
  const cookieFallbacks = cookies ? [cookies] : getCookieFallbacks();

  for (const cookieSource of cookieFallbacks) {
    try {
      return await spawnYtDlpDownload(
        [...args, ...buildCookieArgs(cookieSource), videoUrl],
        onProgress
      );
    } catch (err: any) {
      lastError = err;
    }
  }

  throw lastError || new Error('yt-dlp \u4e0b\u8f7d\u5931\u8d25');
}

function spawnYtDlpDownload(
  args: string[],
  onProgress?: (percent: string, speed: string, eta: string) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const { spawn } = require('child_process');
    const child = spawn(getYtdlpPath(), args, {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdoutTail = '';
    let stderrText = '';
    let lastOutputPath = '';
    child.stdout.on('data', (data: Buffer) => {
      const text = data.toString();
      stdoutTail = (stdoutTail + text).slice(-16384);

      const progMatch = stdoutTail.match(/\[download\]\s+([\d.]+)%[^a]*at\s+([\d.]+\w+\/s)\s+ETA\s+(.+)/);
      if (progMatch && onProgress) {
        onProgress(progMatch[1], progMatch[2], progMatch[3].trim());
      }

      const doneMatch = text.match(/\[Merger\] Merging formats into "(.+\.mp4)"/);
      if (doneMatch) {
        onProgress?.('100', '0', '0');
        lastOutputPath = doneMatch[1];
      }

      // Audio extraction output
      const audioMatch = text.match(/\[ExtractAudio\] Destination: (.+)/);
      if (audioMatch) {
        onProgress?.('100', '0', '0');
        lastOutputPath = audioMatch[1].trim();
      }

      const destinationMatch = text.match(/\[download\] Destination: (.+)/);
      if (destinationMatch) {
        lastOutputPath = destinationMatch[1].trim();
      }

      const existingMatch = text.match(/\[download\] (.+) has already been downloaded/);
      if (existingMatch) {
        lastOutputPath = existingMatch[1].trim();
      }
    });

    child.on('close', (code: number) => {
      if (code === 0) {
        const fileNameMatch = stdoutTail.match(/Destination: (.+)/);
        const mergeMatch = stdoutTail.match(/Merging formats into "(.+)"/);
        const audioMatch = stdoutTail.match(/\[ExtractAudio\] Destination: (.+)/);
        const finalPath = lastOutputPath
          || (mergeMatch ? mergeMatch[1] : undefined)
          || (audioMatch ? audioMatch[1] : undefined)
          || (fileNameMatch ? fileNameMatch[1] : '');
        if (!finalPath) {
          reject(new Error('yt-dlp \u5df2\u5b8c\u6210\u4f46\u672a\u8fd4\u56de\u8f93\u51fa\u6587\u4ef6\u8def\u5f84'));
          return;
        }
        resolve(finalPath);
      } else {
        reject(new Error(stderrText.trim().split(/\r?\n/).slice(-8).join('\n') || `yt-dlp \u5f02\u5e38\u9000\u51fa\uff0c\u9000\u51fa\u7801 ${code}`));
      }
    });

    child.stderr.on('data', (data: Buffer) => {
      stderrText += data.toString();
      if (stderrText.length > 8000) stderrText = stderrText.slice(-8000);
    });
  });
}
