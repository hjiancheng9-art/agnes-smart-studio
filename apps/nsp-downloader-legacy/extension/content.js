// NetSpeedPro - Video Sniffer
(function() {
'use strict';

let seen = {};
let MEDIA_URL_RE = /\.(m3u8|mpd|mp4|m4s|ts|flv|webm|mkv)(?:[?#]|$)/i;
let MEDIA_PATH_RE = /\/m3u8\//i;
let scanRuns = 0;
let scanInterval = null;

function installPageHook() {
  if (!document.documentElement && !document.head) {
    document.addEventListener('DOMContentLoaded', installPageHook, { once: true });
    return;
  }

  let script = document.createElement('script');
  script.src = chrome.runtime.getURL('page-hook.js');
  script.onload = function() { script.remove(); };
  (document.documentElement || document.head).appendChild(script);
}

function extractMediaUrl(url) {
  let resolvedUrl = new URL(url, location.href);
  let params = ['video', 'url', 'src', 'file', 'play'];

  for (let i = 0; i < params.length; i++) {
    let value = resolvedUrl.searchParams.get(params[i]);
    if (value && MEDIA_URL_RE.test(value)) {
      return new URL(value, location.href).toString();
    }
  }

  return resolvedUrl.toString();
}

function getSeenKey(url, label) {
  if (/^(blob|data):/i.test(url)) return url;
  try {
    let parsed = new URL(url);
    if (/\.(m4s|ts)$/i.test(parsed.pathname) || label === 'M4S' || label === 'TS') {
      return parsed.origin + parsed.pathname;
    }
  } catch {
    return url;
  }
  return url;
}

function labelForUrl(url) {
  if (/^blob:/i.test(url)) return 'BLOB';
  if (/\.m3u8(?:[?#]|$)/i.test(url)) return 'M3U8';
  if (/\.mpd(?:[?#]|$)/i.test(url)) return 'DASH';
  if (/\.mp4(?:[?#]|$)/i.test(url)) return 'MP4';
  if (/\.m4s(?:[?#]|$)/i.test(url)) return 'M4S';
  if (/\.ts(?:[?#]|$)/i.test(url)) return 'TS';
  return 'MEDIA';
}

function rememberMedia(url, label) {
  if (!url || typeof url !== 'string') return false;

  let resolvedUrl;
  try {
    resolvedUrl = extractMediaUrl(url);
  } catch {
    return false;
  }

  let mediaLabel = label || labelForUrl(resolvedUrl);
  let seenKey = getSeenKey(resolvedUrl, mediaLabel);
  if (seen[seenKey]) return false;
  seen[seenKey] = true;

  let item = {
    url: resolvedUrl,
    pageUrl: location.href,
    title: document.title || mediaLabel,
    label: mediaLabel,
    timestamp: Date.now(),
  };

  // Store in chrome.storage.local (survives service worker restart)
  let storageKey = 'nsp_media_' + resolvedUrl;
  chrome.storage.local.set({ [storageKey]: item });

  // Also try runtime.sendMessage (works if SW is awake)
  try {
    chrome.runtime.sendMessage({
      type: 'media-found',
      item: item,
    });
  } catch(e) {}

  return true;
}

function looksLikeMediaUrl(url) {
  return typeof url === 'string' && (MEDIA_URL_RE.test(url) || MEDIA_PATH_RE.test(url));
}

function scanPerformanceResources() {
  if (!performance || !performance.getEntriesByType) return 0;

  let count = 0;
  performance.getEntriesByType('resource').forEach(function(entry) {
    if (!entry || !looksLikeMediaUrl(entry.name)) return;
    if (rememberMedia(entry.name, labelForUrl(entry.name))) count += 1;
  });
  return count;
}

function scanMediaElements() {
  let count = 0;
  document.querySelectorAll('video, audio, source').forEach(function(el) {
    let url = el.currentSrc || el.src;
    if (!url) return;
    if (/^blob:/i.test(url) || looksLikeMediaUrl(url)) {
      if (rememberMedia(url, labelForUrl(url))) count += 1;
    }
  });
  return count;
}

// Scan iframe src attributes (catches dplayer.html?video=...m3u8 patterns)
function scanIframeSources() {
  let count = 0;
  document.querySelectorAll('iframe').forEach(function(el) {
    let src = el.src || el.getAttribute('data-src') || '';
    if (!src) return;
    // Direct match on iframe src
    if (looksLikeMediaUrl(src)) {
      if (rememberMedia(src, 'IFRAME')) count += 1;
    }
    // Extract video URLs from query params (e.g. ?video=https://...m3u8)
    try {
      let u = new URL(src, location.href);
      let params = ['video', 'url', 'src', 'file', 'source', 'play', 'v', 'vid', 'mp4', 'm3u8', 'hls', 'dash'];
      for (let i = 0; i < params.length; i++) {
        let val = u.searchParams.get(params[i]);
        if (val && looksLikeMediaUrl(val)) {
          if (rememberMedia(val, 'IFRAME-PARAM')) count += 1;
        }
      }
    } catch(e) {}
  });
  return count;
}

// Scan raw HTML for media URLs (catches inline scripts, data attributes, etc.)
function scanRawHTML() {
  let count = 0;
  try {
    let html = document.documentElement.outerHTML || document.body.innerHTML || '';
    let re = /https?:\/\/[^"'\s<>]+\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)[^"'\s<>]*/gi;
    let m;
    while ((m = re.exec(html)) !== null) {
      if (rememberMedia(m[0], 'RAW-HTML')) count += 1;
    }
    // Also match /m3u8/ paths
    let re2 = /https?:\/\/[^"'\s<>]*\/m3u8\/[^"'\s<>]*/gi;
    while ((m = re2.exec(html)) !== null) {
      if (rememberMedia(m[0], 'RAW-M3U8')) count += 1;
    }
  } catch(e) {}
  return count;
}

// Deep scan data attributes
function scanDataAttributes() {
  let count = 0;
  let attrs = ['data-video', 'data-url', 'data-src', 'data-mp4', 'data-m3u8',
               'data-file', 'data-source', 'data-play', 'data-stream'];
  for (let a = 0; a < attrs.length; a++) {
    document.querySelectorAll('[' + attrs[a] + ']').forEach(function(el) {
      let val = el.getAttribute(attrs[a]);
      if (val && looksLikeMediaUrl(val)) {
        if (rememberMedia(val, 'ATTR')) count += 1;
      }
    });
  }
  return count;
}

function requestPageContextScan() {
  window.postMessage({ source: 'nsp-content', type: 'scan-now' }, '*');
}

function scanNow() {
  requestPageContextScan();
  return scanPerformanceResources() + scanMediaElements() +
         scanIframeSources() + scanRawHTML() + scanDataAttributes();
}

function scheduleStartupScans() {
  scanNow();
  // Also do a delayed scan after full page load (catches late iframes)
  window.setTimeout(function() { scanNow(); }, 1500);
  window.setTimeout(function() { scanNow(); }, 3000);
  // Scan every 2s for the first 30s, then every 5s indefinitely
  scanInterval = window.setInterval(function() {
    scanRuns += 1;
    scanNow();
    // After 15 scans (30s), slow down to every 5s
    if (scanRuns === 15 && scanInterval) {
      window.clearInterval(scanInterval);
      scanInterval = window.setInterval(function() {
        scanNow();
      }, 5000);
    }
  }, 2000);
}

window.addEventListener('message', function(event) {
  if (event.source !== window || !event.data || event.data.source !== 'nsp-page-hook') return;
  rememberMedia(event.data.url, event.data.label || 'MEDIA');
});

installPageHook();

if (window.PerformanceObserver) {
  new PerformanceObserver(function(list) {
    list.getEntries().forEach(function(e) {
      if (looksLikeMediaUrl(e.name)) rememberMedia(e.name, labelForUrl(e.name));
    });
  }).observe({entryTypes:['resource']});
}

let _fetch = window.fetch;
window.fetch = function(u, o) {
  let url = typeof u === 'string' ? u : (u && u.url);
  if (looksLikeMediaUrl(url)) rememberMedia(url, labelForUrl(url));
  return _fetch.apply(this, arguments);
};

let _open = XMLHttpRequest.prototype.open;
let _send = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(m, url) {
  this._nsp_url = url;
  return _open.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function() {
  let self = this;
  this.addEventListener('load', function() {
    if (looksLikeMediaUrl(self._nsp_url)) {
      rememberMedia(self._nsp_url, labelForUrl(self._nsp_url));
    }
  });
  return _send.apply(this, arguments);
};

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (!msg || msg.type !== 'scan-now') return;
  let found = scanNow();
  sendResponse({ success: true, found: found });
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', scheduleStartupScans, { once: true });
} else {
  scheduleStartupScans();
}

console.log('[NSP] Sniffer loaded');
})();
