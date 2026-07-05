import http from 'http';
import https from 'https';
import { URL } from 'url';

interface PlaylistFetchResult {
  content: string;
  finalUrl: string;
}

interface ParsedPlaylist {
  mediaPlaylists: MediaVariant[];
  segments: string[];
  durationSeconds: number;
}

export interface M3u8RequestContext {
  cookies?: string;
  referer?: string;
  userAgent?: string;
}

export interface MediaVariant {
  url: string;
  bandwidth?: number;
  resolution?: string;
  codecs?: string;
  label: string;
}

export interface HlsKeyInfo {
  method: string;
  uri?: string;
  iv?: Buffer;
  keyData?: Buffer;
}

export interface ResolvedPlaylist {
  segments: string[];
  playlist: string;
  finalUrl: string;
  durationSeconds: number;
  key: HlsKeyInfo | null;
}

export interface MediaProbeResult {
  type: 'hls' | 'direct';
  url: string;
  variants: MediaVariant[];
  drm: boolean;
  error?: string;
}

function requestHeaders(context: M3u8RequestContext): Record<string, string> {
  const headers: Record<string, string> = {
    'User-Agent': context.userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
  };
  if (context.cookies) headers.Cookie = context.cookies;
  if (context.referer) headers.Referer = context.referer;
  return headers;
}

function resolvePlaylistUrl(baseUrl: string, value: string): string {
  return new URL(value, baseUrl).toString();
}

async function fetchPlaylist(
  playlistUrl: string,
  context: M3u8RequestContext,
  redirectCount = 0
): Promise<PlaylistFetchResult> {
  if (redirectCount > 5) {
    throw new Error('\u91cd\u5b9a\u5411\u6b21\u6570\u8fc7\u591a\uff0c\u65e0\u6cd5\u83b7\u53d6\u64ad\u653e\u5217\u8868');
  }

  return new Promise<PlaylistFetchResult>((resolve, reject) => {
    const u = new URL(playlistUrl);
    const mod = u.protocol === 'https:' ? https : http;
    const req = mod.get({
      protocol: u.protocol,
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      headers: requestHeaders(context),
      rejectUnauthorized: false,
      timeout: 30000,
    }, (resp) => {
      const statusCode = resp.statusCode || 0;
      const location = resp.headers.location;

      if (statusCode >= 300 && statusCode < 400 && location) {
        resp.destroy();
        fetchPlaylist(resolvePlaylistUrl(playlistUrl, location), context, redirectCount + 1)
          .then(resolve, reject);
        return;
      }

      if (statusCode >= 400) {
        resp.destroy();
        reject(new Error(`\u64ad\u653e\u5217\u8868\u8bf7\u6c42\u5931\u8d25\uff0cHTTP ${statusCode}`));
        return;
      }

      let data = '';
      resp.setEncoding('utf8');
      resp.on('data', (c: string) => { data += c; });
      resp.on('end', () => resolve({ content: data, finalUrl: playlistUrl }));
      resp.on('error', (err) => reject(new Error(`\u54cd\u5e94\u6d41\u9519\u8bef\uff1a${err.message}`)));
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('\u64ad\u653e\u5217\u8868\u8bf7\u6c42\u8d85\u65f6\uff0830\u79d2\uff09'));
    });
  });
}

function parsePlaylist(content: string, baseUrl: string): ParsedPlaylist {
  const mediaPlaylists: MediaVariant[] = [];
  const segments: string[] = [];
  let durationSeconds = 0;
  let pendingVariant: Omit<MediaVariant, 'url' | 'label'> | null = null;

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    if (line.startsWith('#EXTINF:')) {
      const duration = parseFloat(line.slice('#EXTINF:'.length).split(',')[0]);
      if (Number.isFinite(duration)) durationSeconds += duration;
      continue;
    }

    if (line.startsWith('#EXT-X-STREAM-INF')) {
      pendingVariant = parseStreamInfo(line);
      continue;
    }

    if (line.startsWith('#')) continue;

    const resolved = resolvePlaylistUrl(baseUrl, line);
    if (pendingVariant || line.toLowerCase().includes('.m3u8')) {
      mediaPlaylists.push({
        url: resolved,
        ...pendingVariant,
        label: formatVariantLabel(pendingVariant),
      });
      pendingVariant = null;
    } else {
      segments.push(resolved);
    }
  }

  return { mediaPlaylists, segments, durationSeconds };
}

function parseStreamInfo(line: string): Omit<MediaVariant, 'url' | 'label'> {
  return {
    bandwidth: parseNumberAttribute(line, 'BANDWIDTH'),
    resolution: parseStringAttribute(line, 'RESOLUTION'),
    codecs: parseStringAttribute(line, 'CODECS'),
  };
}

