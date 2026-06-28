import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Format {
  id: string; ext: string; resolution: string; filesize: number; note: string;
  hasVideo: boolean; hasAudio: boolean;
}

interface VideoInfo {
  title: string; url: string; formats: Format[];
  httpHeaders?: Record<string, string>;
}

export function DownloadBar(): React.ReactElement {
  const { t } = useTranslation();
  const [url, setUrl] = useState('');
  const [parsing, setParsing] = useState(false);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [selectedFormat, setSelectedFormat] = useState('');
  const [error, setError] = useState('');

  // Any http/https URL that isn't an obvious direct file download
  // gets the "Parse Video" button so yt-dlp can inspect it.
  const isVideoUrl = (u: string) => {
    if (!/^https?:\/\//i.test(u)) return false;
    const pathname = (() => { try { return new URL(u).pathname; } catch { return ''; } })();
    const lowerPath = pathname.toLowerCase();
    // Direct file downloads — skip yt-dlp
    const fileExts = /\.(zip|rar|7z|tar|gz|bz2|xz|lz4|zst|tgz|exe|msi|dmg|pkg|deb|rpm|apk|ipa|whl|jar|war|dll|so|dylib|iso|img|bin|pdf|doc|docx|xls|xlsx|ppt|pptx|safetensors|ckpt|pt|pth|onnx|gguf|ggml|tflite|glb|gltf|obj|fbx|stl|csv|tsv|json|jsonl|yaml|yml|xml|parquet|ttf|otf|woff|woff2|torrent|nzb|psd|ai|eps|svg)(\?|$)/i;
    if (fileExts.test(lowerPath)) return false;
    return true;
  };

  const handleAdd = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;

    // Split by newlines for batch add
    const lines = trimmed.split(/\r?\n/).map((s: string) => s.trim()).filter((s: string) => s.length > 0);
    if (lines.length === 0) return;

    try {
      let firstError = '';
      for (let i = 0; i < lines.length; i++) {
        try {
          await (window as any).electronAPI.download.add(lines[i]);
        } catch (err: any) {
          if (!firstError) firstError = err.message;
        }
      }
      setUrl(''); setVideoInfo(null);
      setError(firstError ? `${lines.length} URLs processed, first error: ${firstError}` : '');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleAddTorrent = async () => {
    try {
      const gid = await (window as any).electronAPI.download.selectTorrent();
      if (gid) {
        setError('');
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleParse = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setParsing(true);
    setError('');
    try {
      const info = await (window as any).electronAPI.video.parse(trimmed);
      setVideoInfo(info);
      // Auto-select first format with both video+audio, or first video format
      const vidFmt = info.formats.find((f: Format) => f.hasVideo && f.hasAudio) || info.formats[0];
      if (vidFmt) setSelectedFormat(vidFmt.id);
    } catch (err: any) {
      setError(err.message);
    }
    setParsing(false);
  };

  const handleDownloadWithFormat = async () => {
    if (!videoInfo || !selectedFormat) return;
    try {
      setError(t('download.downloading'));
      const filePath = await (window as any).electronAPI.video.download(videoInfo.url, selectedFormat);
      setUrl(''); setVideoInfo(null); setSelectedFormat(''); setError('');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const showVideoBtn = isVideoUrl(url);
  const looksLikeFilename = url.trim() && !/^https?:\/\//i.test(url.trim()) && /\.[a-z0-9]{2,4}$/i.test(url.trim().split('?')[0]);

  return (
    <div>
      <div style={styles.bar}>
        <input
          style={styles.input}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') !showVideoBtn ? handleAdd() : handleParse(); }}
          onPaste={(e) => {
            const text = e.clipboardData.getData('text');
            if (text) { e.preventDefault(); setUrl(text); }
        }}
          placeholder={t('download.urlPlaceholder')}
          spellCheck={false}
        />
        {showVideoBtn ? (
          <button style={styles.btnParse} onClick={handleParse} disabled={parsing}>
            {parsing ? t('download.parsing') : t('download.parseVideo')}
          </button>
        ) : (
          <>
            <button style={styles.btn} onClick={handleAdd}>{t('download.add')}</button>
            <button style={styles.btnTorrent} onClick={handleAddTorrent} title={t('download.addTorrent')}>🧲</button>
          </>
        )}

        {looksLikeFilename && !showVideoBtn && (
          <div style={styles.hint}>{t('download.urlHint')}</div>
        )}
      </div>

      {error && <div style={styles.error}>{error}</div>}

      {videoInfo && (
        <div style={styles.panel}>
          <div style={styles.title}>{videoInfo.title}</div>
          <div style={styles.qualityRow}>
            <span style={styles.qlabel}>{t('download.quality')}:</span>
            <select
              style={styles.qselect}
              value={selectedFormat}
              onChange={(e) => setSelectedFormat(e.target.value)}
            >
              {videoInfo.formats.map((f: Format) => (
                <option key={f.id} value={f.id}>
                  {f.resolution} ({f.ext}){!f.hasAudio ? ` [${t('download.noAudio')}]` : ''} {f.filesize ? `- ${(f.filesize / 1024 / 1024).toFixed(1)}MB` : ''}
                </option>
              ))}
            </select>
            <button style={styles.btn} onClick={handleDownloadWithFormat}>{t('download.download')}</button>
          </div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  bar: { display: 'flex', padding: '10px 14px', gap: 8, borderBottom: '1px solid #21262d' },
  input: {
    flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
    padding: '8px 12px', color: '#c9d1d9', fontSize: 13, outline: 'none',
  },
  btn: {
    background: '#238636', color: '#ffffff', border: 'none', borderRadius: 6,
    padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
  },
  btnParse: {
    background: '#1f6feb', color: '#ffffff', border: 'none', borderRadius: 6,
    padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
  },
  btnTorrent: {
    background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 6,
    padding: '6px 10px', fontSize: 16, cursor: 'pointer', whiteSpace: 'nowrap', lineHeight: 1,
  },
  error: { padding: '6px 14px', color: '#f85149', fontSize: 12, background: '#490202', borderBottom: '1px solid #f85149' },
  hint: { padding: '4px 14px', color: '#d29922', fontSize: 11, background: '#1a1200' },
  panel: { padding: '10px 14px', borderBottom: '1px solid #21262d', background: '#161b22' },
  title: { fontSize: 13, fontWeight: 600, color: '#c9d1d9', marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  qualityRow: { display: 'flex', alignItems: 'center', gap: 8 },
  qlabel: { fontSize: 12, color: '#8b949e', whiteSpace: 'nowrap' },
  qselect: {
    flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
    padding: '6px 8px', color: '#c9d1d9', fontSize: 12, outline: 'none',
  },
};
