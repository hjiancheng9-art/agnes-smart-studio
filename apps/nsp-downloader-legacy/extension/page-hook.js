(function() {
  'use strict';

  let seen = {};

  // ── broader media URL detection ──────────────────────────────
  function isMediaUrl(url) {
    if (!url || typeof url !== 'string') return false;
    return /\.(m3u8|mpd|mp4|m4s|ts|flv|webm|mkv|avi|mov|wmv)(?:[?#]|$)/i.test(url) ||
           /\/video\//i.test(url) ||
           /\/hls\//i.test(url) ||
           /\/dash\//i.test(url) ||
           /\/stream/i.test(url) ||
           /\/m3u8\//i.test(url) ||
           /video_id=/i.test(url) ||
           /token=/i.test(url) && /\.(mp4|m3u8)/i.test(url);
  }

  // Extract media URLs from query parameter values (e.g. ?video=https://...m3u8)
  function extractParamMediaUrls(url) {
    let found = [];
    try {
      let u = new URL(url, location.href);
      // Common param names that carry video URLs
      let params = ['video', 'url', 'src', 'file', 'source', 'play', 'v', 'vid', 'mp4', 'm3u8', 'hls', 'dash'];
      params.forEach(function(p) {
        let val = u.searchParams.get(p);
        if (val && isMediaUrl(val)) {
          found.push(val);
        }
      });
    } catch(e) {}
    return found;
  }

  function labelFor(url) {
    if (!url) return 'MEDIA';
    if (/\.m3u8(?:[?#]|$)/i.test(url)) return 'M3U8';
    if (/\.mpd(?:[?#]|$)/i.test(url)) return 'DASH';
    if (/\.mp4(?:[?#]|$)/i.test(url)) return 'MP4';
    if (/\.m4s(?:[?#]|$)/i.test(url)) return 'M4S';
    if (/\.ts(?:[?#]|$)/i.test(url)) return 'TS';
    if (/\.flv(?:[?#]|$)/i.test(url)) return 'FLV';
    if (/\.webm(?:[?#]|$)/i.test(url)) return 'WEBM';
    if (/\/hls\//i.test(url)) return 'HLS';
    return 'MEDIA';
  }

  function report(url, label) {
    if (!url || typeof url !== 'string') return;
    if (!isMediaUrl(url)) return;

    let resolved;
    try {
      resolved = new URL(url, location.href).toString();
    } catch {
      return;
    }

    if (seen[resolved]) return;
    seen[resolved] = true;
    window.postMessage({
      source: 'nsp-page-hook',
      url: resolved,
      label: label || labelFor(resolved),
    }, '*');
  }

  function pickUrl(item) {
    if (!item || typeof item !== 'object') return '';
    return item.baseUrl || item.base_url || item.url || item.src ||
           (item.backupUrl && item.backupUrl[0]) ||
           (item.backup_url && item.backup_url[0]) ||
           (item.url_list && item.url_list[0]) ||
           (item.urlList && item.urlList[0]) || '';
  }

  // ── vidorev / WordPress theme scanner ────────────────────────
  function scanVidorevData() {
    try {
      // vidorev theme stores video config in multiple places
      let cfg = window.vidorev_jav_js_object ||
                window.vidorev_plugin ||
                window._vidorev_video_data ||
                window._video_config;

      // Walk ALL global vars looking for video URLs (covers obfuscated names)
      for (let key of Object.keys(window)) {
        try {
          let val = window[key];
          if (!val || typeof val !== 'object') continue;
          // vidorev often has {video_url, video_source, embed_url, ...}
          let vurl = val.video_url || val.videoUrl || val.video_src || val.videoSrc ||
                     val.embed_url || val.embedUrl || val.file || val.src ||
                     val.url || val.mp4 || val.m3u8;
          if (vurl && typeof vurl === 'string' && isMediaUrl(vurl)) {
            report(vurl, 'VIDOREV');
          }
          // Array of sources
          if (Array.isArray(val.sources) || Array.isArray(val.video_sources)) {
            let srcs = val.sources || val.video_sources;
            srcs.forEach(function(s) {
              let u = typeof s === 'string' ? s : (s.url || s.src || s.file);
              if (u) report(u, 'VIDOREV-SRC');
            });
          }
        } catch(e) { /* skip unreadable props */ }
      }
    } catch(e) { /* ignore */ }
  }

  // ── scan iframe src for known video hosts ────────────────────
  function scanIframeSources() {
    document.querySelectorAll('iframe').forEach(function(el) {
      let src = el.src || el.getAttribute('data-src') || '';
      if (!src) return;
      // iframe itself may contain a media URL
      report(src, 'IFRAME');
      // Extract video URLs from query params (e.g. dplayer.html?video=...m3u8)
      let paramUrls = extractParamMediaUrls(src);
      paramUrls.forEach(function(u) { report(u, 'IFRAME-PARAM'); });
      // Also scan the iframe's document if same-origin
      try {
        let doc = el.contentDocument || el.contentWindow && el.contentWindow.document;
        if (doc) {
          doc.querySelectorAll('video, audio, source').forEach(function(v) {
            let url = v.currentSrc || v.src;
            if (url) report(url, 'IFRAME-MEDIA');
          });
        }
      } catch(e) { /* cross-origin, can't access */ }
    });
  }

  // ── deep scan: find video URLs in any element attribute ──────
  function deepScanAttributes() {
    let attrs = ['data-video', 'data-url', 'data-src', 'data-mp4', 'data-m3u8',
                 'data-file', 'data-source', 'data-play', 'data-stream',
                 'data-video-url', 'data-video-src', 'data-embed'];
    attrs.forEach(function(attr) {
      document.querySelectorAll('[' + attr + ']').forEach(function(el) {
        let val = el.getAttribute(attr);
        if (val) {
          if (isMediaUrl(val)) report(val, 'ATTR-' + attr.toUpperCase());
          // Also extract from query params in attribute values
          extractParamMediaUrls(val).forEach(function(u) {
            report(u, 'ATTR-PARAM');
          });
        }
      });
    });
  }

  // ── scan raw page HTML for media URLs (catches inline scripts, etc.) ──
  function scanRawHTML() {
    try {
      let html = document.documentElement.outerHTML || document.body.innerHTML || '';
      // Match full URLs ending with media extensions
      let re = /https?:\/\/[^"'\s<>]+\.(?:m3u8|mp4|mpd|m4s|ts|flv|webm|mkv)[^"'\s<>]*/gi;
      let match;
      while ((match = re.exec(html)) !== null) {
        report(match[0], 'RAW-HTML');
      }
      // Also match URLs that contain /m3u8/ in path (like cdn2020.com/video/m3u8/.../index.m3u8)
      let re2 = /https?:\/\/[^"'\s<>]*\/m3u8\/[^"'\s<>]*/gi;
      while ((match = re2.exec(html)) !== null) {
        report(match[0], 'RAW-M3U8-PATH');
      }
    } catch(e) {}
  }

  // ── hook AJAX responses to catch dynamically loaded URLs ─────
  let originalFetch = window.fetch;
  window.fetch = function(input, init) {
    let url = typeof input === 'string' ? input : (input && input.url);
    report(url);

    let promise = originalFetch.apply(this, arguments);
    // Try to parse JSON responses for video URLs
    promise.then(function(resp) {
      if (!resp || !resp.clone) return;
      try {
        let clone = resp.clone();
        clone.text().then(function(body) {
          extractUrlsFromText(body);
        }).catch(function() {});
      } catch(e) {}
    }).catch(function() {});
    return promise;
  };

  let originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    this._nsp_url = url;
    report(url);
    return originalOpen.apply(this, arguments);
  };

  let originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function() {
    let self = this;
    this.addEventListener('load', function() {
      if (self.responseText) {
        extractUrlsFromText(self.responseText);
      }
      if (self.responseURL) {
        report(self.responseURL);
      }
    });
    return originalSend.apply(this, arguments);
  };

  function extractUrlsFromText(text) {
    if (!text || typeof text !== 'string') return;
    // Match common URL patterns in JSON/HTML responses
    let patterns = [
      /https?:\/\/[^"'\s]*?\.(?:m3u8|mpd|mp4|m4s|ts|flv|webm)[^"'\s]*/gi,
      /https?:\/\/[^"'\s]*?\/(?:hls|dash|video|stream)\/[^"'\s]*/gi,
      /"video_url"\s*:\s*"([^"]+)"/gi,
      /"videoUrl"\s*:\s*"([^"]+)"/gi,
      /"url"\s*:\s*"([^"]*\.(?:m3u8|mp4|mpd)[^"]*)"/gi,
      /"src"\s*:\s*"([^"]*\.(?:m3u8|mp4|mpd)[^"]*)"/gi,
      /"file"\s*:\s*"([^"]*\.(?:m3u8|mp4|mpd)[^"]*)"/gi,
    ];
    patterns.forEach(function(re) {
      let match;
      while ((match = re.exec(text)) !== null) {
        let u = match[1] || match[0];
        if (u) report(u.replace(/\\\//g, '/'), 'AJAX');
      }
    });
  }

  // ── hook createObjectURL ─────────────────────────────────────
  let originalCreateObjectURL = URL.createObjectURL;
  URL.createObjectURL = function(object) {
    let blobUrl = originalCreateObjectURL.apply(this, arguments);
    window.postMessage({
      source: 'nsp-page-hook',
      url: blobUrl,
      label: 'BLOB',
    }, '*');
    return blobUrl;
  };

  // ── scan media elements ──────────────────────────────────────
  function scanMediaElements() {
    document.querySelectorAll('video, audio, source').forEach(function(el) {
      let url = el.currentSrc || el.src;
      if (/^blob:/i.test(url || '')) {
        window.postMessage({
          source: 'nsp-page-hook',
          url: url,
          label: 'BLOB',
        }, '*');
        return;
      }
      report(url);
    });
  }

  // ── full scan ────────────────────────────────────────────────
  function fullScan() {
    scanMediaElements();
    scanIframeSources();
    deepScanAttributes();
    scanRawHTML();
    scanVidorevData();
    scanBilibiliPlayinfo();
    scanDouyinVideoData();
  }

  function scanBilibiliPlayinfo() {
    let playinfo = window.__playinfo__ || window.__INITIAL_STATE__ && window.__INITIAL_STATE__.playinfo;
    let data = playinfo && (playinfo.data || playinfo.result || playinfo);
    let dash = data && data.dash;
    if (!dash) return;
    (dash.video || []).forEach(function(item) { report(pickUrl(item), 'BILI-DASH-VIDEO'); });
    (dash.audio || []).forEach(function(item) { report(pickUrl(item), 'BILI-DASH-AUDIO'); });
  }

  function scanDouyinVideoData() {
    try {
      let renderData = window._SSR_HYDRATED_DATA || window.__RENDER_DATA__;
      if (!renderData) return;
      let detail = renderData.app && renderData.app.videoDetail || renderData.detail;
      if (!detail) return;
      let video = detail.video || detail.videoInfo;
      if (!video) return;
      let playAddr = video.play_addr || video.playAddr;
      if (playAddr) {
        let urlList = playAddr.url_list || playAddr.urlList || [];
        urlList.forEach(function(u) { report(u, 'DOUYIN-VIDEO'); });
      }
      let downloadAddr = video.download_addr || video.downloadAddr;
      if (downloadAddr) {
        let dlUrlList = downloadAddr.url_list || downloadAddr.urlList || [];
        dlUrlList.forEach(function(u) { report(u, 'DOUYIN-DOWNLOAD'); });
      }
    } catch (e) { /* ignore */ }
  }

  // ── message handler ──────────────────────────────────────────
  window.addEventListener('message', function(event) {
    if (event.source !== window || !event.data || event.data.source !== 'nsp-content') return;
    if (event.data.type === 'scan-now') {
      fullScan();
    }
  });

  // ── persistent mutation observer (never stops) ───────────────
  new MutationObserver(function() {
    fullScan();
  }).observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['src', 'data-src', 'data-video', 'data-url', 'style'],
  });

  // ── initial scan + periodic re-scan (keeps running) ──────────
  fullScan();

  // Keep scanning every 2 seconds indefinitely (catches delayed loads)
  setInterval(fullScan, 2000);
})();
