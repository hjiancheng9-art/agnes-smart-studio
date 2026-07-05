// NetSpeedPro Background Worker
let mediaByTab = {};
let MAX_ITEMS_PER_TAB = 20;
let pendingRequests = {};
let pendingDownloads = {};
let RECENT_REQUEST_TTL = 30000;
let DOWNLOAD_EXTENSIONS = [
  '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
  '.exe', '.msi', '.apk', '.iso', '.img', '.bin',
  '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
  '.mp3', '.flac', '.wav', '.aac', '.ogg',
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.torrent'
];
let DRIVE_HOSTS = [
  'pan.quark.cn',
  'pan.baidu.com',
  'pan.xunlei.com',
  'www.xiaohongshu.com',
  'xiaohongshu.com',
  'xhslink.com',
  'xhscdn.com',
  'www.kuaishou.com',
  'kuaishou.com',
  'gifshow.com',
  'kwai.com',
  'www.douyin.com',
  'douyin.com',
  'iesdouyin.com',
  'amemv.com',
  'yunpan.360.cn',
  'aliyundrive.com',
  'www.aliyundrive.com',
  'cloud.189.cn',
  '115.com',
  'caiyun.139.com'
];

chrome.runtime.onInstalled.addListener(function() {
  console.log('[NSP] Installed');
  createContextMenus();
});

chrome.runtime.onStartup.addListener(function() {
  createContextMenus();
});

function getTabKey(tabId) {
  return String(tabId || 'unknown');
}

function rememberMedia(tabId, item) {
  let key = getTabKey(tabId);
  let list = mediaByTab[key] || [];

  if (list.some(function(existing) { return existing.url === item.url; })) {
    return;
  }

  list.unshift(item);
  mediaByTab[key] = list.slice(0, MAX_ITEMS_PER_TAB);
  chrome.action.setBadgeText({ tabId: tabId, text: String(mediaByTab[key].length) });
  chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: '#238636' });
}

function createContextMenus() {
  if (!chrome.contextMenus) return;

  chrome.contextMenus.removeAll(function() {
    chrome.contextMenus.create({
      id: 'nsp-download-link',
      title: '\u7528\u7f51\u901f\u52a0\u52a0\u4e0b\u8f7d\u6b64\u94fe\u63a5',
      contexts: ['link'],
    });
    chrome.contextMenus.create({
      id: 'nsp-download-page',
      title: '\u7528\u7f51\u901f\u52a0\u52a0\u5904\u7406\u5f53\u524d\u9875\u94fe\u63a5',
      contexts: ['page'],
    });
    chrome.contextMenus.create({
      id: 'nsp-download-selection',
      title: '\u7528\u7f51\u901f\u52a0\u52a0\u4e0b\u8f7d\u9009\u4e2d\u94fe\u63a5',
      contexts: ['selection'],
    });
  });
}