function parseNumberAttribute(line: string, key: string): number | undefined {
  const value = parseStringAttribute(line, key);
  if (!value) return undefined;
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseStringAttribute(line: string, key: string): string | undefined {
  const match = line.match(new RegExp(`${key}=("[^"]+"|[^,]+)`));
  if (!match) return undefined;
  return match[1].replace(/^"|"$/g, '');
}

function formatVariantLabel(variant?: Omit<MediaVariant, 'url' | 'label'> | null): string {
  if (!variant) return 'HLS';

  const parts: string[] = [];
  if (variant.resolution) parts.push(variant.resolution);
  if (variant.bandwidth) parts.push(`${Math.round(variant.bandwidth / 1000)} kbps`);
  if (variant.codecs) parts.push(variant.codecs.split(',')[0]);
  return parts.join(' / ') || 'HLS';
}

function extractKeyInfo(content: string, baseUrl: string): HlsKeyInfo | null {
  const match = content.match(/#EXT-X-KEY:METHOD=([^,\s]+)((?:,[^,\s]+)*)/i);
  if (!match) return null;

  const method = match[1].toUpperCase();
  const attrs = match[2] || '';

  const uri = parseStringAttributeFromText(attrs, 'URI');
  const ivHex = parseStringAttributeFromText(attrs, 'IV');

  const key: HlsKeyInfo = { method };

  if (uri) {
    key.uri = resolvePlaylistUrl(baseUrl, uri);
  }

  if (ivHex && /^0x[0-9a-fA-F]+$/.test(ivHex)) {
    key.iv = Buffer.from(ivHex.slice(2), 'hex');
  }

  return key;
}

function parseStringAttributeFromText(text: string, key: string): string | undefined {
  const match = text.match(new RegExp(`${key}=("[^"]+"|[^,]+)`));
  if (!match) return undefined;
  return match[1].replace(/^"|"$/g, '');
}

async function fetchHlsKey(keyUri: string, context: M3u8RequestContext): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const u = new URL(keyUri);
    const mod = u.protocol === 'https:' ? https : http;
    const req = mod.get({
      protocol: u.protocol,
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      headers: requestHeaders(context),
      rejectUnauthorized: false,
      timeout: 15000,
    }, (resp) => {
      const statusCode = resp.statusCode || 0;
      if (statusCode >= 300) {
        resp.destroy();
        reject(new Error(`\u5bc6\u94a5\u8bf7\u6c42\u5931\u8d25\uff0cHTTP ${statusCode}`));
        return;
      }

      const chunks: Buffer[] = [];
      resp.on('data', (c: Buffer) => chunks.push(c));
      resp.on('end', () => resolve(Buffer.concat(chunks)));
      resp.on('error', reject);
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('\u5bc6\u94a5\u8bf7\u6c42\u8d85\u65f6'));
    });
  });
}

export async function resolveM3u8Playlist(
  playlistUrl: string,
  context: M3u8RequestContext,
  visited = new Set<string>()
): Promise<ResolvedPlaylist> {
  if (visited.has(playlistUrl)) {
    throw new Error('\u64ad\u653e\u5217\u8868\u4e2d\u5b58\u5728\u5faa\u73af\u5f15\u7528');
  }
  visited.add(playlistUrl);

  const fetched = await fetchPlaylist(playlistUrl, context);
  const parsed = parsePlaylist(fetched.content, fetched.finalUrl);

  if (parsed.segments.length > 0) {
    const key = extractKeyInfo(fetched.content, fetched.finalUrl);
    let resolvedKey: HlsKeyInfo | null = key;

    // If key has a URI, fetch it now
    if (key && key.uri && key.method === 'AES-128') {
      try {
        key.keyData = await fetchHlsKey(key.uri, context);
      } catch (err: any) {
        console.warn('[nsp] Failed to fetch HLS key, ffmpeg may try itself:', err.message);
        // Keep key without keyData — ffmpeg will try to fetch it
      }
    }

    return {
      segments: parsed.segments,
      playlist: fetched.content,
      finalUrl: fetched.finalUrl,
      durationSeconds: parsed.durationSeconds,
      key: resolvedKey,
    };
  }

  if (parsed.mediaPlaylists.length === 0) {
    return {
      segments: [],
      playlist: fetched.content,
      finalUrl: fetched.finalUrl,
      durationSeconds: parsed.durationSeconds,
      key: null,
    };
  }

  return resolveM3u8Playlist(parsed.mediaPlaylists[0].url, context, visited);
}

export async function probeMediaUrl(url: string, context: M3u8RequestContext): Promise<MediaProbeResult> {
  if (!url.toLowerCase().includes('.m3u8')) {
    return {
      type: 'direct',
      url,
      variants: [{ url, label: 'Direct media' }],
      drm: false,
    };
  }

  try {
    const fetched = await fetchPlaylist(url, context);
    const drm = fetched.content.includes('#EXT-X-KEY') && /METHOD=(SAMPLE-AES|AES-128|ISO-23001-7)/i.test(fetched.content);
    const parsed = parsePlaylist(fetched.content, fetched.finalUrl);
    const variants = parsed.mediaPlaylists.length > 0
      ? parsed.mediaPlaylists
      : [{ url: fetched.finalUrl, label: 'HLS', bandwidth: undefined, resolution: undefined, codecs: undefined }];

    return {
      type: 'hls',
      url: fetched.finalUrl,
      variants,
      drm,
    };
  } catch (err: any) {
    return {
      type: 'hls',
      url,
      variants: [{ url, label: 'HLS' }],
      drm: false,
      error: err.message,
    };
  }
}
