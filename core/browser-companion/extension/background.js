/* CRUX Browser Agent — background service worker.

Communication channels:
1. Native Messaging (primary) — Chrome ↔ Python host via stdin/stdout
2. HTTP bridge (fallback) — localhost:4366

Responsibilities:
- Pull pending tasks from CRUX bridge
- Show badge count for pending tasks
- Forward MEDIA_DETECTED events
- Store state in chrome.storage.session (survives SW restart)
- Outbox for failed bridge calls
*/

const DEFAULT_V2_BASE_URL = 'http://127.0.0.1:4366';
const NATIVE_HOST_NAME = 'com.crux.bridge';

// ── Native Messaging connection ──

let nativePort = null;

function connectNative() {
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
    nativePort.onMessage.addListener((msg) => {
      if (msg.type === 'ready') {
        console.log('[CRUX] Native bridge connected, PID:', msg.pid);
      }
    });
    nativePort.onDisconnect.addListener(() => {
      console.log('[CRUX] Native bridge disconnected, will fallback to HTTP');
      nativePort = null;
      // Try to reconnect after 30s
      setTimeout(connectNative, 30000);
    });
  } catch (e) {
    console.log('[CRUX] Native bridge not available, using HTTP');
    nativePort = null;
  }
}

function sendNative(msg) {
  return new Promise((resolve, reject) => {
    if (!nativePort) {
      reject(new Error('native_not_available'));
      return;
    }
    const listener = (response) => {
      nativePort.onMessage.removeListener(listener);
      resolve(response);
    };
    nativePort.onMessage.addListener(listener);
    nativePort.postMessage(msg);
    // Timeout after 10s
    setTimeout(() => {
      nativePort.onMessage.removeListener(listener);
      reject(new Error('native_timeout'));
    }, 10000);
  });
}

// ── HTTP bridge (fallback) ──

async function httpFetch(path, options) {
  const settings = await getSettings();
  const baseUrl = String(settings.v2BaseUrl || DEFAULT_V2_BASE_URL).replace(/\/+$/g, '');
  const url = baseUrl + path;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

// ── Dual-channel communication ──

async function bridgeSend(type, payload) {
  // Try native first, fallback to HTTP
  if (nativePort) {
    try {
      const result = await sendNative({ type, ...payload });
      return result;
    } catch (e) {
      console.log('[CRUX] Native failed, using HTTP:', e.message);
    }
  }
  // HTTP fallback
  try {
    if (type === 'media_detected') {
      return await httpFetch('/api/browser-companion/media', {
        method: 'POST', body: JSON.stringify(payload),
      });
    }
    if (type === 'get_tasks') {
      return await httpFetch('/api/browser-companion/tasks/next');
    }
    if (type === 'submit_result') {
      const taskId = payload.taskId;
      return await httpFetch(`/api/browser-companion/tasks/${encodeURIComponent(taskId)}/result`, {
        method: 'POST', body: JSON.stringify(payload.result || {}),
      });
    }
    if (type === 'get_pending_media') {
      return await httpFetch('/download/pending');
    }
  } catch (e) {
    console.log('[CRUX] HTTP bridge also failed:', e.message);
    throw e;
  }
}

// ── State management ──

async function getState() {
  const item = await chrome.storage.session.get('cruxState');
  return item.cruxState || { pendingTasks: [], lastPullAt: 0 };
}

async function setStatePatch(patch) {
  const current = await getState();
  await chrome.storage.session.set({
    cruxState: { ...current, ...patch, updatedAt: Date.now() },
  });
}

async function getSettings() {
  const data = await chrome.storage.local.get({ v2BaseUrl: DEFAULT_V2_BASE_URL, currentTask: null });
  return data;
}

// ── Task pulling ──

async function pullTasks() {
  try {
    const data = await bridgeSend('get_tasks');
    const task = data.task || null;
    const pending = task ? [task] : [];
    await setStatePatch({ pendingTasks: pending, lastPullAt: Date.now() });
    updateBadge();
  } catch (e) {
    // Bridge not running — silent
  }
}

function updateBadge() {
  getState().then(state => {
    const count = state.pendingTasks ? state.pendingTasks.length : 0;
    if (count > 0) {
      chrome.action.setBadgeText({ text: String(count) });
      chrome.action.setBadgeBackgroundColor({ color: '#7c3aed' });
    } else {
      chrome.action.setBadgeText({ text: '' });
    }
  });
}

// ── Outbox ──

async function getOutbox() {
  const data = await chrome.storage.local.get('outbox');
  return data.outbox || [];
}

async function addToOutbox(item) {
  const outbox = await getOutbox();
  outbox.unshift({ ...item, createdAt: Date.now() });
  await chrome.storage.local.set({ outbox: outbox.slice(0, 200) });
}

async function flushOutbox() {
  const outbox = await getOutbox();
  if (outbox.length === 0) return;
  const remaining = [];
  for (const item of outbox) {
    try {
      await bridgeSend('media_detected', item.payload || {});
    } catch (e) {
      remaining.push(item);
    }
  }
  await chrome.storage.local.set({ outbox: remaining });
}

// ── Alarms (MV3-safe periodic tasks) ──

chrome.runtime.onInstalled.addListener(() => {
  connectNative();
  chrome.alarms.create('crux-pull', { periodInMinutes: 0.5 });
  pullTasks();
});

chrome.runtime.onStartup.addListener(() => {
  connectNative();
  flushOutbox();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'crux-pull') { pullTasks(); flushOutbox(); }
});

