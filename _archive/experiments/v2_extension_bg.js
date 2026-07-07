const DEFAULT_V2_BASE_URL = 'http://127.0.0.1:4366';

async function getSettings() {
  const data = await chrome.storage.local.get({ v2BaseUrl: DEFAULT_V2_BASE_URL, currentTask: null });
  return data;
}

async function setCurrentTask(task) {
  await chrome.storage.local.set({ currentTask: task || null });
}

async function v2Fetch(path, options = {}) {
  const settings = await getSettings();
  const baseUrl = String(settings.v2BaseUrl || DEFAULT_V2_BASE_URL).replace(/\/+$/g, '');
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || data.detail || `v2_http_${response.status}`);
    error.payload = data;
    throw error;
  }
  return data;
}

async function pullNextTask() {
  const data = await v2Fetch('/api/browser-companion/tasks/next');
  await setCurrentTask(data.task || null);
  return data.task || null;
}

async function openTask(task) {
  if (!task?.targetUrl) throw new Error('task_target_url_missing');
  const tab = await chrome.tabs.create({ url: task.targetUrl, active: true });
  await setCurrentTask(task);
  await v2Fetch(`/api/browser-companion/tasks/${encodeURIComponent(task.taskId)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status: 'opened', pageUrl: task.targetUrl })
  }).catch(() => {});
  return tab;
}

async function sendTaskToActiveTab(task) {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id) throw new Error('active_tab_missing');
  await chrome.tabs.sendMessage(tab.id, { type: 'V2_COMPANION_TASK', task });
}

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
      const task = await pullNextTask();
      sendResponse({ ok: true, task });
      return;
    }
    if (message.type === 'OPEN_TASK') {
      const task = message.task || (await getSettings()).currentTask || await pullNextTask();
      const tab = await openTask(task);
      sendResponse({ ok: true, task, tabId: tab.id });
      return;
    }
    if (message.type === 'SEND_TASK_TO_TAB') {
      const task = message.task || (await getSettings()).currentTask;
      await sendTaskToActiveTab(task);
      sendResponse({ ok: true, task });
      return;
    }
    if (message.type === 'TASK_STATUS') {
      const task = message.task || (await getSettings()).currentTask;
      const data = await v2Fetch(`/api/browser-companion/tasks/${encodeURIComponent(task.taskId)}/status`, {
        method: 'POST',
        body: JSON.stringify(message.payload || {})
      });
      sendResponse({ ok: true, data });
      return;
    }
    if (message.type === 'TASK_RESULT') {
      const task = message.task || (await getSettings()).currentTask;
      const data = await v2Fetch(`/api/browser-companion/tasks/${encodeURIComponent(task.taskId)}/result`, {
        method: 'POST',
        body: JSON.stringify(message.payload || {})
      });
      await setCurrentTask(null);
      sendResponse({ ok: true, data });
      return;
    }
    if (message.type === 'TASK_ERROR') {
      const task = message.task || (await getSettings()).currentTask;
      const data = await v2Fetch(`/api/browser-companion/tasks/${encodeURIComponent(task.taskId)}/error`, {
        method: 'POST',
        body: JSON.stringify(message.payload || {})
      });
      sendResponse({ ok: true, data });
      return;
    }
    sendResponse({ ok: false, error: 'unknown_message_type' });
  })().catch(error => {
    sendResponse({ ok: false, error: error.message || String(error) });
  });
  return true;
});