function normalizeThunderUrl(url) {
  if (!/^thunder:\/\//i.test(url)) return url;
  try {
    let encoded = url.replace(/^thunder:\/\//i, '');
    let decoded = atob(encoded);
    let match = decoded.match(/^AA(.+)ZZ$/);
    return match ? match[1] : url;
  } catch {
    return url;
  }
}

function normalizeDownloadUrl(url) {
  if (!url || typeof url !== 'string') return '';
  return normalizeThunderUrl(url.trim());
}

function isSpecialDownloadUrl(url) {
  return /^(magnet:\?|ed2k:\/\/|thunder:\/\/)/i.test(url || '');
}

function getHost(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return '';
  }
}

function isDriveHost(url) {
  let host = getHost(url);
  return DRIVE_HOSTS.some(function(domain) {
    return host === domain || host.endsWith('.' + domain);
  });
}

function isLikelyDownloadUrl(url) {
  if (!url || typeof url !== 'string') return false;
  if (isSpecialDownloadUrl(url)) return true;
  if (!/^https?:\/\//i.test(url)) return false;

  let lower = url.toLowerCase();
  if (DOWNLOAD_EXTENSIONS.some(function(ext) { return lower.includes(ext); })) return true;
  if (/[?&](download|dl|export|attname|filename)=/i.test(lower)) return true;
  if (/\/(download|dl|dlink|file|attachment)\//i.test(lower)) return true;
  return false;
}

function shouldAutoInterceptDownload(url) {
  if (!url || /^blob:/i.test(url)) return false;
  if (isSpecialDownloadUrl(url)) return true;
  if (!/^https?:\/\//i.test(url)) return false;
  if (isDriveHost(url)) return true;
  return isLikelyDownloadUrl(url);
}

function rememberCandidate(tabId, url, label, title, pageUrl) {
  if (!url) return;
  rememberMedia(tabId, {
    url: url,
    pageUrl: pageUrl || '',
    title: title || label || 'Download',
    label: label || 'DOWNLOAD',
    timestamp: Date.now(),
  });
}

function getCookieHeader(url, callback) {
  if (!/^https?:\/\//i.test(url)) {
    callback('');
    return;
  }

  chrome.cookies.getAll({ url: url }, function(cookies) {
    if (chrome.runtime.lastError || !cookies || cookies.length === 0) {
      callback('');
      return;
    }

    callback(cookies.map(function(cookie) {
      return cookie.name + '=' + cookie.value;
    }).join('; '));
  });
}

function sendToApp(payload, sendResponse) {
  fetch('http://127.0.0.1:17081/add-download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(function(resp) { return resp.json(); })
    .then(function(data) { sendResponse(data); })
    .catch(function(err) {
      sendResponse({ success: false, error: err.message });
    });
}

function sendUrlToApp(url, referer, sendResponse) {
  let normalized = normalizeDownloadUrl(url);
  if (!normalized) {
    sendResponse({ success: false, error: 'Missing download URL' });
    return;
  }

  // Send directly without waiting for cookies (cookie API can be slow in SW)
  sendToApp({
    url: normalized,
    cookies: '',
    referer: referer || '',
    userAgent: navigator.userAgent,
  }, sendResponse);
}

function probeMedia(payload, sendResponse) {
  fetch('http://127.0.0.1:17080/probe-media', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then(function(resp) { return resp.json(); })
    .then(function(data) { sendResponse(data); })
    .catch(function(err) {
      sendResponse({ success: false, error: err.message });
    });
}

function scanTab(tabId, sendResponse, didInject) {
  chrome.tabs.sendMessage(tabId, { type: 'scan-now' }, function(response) {
    if (!chrome.runtime.lastError) {
      sendResponse(response || { success: true, found: 0 });
      return;
    }

    if (didInject || !chrome.scripting) {
      sendResponse({ success: false, error: chrome.runtime.lastError.message });
      return;
    }

    chrome.scripting.executeScript({
      target: { tabId: tabId, allFrames: true },
      files: ['content.js'],
    }, function() {
      if (chrome.runtime.lastError) {
        sendResponse({ success: false, error: chrome.runtime.lastError.message });
        return;
      }

      setTimeout(function() {
        scanTab(tabId, sendResponse, true);
      }, 250);
    });
  });
}

function getHeader(headers, name) {
  if (!headers) return '';
  let lower = name.toLowerCase();
  for (let i = 0; i < headers.length; i++) {
    if ((headers[i].name || '').toLowerCase() === lower) {
      return headers[i].value || '';
    }
  }
  return '';
}

function isAttachmentResponse(details) {
  let disposition = getHeader(details.responseHeaders, 'content-disposition');
  let type = getHeader(details.responseHeaders, 'content-type');
  if (/attachment|filename=/i.test(disposition)) return true;
  if (/application\/(octet-stream|x-msdownload|x-bittorrent|zip|x-7z-compressed|x-rar-compressed)/i.test(type)) return true;
  return false;
}

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'media-found' && msg.item) {
    rememberMedia(sender.tab && sender.tab.id, msg.item);
    sendResponse({ success: true });
    return true;
  }

  if (msg.type === 'media-list') {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      let tab = tabs[0];
      let key = getTabKey(tab && tab.id);
      sendResponse({ success: true, items: mediaByTab[key] || [] });
    });
    return true;
  }

  if (msg.type === 'media-clear') {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      let tab = tabs[0];
      let key = getTabKey(tab && tab.id);
      mediaByTab[key] = [];
      if (tab && tab.id) chrome.action.setBadgeText({ tabId: tab.id, text: '' });
      sendResponse({ success: true });
    });
    return true;
  }

  if (msg.type === 'scan-active-tab') {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      let tab = tabs[0];
      if (!tab || !tab.id) {
        sendResponse({ success: false, error: 'No active tab' });
        return;
      }

      scanTab(tab.id, sendResponse, false);
    });
    return true;
  }

  if (msg.type === 'send-video' && msg.url) {
    sendUrlToApp(msg.url, msg.referer || '', sendResponse);
    return true;
  }

  if (msg.type === 'send-download' && msg.url) {
    sendUrlToApp(msg.url, msg.referer || '', sendResponse);
    return true;
  }

  if (msg.type === 'probe-media' && msg.url) {
    getCookieHeader(msg.url, function(cookies) {
      probeMedia({
        url: msg.url,
        cookies: cookies,
        referer: msg.referer || '',
        userAgent: navigator.userAgent,
      }, sendResponse);
    });
    return true;
  }

  if (msg.type === 'check-nsp') {
    fetch('http://127.0.0.1:17081/add-download', { method: 'OPTIONS' })
      .then(function() { sendResponse({ available: true }); })
      .catch(function() { sendResponse({ available: false }); });
    return true;
  }
});

