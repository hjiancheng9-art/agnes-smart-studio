/* ProviderAdapter — base class for all CRUX provider integrations.

Each provider defines selectors for: promptInput, sendButton, responseRoot.
Common operations (fillPrompt, clickSend, getSelectedText) live here.
*/

export class ProviderAdapter {
  constructor(config) {
    this.name = config.name;
    this.hosts = config.hosts || [];
    this.selectors = config.selectors || {};
  }

  matches(url = location.href) {
    return this.hosts.some((host) => new URL(url).hostname.includes(host));
  }

  findPromptInput() {
    return queryFirst(this.selectors.promptInput || []);
  }

  findSendButton() {
    return queryFirst(this.selectors.sendButton || []);
  }

  findResponseRoot() {
    return queryFirst(this.selectors.responseRoot || []);
  }

  async fillPrompt(text) {
    const input = await waitFor(() => this.findPromptInput(), 8000);
    if (!input) return false;

    input.focus();
    if ('value' in input) {
      input.value = text;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      input.textContent = text;
      input.dispatchEvent(new InputEvent('input', {
        bubbles: true, inputType: 'insertText', data: text,
      }));
    }
    return true;
  }

  async clickSend() {
    const button = await waitFor(() => this.findSendButton(), 8000);
    if (button) { button.click(); return true; }
    return false;
  }

  getSelectedText() {
    return String(window.getSelection ? window.getSelection().toString() : '').trim();
  }

  extractLatestResponse() {
    const root = this.findResponseRoot();
    return root ? root.innerText.trim() : '';
  }

  getUserInstructions(task) {
    return 'Copy or paste the prompt manually, submit yourself, then send the result back.';
  }

  getKnownLimitMessage() {
    return 'Prompt input not found. Please paste manually.';
  }
}

export function queryFirst(selectors) {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

export async function waitFor(fn, timeoutMs = 5000, intervalMs = 100) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const result = fn();
    if (result) return result;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return null;
}
