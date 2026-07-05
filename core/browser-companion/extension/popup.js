/* CRUX Browser Agent — popup UI.
Shows pending tasks, one-click "Run in provider".
*/

function send(message) {
  return chrome.runtime.sendMessage(message);
}

function setStatus(text, isError) {
  const el = document.getElementById('status');
  if (el) {
    el.textContent = text;
    el.style.color = isError ? '#f87171' : '#a1a1aa';
  }
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

document.addEventListener('DOMContentLoaded', async () => {
  const taskList = document.getElementById('task-list');
  const pullBtn = document.getElementById('pull-btn');
  const settingsBtn = document.getElementById('settings-btn');

  // Load pending tasks
  async function loadTasks() {
    try {
      const res = await send({ type: 'GET_PENDING_TASKS' });
      const tasks = res?.tasks || [];
      renderTasks(tasks);
    } catch (e) {
      setStatus('Error loading tasks', true);
    }
  }

  function renderTasks(tasks) {
    if (!taskList) return;
    if (tasks.length === 0) {
      taskList.innerHTML = '<div class="empty-state">No pending tasks</div>';
      return;
    }
    let html = '';
    for (const task of tasks) {
      const prompt = task.prompt || '';
      const preview = prompt.length > 120 ? prompt.slice(0, 117) + '...' : prompt;
      const providerUrl = task.targetUrl || '';
      const providerName = task.providerName || task.provider || guessProvider(providerUrl);
      html += `
        <div class="task-card">
          <div class="task-header">
            <span class="task-provider">${escapeHtml(providerName)}</span>
            <span class="task-type">${escapeHtml(task.type || 'task')}</span>
          </div>
          <div class="task-prompt">${escapeHtml(preview)}</div>
          <div class="task-actions">
            <button class="btn btn-primary run-btn" data-task='${escapeHtml(JSON.stringify(task))}'>
              Run in ${escapeHtml(providerName)}
            </button>
          </div>
        </div>`;
    }
    taskList.innerHTML = html;

    // Bind run buttons
    taskList.querySelectorAll('.run-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        try {
          const task = JSON.parse(btn.dataset.task);
          btn.disabled = true;
          btn.textContent = 'Opening...';
          const res = await send({ type: 'OPEN_TASK', task });
          if (res?.ok) {
            window.close(); // Close popup after opening
          } else {
            btn.disabled = false;
            btn.textContent = 'Retry';
            setStatus(res?.error || 'Failed to open', true);
          }
        } catch (e) {
          setStatus(String(e), true);
        }
      });
    });
  }

  function guessProvider(url) {
    if (!url) return 'Provider';
    if (url.includes('chatgpt') || url.includes('chat.openai')) return 'ChatGPT';
    if (url.includes('gemini')) return 'Gemini';
    if (url.includes('deepseek')) return 'DeepSeek';
    if (url.includes('claude')) return 'Claude';
    return 'Provider';
  }

  // Pull new task
  if (pullBtn) {
    pullBtn.addEventListener('click', async () => {
      pullBtn.disabled = true;
      pullBtn.textContent = 'Pulling...';
      try {
        // Trigger server-side pull by calling background
        const res = await chrome.runtime.sendMessage({ type: 'PULL_NEXT_TASK' });
        if (res?.task) {
          setStatus('Task pulled!');
        } else {
          setStatus('No pending tasks');
        }
        await loadTasks();
      } catch (e) {
        setStatus('Bridge not running?', true);
      }
      pullBtn.disabled = false;
      pullBtn.textContent = 'Pull task';
    });
  }

  // Settings
  if (settingsBtn) {
    settingsBtn.addEventListener('click', () => {
      const url = prompt('CRUX Bridge URL:', 'http://127.0.0.1:4366');
      if (url) {
        send({ type: 'SAVE_SETTINGS', v2BaseUrl: url });
      }
    });
  }

  // Initial load
  await loadTasks();
});