// ── Message handling (from popup/content-script) ──

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === 'GET_SETTINGS') {
      sendResponse({ ok: true, settings: await getSettings() });
      return;
    }
    if (message.type === 'SAVE_SETTINGS') {
      await chrome.storage.local.set({ v2BaseUrl: message.v2BaseUrl || DEFAULT_V2_BASE_URL });
      sendResponse({ ok: true, settings: await getSettings() });
      return;
    }
    if (message.type === 'PULL_NEXT_TASK') {
      await pullTasks();
      const state = await getState();
      const task = state.pendingTasks[0] || null;
      sendResponse({ ok: true, task });
      return;
    }
    if (message.type === 'GET_PENDING_TASKS') {
      const state = await getState();
      sendResponse({ ok: true, tasks: state.pendingTasks || [] });
      return;
    }
    if (message.type === 'OPEN_TASK') {
      const task = message.task;
      if (!task) {
        const state = await getState();
        const task2 = state.pendingTasks[0];
        if (!task2) { sendResponse({ ok: false, error: 'no_task' }); return; }
        message.task = task2;
      }
      try {
        const tab = await chrome.tabs.create({ url: message.task.targetUrl, active: true });
        await chrome.storage.session.set({ pendingCruxTask: message.task });
        sendResponse({ ok: true, task: message.task, tabId: tab.id });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
      return;
    }
    if (message.type === 'SEND_TASK_TO_TAB') {
      try {
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        const tab = tabs[0];
        if (tab?.id && message.task) {
          await chrome.tabs.sendMessage(tab.id, { type: 'V2_COMPANION_TASK', task: message.task });
        }
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
      return;
    }
    if (message.type === 'TASK_RESULT') {
      try {
        await bridgeSend('submit_result', { taskId: message.task?.taskId, result: message.payload || {} });
        await setStatePatch({ pendingTasks: [] });
        updateBadge();
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
      return;
    }
    if (message.type === 'MEDIA_DETECTED') {
      try {
        await bridgeSend('media_detected', message.payload || {});
        sendResponse({ ok: true });
      } catch (e) {
        await addToOutbox({ type: 'MEDIA_DETECTED', payload: message.payload });
        sendResponse({ ok: true, cached: true });
      }
      return;
    }
    sendResponse({ ok: false, error: 'unknown_message_type' });
  })().catch(error => {
    sendResponse({ ok: false, error: error.message || String(error) });
  });
  return true;
});
