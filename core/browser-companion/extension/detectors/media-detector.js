/* Media URL Detector — sniff media URLs from page content and network.

Port of nsp-downloader/extension/content.js sniffing logic.
Detects: M3U8, MPD/DASH, MP4, TS, FLV, WebM, MKV
*/

(function() {
'use strict';

const MEDIA_URL_RE = /\.(m3u8|mpd|mp4|m4s|ts|flv|webm|mkv)(?:[?#]|$)/i;
const MEDIA_PATH_RE = /\/m3u8\//i;

function detectKind(url) {
  const u = url.split('?')[0].split('#')[0];
  if (/\.m3u8$/i.test(u)) return 'm3u8';
  if (/\.mpd$/i.test(u)) return 'dash';
  if (/\.mp4$/i.test(u)) return 'mp4';
  if (/\.(ts|m4s)$/i.test(u)) return 'segment';
  if (/\.(flv|webm|mkv)$/i.test(u)) return 'video';
  return 'unknown';
}

function scanAnchors() {
  const candidates = [];
  const anchors = document.querySelectorAll('a[href]');
  for (const a of anchors) {
    const url = a.href;
    if (MEDIA_URL_RE.test(url) || MEDIA_PATH_RE.test(url)) {
      candidates.push({
        url: url,
        kind: detectKind(url),
        source: 'dom',
        confidence: 0.7,
        title: a.textContent?.trim() || ''
      });
    }
  }
  return candidates;
}

function scanVideoElements() {
  const candidates = [];
  const videos = document.querySelectorAll('video');
  for (const v of videos) {
    if (v.src && MEDIA_URL_RE.test(v.src)) {
      candidates.push({
        url: v.src,
        kind: detectKind(v.src),
        source: 'dom',
        confidence: 0.9,
        title: v.title || document.title
      });
    }
    const sources = v.querySelectorAll('source[src]');
    for (const s of sources) {
      if (MEDIA_URL_RE.test(s.src)) {
        candidates.push({
          url: s.src,
          kind: detectKind(s.src),
          source: 'dom',
          confidence: 0.9,
          title: s.title || v.title || document.title
        });
      }
    }
  }
  return candidates;
}

function scanPage() {
  const seen = new Set();
  const all = [...scanAnchors(), ...scanVideoElements()];
  return all.filter(c => {
    const key = c.url;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Expose for use by content-script
window.__CRUX_MEDIA_DETECTOR__ = {
  scanPage,
  detectKind,
  MEDIA_URL_RE
};

})();
