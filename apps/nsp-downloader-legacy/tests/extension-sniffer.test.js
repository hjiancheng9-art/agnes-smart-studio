const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

function assertIncludes(content, needle, label) {
  if (!content.includes(needle)) {
    throw new Error(`${label} is missing: ${needle}`);
  }
}

try {
  const content = read('extension/content.js');
  const hook = read('extension/page-hook.js');
  const background = read('extension/background.js');
  const popup = read('extension/popup.js');

  assertIncludes(content, 'm4s|ts', 'content media matcher');
  assertIncludes(content, "performance.getEntriesByType('resource')", 'initial performance scan');
  assertIncludes(content, "msg.type !== 'scan-now'", 'content rescan handler');
  assertIncludes(content, "source: 'nsp-content'", 'page hook scan request');

  assertIncludes(hook, 'scanBilibiliPlayinfo', 'Bilibili playinfo scan');
  assertIncludes(hook, 'window.__playinfo__', 'Bilibili __playinfo__ support');
  assertIncludes(hook, 'BILI-DASH-VIDEO', 'Bilibili DASH video label');
  assertIncludes(hook, 'BILI-DASH-AUDIO', 'Bilibili DASH audio label');

  assertIncludes(background, "msg.type === 'scan-active-tab'", 'background active tab scan');
  assertIncludes(background, "chrome.tabs.sendMessage(tabId, { type: 'scan-now' }", 'background scan forwarding');
  assertIncludes(background, "chrome.scripting.executeScript", 'background content script injection fallback');
  assertIncludes(background, "chrome.downloads.onCreated", 'browser download interception');
  assertIncludes(background, "chrome.contextMenus.create", 'download context menu');
  assertIncludes(background, "chrome.webRequest.onHeadersReceived", 'download response detection');
  assertIncludes(background, "pan.quark.cn", 'Quark drive host detection');
  assertIncludes(background, "pan.baidu.com", 'Baidu drive host detection');
  assertIncludes(background, "pan.xunlei.com", 'Xunlei drive host detection');
  assertIncludes(background, "magnet:", 'magnet link support');
  assertIncludes(background, 'ed2k', 'ed2k link support');
  assertIncludes(background, 'thunder', 'thunder link support');

  assertIncludes(popup, "type: 'scan-active-tab'", 'popup scan trigger');
  assertIncludes(popup, 'DASH/M4S', 'popup unsupported DASH/M4S hint');

  console.log('[PASS] Extension sniffer regression checks passed.');
} catch (err) {
  console.error('[FAIL] Extension sniffer regression checks failed.');
  console.error(err.message);
  process.exit(1);
}