chrome.contextMenus.onClicked.addListener(function(info, tab) {
  let url = '';
  if (info.menuItemId === 'nsp-download-link') {
    url = info.linkUrl || '';
  } else if (info.menuItemId === 'nsp-download-page') {
    url = info.pageUrl || '';
  } else if (info.menuItemId === 'nsp-download-selection') {
    let match = (info.selectionText || '').match(/(magnet:\?[^\s]+|ed2k:\/\/[^\s]+|thunder:\/\/[^\s]+|https?:\/\/[^\s<>"{}|\\^`[\]]+)/i);
    url = match ? match[1] : '';
  }

  if (!url) return;
  sendUrlToApp(url, info.pageUrl || tab && tab.url || '', function(res) {
    if (!res || !res.success) {
      rememberCandidate(tab && tab.id, normalizeDownloadUrl(url), 'LINK', 'Link', info.pageUrl || tab && tab.url || '');
    }
  });
});

if (chrome.webRequest && chrome.webRequest.onBeforeSendHeaders) {
  chrome.webRequest.onBeforeSendHeaders.addListener(function(details) {
    pendingRequests[details.requestId] = {
      url: details.url,
      tabId: details.tabId,
      time: Date.now(),
      referer: getHeader(details.requestHeaders, 'referer'),
      userAgent: getHeader(details.requestHeaders, 'user-agent'),
    };
    return {};
  }, { urls: ['<all_urls>'] }, ['requestHeaders']);
}

// ── Video stream sniffer: intercept m3u8/mp4/ts/m4s/mpd requests at network level ──
let MEDIA_URL_RE = /\.(m3u8|mp4|ts|m4s|mpd|flv|webm|mkv)(?:[?#]|$)/i;
let MEDIA_PATH_RE = /\/m3u8\/|\/hls\/|\/dash\/|\/video\/stream/i;

function isMediaStreamUrl(url) {
  if (!url || !/^https?:\/\//i.test(url)) return false;
  return MEDIA_URL_RE.test(url) || MEDIA_PATH_RE.test(url);
}

function sniffMediaFromRequest(details) {
  if (details.tabId < 0) return; // skip non-tab requests
  if (!isMediaStreamUrl(details.url)) return;
  let request = pendingRequests[details.requestId] || {};
  let label = 'MEDIA';
  if (/\.m3u8/i.test(details.url)) label = 'M3U8';
  else if (/\.mpd/i.test(details.url)) label = 'DASH';
  else if (/\.mp4/i.test(details.url)) label = 'MP4';
  else if (/\.m4s/i.test(details.url)) label = 'M4S';
  else if (/\.ts/i.test(details.url)) label = 'TS';
  else if (/\/m3u8\//i.test(details.url)) label = 'M3U8-PATH';

  rememberMedia(details.tabId, {
    url: details.url,
    pageUrl: request.referer || '',
    title: label,
    label: label,
    timestamp: Date.now(),
  });
}

if (chrome.webRequest && chrome.webRequest.onBeforeRequest) {
  chrome.webRequest.onBeforeRequest.addListener(
    sniffMediaFromRequest,
    { urls: ['<all_urls>'] }
  );
}

if (chrome.webRequest && chrome.webRequest.onHeadersReceived) {
  chrome.webRequest.onHeadersReceived.addListener(function(details) {
    // Sniff video streams by URL pattern
    sniffMediaFromRequest(details);

    // Also check Content-Type for HLS/DASH
    let contentType = getHeader(details.responseHeaders, 'content-type');
    if (/application\/(vnd\.apple\.mpegurl|x-mpegURL|dash\+xml)/i.test(contentType) ||
        /video\/(mp4|mp2t|x-mpegURL)/i.test(contentType)) {
      sniffMediaFromRequest(details);
    }

    if (!isLikelyDownloadUrl(details.url) && !isAttachmentResponse(details)) return {};
    let request = pendingRequests[details.requestId] || {};
    rememberCandidate(details.tabId, details.url, 'DOWNLOAD', 'Download', request.referer || '');
    return {};
  }, { urls: ['<all_urls>'] }, ['responseHeaders']);
}

if (chrome.webRequest && chrome.webRequest.onCompleted) {
  chrome.webRequest.onCompleted.addListener(function(details) {
    delete pendingRequests[details.requestId];
  }, { urls: ['<all_urls>'] });
}

if (chrome.webRequest && chrome.webRequest.onErrorOccurred) {
  chrome.webRequest.onErrorOccurred.addListener(function(details) {
    delete pendingRequests[details.requestId];
  }, { urls: ['<all_urls>'] });
}

if (chrome.downloads && chrome.downloads.onCreated) {
  chrome.downloads.onCreated.addListener(function(item) {
    if (!item || !item.url || !shouldAutoInterceptDownload(item.url)) return;
    if (pendingDownloads[item.url] && Date.now() - pendingDownloads[item.url] < RECENT_REQUEST_TTL) return;
    pendingDownloads[item.url] = Date.now();

    sendUrlToApp(item.url, item.referrer || '', function(res) {
      if (res && res.success && item.id) {
        chrome.downloads.cancel(item.id, function() {
          chrome.downloads.erase({ id: item.id });
        });
      }
    });
  });
}

chrome.tabs.onRemoved.addListener(function(tabId) {
  delete mediaByTab[getTabKey(tabId)];
});
