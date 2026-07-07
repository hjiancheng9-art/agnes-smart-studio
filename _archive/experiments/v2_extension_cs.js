(function () {
  const PANEL_ID = 'v2-browser-companion-panel';
  let currentTask = null;

  function adapters() {
    return window.V2BrowserCompanionProviders || [];
  }

  function activeAdapter() {
    return adapters().find(adapter => adapter.matchUrl(window.location.href)) || null;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function send(message) {
    return chrome.runtime.sendMessage(message);
  }

  function status(status, note) {
    if (!currentTask) return Promise.resolve();
    return send({
      type: 'TASK_STATUS',
      task: currentTask,
      payload: { status, note, pageUrl: window.location.href }
    });
  }

  async function copyPrompt() {
    if (!currentTask?.prompt) return;
    await navigator.clipboard.writeText(currentTask.prompt);
    await status('prompt_copied', 'prompt copied by user');
    setMessage('Prompt copied.');
  }

  async function fillPrompt() {
    const adapter = activeAdapter();
    if (!adapter) {
      setMessage('No adapter matched this page. Please paste manually.');
      return;
    }
    const ok = await adapter.fillPrompt(currentTask.prompt);
    if (ok) {
      await status('prompt_filled', 'prompt filled by companion');
      setMessage('Prompt filled. Please review and submit manually.');
    } else {
      setMessage(adapter.getKnownLimitMessage() || 'Prompt input not found. Please paste manually.');
    }
  }

  async function markSubmitted() {
    await status('submitted_by_user', 'user confirmed manual submit');
    setMessage('Marked submitted. Use result import after generation completes.');
  }

  function selectedText() {
    return String(window.getSelection()?.toString() || '').trim();
  }

  async function sendResult() {
    const adapter = activeAdapter();
    const adapterResult = adapter?.getSelectedResult ? await adapter.getSelectedResult() : {};
    const payload = {
      selectedText: selectedText(),
      resultText: adapterResult.resultText || selectedText(),
      resultUrl: adapterResult.resultUrl || window.location.href,
      localFileHint: adapterResult.localFileHint || '',
      images: adapterResult.images || [],
      provider: currentTask.provider,
      artifactType: currentTask.artifactType,
      metadata: {
        pageTitle: document.title,
        pageUrl: window.location.href,
        providerName: currentTask.providerName || '',
        importedBy: 'v2-browser-companion'
      }
    };
    await send({ type: 'TASK_RESULT', task: currentTask, payload });
    setMessage('Result sent to V2.');
  }

  async function markFailed() {
    const message = prompt('Failure reason', 'user_cancelled') || 'user_cancelled';
    await send({
      type: 'TASK_ERROR',
      task: currentTask,
      payload: { errorType: message, message, pageUrl: window.location.href }
    });
    setMessage('Failure sent to V2.');
  }

  function setMessage(text) {
    const node = document.querySelector(`#${PANEL_ID} [data-v2-message]`);
    if (node) node.textContent = text;
  }

  function renderPanel() {
    let panel = document.getElementById(PANEL_ID);
    if (!panel) {
      panel = document.createElement('aside');
      panel.id = PANEL_ID;
      document.documentElement.appendChild(panel);
    }
    const adapter = activeAdapter();
    const instructions = adapter?.buildUserInstructions ? adapter.buildUserInstructions(currentTask) : 'Copy or paste the prompt manually, submit yourself, then send the result back.';
    panel.innerHTML = `
      <div class="v2bc-head">
        <strong>V2 Browser Companion</strong>
        <button type="button" data-v2-close>Close</button>
      </div>
      <div class="v2bc-body">
        <p><b>Provider:</b> ${escapeHtml(currentTask?.providerName || currentTask?.provider || 'none')}</p>
        <p><b>Task:</b> ${escapeHtml(currentTask?.taskId || '')}</p>
        <textarea readonly>${escapeHtml(currentTask?.prompt || '')}</textarea>
        <div class="v2bc-actions">
          <button type="button" data-v2-copy>Copy prompt</button>
          <button type="button" data-v2-fill>Try fill</button>
          <button type="button" data-v2-submitted>I submitted manually</button>
          <button type="button" data-v2-result>Send selected result</button>
          <button type="button" data-v2-failed>Mark failed</button>
        </div>
        <small>${escapeHtml(instructions)}</small>
        <p data-v2-message></p>
      </div>
    `;
    panel.querySelector('[data-v2-close]').addEventListener('click', () => panel.remove());
    panel.querySelector('[data-v2-copy]').addEventListener('click', copyPrompt);
    panel.querySelector('[data-v2-fill]').addEventListener('click', fillPrompt);
    panel.querySelector('[data-v2-submitted]').addEventListener('click', markSubmitted);
    panel.querySelector('[data-v2-result]').addEventListener('click', sendResult);
    panel.querySelector('[data-v2-failed]').addEventListener('click', markFailed);
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type !== 'V2_COMPANION_TASK') return;
    currentTask = message.task;
    renderPanel();
    sendResponse({ ok: true });
  });

  chrome.storage.local.get({ currentTask: null }).then(data => {
    if (!data.currentTask) return;
    const adapter = activeAdapter();
    if (adapter && adapter.matchUrl(window.location.href)) {
      currentTask = data.currentTask;
      renderPanel();
    }
  });
}());
